"""Tests for ResourceGraph adapter."""

import pytest

from venomqa.v1.adapters.resource_graph import (
    Resource,
    ResourceGraph,
    ResourceSchema,
    ResourceSnapshot,
    ResourceType,
    schema_from_openapi,
    _parse_path_segments,
    _singularize,
)


class TestResourceType:
    def test_create_simple(self):
        rt = ResourceType(name="workspace")
        assert rt.name == "workspace"
        assert rt.parent is None
        assert rt.id_field == "id"

    def test_create_with_parent(self):
        rt = ResourceType(name="upload", parent="workspace")
        assert rt.name == "upload"
        assert rt.parent == "workspace"


class TestResourceSchema:
    @pytest.fixture
    def schema(self):
        return ResourceSchema(
            types={
                "workspace": ResourceType(name="workspace"),
                "upload": ResourceType(name="upload", parent="workspace"),
                "member": ResourceType(name="member", parent="workspace"),
                "comment": ResourceType(name="comment", parent="upload"),
            }
        )

    def test_get_parent(self, schema):
        assert schema.get_parent("workspace") is None
        assert schema.get_parent("upload") == "workspace"
        assert schema.get_parent("comment") == "upload"
        assert schema.get_parent("nonexistent") is None

    def test_get_children(self, schema):
        children = schema.get_children("workspace")
        assert set(children) == {"upload", "member"}
        assert schema.get_children("upload") == ["comment"]
        assert schema.get_children("comment") == []

    def test_get_ancestors(self, schema):
        assert schema.get_ancestors("workspace") == []
        assert schema.get_ancestors("upload") == ["workspace"]
        assert schema.get_ancestors("comment") == ["upload", "workspace"]


