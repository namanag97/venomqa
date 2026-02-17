"""Tests for ResourceGraph functionality."""

import pytest

from runtime_core import (
    Resource,
    ResourceGraph,
    ResourceSchema,
    ResourceSnapshot,
    ResourceType,
)


@pytest.fixture
def simple_schema() -> ResourceSchema:
    """A simple schema with workspace -> upload hierarchy."""
    return ResourceSchema(
        types={
            "workspace": ResourceType(name="workspace"),
            "upload": ResourceType(name="upload", parent="workspace"),
            "version": ResourceType(name="version", parent="upload"),
        }
    )


@pytest.fixture
def graph(simple_schema: ResourceSchema) -> ResourceGraph:
    """An empty ResourceGraph with the simple schema."""
    return ResourceGraph(simple_schema)


class TestCreateResource:
    """Tests for ResourceGraph.create()."""

    def test_create_root_resource(self, graph: ResourceGraph) -> None:
        """Can create a root resource without parent."""
        ws = graph.create("workspace", "ws-1", data={"name": "Test"})

        assert ws.type == "workspace"
        assert ws.id == "ws-1"
        assert ws.parent is None
        assert ws.data == {"name": "Test"}
        assert ws.alive is True

    def test_create_child_resource(self, graph: ResourceGraph) -> None:
        """Can create a child resource with parent."""
        ws = graph.create("workspace", "ws-1")
        upload = graph.create("upload", "up-1", parent_id="ws-1")

        assert upload.type == "upload"
        assert upload.id == "up-1"
        assert upload.parent is ws
        assert upload.alive is True

    def test_create_requires_parent_when_type_has_parent(
        self, graph: ResourceGraph
    ) -> None:
        """Creating a child type without parent_id raises error."""
        with pytest.raises(ValueError, match="requires a parent"):
            graph.create("upload", "up-1")

    def test_create_rejects_parent_for_root_type(
        self, graph: ResourceGraph
    ) -> None:
        """Creating a root type with parent_id raises error."""
        graph.create("workspace", "ws-1")
        with pytest.raises(ValueError, match="does not have a parent"):
            graph.create("workspace", "ws-2", parent_id="ws-1")

    def test_create_requires_existing_parent(self, graph: ResourceGraph) -> None:
        """Parent must exist to create child."""
        with pytest.raises(ValueError, match="not found"):
            graph.create("upload", "up-1", parent_id="nonexistent")

    def test_create_rejects_duplicate_id(self, graph: ResourceGraph) -> None:
        """Cannot create resource with duplicate type+id."""
        graph.create("workspace", "ws-1")
        with pytest.raises(ValueError, match="already exists"):
            graph.create("workspace", "ws-1")

    def test_create_unknown_type_raises(self, graph: ResourceGraph) -> None:
        """Unknown resource type raises error."""
        with pytest.raises(ValueError, match="Unknown resource type"):
            graph.create("unknown", "id-1")


class TestDestroyResource:
    """Tests for ResourceGraph.destroy()."""

    def test_destroy_marks_as_not_alive(self, graph: ResourceGraph) -> None:
        """Destroying sets alive=False."""
        ws = graph.create("workspace", "ws-1")
        graph.destroy("workspace", "ws-1")

        # Can't get destroyed resource
        assert graph.get("workspace", "ws-1") is None
        # But it's still in internal storage with alive=False
        assert ws.alive is False

    def test_destroy_cascades_to_children(self, graph: ResourceGraph) -> None:
        """Destroying parent destroys all children."""
        graph.create("workspace", "ws-1")
        graph.create("upload", "up-1", parent_id="ws-1")
        graph.create("upload", "up-2", parent_id="ws-1")
        graph.create("version", "v-1", parent_id="up-1")

        graph.destroy("workspace", "ws-1")

        assert graph.get("workspace", "ws-1") is None
        assert graph.get("upload", "up-1") is None
        assert graph.get("upload", "up-2") is None
        assert graph.get("version", "v-1") is None

    def test_destroy_nonexistent_raises(self, graph: ResourceGraph) -> None:
        """Destroying nonexistent resource raises error."""
        with pytest.raises(ValueError, match="not found"):
            graph.destroy("workspace", "nonexistent")


