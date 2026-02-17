"""ResourceGraph adapter for VenomQA.

Wraps the runtime-core ResourceGraph as a VenomQA Rollbackable system,
enabling typed resource tracking with auto-cascade deletes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from venomqa.v1.core.state import Observation
from venomqa.v1.world.rollbackable import Rollbackable, SystemCheckpoint

if TYPE_CHECKING:
    from venomqa.v1.core.context import Context


@dataclass
class ResourceType:
    """Definition of a resource type."""

    name: str
    parent: str | None = None
    id_field: str = "id"
    path_param: str | None = None


@dataclass
class ResourceSchema:
    """Schema defining all resource types and relationships."""

    types: dict[str, ResourceType] = field(default_factory=dict)

    def get_parent(self, type_name: str) -> str | None:
        """Get parent type name, or None if root."""
        rt = self.types.get(type_name)
        return rt.parent if rt else None

    def get_children(self, type_name: str) -> list[str]:
        """Get all direct child type names."""
        return [t.name for t in self.types.values() if t.parent == type_name]

    def get_ancestors(self, type_name: str) -> list[str]:
        """Get all ancestor type names (parent, grandparent, etc.)."""
        ancestors = []
        current = self.get_parent(type_name)
        while current:
            ancestors.append(current)
            current = self.get_parent(current)
        return ancestors


@dataclass
class Resource:
    """A resource instance."""

    type: str
    id: str
    parent: Resource | None = None
    data: dict[str, Any] = field(default_factory=dict)
    alive: bool = True


@dataclass
class ResourceSnapshot(SystemCheckpoint):
    """Snapshot of ResourceGraph state for rollback."""

    resources: dict[tuple[str, str], Resource] = field(default_factory=dict)


class ResourceGraph(Rollbackable):
    """Typed resource graph with parent-child relationships.

    Tracks what resources exist and their relationships.
    Auto-cascades deletes to children.
    Integrates with VenomQA World via Rollbackable protocol.
    """

    def __init__(self, schema: ResourceSchema | None = None) -> None:
        self.schema = schema or ResourceSchema()
        self._resources: dict[tuple[str, str], Resource] = {}

    def create(
        self,
        type: str,
        id: str,
        parent_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> Resource:
        """Create a new resource.

        Args:
            type: Resource type name (e.g., "workspace", "upload")
            id: Resource ID
            parent_id: Parent resource ID (if this type has a parent)
            data: Optional data to store with the resource

        Returns:
            The created Resource
        """
        parent = None
        if parent_id and self.schema:
            parent_type = self.schema.get_parent(type)
            if parent_type:
                parent = self.get(parent_type, parent_id)

        resource = Resource(
            type=type,
            id=id,
            parent=parent,
            data=data or {},
            alive=True,
        )
        self._resources[(type, id)] = resource
        return resource

    def destroy(self, type: str, id: str) -> None:
        """Destroy a resource and all its descendants.

        Args:
            type: Resource type name
            id: Resource ID
        """
        resource = self._resources.get((type, id))
        if resource:
            resource.alive = False
            # Cascade to children
            for key, child in self._resources.items():
                if child.parent is resource and child.alive:
                    self.destroy(child.type, child.id)

    def get(self, type: str, id: str) -> Resource | None:
        """Get a resource by type and ID."""
        return self._resources.get((type, id))

    def exists(self, type: str, id: str) -> bool:
        """Check if a resource exists and is alive."""
        resource = self._resources.get((type, id))
        return resource is not None and resource.alive

    def get_children(self, type: str, id: str) -> list[Resource]:
        """Get all alive children of a resource."""
        resource = self.get(type, id)
        if not resource:
            return []
        return [
            r for r in self._resources.values() if r.parent is resource and r.alive
        ]

    def can_execute(self, requires: list[str], bindings: dict[str, str]) -> bool:
        """Check if all required resources exist.

        Args:
            requires: List of resource type names that must exist
            bindings: Dict mapping "{type}_id" to actual IDs

        Returns:
            True if all required resources exist and are alive
        """
        for req_type in requires:
            id_key = f"{req_type}_id"
            resource_id = bindings.get(id_key)
            if not resource_id or not self.exists(req_type, resource_id):
                return False
        return True

    # ── Rollbackable protocol ──────────────────────────────────────────────

    def observe(self) -> Observation:
        """Get current state as an Observation."""
        data = {
            "resources": [
                {
                    "type": r.type,
                    "id": r.id,
                    "parent_type": r.parent.type if r.parent else None,
                    "parent_id": r.parent.id if r.parent else None,
                    "alive": r.alive,
                }
                for r in self._resources.values()
                if r.alive
            ],
            "count": sum(1 for r in self._resources.values() if r.alive),
        }
        return Observation(system="resources", data=data)

    def checkpoint(self, name: str) -> ResourceSnapshot:
        """Create a checkpoint of current state."""
        # Deep copy resources
        copied = {}
        for key, resource in self._resources.items():
            copied[key] = Resource(
                type=resource.type,
                id=resource.id,
                parent=None,  # Will fix parent refs after
                data=resource.data.copy(),
                alive=resource.alive,
            )
        # Fix parent references
        for key, resource in self._resources.items():
            if resource.parent:
                parent_key = (resource.parent.type, resource.parent.id)
                copied[key].parent = copied.get(parent_key)

        return ResourceSnapshot(resources=copied)

    def rollback(self, checkpoint: SystemCheckpoint) -> None:
        """Rollback to a previous checkpoint."""
        if not isinstance(checkpoint, ResourceSnapshot):
            raise TypeError(f"Expected ResourceSnapshot, got {type(checkpoint)}")

        # Deep copy from snapshot
        self._resources = {}
        for key, resource in checkpoint.resources.items():
            self._resources[key] = Resource(
                type=resource.type,
                id=resource.id,
                parent=None,
                data=resource.data.copy(),
                alive=resource.alive,
            )
        # Fix parent references
        for key, resource in checkpoint.resources.items():
            if resource.parent:
                parent_key = (resource.parent.type, resource.parent.id)
                self._resources[key].parent = self._resources.get(parent_key)

    # ── Convenience methods ────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Convert graph to dict for debugging/logging."""
        return {
            "resources": [
                {"type": r.type, "id": r.id, "alive": r.alive}
                for r in self._resources.values()
            ]
        }

    def clear(self) -> None:
        """Clear all resources."""
        self._resources.clear()

    @property
    def alive_count(self) -> int:
        """Count of alive resources."""
        return sum(1 for r in self._resources.values() if r.alive)


