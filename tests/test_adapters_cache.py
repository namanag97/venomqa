"""Tests for cache adapters in VenomQA."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from venomqa.ports.cache import CacheStats
from venomqa.adapters.cache import MockCacheAdapter


class TestMockCacheAdapter:
    """Tests for MockCacheAdapter."""

    @pytest.fixture
    def adapter(self) -> MockCacheAdapter:
        return MockCacheAdapter()

    def test_adapter_initialization(self, adapter: MockCacheAdapter) -> None:
        assert adapter.health_check() is True
        assert adapter.get_stats().keys_count == 0

    def test_set_and_get_value(self, adapter: MockCacheAdapter) -> None:
        adapter.set("key1", "value1")
        result = adapter.get("key1")
        assert result == "value1"

    def test_get_nonexistent_key_returns_none(self, adapter: MockCacheAdapter) -> None:
        result = adapter.get("nonexistent")
        assert result is None

    def test_set_overwrites_existing_value(self, adapter: MockCacheAdapter) -> None:
        adapter.set("key1", "value1")
        adapter.set("key1", "value2")
        assert adapter.get("key1") == "value2"

    def test_delete_existing_key(self, adapter: MockCacheAdapter) -> None:
        adapter.set("key1", "value1")
        result = adapter.delete("key1")
        assert result is True
        assert adapter.get("key1") is None

    def test_delete_nonexistent_key(self, adapter: MockCacheAdapter) -> None:
        result = adapter.delete("nonexistent")
        assert result is False

    def test_exists_returns_true_for_existing(self, adapter: MockCacheAdapter) -> None:
        adapter.set("key1", "value1")
        assert adapter.exists("key1") is True

    def test_exists_returns_false_for_nonexistent(self, adapter: MockCacheAdapter) -> None:
        assert adapter.exists("nonexistent") is False

    def test_set_with_ttl(self, adapter: MockCacheAdapter) -> None:
        adapter.set("key1", "value1", ttl=60)
        ttl = adapter.get_ttl("key1")
        assert ttl is not None
        assert ttl > 0
        assert ttl <= 60

    def test_get_ttl_for_key_without_expiry(self, adapter: MockCacheAdapter) -> None:
        adapter.set("key1", "value1")
        ttl = adapter.get_ttl("key1")
        assert ttl == -1

    def test_get_ttl_for_nonexistent_key(self, adapter: MockCacheAdapter) -> None:
        ttl = adapter.get_ttl("nonexistent")
        assert ttl is None

    def test_set_ttl_on_existing_key(self, adapter: MockCacheAdapter) -> None:
        adapter.set("key1", "value1")
        result = adapter.set_ttl("key1", 120)
        assert result is True
        ttl = adapter.get_ttl("key1")
        assert ttl is not None
        assert ttl > 0

    def test_set_ttl_on_nonexistent_key(self, adapter: MockCacheAdapter) -> None:
        result = adapter.set_ttl("nonexistent", 60)
        assert result is False

    def test_expired_key_returns_none(self, adapter: MockCacheAdapter) -> None:
        adapter.set("key1", "value1", ttl=-1)
        result = adapter.get("key1")
        assert result is None

    def test_expired_key_not_in_exists(self, adapter: MockCacheAdapter) -> None:
        adapter.set("key1", "value1", ttl=-1)
        assert adapter.exists("key1") is False

    def test_get_many(self, adapter: MockCacheAdapter) -> None:
        adapter.set("key1", "value1")
        adapter.set("key2", "value2")
        adapter.set("key3", "value3")

        result = adapter.get_many(["key1", "key2", "nonexistent"])
        assert result == {"key1": "value1", "key2": "value2"}

    def test_get_many_all_nonexistent(self, adapter: MockCacheAdapter) -> None:
        result = adapter.get_many(["a", "b", "c"])
        assert result == {}

    def test_set_many(self, adapter: MockCacheAdapter) -> None:
        mapping = {"key1": "value1", "key2": "value2", "key3": "value3"}
        result = adapter.set_many(mapping)
        assert result is True
        assert adapter.get("key1") == "value1"
        assert adapter.get("key2") == "value2"
        assert adapter.get("key3") == "value3"

    def test_set_many_with_ttl(self, adapter: MockCacheAdapter) -> None:
        mapping = {"key1": "value1", "key2": "value2"}
        adapter.set_many(mapping, ttl=60)

        ttl1 = adapter.get_ttl("key1")
        ttl2 = adapter.get_ttl("key2")
        assert ttl1 is not None and ttl1 > 0
        assert ttl2 is not None and ttl2 > 0

    def test_delete_many(self, adapter: MockCacheAdapter) -> None:
        adapter.set("key1", "value1")
        adapter.set("key2", "value2")
        adapter.set("key3", "value3")

        count = adapter.delete_many(["key1", "key2", "nonexistent"])
        assert count == 2
        assert adapter.exists("key1") is False
        assert adapter.exists("key2") is False
        assert adapter.exists("key3") is True

    def test_clear_removes_all_keys(self, adapter: MockCacheAdapter) -> None:
        for i in range(10):
            adapter.set(f"key{i}", f"value{i}")

        result = adapter.clear()
        assert result is True
        assert adapter.get_stats().keys_count == 0

    def test_get_stats_empty_cache(self, adapter: MockCacheAdapter) -> None:
        stats = adapter.get_stats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.hit_rate == 0.0
        assert stats.keys_count == 0

    def test_get_stats_with_operations(self, adapter: MockCacheAdapter) -> None:
        adapter.set("key1", "value1")
        adapter.get("key1")
        adapter.get("key1")
        adapter.get("nonexistent")

        stats = adapter.get_stats()
        assert stats.hits == 2
        assert stats.misses == 1
        assert stats.hit_rate == pytest.approx(2 / 3, rel=0.01)

    def test_health_check_returns_true_by_default(self, adapter: MockCacheAdapter) -> None:
        assert adapter.health_check() is True

    def test_set_healthy_changes_status(self, adapter: MockCacheAdapter) -> None:
        adapter.set_healthy(False)
        assert adapter.health_check() is False

        adapter.set_healthy(True)
        assert adapter.health_check() is True

    def test_reset_stats(self, adapter: MockCacheAdapter) -> None:
        adapter.set("key1", "value1")
        adapter.get("key1")
        adapter.get("nonexistent")

        adapter.reset_stats()
        stats = adapter.get_stats()
        assert stats.hits == 0
        assert stats.misses == 0

    def test_complex_value_storage(self, adapter: MockCacheAdapter) -> None:
        complex_value = {
            "user": {
                "id": 1,
                "name": "John",
                "roles": ["admin", "user"],
            },
            "settings": {
                "theme": "dark",
                "notifications": True,
            },
        }
        adapter.set("complex_key", complex_value)
        result = adapter.get("complex_key")
        assert result == complex_value

    def test_list_value_storage(self, adapter: MockCacheAdapter) -> None:
        value = [1, 2, 3, 4, 5]
        adapter.set("list_key", value)
        assert adapter.get("list_key") == value

    def test_none_value_storage(self, adapter: MockCacheAdapter) -> None:
        adapter.set("none_key", None)
        adapter.set("real_key", "value")

        assert adapter.exists("none_key") is True
        assert adapter.get("none_key") is None

    def test_integer_value_storage(self, adapter: MockCacheAdapter) -> None:
        adapter.set("int_key", 42)
        assert adapter.get("int_key") == 42

    def test_float_value_storage(self, adapter: MockCacheAdapter) -> None:
        adapter.set("float_key", 3.14159)
        assert adapter.get("float_key") == pytest.approx(3.14159)

    def test_boolean_value_storage(self, adapter: MockCacheAdapter) -> None:
        adapter.set("bool_true", True)
        adapter.set("bool_false", False)
        assert adapter.get("bool_true") is True
        assert adapter.get("bool_false") is False

    def test_bytes_value_storage(self, adapter: MockCacheAdapter) -> None:
        value = b"binary data"
        adapter.set("bytes_key", value)
        assert adapter.get("bytes_key") == value

    def test_overwrite_updates_created_at(self, adapter: MockCacheAdapter) -> None:
        adapter.set("key1", "value1")
        first_entry = adapter._cache.get("key1")

        adapter.set("key1", "value2")
        second_entry = adapter._cache.get("key1")

        assert first_entry is not None
        assert second_entry is not None
        assert second_entry.created_at >= first_entry.created_at

    def test_stats_size_matches_key_count(self, adapter: MockCacheAdapter) -> None:
        for i in range(5):
            adapter.set(f"key{i}", f"value{i}")

        stats = adapter.get_stats()
        assert stats.size == 5
        assert stats.keys_count == 5

    def test_delete_many_empty_list(self, adapter: MockCacheAdapter) -> None:
        adapter.set("key1", "value1")
        count = adapter.delete_many([])
        assert count == 0
        assert adapter.exists("key1") is True

    def test_get_many_empty_list(self, adapter: MockCacheAdapter) -> None:
        adapter.set("key1", "value1")
        result = adapter.get_many([])
        assert result == {}

    def test_multiple_operations_consistency(self, adapter: MockCacheAdapter) -> None:
        adapter.set("a", 1)
        adapter.set("b", 2)
        adapter.set("c", 3)

        adapter.delete("b")

        adapter.set("a", 10)
        adapter.set("d", 4)

        assert adapter.get("a") == 10
        assert adapter.get("b") is None
        assert adapter.get("c") == 3
        assert adapter.get("d") == 4