class TestResourceGraph:
    @pytest.fixture
    def schema(self):
        return ResourceSchema(
            types={
                "workspace": ResourceType(name="workspace"),
                "upload": ResourceType(name="upload", parent="workspace"),
                "member": ResourceType(name="member", parent="workspace"),
            }
        )

    @pytest.fixture
    def graph(self, schema):
        return ResourceGraph(schema=schema)

    def test_create_resource(self, graph):
        res = graph.create("workspace", "ws_123", data={"name": "Test"})
        assert res.type == "workspace"
        assert res.id == "ws_123"
        assert res.data == {"name": "Test"}
        assert res.alive is True
        assert res.parent is None

    def test_create_child_resource(self, graph):
        graph.create("workspace", "ws_123")
        upload = graph.create("upload", "up_456", parent_id="ws_123")

        assert upload.type == "upload"
        assert upload.id == "up_456"
        assert upload.parent is not None
        assert upload.parent.id == "ws_123"

    def test_exists(self, graph):
        assert graph.exists("workspace", "ws_123") is False
        graph.create("workspace", "ws_123")
        assert graph.exists("workspace", "ws_123") is True

    def test_get(self, graph):
        assert graph.get("workspace", "ws_123") is None
        graph.create("workspace", "ws_123")
        res = graph.get("workspace", "ws_123")
        assert res is not None
        assert res.id == "ws_123"

    def test_destroy_simple(self, graph):
        graph.create("workspace", "ws_123")
        assert graph.exists("workspace", "ws_123") is True

        graph.destroy("workspace", "ws_123")
        assert graph.exists("workspace", "ws_123") is False

        # Resource still in dict but marked as not alive
        res = graph.get("workspace", "ws_123")
        assert res is not None
        assert res.alive is False

    def test_destroy_cascades_to_children(self, graph):
        """Destroying a parent should mark all children as not alive."""
        graph.create("workspace", "ws_123")
        graph.create("upload", "up_1", parent_id="ws_123")
        graph.create("upload", "up_2", parent_id="ws_123")
        graph.create("member", "mem_1", parent_id="ws_123")

        assert graph.exists("workspace", "ws_123")
        assert graph.exists("upload", "up_1")
        assert graph.exists("upload", "up_2")
        assert graph.exists("member", "mem_1")

        # Destroy workspace
        graph.destroy("workspace", "ws_123")

        # All should be gone
        assert not graph.exists("workspace", "ws_123")
        assert not graph.exists("upload", "up_1")
        assert not graph.exists("upload", "up_2")
        assert not graph.exists("member", "mem_1")

    def test_destroy_does_not_affect_siblings(self, graph):
        """Destroying one child should not affect siblings."""
        graph.create("workspace", "ws_123")
        graph.create("upload", "up_1", parent_id="ws_123")
        graph.create("upload", "up_2", parent_id="ws_123")

        graph.destroy("upload", "up_1")

        assert graph.exists("workspace", "ws_123")
        assert not graph.exists("upload", "up_1")
        assert graph.exists("upload", "up_2")

    def test_get_children(self, graph):
        graph.create("workspace", "ws_123")
        graph.create("upload", "up_1", parent_id="ws_123")
        graph.create("upload", "up_2", parent_id="ws_123")

        children = graph.get_children("workspace", "ws_123")
        assert len(children) == 2
        assert {c.id for c in children} == {"up_1", "up_2"}

    def test_get_children_excludes_dead(self, graph):
        graph.create("workspace", "ws_123")
        graph.create("upload", "up_1", parent_id="ws_123")
        graph.create("upload", "up_2", parent_id="ws_123")

        graph.destroy("upload", "up_1")

        children = graph.get_children("workspace", "ws_123")
        assert len(children) == 1
        assert children[0].id == "up_2"

    def test_can_execute_all_exist(self, graph):
        graph.create("workspace", "ws_123")
        graph.create("upload", "up_456", parent_id="ws_123")

        bindings = {"workspace_id": "ws_123", "upload_id": "up_456"}
        assert graph.can_execute(["workspace", "upload"], bindings) is True

    def test_can_execute_missing_resource(self, graph):
        graph.create("workspace", "ws_123")

        bindings = {"workspace_id": "ws_123", "upload_id": "up_456"}
        assert graph.can_execute(["workspace", "upload"], bindings) is False

    def test_can_execute_dead_resource(self, graph):
        graph.create("workspace", "ws_123")
        graph.create("upload", "up_456", parent_id="ws_123")
        graph.destroy("upload", "up_456")

        bindings = {"workspace_id": "ws_123", "upload_id": "up_456"}
        assert graph.can_execute(["workspace", "upload"], bindings) is False

    def test_can_execute_missing_binding(self, graph):
        graph.create("workspace", "ws_123")

        bindings = {"workspace_id": "ws_123"}  # missing upload_id
        assert graph.can_execute(["workspace", "upload"], bindings) is False


class TestResourceGraphCheckpointRollback:
    @pytest.fixture
    def schema(self):
        return ResourceSchema(
            types={
                "workspace": ResourceType(name="workspace"),
                "upload": ResourceType(name="upload", parent="workspace"),
            }
        )

    @pytest.fixture
    def graph(self, schema):
        return ResourceGraph(schema=schema)

    def test_checkpoint_creates_snapshot(self, graph):
        graph.create("workspace", "ws_123")
        snapshot = graph.checkpoint("cp1")

        assert isinstance(snapshot, ResourceSnapshot)
        assert ("workspace", "ws_123") in snapshot.resources

    def test_rollback_restores_state(self, graph):
        graph.create("workspace", "ws_123")
        snapshot = graph.checkpoint("cp1")

        # Create more resources after checkpoint
        graph.create("upload", "up_1", parent_id="ws_123")
        graph.create("upload", "up_2", parent_id="ws_123")

        assert graph.exists("upload", "up_1")
        assert graph.exists("upload", "up_2")

        # Rollback
        graph.rollback(snapshot)

        # New resources should be gone
        assert graph.exists("workspace", "ws_123")
        assert not graph.exists("upload", "up_1")
        assert not graph.exists("upload", "up_2")

    def test_rollback_restores_destroyed_resources(self, graph):
        graph.create("workspace", "ws_123")
        graph.create("upload", "up_1", parent_id="ws_123")

        snapshot = graph.checkpoint("cp1")

        # Destroy after checkpoint
        graph.destroy("upload", "up_1")
        assert not graph.exists("upload", "up_1")

        # Rollback
        graph.rollback(snapshot)

        # Should be alive again
        assert graph.exists("upload", "up_1")

    def test_rollback_preserves_parent_references(self, graph):
        graph.create("workspace", "ws_123")
        graph.create("upload", "up_1", parent_id="ws_123")

        snapshot = graph.checkpoint("cp1")
        graph.destroy("workspace", "ws_123")
        graph.rollback(snapshot)

        # Check parent reference is preserved
        upload = graph.get("upload", "up_1")
        assert upload is not None
        assert upload.parent is not None
        assert upload.parent.id == "ws_123"

    def test_checkpoint_is_independent_copy(self, graph):
        graph.create("workspace", "ws_123")
        snapshot = graph.checkpoint("cp1")

        # Modify original
        graph.get("workspace", "ws_123").data["modified"] = True

        # Snapshot should not be affected
        assert "modified" not in snapshot.resources[("workspace", "ws_123")].data


