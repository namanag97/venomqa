"""Integration tests for v2 architecture: ResourceGraph + World + Agent.

These tests verify the complete flow:
1. Parse OpenAPI spec → ResourceSchema + Actions
2. ResourceGraph tracks resource lifecycle
3. World checkpoints/rollbacks include ResourceGraph
4. Agent filters actions based on resource existence
5. Auto-cascade on delete
"""

import pytest

from venomqa.v1 import (
    Action,
    ActionResult,
    Agent,
    BFS,
    DFS,
    Invariant,
    World,
)
from venomqa.v1.adapters.resource_graph import (
    ResourceGraph,
    ResourceSchema,
    ResourceType,
    schema_from_openapi,
)
from venomqa.v1.core.action import HTTPRequest, HTTPResponse
from venomqa.v1.core.context import Context
from venomqa.v1.generators.openapi_actions import generate_actions, generate_schema_and_actions


class MockHttpClient:
    """Mock HTTP client that tracks calls and simulates resource creation."""

    def __init__(self):
        self.calls = []
        self._id_counter = 0

    def _next_id(self, prefix: str) -> str:
        self._id_counter += 1
        return f"{prefix}_{self._id_counter}"

    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        return ActionResult.from_response(
            HTTPRequest("GET", url),
            HTTPResponse(200, body={"data": []}),
        )

    def post(self, url, json=None, **kwargs):
        self.calls.append(("POST", url, json))
        # Generate ID based on URL
        if "workspaces" in url and "uploads" not in url:
            new_id = self._next_id("ws")
        elif "uploads" in url:
            new_id = self._next_id("up")
        elif "members" in url:
            new_id = self._next_id("mem")
        else:
            new_id = self._next_id("res")

        return ActionResult.from_response(
            HTTPRequest("POST", url),
            HTTPResponse(201, body={"id": new_id}),
        )

    def delete(self, url, **kwargs):
        self.calls.append(("DELETE", url))
        return ActionResult.from_response(
            HTTPRequest("DELETE", url),
            HTTPResponse(204),
        )

    def put(self, url, json=None, **kwargs):
        self.calls.append(("PUT", url, json))
        return ActionResult.from_response(
            HTTPRequest("PUT", url),
            HTTPResponse(200, body=json or {}),
        )


@pytest.fixture
def schema():
    """Resource schema for workspace -> upload hierarchy."""
    return ResourceSchema(
        types={
            "workspace": ResourceType(name="workspace"),
            "upload": ResourceType(name="upload", parent="workspace"),
            "member": ResourceType(name="member", parent="workspace"),
        }
    )


@pytest.fixture
def openapi_spec():
    """Simple OpenAPI spec for testing."""
    return {
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/workspaces": {
                "post": {"operationId": "createWorkspace", "summary": "Create workspace"},
            },
            "/workspaces/{workspace_id}": {
                "get": {"operationId": "getWorkspace"},
                "delete": {"operationId": "deleteWorkspace"},
            },
            "/workspaces/{workspace_id}/uploads": {
                "post": {"operationId": "createUpload"},
            },
            "/workspaces/{workspace_id}/uploads/{upload_id}": {
                "get": {"operationId": "getUpload"},
                "delete": {"operationId": "deleteUpload"},
            },
        },
    }