class TestCheckpointRollback:
    """Tests for ResourceGraph.checkpoint() and rollback()."""

    def test_checkpoint_captures_state(self, graph: ResourceGraph) -> None:
        """Checkpoint returns a snapshot of current state."""
        graph.create("workspace", "ws-1", data={"name": "Test"})
        snap = graph.checkpoint()

        assert isinstance(snap, ResourceSnapshot)
        assert ("workspace", "ws-1") in snap.resources
        assert snap.resources[("workspace", "ws-1")].data == {"name": "Test"}

    def test_rollback_restores_state(self, graph: ResourceGraph) -> None:
        """Rollback restores to checkpointed state."""
        graph.create("workspace", "ws-1")
        snap = graph.checkpoint()

        # Make changes
        graph.create("upload", "up-1", parent_id="ws-1")
        graph.destroy("workspace", "ws-1")

        # Rollback
        graph.rollback(snap)

        # State restored
        assert graph.exists("workspace", "ws-1")
        assert not graph.exists("upload", "up-1")

    def test_rollback_restores_destroyed_resources(
        self, graph: ResourceGraph
    ) -> None:
        """Rollback brings back destroyed resources."""
        graph.create("workspace", "ws-1")
        graph.create("upload", "up-1", parent_id="ws-1")
        snap = graph.checkpoint()

        graph.destroy("workspace", "ws-1")
        assert not graph.exists("upload", "up-1")

        graph.rollback(snap)
        assert graph.exists("workspace", "ws-1")
        assert graph.exists("upload", "up-1")

    def test_rollback_restores_data(self, graph: ResourceGraph) -> None:
        """Rollback restores resource data."""
        graph.create("workspace", "ws-1", data={"count": 1})
        snap = graph.checkpoint()

        # Modify data
        ws = graph.get("workspace", "ws-1")
        assert ws is not None
        ws.data["count"] = 100

        graph.rollback(snap)

        ws = graph.get("workspace", "ws-1")
        assert ws is not None
        assert ws.data["count"] == 1

    def test_snapshot_is_isolated(self, graph: ResourceGraph) -> None:
        """Changes after checkpoint don't affect the snapshot."""
        graph.create("workspace", "ws-1", data={"items": [1, 2, 3]})
        snap = graph.checkpoint()

        # Modify mutable data
        ws = graph.get("workspace", "ws-1")
        assert ws is not None
        ws.data["items"].append(4)

        # Snapshot is unchanged
        assert snap.resources[("workspace", "ws-1")].data["items"] == [1, 2, 3]


class TestExistsChecksAlive:
    """Tests for ResourceGraph.exists()."""

    def test_exists_returns_true_for_alive(self, graph: ResourceGraph) -> None:
        """exists() returns True for alive resources."""
        graph.create("workspace", "ws-1")
        assert graph.exists("workspace", "ws-1") is True

    def test_exists_returns_false_for_destroyed(
        self, graph: ResourceGraph
    ) -> None:
        """exists() returns False for destroyed resources."""
        graph.create("workspace", "ws-1")
        graph.destroy("workspace", "ws-1")
        assert graph.exists("workspace", "ws-1") is False

    def test_exists_returns_false_for_nonexistent(
        self, graph: ResourceGraph
    ) -> None:
        """exists() returns False for never-created resources."""
        assert graph.exists("workspace", "nonexistent") is False