def schema_from_openapi(spec: dict[str, Any]) -> ResourceSchema:
    """Parse OpenAPI spec to extract ResourceSchema.

    Infers resource types and parent-child relationships from URL paths.

    Args:
        spec: Parsed OpenAPI spec (dict)

    Returns:
        ResourceSchema with inferred types

    Example:
        /workspaces/{workspace_id}/uploads/{upload_id}
        -> workspace (root), upload (parent=workspace)
    """
    types: dict[str, ResourceType] = {}

    for path in spec.get("paths", {}).keys():
        segments = _parse_path_segments(path)

        for i, (resource_name, param_name) in enumerate(segments):
            singular = _singularize(resource_name)
            parent = None
            if i > 0:
                parent = _singularize(segments[i - 1][0])

            if singular not in types:
                types[singular] = ResourceType(
                    name=singular,
                    parent=parent,
                    path_param=param_name,
                )

    return ResourceSchema(types=types)


def _parse_path_segments(path: str) -> list[tuple[str, str | None]]:
    """Parse URL path into (resource_name, param_name) pairs.

    Example:
        "/workspaces/{workspace_id}/uploads/{upload_id}"
        -> [("workspaces", "workspace_id"), ("uploads", "upload_id")]
    """
    segments = []
    parts = [p for p in path.split("/") if p]

    i = 0
    while i < len(parts):
        part = parts[i]
        if part.startswith("{"):
            # This is a parameter, skip (already captured)
            i += 1
            continue

        # Resource name
        param_name = None
        if i + 1 < len(parts) and parts[i + 1].startswith("{"):
            param_name = parts[i + 1].strip("{}")
            i += 2
        else:
            i += 1

        segments.append((part, param_name))

    return segments


def _singularize(name: str) -> str:
    """Convert plural resource name to singular.

    Simple heuristic - handles common cases.
    """
    if name.endswith("ies"):
        return name[:-3] + "y"
    # "statuses" -> "status", "boxes" -> "box"
    if name.endswith("ses") or name.endswith("xes") or name.endswith("ches") or name.endswith("shes"):
        return name[:-2]
    if name.endswith("s") and not name.endswith("ss"):
        return name[:-1]
    return name


__all__ = [
    "Resource",
    "ResourceGraph",
    "ResourceSchema",
    "ResourceSnapshot",
    "ResourceType",
    "schema_from_openapi",
]
