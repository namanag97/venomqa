"""Tests for World + ResourceGraph integration."""

import pytest

from venomqa.v1.adapters.resource_graph import (
    ResourceGraph,
    ResourceSchema,
    ResourceType,
)
from venomqa.v1.core.action import Action, ActionResult, HTTPRequest, HTTPResponse
from venomqa.v1.core.context import Context
from venomqa.v1.world import World


class MockHttpClient:
    """Minimal HTTP client for testing."""

    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        return ActionResult.from_response(
            HTTPRequest("GET", url),
            HTTPResponse(200, body={"ok": True}),
        )

    def post(self, url, **kwargs):
        self.calls.append(("POST", url))
        return ActionResult.from_response(
            HTTPRequest("POST", url),
            HTTPResponse(201, body={"id": "new_123"}),
        )

    def delete(self, url, **kwargs):
        self.calls.append(("DELETE", url))
        return ActionResult.from_response(
            HTTPRequest("DELETE", url),
            HTTPResponse(204),
        )


@pytest.fixture
def schema():
    return ResourceSchema(
        types={
            "workspace": ResourceType(name="workspace"),
            "upload": ResourceType(name="upload", parent="workspace"),
        }
    )


@pytest.fixture
def world(schema):
    return World(
        api=MockHttpClient(),
        systems={
            "resources": ResourceGraph(schema=schema),
        },
    )


class TestWorldResourceGraphIntegration:
    def test_resources_property(self, world):
        """World.resources returns the ResourceGraph."""
        assert world.resources is not None
        assert isinstance(world.resources, ResourceGraph)

    def test_resources_property_none_when_not_configured(self):
        """World.resources returns None when no ResourceGraph."""
        world = World(api=MockHttpClient())
        assert world.resources is None

    def test_resource_exists(self, world):
        """World.resource_exists delegates to ResourceGraph."""
        assert world.resource_exists("workspace", "ws_123") is False

        world.resources.create("workspace", "ws_123")
        assert world.resource_exists("workspace", "ws_123") is True

    def test_resource_exists_returns_false_when_no_graph(self):
        """World.resource_exists returns False when no ResourceGraph."""
        world = World(api=MockHttpClient())
        assert world.resource_exists("workspace", "ws_123") is False

    def test_checkpoint_rollback_includes_resources(self, world):
        """Checkpoint/rollback preserves ResourceGraph state."""
        # Initial state
        world.resources.create("workspace", "ws_123")

        # Checkpoint
        cp_id = world.checkpoint("before_upload")

        # Add resources after checkpoint
        world.resources.create("upload", "up_1", parent_id="ws_123")
        world.resources.create("upload", "up_2", parent_id="ws_123")

        assert world.resource_exists("upload", "up_1")
        assert world.resource_exists("upload", "up_2")

        # Rollback
        world.rollback(cp_id)

        # New resources should be gone
        assert world.resource_exists("workspace", "ws_123")
        assert not world.resource_exists("upload", "up_1")
        assert not world.resource_exists("upload", "up_2")

    def test_checkpoint_rollback_restores_destroyed(self, world):
        """Rollback restores destroyed resources."""
        world.resources.create("workspace", "ws_123")
        world.resources.create("upload", "up_1", parent_id="ws_123")

        cp_id = world.checkpoint("with_upload")

        # Destroy after checkpoint
        world.resources.destroy("upload", "up_1")
        assert not world.resource_exists("upload", "up_1")

        # Rollback
        world.rollback(cp_id)

        # Should be alive again
        assert world.resource_exists("upload", "up_1")

    def test_observe_includes_resources(self, world):
        """State observation includes ResourceGraph data."""
        world.resources.create("workspace", "ws_123")

        state = world.observe()
        obs = state.observations.get("resources")

        assert obs is not None
        assert obs.data["count"] == 1

    def test_can_execute_action_with_requirements(self, world):
        """can_execute_action checks resource requirements."""

        def dummy_action(api, ctx):
            return api.get("/test")

        # Action that requires workspace
        action = Action(
            name="create_upload",
            execute=dummy_action,
        )
        # Add requires attribute (normally set by action generator)
        action.requires = ["workspace"]

        # No workspace exists
        assert world.can_execute_action(action) is False

        # Create workspace
        world.resources.create("workspace", "ws_123")
        world.context.set("workspace_id", "ws_123")

        # Now should pass
        assert world.can_execute_action(action) is True

    def test_can_execute_action_without_graph(self):
        """can_execute_action works when no ResourceGraph."""
        world = World(api=MockHttpClient())

        def dummy_action(api):
            return api.get("/test")

        action = Action(name="test", execute=dummy_action)
        # Should not crash, just check regular preconditions
        assert world.can_execute_action(action) is True


class TestResourceGraphWithContext:
    """Test ResourceGraph syncing with Context bindings."""

    def test_context_bindings_for_can_execute(self, world):
        """can_execute uses context bindings for resource IDs."""
        world.resources.create("workspace", "ws_A")
        world.resources.create("workspace", "ws_B")

        def action_fn(api, ctx):
            return api.get("/test")

        action = Action(name="test", execute=action_fn)
        action.requires = ["workspace"]

        # Point to ws_A
        world.context.set("workspace_id", "ws_A")
        assert world.can_execute_action(action) is True

        # Point to non-existent
        world.context.set("workspace_id", "ws_NONEXISTENT")
        assert world.can_execute_action(action) is False

        # Point to ws_B
        world.context.set("workspace_id", "ws_B")
        assert world.can_execute_action(action) is True

    def test_destroyed_resource_blocks_action(self, world):
        """Actions are blocked when their required resources are destroyed."""
        world.resources.create("workspace", "ws_123")
        world.context.set("workspace_id", "ws_123")

        def action_fn(api, ctx):
            return api.get("/test")

        action = Action(name="test", execute=action_fn)
        action.requires = ["workspace"]

        assert world.can_execute_action(action) is True

        # Destroy the workspace
        world.resources.destroy("workspace", "ws_123")

        # Action should now be blocked
        assert world.can_execute_action(action) is False