class TestCanExecute:
    """Tests for ResourceGraph.can_execute()."""

    def test_can_execute_with_no_requirements(
        self, graph: ResourceGraph
    ) -> None:
        """Empty requires list always passes."""
        assert graph.can_execute([]) is True

    def test_can_execute_checks_type_exists(self, graph: ResourceGraph) -> None:
        """Requires checks if any resource of type exists."""
        assert graph.can_execute(["workspace"]) is False

        graph.create("workspace", "ws-1")
        assert graph.can_execute(["workspace"]) is True

    def test_can_execute_checks_all_types(self, graph: ResourceGraph) -> None:
        """All required types must have instances."""
        graph.create("workspace", "ws-1")

        # workspace exists but upload doesn't
        assert graph.can_execute(["workspace", "upload"]) is False

        graph.create("upload", "up-1", parent_id="ws-1")
        assert graph.can_execute(["workspace", "upload"]) is True

    def test_can_execute_with_specific_bindings(
        self, graph: ResourceGraph
    ) -> None:
        """Bindings check for specific resource IDs."""
        graph.create("workspace", "ws-1")
        graph.create("workspace", "ws-2")

        assert graph.can_execute(["workspace"], {"workspace": "ws-1"}) is True
        assert graph.can_execute(["workspace"], {"workspace": "ws-2"}) is True
        assert graph.can_execute(["workspace"], {"workspace": "ws-3"}) is False

    def test_can_execute_respects_destroyed(self, graph: ResourceGraph) -> None:
        """can_execute returns False for destroyed resources."""
        graph.create("workspace", "ws-1")
        assert graph.can_execute(["workspace"]) is True

        graph.destroy("workspace", "ws-1")
        assert graph.can_execute(["workspace"]) is False


class TestGetChildren:
    """Tests for ResourceGraph.get_children()."""

    def test_get_children_returns_direct_children(
        self, graph: ResourceGraph
    ) -> None:
        """get_children returns only direct children."""
        graph.create("workspace", "ws-1")
        graph.create("upload", "up-1", parent_id="ws-1")
        graph.create("upload", "up-2", parent_id="ws-1")
        graph.create("version", "v-1", parent_id="up-1")

        children = graph.get_children("workspace", "ws-1")

        assert len(children) == 2
        assert all(c.type == "upload" for c in children)
        # version is grandchild, not direct child
        assert not any(c.type == "version" for c in children)

    def test_get_children_excludes_destroyed(self, graph: ResourceGraph) -> None:
        """get_children excludes destroyed children."""
        graph.create("workspace", "ws-1")
        graph.create("upload", "up-1", parent_id="ws-1")
        graph.create("upload", "up-2", parent_id="ws-1")

        graph.destroy("upload", "up-1")

        children = graph.get_children("workspace", "ws-1")
        assert len(children) == 1
        assert children[0].id == "up-2"


class TestGetAll:
    """Tests for ResourceGraph.get_all()."""

    def test_get_all_returns_all_alive(self, graph: ResourceGraph) -> None:
        """get_all returns all alive resources."""
        graph.create("workspace", "ws-1")
        graph.create("workspace", "ws-2")
        graph.create("upload", "up-1", parent_id="ws-1")

        all_resources = graph.get_all()
        assert len(all_resources) == 3

    def test_get_all_filters_by_type(self, graph: ResourceGraph) -> None:
        """get_all can filter by type."""
        graph.create("workspace", "ws-1")
        graph.create("workspace", "ws-2")
        graph.create("upload", "up-1", parent_id="ws-1")

        workspaces = graph.get_all("workspace")
        assert len(workspaces) == 2
        assert all(r.type == "workspace" for r in workspaces)

    def test_get_all_excludes_destroyed(self, graph: ResourceGraph) -> None:
        """get_all excludes destroyed resources."""
        graph.create("workspace", "ws-1")
        graph.create("workspace", "ws-2")
        graph.destroy("workspace", "ws-1")

        all_resources = graph.get_all()
        assert len(all_resources) == 1
        assert all_resources[0].id == "ws-2"