class TestResourceGraphIntegration:
    """Test ResourceGraph with World and Agent."""

    def test_world_with_resource_graph(self, schema):
        """World can use ResourceGraph as a system."""
        api = MockHttpClient()
        graph = ResourceGraph(schema=schema)

        world = World(
            api=api,
            systems={"resources": graph},
            state_from_context=["workspace_id", "upload_id"],
        )

        assert world.resources is not None
        assert world.resources is graph

    def test_checkpoint_rollback_with_resources(self, schema):
        """Checkpoint/rollback preserves ResourceGraph state."""
        api = MockHttpClient()
        graph = ResourceGraph(schema=schema)

        world = World(
            api=api,
            systems={"resources": graph},
            state_from_context=["workspace_id"],
        )

        # Create workspace
        graph.create("workspace", "ws_1")
        world.context.set("workspace_id", "ws_1")

        # Checkpoint
        cp_id = world.checkpoint("before_uploads")

        # Create uploads after checkpoint
        graph.create("upload", "up_1", parent_id="ws_1")
        graph.create("upload", "up_2", parent_id="ws_1")

        assert graph.exists("upload", "up_1")
        assert graph.exists("upload", "up_2")

        # Rollback
        world.rollback(cp_id)

        # Uploads should be gone
        assert not graph.exists("upload", "up_1")
        assert not graph.exists("upload", "up_2")
        # Workspace should remain
        assert graph.exists("workspace", "ws_1")

    def test_cascade_delete(self, schema):
        """Destroying parent cascades to children."""
        graph = ResourceGraph(schema=schema)

        graph.create("workspace", "ws_1")
        graph.create("upload", "up_1", parent_id="ws_1")
        graph.create("upload", "up_2", parent_id="ws_1")
        graph.create("member", "mem_1", parent_id="ws_1")

        # Destroy workspace
        graph.destroy("workspace", "ws_1")

        # All children should be destroyed
        assert not graph.exists("workspace", "ws_1")
        assert not graph.exists("upload", "up_1")
        assert not graph.exists("upload", "up_2")
        assert not graph.exists("member", "mem_1")


class TestAgentWithResourceGraph:
    """Test Agent filtering actions based on ResourceGraph."""

    def test_agent_skips_actions_without_required_resources(self, schema):
        """Agent skips actions when required resources don't exist."""
        api = MockHttpClient()
        graph = ResourceGraph(schema=schema)

        world = World(
            api=api,
            systems={"resources": graph},
            state_from_context=["workspace_id", "upload_id"],
        )

        # Action that requires workspace
        def create_upload(api, ctx):
            resp = api.post(f"/workspaces/{ctx.get('workspace_id')}/uploads")
            if resp.ok:
                graph.create("upload", resp.json()["id"], parent_id=ctx.get("workspace_id"))
                ctx.set("upload_id", resp.json()["id"])
            return resp

        action = Action(name="create_upload", execute=create_upload)
        action.requires = ["workspace"]

        # No workspace exists
        valid = agent_valid_actions(world, [action])
        assert len(valid) == 0

        # Create workspace
        graph.create("workspace", "ws_1")
        world.context.set("workspace_id", "ws_1")

        # Now action should be valid
        valid = agent_valid_actions(world, [action])
        assert len(valid) == 1

    def test_agent_exploration_with_resources(self, schema):
        """Full exploration with ResourceGraph tracking."""
        api = MockHttpClient()
        graph = ResourceGraph(schema=schema)

        world = World(
            api=api,
            systems={"resources": graph},
            state_from_context=["workspace_id", "upload_id"],
        )

        # Define actions that update the ResourceGraph
        def create_workspace(api, ctx):
            resp = api.post("/workspaces")
            if resp.ok:
                ws_id = resp.json()["id"]
                graph.create("workspace", ws_id)
                ctx.set("workspace_id", ws_id)
            return resp

        def create_upload(api, ctx):
            ws_id = ctx.get("workspace_id")
            resp = api.post(f"/workspaces/{ws_id}/uploads")
            if resp.ok:
                up_id = resp.json()["id"]
                graph.create("upload", up_id, parent_id=ws_id)
                ctx.set("upload_id", up_id)
            return resp

        actions = [
            Action(name="create_workspace", execute=create_workspace),
            Action(name="create_upload", execute=create_upload),
        ]
        actions[1].requires = ["workspace"]

        # Simple invariant
        invariants = [
            Invariant(name="always_true", check=lambda w: True),
        ]

        agent = Agent(
            world=world,
            actions=actions,
            invariants=invariants,
            strategy=DFS(),
            max_steps=20,
        )

        result = agent.explore()

        # Should have created at least one workspace
        assert result.states_visited >= 1
        assert "create_workspace" in result.used_actions
        # create_upload may or may not run depending on state exploration
        # The important thing is no violations


