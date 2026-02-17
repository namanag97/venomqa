"""Type system for resource hierarchies.

This module provides data structures for defining resource types and their
relationships. A ResourceSchema holds the complete type hierarchy and
provides methods for navigating parent/child relationships.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ResourceType:
    """Definition of a resource type in the system.

    A ResourceType describes a category of resources (e.g., "workspace",
    "upload", "user") including its hierarchical position and how to
    identify instances.

    Attributes:
        name: Unique identifier for this type (e.g., "workspace", "upload")
        parent: Name of the parent type, or None for root types
        id_field: Field name containing the ID in API responses (default: "id")
        path_param: URL path parameter name for this resource (e.g., "workspace_id")

    Example:
        >>> workspace = ResourceType(name="workspace")
        >>> upload = ResourceType(
        ...     name="upload",
        ...     parent="workspace",
        ...     path_param="upload_id"
        ... )
    """

    name: str
    parent: str | None = None
    id_field: str = "id"
    path_param: str | None = None

    def __post_init__(self) -> None:
        """Validate the resource type configuration."""
        if not self.name:
            raise ValueError("ResourceType name cannot be empty")


@dataclass
class ResourceSchema:
    """Schema defining all resource types and their relationships.

    A ResourceSchema is the complete type system for a set of resources,
    providing methods to navigate the parent/child hierarchy.

    Attributes:
        types: Mapping from type name to ResourceType

    Example:
        >>> schema = ResourceSchema(types={
        ...     "workspace": ResourceType(name="workspace"),
        ...     "upload": ResourceType(name="upload", parent="workspace"),
        ...     "version": ResourceType(name="version", parent="upload"),
        ... })
        >>> schema.get_ancestors("version")  # ["upload", "workspace"]
    """

    types: dict[str, ResourceType] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate parent references exist."""
        for name, rt in self.types.items():
            if rt.parent is not None and rt.parent not in self.types:
                raise ValueError(
                    f"ResourceType '{name}' references unknown parent '{rt.parent}'"
                )

    def get_type(self, name: str) -> ResourceType | None:
        """Look up a resource type by name.

        Args:
            name: The resource type name

        Returns:
            The ResourceType if found, None otherwise
        """
        return self.types.get(name)

    def get_parent(self, type_name: str) -> str | None:
        """Get the parent type name for a given type.

        Args:
            type_name: Name of the resource type

        Returns:
            Parent type name, or None if type is a root or not found
        """
        rt = self.types.get(type_name)
        return rt.parent if rt else None

    def get_children(self, type_name: str) -> list[str]:
        """Get all direct child types of a given type.

        Args:
            type_name: Name of the parent resource type

        Returns:
            List of child type names (may be empty)
        """
        return [
            name for name, rt in self.types.items()
            if rt.parent == type_name
        ]

    def get_ancestors(self, type_name: str) -> list[str]:
        """Get all ancestor types from immediate parent to root.

        Args:
            type_name: Name of the resource type

        Returns:
            List of ancestor type names, ordered from immediate parent
            to the root. Empty if type is a root or not found.

        Example:
            >>> # Given: version -> upload -> workspace
            >>> schema.get_ancestors("version")
            ["upload", "workspace"]
        """
        ancestors: list[str] = []
        current = type_name

        # Prevent infinite loops from circular references
        visited: set[str] = set()

        while current and current not in visited:
            visited.add(current)
            parent = self.get_parent(current)
            if parent:
                ancestors.append(parent)
                current = parent
            else:
                break

        return ancestors

    def get_descendants(self, type_name: str) -> list[str]:
        """Get all descendant types (children, grandchildren, etc.).

        Args:
            type_name: Name of the resource type

        Returns:
            List of all descendant type names in breadth-first order
        """
        descendants: list[str] = []
        queue = self.get_children(type_name)

        while queue:
            child = queue.pop(0)
            descendants.append(child)
            queue.extend(self.get_children(child))

        return descendants

    def is_root(self, type_name: str) -> bool:
        """Check if a type is a root (has no parent).

        Args:
            type_name: Name of the resource type

        Returns:
            True if the type exists and has no parent
        """
        rt = self.types.get(type_name)
        return rt is not None and rt.parent is None

    def root_types(self) -> list[str]:
        """Get all root types (types with no parent).

        Returns:
            List of root type names
        """
        return [name for name, rt in self.types.items() if rt.parent is None]
