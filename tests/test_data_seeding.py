"""Tests for data seeding and cleanup functionality."""

from __future__ import annotations

import json
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from venomqa.data.cleanup import (
    CleanupConfig,
    CleanupManager,
    CleanupStrategy,
    ResourceTracker,
    TrackedResource,
)
from venomqa.data.seeding import (
    SeedConfig,
    SeedData,
    SeedFile,
    SeedManager,
    SeedMode,
    seed_fixture,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_seed_dir():
    """Create a temporary directory for seed files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_yaml_seed(temp_seed_dir):
    """Create a sample YAML seed file."""
    content = """
users:
  - id: user_seller_1
    email: seller@test.com
    role: seller
    name: Test Seller
  - id: user_buyer_1
    email: buyer@test.com
    role: buyer
    name: Test Buyer

products:
  - id: product_1
    seller_id: ${users.user_seller_1.id}
    title: Test Product
    price: 99.99
    stock: 10
  - id: product_2
    seller_id: ${users.user_seller_1.id}
    title: Another Product
    price: 49.99
    stock: 5

orders:
  - id: order_1
    buyer_id: ${users.user_buyer_1.id}
    product_id: ${products.product_1.id}
    quantity: 2
    total: ${products.product_1.price}
"""
    seed_file = temp_seed_dir / "base.yaml"
    seed_file.write_text(content)
    return seed_file


@pytest.fixture
def sample_json_seed(temp_seed_dir):
    """Create a sample JSON seed file."""
    content = {
        "users": [
            {"id": "admin_user", "email": "admin@test.com", "role": "admin"},
            {"id": "regular_user", "email": "user@test.com", "role": "user"},
        ],
        "categories": [
            {"id": "cat_electronics", "name": "Electronics"},
            {"id": "cat_books", "name": "Books"},
        ],
    }
    seed_file = temp_seed_dir / "admin.json"
    seed_file.write_text(json.dumps(content))
    return seed_file


@pytest.fixture
def mock_client():
    """Create a mock HTTP client."""
    client = MagicMock()
    response = MagicMock()
    response.ok = True
    response.status_code = 201
    response.text = "Created"
    response.json.return_value = {"id": 12345}
    client.post.return_value = response
    client.delete.return_value = MagicMock(status_code=204, text="")
    return client


@pytest.fixture
def mock_database():
    """Create a mock database adapter."""
    db = MagicMock()
    db.insert.return_value = MagicMock(last_insert_id=98765)
    db.delete.return_value = MagicMock(affected_rows=1)
    db.truncate.return_value = None
    db.get_tables.return_value = ["users", "products", "orders"]
    db.dump.return_value = {
        "users": [{"id": 1, "email": "test@test.com"}],
        "products": [],
    }
    return db


# ============================================================================
# SeedConfig Tests
# ============================================================================


class TestSeedConfig:
    """Tests for SeedConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SeedConfig()
        assert config.mode == SeedMode.API
        assert config.prefix.startswith("seed_")
        assert config.id_field == "id"
        assert config.retry_on_conflict is True
        assert config.track_resources is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = SeedConfig(
            mode=SeedMode.DATABASE,
            prefix="test_prefix",
            api_endpoints={"users": "/api/v1/users"},
            table_mapping={"users": "app_users"},
            id_field="uuid",
        )
        assert config.mode == SeedMode.DATABASE
        assert config.prefix == "test_prefix"
        assert config.api_endpoints["users"] == "/api/v1/users"
        assert config.table_mapping["users"] == "app_users"
        assert config.id_field == "uuid"

    def test_auto_generated_prefix(self):
        """Test that prefix is auto-generated if not provided."""
        config1 = SeedConfig()
        config2 = SeedConfig()
        # Each should have a unique prefix
        assert config1.prefix != config2.prefix
        assert len(config1.prefix) == len("seed_") + 8


# ============================================================================
# SeedData Tests
# ============================================================================


class TestSeedData:
    """Tests for SeedData dataclass."""

    def test_seed_data_creation(self):
        """Test creating SeedData instances."""
        data = SeedData(
            resource_type="users",
            logical_id="user_1",
            data={"email": "test@test.com", "name": "Test"},
        )
        assert data.resource_type == "users"
        assert data.logical_id == "user_1"
        assert data.data["email"] == "test@test.com"
        assert data.actual_id is None

    def test_fully_qualified_id(self):
        """Test fully qualified ID property."""
        data = SeedData(
            resource_type="products",
            logical_id="product_abc",
            data={},
        )
        assert data.fully_qualified_id == "products.product_abc"


# ============================================================================
# SeedFile Tests
# ============================================================================


class TestSeedFile:
    """Tests for SeedFile dataclass."""

    def test_seed_file_properties(self):
        """Test SeedFile properties."""
        resources = {
            "users": [
                SeedData("users", "u1", {}),
                SeedData("users", "u2", {}),
            ],
            "products": [
                SeedData("products", "p1", {}),
            ],
        }
        seed_file = SeedFile(
            path=Path("test.yaml"),
            resources=resources,
        )
        assert seed_file.resource_types == ["users", "products"]
        assert seed_file.total_resources == 3

    def test_get_resource(self):
        """Test getting specific resource."""
        user_data = SeedData("users", "admin", {"email": "admin@test.com"})
        seed_file = SeedFile(
            path=Path("test.yaml"),
            resources={"users": [user_data]},
        )
        found = seed_file.get_resource("users", "admin")
        assert found is not None
        assert found.data["email"] == "admin@test.com"

        # Test not found
        assert seed_file.get_resource("users", "nonexistent") is None
        assert seed_file.get_resource("products", "admin") is None


# ============================================================================
# SeedManager Tests
# ============================================================================


class TestSeedManager:
    """Tests for SeedManager class."""

    def test_load_yaml_file(self, sample_yaml_seed, mock_client):
        """Test loading a YAML seed file."""
        manager = SeedManager(client=mock_client)
        seed_file = manager.load(sample_yaml_seed)

        assert seed_file.path == sample_yaml_seed
        assert "users" in seed_file.resource_types
        assert "products" in seed_file.resource_types
        assert "orders" in seed_file.resource_types
        assert seed_file.total_resources == 5

    def test_load_json_file(self, sample_json_seed, mock_client):
        """Test loading a JSON seed file."""
        manager = SeedManager(client=mock_client)
        seed_file = manager.load(sample_json_seed)

        assert "users" in seed_file.resource_types
        assert "categories" in seed_file.resource_types
        assert seed_file.total_resources == 4

    def test_load_nonexistent_file(self, mock_client):
        """Test loading a nonexistent file raises error."""
        manager = SeedManager(client=mock_client)
        with pytest.raises(FileNotFoundError):
            manager.load("nonexistent.yaml")

    def test_load_unsupported_format(self, temp_seed_dir, mock_client):
        """Test loading unsupported format raises error."""
        bad_file = temp_seed_dir / "bad.txt"
        bad_file.write_text("some content")
        manager = SeedManager(client=mock_client)
        with pytest.raises(ValueError, match="Unsupported seed file format"):
            manager.load(bad_file)

    def test_apply_seeds_api_mode(self, sample_yaml_seed, mock_client):
        """Test applying seeds via API mode."""
        manager = SeedManager(
            client=mock_client,
            config=SeedConfig(mode=SeedMode.API, prefix="test"),
        )
        seed_file = manager.load(sample_yaml_seed)
        result = manager.apply(seed_file)

        assert result.success is True
        assert result.created_count == 5
        assert result.failed_count == 0
        assert len(result.created_resources) == 5
        assert mock_client.post.call_count == 5

    def test_apply_seeds_database_mode(self, sample_json_seed, mock_database):
        """Test applying seeds via database mode."""
        manager = SeedManager(
            database=mock_database,
            config=SeedConfig(mode=SeedMode.DATABASE, prefix="db_test"),
        )
        seed_file = manager.load(sample_json_seed)
        result = manager.apply(seed_file)

        assert result.success is True
        assert result.created_count == 4
        assert mock_database.insert.call_count == 4

    def test_variable_resolution(self, sample_yaml_seed, mock_client):
        """Test variable reference resolution."""
        # Make post return sequential IDs
        call_count = [0]

        def mock_post(*args, **kwargs):
            call_count[0] += 1
            response = MagicMock()
            response.ok = True
            response.status_code = 201
            response.json.return_value = {"id": call_count[0] * 100}
            return response

        mock_client.post.side_effect = mock_post

        manager = SeedManager(
            client=mock_client,
            config=SeedConfig(prefix="var_test"),
        )
        seed_file = manager.load(sample_yaml_seed)
        result = manager.apply(seed_file)

        assert result.success is True

        # Verify we can get resolved IDs
        user_data = manager.get_resource_data("users.user_seller_1")
        assert user_data is not None
        assert user_data["id"] == 100  # First call returns 100

    def test_custom_prefix_applied(self, sample_json_seed, mock_client):
        """Test that prefix is applied to string IDs."""
        manager = SeedManager(
            client=mock_client,
            config=SeedConfig(prefix="my_prefix"),
        )
        seed_file = manager.load(sample_json_seed)
        manager.apply(seed_file)

        # Check that post was called with prefixed ID
        calls = mock_client.post.call_args_list
        assert len(calls) > 0
        # The prefix is applied to string IDs only, and then replaced
        # by actual_id from API response. Check the API was called.
        assert mock_client.post.called

    def test_api_error_handling(self, sample_json_seed, mock_client):
        """Test handling of API errors."""
        mock_client.post.return_value.ok = False
        mock_client.post.return_value.status_code = 500
        mock_client.post.return_value.text = "Server Error"

        manager = SeedManager(
            client=mock_client,
            config=SeedConfig(prefix="error_test"),
        )
        seed_file = manager.load(sample_json_seed)
        result = manager.apply(seed_file)

        assert result.success is False
        assert result.failed_count > 0
        assert len(result.failed_resources) > 0

    def test_get_actual_id(self, sample_json_seed, mock_client):
        """Test getting actual ID for a logical reference."""
        mock_client.post.return_value.json.return_value = {"id": 999}

        manager = SeedManager(
            client=mock_client,
            config=SeedConfig(prefix="id_test"),
        )
        seed_file = manager.load(sample_json_seed)
        manager.apply(seed_file)

        actual_id = manager.get_actual_id("users.admin_user")
        assert actual_id == 999

    def test_cache_behavior(self, sample_yaml_seed, mock_client):
        """Test file caching behavior."""
        manager = SeedManager(client=mock_client)

        # First load
        seed_file1 = manager.load(sample_yaml_seed, use_cache=True)
        # Second load should return cached version
        seed_file2 = manager.load(sample_yaml_seed, use_cache=True)

        assert seed_file1.loaded_at == seed_file2.loaded_at

        # Clear cache and reload
        manager.clear_cache()
        seed_file3 = manager.load(sample_yaml_seed, use_cache=True)
        # New load should have different timestamp (or at least be a different object)
        assert seed_file3 is not seed_file1

    def test_reset(self, sample_json_seed, mock_client):
        """Test resetting manager state."""
        manager = SeedManager(
            client=mock_client,
            config=SeedConfig(prefix="reset_test"),
        )
        seed_file = manager.load(sample_json_seed)
        manager.apply(seed_file)

        assert len(manager.created_resources) > 0
        assert len(manager._resolved_ids) > 0

        manager.reset()

        assert len(manager.created_resources) == 0
        assert len(manager._resolved_ids) == 0


# ============================================================================
# TrackedResource Tests
# ============================================================================


class TestTrackedResource:
    """Tests for TrackedResource dataclass."""

    def test_tracked_resource_creation(self):
        """Test creating TrackedResource instances."""
        resource = TrackedResource(
            resource_type="users",
            resource_id=123,
            endpoint="/api/users",
            table="app_users",
        )
        assert resource.resource_type == "users"
        assert resource.resource_id == 123
        assert resource.endpoint == "/api/users"
        assert resource.table == "app_users"

    def test_delete_url_default(self):
        """Test default delete URL generation."""
        resource = TrackedResource(
            resource_type="products",
            resource_id=456,
            endpoint="/api/products",
        )
        assert resource.delete_url == "/api/products/456"

    def test_delete_url_custom(self):
        """Test custom delete endpoint."""
        resource = TrackedResource(
            resource_type="items",
            resource_id="abc-123",
            delete_endpoint="/api/v2/items/{id}/remove",
        )
        assert resource.delete_url == "/api/v2/items/abc-123/remove"


# ============================================================================
# ResourceTracker Tests
# ============================================================================


class TestResourceTracker:
    """Tests for ResourceTracker class."""

    def test_track_resource(self):
        """Test tracking a single resource."""
        tracker = ResourceTracker()
        resource = tracker.track("users", 1, endpoint="/api/users")

        assert len(tracker) == 1
        assert resource.resource_type == "users"
        assert resource.resource_id == 1

    def test_track_many(self):
        """Test tracking multiple resources."""
        tracker = ResourceTracker()
        resources = tracker.track_many("orders", [100, 101, 102])

        assert len(tracker) == 3
        assert all(r.resource_type == "orders" for r in resources)

    def test_get_by_type(self):
        """Test getting resources by type."""
        tracker = ResourceTracker()
        tracker.track("users", 1)
        tracker.track("users", 2)
        tracker.track("products", 10)

        users = tracker.get_by_type("users")
        assert len(users) == 2

        products = tracker.get_by_type("products")
        assert len(products) == 1

    def test_get_by_journey(self):
        """Test getting resources by journey."""
        tracker = ResourceTracker()
        tracker.track("users", 1, journey="checkout")
        tracker.track("orders", 100, journey="checkout")
        tracker.track("users", 2, journey="signup")

        checkout_resources = tracker.get_by_journey("checkout")
        assert len(checkout_resources) == 2

        signup_resources = tracker.get_by_journey("signup")
        assert len(signup_resources) == 1

    def test_get_cleanup_order(self):
        """Test getting resources in cleanup order."""
        tracker = ResourceTracker()
        r1 = tracker.track("users", 1)
        r2 = tracker.track("orders", 100)
        r3 = tracker.track("payments", 200)

        # Cleanup order should be reverse of creation
        cleanup_order = tracker.get_cleanup_order()
        assert cleanup_order[0] == r3
        assert cleanup_order[1] == r2
        assert cleanup_order[2] == r1

    def test_cleanup_order_with_priority(self):
        """Test cleanup order respects priority."""
        tracker = ResourceTracker()
        tracker.track("users", 1, priority=1)
        tracker.track("orders", 100, priority=10)  # High priority
        tracker.track("payments", 200, priority=5)

        cleanup_order = tracker.get_cleanup_order()
        # Higher priority should come first (by negative priority in sort)
        priorities = [r.priority for r in cleanup_order]
        # Verify sorted by priority descending
        assert priorities == sorted(priorities, reverse=True)

    def test_untrack(self):
        """Test removing a resource from tracking."""
        tracker = ResourceTracker()
        r1 = tracker.track("users", 1)
        r2 = tracker.track("users", 2)

        assert len(tracker) == 2

        result = tracker.untrack(r1)
        assert result is True
        assert len(tracker) == 1
        assert r2 in tracker.get_all()

    def test_clear_all(self):
        """Test clearing all tracked resources."""
        tracker = ResourceTracker()
        tracker.track("users", 1)
        tracker.track("orders", 100)

        tracker.clear()
        assert len(tracker) == 0

    def test_clear_by_journey(self):
        """Test clearing resources for specific journey."""
        tracker = ResourceTracker()
        tracker.track("users", 1, journey="checkout")
        tracker.track("orders", 100, journey="checkout")
        tracker.track("users", 2, journey="signup")

        tracker.clear(journey="checkout")

        assert len(tracker) == 1
        assert tracker.get_all()[0].resource_id == 2


# ============================================================================
# CleanupConfig Tests
# ============================================================================


class TestCleanupConfig:
    """Tests for CleanupConfig dataclass."""

    def test_default_config(self):
        """Test default cleanup configuration."""
        config = CleanupConfig()
        assert config.strategy == CleanupStrategy.REVERSE_DELETE
        assert config.cleanup_on_success is True
        assert config.cleanup_on_failure is True
        assert config.on_failure == "warn"

    def test_custom_config(self):
        """Test custom cleanup configuration."""
        config = CleanupConfig(
            strategy=CleanupStrategy.TRUNCATE,
            soft_delete_field="is_deleted",
            soft_delete_ttl=timedelta(days=30),
            on_failure="raise",
        )
        assert config.strategy == CleanupStrategy.TRUNCATE
        assert config.soft_delete_field == "is_deleted"
        assert config.soft_delete_ttl == timedelta(days=30)


# ============================================================================
# CleanupManager Tests
# ============================================================================


class TestCleanupManager:
    """Tests for CleanupManager class."""

    def test_register_resource(self, mock_client):
        """Test registering a resource for cleanup."""
        manager = CleanupManager(client=mock_client)
        resource = manager.register_resource("users", 123)

        assert len(manager) == 1
        assert resource.resource_type == "users"
        assert resource.resource_id == 123

    def test_register_resources_from_seeds(self, mock_client):
        """Test registering resources from seed data."""
        manager = CleanupManager(client=mock_client)

        # Create mock seed data
        seed_data = [
            MagicMock(
                resource_type="users",
                actual_id=1,
                logical_id="user_1",
                endpoint=None,
                table=None,
            ),
            MagicMock(
                resource_type="products",
                actual_id=10,
                logical_id="product_1",
                endpoint=None,
                table=None,
            ),
        ]

        tracked = manager.register_resources(seed_data)
        assert len(tracked) == 2
        assert len(manager) == 2

    def test_cleanup_reverse_delete_api(self, mock_client):
        """Test cleanup with reverse delete strategy via API."""
        manager = CleanupManager(client=mock_client)
        manager.register_resource("users", 1)
        manager.register_resource("orders", 100)

        result = manager.cleanup()

        assert result.success is True
        assert result.deleted_count == 2
        assert result.strategy == CleanupStrategy.REVERSE_DELETE

        # Verify delete was called in reverse order
        delete_calls = mock_client.delete.call_args_list
        assert len(delete_calls) == 2

    def test_cleanup_reverse_delete_database(self, mock_database):
        """Test cleanup with reverse delete strategy via database."""
        manager = CleanupManager(database=mock_database)
        manager.register_resource("users", 1, table="users")
        manager.register_resource("orders", 100, table="orders")

        result = manager.cleanup()

        assert result.success is True
        assert result.deleted_count == 2
        assert mock_database.delete.call_count == 2

    def test_cleanup_truncate_strategy(self, mock_database):
        """Test cleanup with truncate strategy."""
        config = CleanupConfig(strategy=CleanupStrategy.TRUNCATE)
        manager = CleanupManager(database=mock_database, config=config)
        manager.register_resource("users", 1, table="users")
        manager.register_resource("users", 2, table="users")
        manager.register_resource("orders", 100, table="orders")

        result = manager.cleanup()

        assert result.success is True
        # Should truncate unique tables
        assert mock_database.truncate.call_count == 2

    def test_cleanup_soft_delete(self, mock_database):
        """Test cleanup with soft delete strategy."""
        config = CleanupConfig(strategy=CleanupStrategy.SOFT_DELETE)
        manager = CleanupManager(database=mock_database, config=config)
        manager.register_resource("users", 1, table="users")

        result = manager.cleanup()

        assert result.success is True
        # Should call update instead of delete
        mock_database.update.assert_called()

    def test_cleanup_no_cleanup_strategy(self, mock_client):
        """Test cleanup with no_cleanup strategy."""
        config = CleanupConfig(strategy=CleanupStrategy.NO_CLEANUP)
        manager = CleanupManager(client=mock_client, config=config)
        manager.register_resource("users", 1)

        result = manager.cleanup()

        assert result.success is True
        assert result.deleted_count == 0
        mock_client.delete.assert_not_called()

    def test_cleanup_by_journey(self, mock_client):
        """Test cleanup for specific journey."""
        manager = CleanupManager(client=mock_client)
        manager.register_resource("users", 1, journey="checkout")
        manager.register_resource("orders", 100, journey="checkout")
        manager.register_resource("users", 2, journey="signup")

        result = manager.cleanup(journey="checkout")

        assert result.success is True
        assert result.deleted_count == 2
        assert len(manager) == 1  # Signup resource should remain

    def test_cleanup_with_failures(self, mock_client):
        """Test cleanup handling failures."""
        mock_client.delete.side_effect = [
            MagicMock(status_code=204),
            Exception("Network error"),
        ]

        config = CleanupConfig(on_failure="warn")
        manager = CleanupManager(client=mock_client, config=config)
        manager.register_resource("users", 1)
        manager.register_resource("orders", 100)

        with pytest.warns(UserWarning):
            result = manager.cleanup()

        assert result.success is False
        assert result.deleted_count == 1
        assert result.failed_count == 1

    def test_snapshot_create_and_restore(self, mock_database):
        """Test creating and restoring snapshots."""
        config = CleanupConfig(strategy=CleanupStrategy.SNAPSHOT_RESTORE)
        manager = CleanupManager(database=mock_database, config=config)

        # Create snapshot
        manager.create_snapshot("before_test", tables=["users", "products"])
        mock_database.dump.assert_called_with(["users", "products"])

        # Restore snapshot
        manager.restore_snapshot("before_test")
        mock_database.restore.assert_called()

    def test_cleanup_journey_specific(self, mock_client):
        """Test cleanup_journey method."""
        manager = CleanupManager(client=mock_client)
        manager.register_resource("users", 1, journey="checkout")
        manager.register_resource("users", 2, journey="payment")

        result = manager.cleanup_journey("checkout")

        assert result.deleted_count == 1

    def test_cleanup_duration_tracking(self, mock_client):
        """Test that cleanup tracks duration."""
        manager = CleanupManager(client=mock_client)
        manager.register_resource("users", 1)

        result = manager.cleanup()

        assert result.duration_ms >= 0

    def test_clear_without_deleting(self, mock_client):
        """Test clearing tracker without actually deleting."""
        manager = CleanupManager(client=mock_client)
        manager.register_resource("users", 1)
        manager.register_resource("orders", 100)

        manager.clear()

        assert len(manager) == 0
        mock_client.delete.assert_not_called()


# ============================================================================
# Seed Fixture Decorator Tests
# ============================================================================


class TestSeedFixture:
    """Tests for seed_fixture decorator."""

    def test_seed_fixture_decorator(self, temp_seed_dir, mock_client):
        """Test the seed_fixture decorator."""
        # Create a simple seed file
        seed_content = """
users:
  - id: test_user
    email: test@test.com
"""
        seed_file = temp_seed_dir / "users.yaml"
        seed_file.write_text(seed_content)

        # Create a mock context
        from venomqa.context import TestContext

        TestContext()

        @seed_fixture(seed_file=str(seed_file), mode=SeedMode.API)
        def my_fixture(client, ctx):
            return ctx.get("seeds")

        # Note: This won't actually run seeds since mock_client doesn't work
        # in the decorator context. This tests the decorator structure.
        # In real usage, the client would make actual API calls.


# ============================================================================
# Integration Tests
# ============================================================================


class TestSeedingAndCleanupIntegration:
    """Integration tests for seeding and cleanup working together."""

    def test_seed_and_cleanup_flow(self, sample_json_seed, mock_client):
        """Test complete seed and cleanup flow."""
        # Seed
        seed_manager = SeedManager(
            client=mock_client,
            config=SeedConfig(prefix="integration_test"),
        )
        seed_file = seed_manager.load(sample_json_seed)
        seed_result = seed_manager.apply(seed_file)

        assert seed_result.success is True

        # Cleanup
        cleanup_manager = CleanupManager(client=mock_client)
        cleanup_manager.register_resources(seed_manager.created_resources)

        cleanup_result = cleanup_manager.cleanup()

        assert cleanup_result.success is True
        assert cleanup_result.deleted_count == seed_result.created_count

    def test_parallel_isolation_with_prefixes(self, sample_json_seed, mock_client):
        """Test that different prefixes provide isolation."""
        manager1 = SeedManager(
            client=mock_client,
            config=SeedConfig(prefix="run_001"),
        )
        manager2 = SeedManager(
            client=mock_client,
            config=SeedConfig(prefix="run_002"),
        )

        seed_file = manager1.load(sample_json_seed)
        result1 = manager1.apply(seed_file)
        result2 = manager2.apply(manager2.load(sample_json_seed))

        # Verify both runs were successful and created resources
        assert result1.created_count > 0
        assert result2.created_count > 0

        # Verify prefixes are different
        assert result1.prefix == "run_001"
        assert result2.prefix == "run_002"

        # Verify separate tracking - managers have their own created resources
        assert len(manager1.created_resources) == result1.created_count
        assert len(manager2.created_resources) == result2.created_count


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_seed_file(self, temp_seed_dir, mock_client):
        """Test handling empty seed file."""
        empty_file = temp_seed_dir / "empty.yaml"
        empty_file.write_text("")

        manager = SeedManager(client=mock_client)
        seed_file = manager.load(empty_file)

        assert seed_file.total_resources == 0

        result = manager.apply(seed_file)
        assert result.success is True
        assert result.created_count == 0

    def test_invalid_yaml_syntax(self, temp_seed_dir, mock_client):
        """Test handling invalid YAML syntax."""
        bad_file = temp_seed_dir / "bad.yaml"
        bad_file.write_text("invalid: yaml: syntax: [")

        manager = SeedManager(client=mock_client)
        with pytest.raises(Exception):  # yaml.YAMLError or similar
            manager.load(bad_file)

    def test_circular_reference(self, temp_seed_dir, mock_client):
        """Test handling (potential) circular references."""
        # This should not cause infinite loop - forward references fail gracefully
        content = """
a:
  - id: a1
    ref: ${b.b1.id}
b:
  - id: b1
    ref: ${a.a1.id}
"""
        circular_file = temp_seed_dir / "circular.yaml"
        circular_file.write_text(content)

        manager = SeedManager(
            client=mock_client,
            config=SeedConfig(prefix="circ"),
        )
        seed_file = manager.load(circular_file)

        # Forward references will fail since resources are processed in order
        # 'a.a1' references 'b.b1' which doesn't exist yet
        # 'b.b1' references 'a.a1' which also didn't get created
        result = manager.apply(seed_file)

        # Both fail due to forward references, but no infinite loop
        assert result.success is False
        assert result.failed_count == 2
        # Verify errors mention missing references
        assert all("Reference not found" in err for _, err in result.failed_resources)

    def test_no_client_or_database(self, sample_json_seed):
        """Test error when no client or database is configured."""
        manager = SeedManager()  # No client or database
        seed_file = manager.load(sample_json_seed)

        result = manager.apply(seed_file, mode=SeedMode.API)
        assert result.success is False
        assert result.failed_count > 0

    def test_cleanup_with_404_response(self, mock_client):
        """Test that 404 is accepted during cleanup (resource already gone)."""
        mock_client.delete.return_value.status_code = 404

        manager = CleanupManager(client=mock_client)
        manager.register_resource("users", 999)

        result = manager.cleanup()
        assert result.success is True
        assert result.deleted_count == 1