class TestOpenAPIActionGeneration:
    """Test generating actions from OpenAPI spec."""

    def test_generate_schema_and_actions(self, openapi_spec):
        """Generate both schema and actions from spec."""
        schema, actions = generate_schema_and_actions(openapi_spec)

        # Check schema
        assert "workspace" in schema.types
        assert "upload" in schema.types
        assert schema.types["upload"].parent == "workspace"

        # Check actions
        action_names = {a.name for a in actions}
        assert "createWorkspace" in action_names
        assert "createUpload" in action_names
        assert "deleteWorkspace" in action_names

    def test_generated_actions_have_requires(self, openapi_spec):
        """Generated actions have correct requires attribute."""
        actions = generate_actions(openapi_spec)

        create_upload = next(a for a in actions if a.name == "createUpload")
        assert "workspace" in create_upload.requires

        create_workspace = next(a for a in actions if a.name == "createWorkspace")
        assert create_workspace.requires == []

    def test_full_exploration_with_generated_actions(self, openapi_spec, schema):
        """Full exploration using generated actions."""
        api = MockHttpClient()
        graph = ResourceGraph(schema=schema)

        world = World(
            api=api,
            systems={"resources": graph},
            state_from_context=["workspace_id", "upload_id"],
        )

        # Generate actions
        actions = generate_actions(openapi_spec)

        # Wrap actions to update ResourceGraph
        wrapped_actions = []
        for action in actions:
            wrapped = wrap_action_with_resource_tracking(action, graph)
            wrapped_actions.append(wrapped)

        invariants = [
            Invariant(name="no_crashes", check=lambda w: True),
        ]

        agent = Agent(
            world=world,
            actions=wrapped_actions,
            invariants=invariants,
            strategy=DFS(),
            max_steps=20,
        )

        result = agent.explore()

        # Should have made progress
        assert result.states_visited >= 1
        assert not result.violations


class TestCrossContaminationBug:
    """Test that ResourceGraph prevents the cross-contamination bug.

    The bug: after deleting a workspace, its upload_id might be used
    against a newly created workspace.
    """

    def test_stale_upload_blocked_after_workspace_delete(self, schema):
        """Actions using stale upload are blocked after parent deleted."""
        api = MockHttpClient()
        graph = ResourceGraph(schema=schema)

        world = World(
            api=api,
            systems={"resources": graph},
            state_from_context=["workspace_id", "upload_id"],
        )

        # Create workspace and upload
        graph.create("workspace", "ws_1")
        graph.create("upload", "up_1", parent_id="ws_1")
        world.context.set("workspace_id", "ws_1")
        world.context.set("upload_id", "up_1")

        # Action that requires upload
        def get_upload(api, ctx):
            return api.get(f"/uploads/{ctx.get('upload_id')}")

        action = Action(name="get_upload", execute=get_upload)
        action.requires = ["upload"]

        # Action should be valid now
        assert world.can_execute_action(action)

        # Delete workspace (cascades to upload)
        graph.destroy("workspace", "ws_1")

        # Context still has upload_id, but ResourceGraph knows it's gone
        assert world.context.get("upload_id") == "up_1"
        assert not graph.exists("upload", "up_1")

        # Action should now be blocked
        assert not world.can_execute_action(action)


# Helper functions

def agent_valid_actions(world: World, actions: list[Action]) -> list[Action]:
    """Get valid actions using the same logic as Agent._get_valid_actions."""
    from venomqa.v1.core.state import State

    state = world.observe()
    graph = world.resources
    bindings = world.context.to_dict()

    valid = []
    for a in actions:
        requires = getattr(a, "requires", None)
        if graph and requires:
            if not graph.can_execute(requires, bindings):
                continue
        valid.append(a)

    return valid


def wrap_action_with_resource_tracking(action: Action, graph: ResourceGraph) -> Action:
    """Wrap an action to update ResourceGraph on success."""
    original_execute = action.execute

    def wrapped(api, ctx):
        result = original_execute(api, ctx)

        # If this was a create operation and it succeeded, register resource
        if result.ok and result.status_code == 201:
            try:
                data = result.json()
                if isinstance(data, dict) and "id" in data:
                    # Infer resource type from action name
                    if "workspace" in action.name.lower():
                        graph.create("workspace", data["id"])
                    elif "upload" in action.name.lower():
                        parent_id = ctx.get("workspace_id")
                        if parent_id:
                            graph.create("upload", data["id"], parent_id=parent_id)
            except Exception:
                pass

        return result

    wrapped_action = Action(
        name=action.name,
        execute=wrapped,
        description=action.description,
    )
    wrapped_action.requires = getattr(action, "requires", [])
    return wrapped_action