class TestResourceGraphObserve:
    def test_observe_empty(self):
        graph = ResourceGraph()
        obs = graph.observe()
        assert obs.system == "resources"
        assert obs.data["count"] == 0
        assert obs.data["resources"] == []

    def test_observe_with_resources(self):
        schema = ResourceSchema(
            types={
                "workspace": ResourceType(name="workspace"),
                "upload": ResourceType(name="upload", parent="workspace"),
            }
        )
        graph = ResourceGraph(schema=schema)
        graph.create("workspace", "ws_123")
        graph.create("upload", "up_1", parent_id="ws_123")

        obs = graph.observe()
        assert obs.data["count"] == 2
        assert len(obs.data["resources"]) == 2

    def test_observe_excludes_dead(self):
        graph = ResourceGraph()
        graph.create("workspace", "ws_123")
        graph.create("workspace", "ws_456")
        graph.destroy("workspace", "ws_123")

        obs = graph.observe()
        assert obs.data["count"] == 1


class TestOpenAPIParser:
    def test_parse_path_segments_simple(self):
        segments = _parse_path_segments("/workspaces")
        assert segments == [("workspaces", None)]

    def test_parse_path_segments_with_param(self):
        segments = _parse_path_segments("/workspaces/{workspace_id}")
        assert segments == [("workspaces", "workspace_id")]

    def test_parse_path_segments_nested(self):
        segments = _parse_path_segments("/workspaces/{workspace_id}/uploads/{upload_id}")
        assert segments == [
            ("workspaces", "workspace_id"),
            ("uploads", "upload_id"),
        ]

    def test_singularize(self):
        assert _singularize("workspaces") == "workspace"
        assert _singularize("uploads") == "upload"
        assert _singularize("entries") == "entry"
        assert _singularize("statuses") == "status"
        assert _singularize("user") == "user"

    def test_schema_from_openapi_simple(self):
        spec = {
            "paths": {
                "/workspaces": {},
                "/workspaces/{workspace_id}": {},
            }
        }
        schema = schema_from_openapi(spec)
        assert "workspace" in schema.types
        assert schema.types["workspace"].parent is None

    def test_schema_from_openapi_nested(self):
        spec = {
            "paths": {
                "/workspaces": {},
                "/workspaces/{workspace_id}": {},
                "/workspaces/{workspace_id}/uploads": {},
                "/workspaces/{workspace_id}/uploads/{upload_id}": {},
            }
        }
        schema = schema_from_openapi(spec)

        assert "workspace" in schema.types
        assert "upload" in schema.types
        assert schema.types["workspace"].parent is None
        assert schema.types["upload"].parent == "workspace"

    def test_schema_from_openapi_deeply_nested(self):
        spec = {
            "paths": {
                "/orgs/{org_id}/teams/{team_id}/members/{member_id}": {},
            }
        }
        schema = schema_from_openapi(spec)

        assert schema.types["org"].parent is None
        assert schema.types["team"].parent == "org"
        assert schema.types["member"].parent == "team"
