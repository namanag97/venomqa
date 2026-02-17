"""Resource graph for tracking live resource instances.

This module provides the runtime representation of resources, including
lifecycle management (create/destroy with cascading), checkpoint/rollback
for exploration branching, and precondition checking.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from .type_system import ResourceSchema


@dataclass
class Resource:
    """A live instance of a resource type.

    Resources track both identity (type + id) and state (data, alive).
    The alive flag enables soft deletion with cascade behavior.

    Attributes:
        type: The resource type name (e.g., "workspace")
        id: Unique identifier within the type
        parent: Reference to parent resource, if any
        data: Arbitrary data associated with this resource
        alive: Whether this resource is currently active

    Example:
        >>> ws = Resource(type="workspace", id="ws-123", data={"name": "My Project"})
        >>> upload = Resource(type="upload", id="up-456", parent=ws)
    """

    type: str
    id: str
    parent: Resource | None = None
    data: dict[str, Any] = field(default_factory=dict)
    alive: bool = True

    def __hash__(self) -> int:
        """Hash by type and id for use in sets/dicts."""
        return hash((self.type, self.id))

    def __eq__(self, other: object) -> bool:
        """Equality by type and id."""
        if not isinstance(other, Resource):
            return NotImplemented
        return self.type == other.type and self.id == other.id


@dataclass
class ResourceSnapshot:
    """Immutable snapshot of all resources for checkpoint/rollback.

    Stores a deep copy of all resources at a point in time.

    Attributes:
        resources: Mapping from (type, id) tuple to Resource
    """

    resources: dict[tuple[str, str], Resource] = field(default_factory=dict)


class ResourceGraph:
    """Graph of live resources with lifecycle management.

    ResourceGraph tracks all resource instances, their parent/child
    relationships, and supports checkpoint/rollback for branching
    exploration.

    Example:
        >>> schema = ResourceSchema(types={
        ...     "workspace": ResourceType(name="workspace"),
        ...     "upload": ResourceType(name="upload", parent="workspace"),
        ... })
        >>> graph = ResourceGraph(schema)
        >>> ws = graph.create("workspace", "ws-1")
        >>> up = graph.create("upload", "up-1", parent_id="ws-1")
        >>> snap = graph.checkpoint()
        >>> graph.destroy("workspace", "ws-1")  # cascades to upload
        >>> graph.rollback(snap)  # both restored
    """

    def __init__(self, schema: ResourceSchema) -> None:
        """Initialize an empty resource graph.

        Args:
            schema: The ResourceSchema defining valid types
        """
        self._schema = schema
        self._resources: dict[tuple[str, str], Resource] = {}

    @property
    def schema(self) -> ResourceSchema:
        """The schema defining resource types."""
        return self._schema

    def create(
        self,
        type: str,
        id: str,
        parent_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> Resource:
        """Create a new resource instance.

        Args:
            type: The resource type name
            id: Unique identifier for this resource
            parent_id: ID of the parent resource (if type has a parent)
            data: Optional data to associate with the resource

        Returns:
            The newly created Resource

        Raises:
            ValueError: If type is unknown or parent requirements not met
        """
        # Validate type exists
        rt = self._schema.get_type(type)
        if rt is None:
            raise ValueError(f"Unknown resource type: {type}")

        # Validate parent
        parent: Resource | None = None
        if rt.parent is not None:
            if parent_id is None:
                raise ValueError(
                    f"Resource type '{type}' requires a parent of type '{rt.parent}'"
                )
            parent = self.get(rt.parent, parent_id)
            if parent is None:
                raise ValueError(
                    f"Parent {rt.parent}:{parent_id} not found for {type}:{id}"
                )
        elif parent_id is not None:
            raise ValueError(
                f"Resource type '{type}' does not have a parent, "
                f"but parent_id was provided"
            )

        # Check for duplicate
        key = (type, id)
        if key in self._resources and self._resources[key].alive:
            raise ValueError(f"Resource {type}:{id} already exists")

        # Create resource
        resource = Resource(
            type=type,
            id=id,
            parent=parent,
            data=data if data else {},
            alive=True,
        )
        self._resources[key] = resource
        return resource

    def destroy(self, type: str, id: str) -> None:
        """Destroy a resource and cascade to all children.

        Children are determined by the schema's parent/child relationships
        and by actual parent references.

        Args:
            type: The resource type name
            id: The resource ID

        Raises:
            ValueError: If resource not found
        """
        resource = self.get(type, id)
        if resource is None:
            raise ValueError(f"Resource {type}:{id} not found")

        # Find and destroy children first (cascade)
        children = self.get_children(type, id)
        for child in children:
            self.destroy(child.type, child.id)

        # Mark as destroyed
        resource.alive = False

    def get(self, type: str, id: str) -> Resource | None:
        """Get a resource by type and ID.

        Args:
            type: The resource type name
            id: The resource ID

        Returns:
            The Resource if found and alive, None otherwise
        """
        key = (type, id)
        resource = self._resources.get(key)
        if resource and resource.alive:
            return resource
        return None

    def exists(self, type: str, id: str) -> bool:
        """Check if a resource exists and is alive.

        Args:
            type: The resource type name
            id: The resource ID

        Returns:
            True if resource exists and is alive
        """
        return self.get(type, id) is not None

    def get_children(self, type: str, id: str) -> list[Resource]:
        """Get all live children of a resource.

        Finds resources whose parent reference points to the given resource.

        Args:
            type: The parent resource type name
            id: The parent resource ID

        Returns:
            List of child Resources
        """
        parent = self.get(type, id)
        if parent is None:
            return []

        return [
            r for r in self._resources.values()
            if r.alive and r.parent is not None and
            r.parent.type == type and r.parent.id == id
        ]

    def get_all(self, type: str | None = None) -> list[Resource]:
        """Get all live resources, optionally filtered by type.

        Args:
            type: Optional type name to filter by

        Returns:
            List of matching Resources
        """
        resources = [r for r in self._resources.values() if r.alive]
        if type is not None:
            resources = [r for r in resources if r.type == type]
        return resources

    def checkpoint(self) -> ResourceSnapshot:
        """Create a snapshot of all current resources.

        Returns:
            A ResourceSnapshot that can be passed to rollback()
        """
        # Deep copy all resources
        snapshot_resources: dict[tuple[str, str], Resource] = {}

        for key, resource in self._resources.items():
            snapshot_resources[key] = Resource(
                type=resource.type,
                id=resource.id,
                parent=None,  # Will fix parent refs below
                data=copy.deepcopy(resource.data),
                alive=resource.alive,
            )

        # Fix parent references to point to snapshot copies
        for key, resource in self._resources.items():
            if resource.parent is not None:
                parent_key = (resource.parent.type, resource.parent.id)
                if parent_key in snapshot_resources:
                    snapshot_resources[key].parent = snapshot_resources[parent_key]

        return ResourceSnapshot(resources=snapshot_resources)

    def rollback(self, snapshot: ResourceSnapshot) -> None:
        """Restore state from a snapshot.

        Args:
            snapshot: A ResourceSnapshot from checkpoint()
        """
        # Clear current state
        self._resources.clear()

        # Restore from snapshot (deep copy to avoid sharing)
        for key, resource in snapshot.resources.items():
            self._resources[key] = Resource(
                type=resource.type,
                id=resource.id,
                parent=None,  # Will fix below
                data=copy.deepcopy(resource.data),
                alive=resource.alive,
            )

        # Fix parent references
        for key, resource in snapshot.resources.items():
            if resource.parent is not None:
                parent_key = (resource.parent.type, resource.parent.id)
                if parent_key in self._resources:
                    self._resources[key].parent = self._resources[parent_key]

    def can_execute(
        self,
        requires: list[str],
        bindings: dict[str, str] | None = None,
    ) -> bool:
        """Check if required resources exist for action execution.

        This verifies that for each required resource type, at least one
        live instance exists. If bindings are provided, checks that
        specific IDs exist.

        Args:
            requires: List of required resource type names
            bindings: Optional mapping from type name to specific ID

        Returns:
            True if all requirements are satisfied

        Example:
            >>> graph.can_execute(["workspace"])  # any workspace exists?
            >>> graph.can_execute(["workspace"], {"workspace": "ws-1"})  # specific one?
        """
        bindings = bindings or {}

        for req_type in requires:
            if req_type in bindings:
                # Check specific resource exists
                if not self.exists(req_type, bindings[req_type]):
                    return False
            else:
                # Check any resource of this type exists
                if not self.get_all(req_type):
                    return False

        return True
