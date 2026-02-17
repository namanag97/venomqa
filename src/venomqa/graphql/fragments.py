"""GraphQL fragment support for VenomQA.

Provides fragment definitions, registration, and query composition
for reusable GraphQL selections.

Example:
    >>> from venomqa.graphql import fragment, compose_query, FragmentRegistry
    >>>
    >>> @fragment("UserFields", on="User")
    >>> def user_fields():
    ...     return '''
    ...         id
    ...         name
    ...         email
    ...         createdAt
    ...     '''
    >>>
    >>> query = compose_query('''
    ...     query GetUsers {
    ...         users {
    ...             ...UserFields
    ...         }
    ...     }
    ... ''', fragments=["UserFields"])
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., str])


@dataclass
class Fragment:
    """Represents a GraphQL fragment.

    Attributes:
        name: The fragment name.
        on_type: The type the fragment is on.
        fields: The fragment selection set.
        description: Optional description.
        dependencies: Other fragments this fragment depends on.
    """

    name: str
    on_type: str
    fields: str
    description: str | None = None
    dependencies: list[str] = field(default_factory=list)

    def to_graphql(self) -> str:
        """Convert the fragment to a GraphQL string.

        Returns:
            GraphQL fragment definition string.
        """
        return f"fragment {self.name} on {self.on_type} {{\n{self.fields}\n}}"

    def get_spread(self) -> str:
        """Get the fragment spread syntax.

        Returns:
            Fragment spread string (e.g., "...UserFields").
        """
        return f"...{self.name}"


class FragmentRegistry:
    """Registry for managing GraphQL fragments.

    Provides registration, lookup, and dependency resolution
    for fragments used across queries.

    Example:
        >>> registry = FragmentRegistry()
        >>> registry.register(Fragment(
        ...     name="UserFields",
        ...     on_type="User",
        ...     fields="id name email"
        ... ))
        >>> registry.get("UserFields")
        Fragment(name='UserFields', on_type='User', ...)
    """

    def __init__(self) -> None:
        """Initialize the fragment registry."""
        self._fragments: dict[str, Fragment] = {}

    def register(self, fragment: Fragment) -> None:
        """Register a fragment.

        Args:
            fragment: The fragment to register.

        Raises:
            ValueError: If fragment name is already registered.
        """
        if fragment.name in self._fragments:
            raise ValueError(f"Fragment '{fragment.name}' is already registered")
        self._fragments[fragment.name] = fragment

    def get(self, name: str) -> Fragment | None:
        """Get a fragment by name.

        Args:
            name: The fragment name.

        Returns:
            The fragment or None if not found.
        """
        return self._fragments.get(name)

    def has(self, name: str) -> bool:
        """Check if a fragment is registered.

        Args:
            name: The fragment name.

        Returns:
            True if the fragment is registered.
        """
        return name in self._fragments

    def remove(self, name: str) -> bool:
        """Remove a fragment from the registry.

        Args:
            name: The fragment name.

        Returns:
            True if the fragment was removed, False if not found.
        """
        if name in self._fragments:
            del self._fragments[name]
            return True
        return False

    def list_all(self) -> list[Fragment]:
        """List all registered fragments.

        Returns:
            List of all fragments.
        """
        return list(self._fragments.values())

    def list_for_type(self, type_name: str) -> list[Fragment]:
        """List all fragments for a specific type.

        Args:
            type_name: The type name to filter by.

        Returns:
            List of fragments for the type.
        """
        return [f for f in self._fragments.values() if f.on_type == type_name]

    def resolve_dependencies(self, fragment_names: list[str]) -> list[Fragment]:
        """Resolve fragment dependencies and return in order.

        Args:
            fragment_names: List of fragment names to resolve.

        Returns:
            List of fragments with dependencies resolved (dependencies first).

        Raises:
            ValueError: If a fragment is not found or circular dependency detected.
        """
        resolved: list[Fragment] = []
        seen: set[str] = set()
        resolving: set[str] = set()

        def resolve(name: str) -> None:
            if name in seen:
                return
            if name in resolving:
                raise ValueError(f"Circular dependency detected for fragment '{name}'")

            fragment = self._fragments.get(name)
            if not fragment:
                raise ValueError(f"Fragment '{name}' not found")

            resolving.add(name)

            for dep in fragment.dependencies:
                resolve(dep)

            resolving.remove(name)
            seen.add(name)
            resolved.append(fragment)

        for name in fragment_names:
            resolve(name)

        return resolved

    def clear(self) -> None:
        """Clear all registered fragments."""
        self._fragments.clear()


# Global fragment registry
_global_registry = FragmentRegistry()


def get_global_registry() -> FragmentRegistry:
    """Get the global fragment registry.

    Returns:
        The global FragmentRegistry instance.
    """
    return _global_registry


def fragment(
    name: str,
    on: str,
    *,
    description: str | None = None,
    dependencies: list[str] | None = None,
    registry: FragmentRegistry | None = None,
) -> Callable[[F], F]:
    """Decorator to define and register a GraphQL fragment.

    The decorated function should return the fragment's selection set
    (fields) as a string.

    Args:
        name: The fragment name.
        on: The type the fragment is on.
        description: Optional description.
        dependencies: Other fragments this fragment depends on.
        registry: Registry to use (default: global registry).

    Returns:
        Decorator function.

    Example:
        >>> @fragment("ProductFields", on="Product")
        >>> def product_fields():
        ...     return '''
        ...         id
        ...         title
        ...         price
        ...         inStock
        ...     '''
    """
    reg = registry or _global_registry

    def decorator(func: F) -> F:
        fields = func()
        frag = Fragment(
            name=name,
            on_type=on,
            fields=fields.strip() if isinstance(fields, str) else str(fields),
            description=description or func.__doc__,
            dependencies=dependencies or [],
        )
        reg.register(frag)

        @functools.wraps(func)
        def wrapper() -> str:
            return frag.to_graphql()

        # Attach fragment metadata
        wrapper._fragment = frag  # type: ignore
        wrapper._is_fragment = True  # type: ignore

        return wrapper  # type: ignore

    return decorator


def compose_query(
    query: str,
    fragments: list[str] | None = None,
    *,
    registry: FragmentRegistry | None = None,
    auto_detect: bool = True,
) -> str:
    """Compose a query with fragment definitions.

    Args:
        query: The GraphQL query string (may contain fragment spreads).
        fragments: Explicit list of fragment names to include.
        registry: Fragment registry to use (default: global registry).
        auto_detect: Automatically detect used fragments from spreads.

    Returns:
        Complete query string with fragment definitions appended.

    Example:
        >>> query = compose_query('''
        ...     query GetProducts {
        ...         products {
        ...             ...ProductFields
        ...         }
        ...     }
        ... ''')
    """
    reg = registry or _global_registry
    fragment_names = list(fragments) if fragments else []

    # Auto-detect fragment spreads
    if auto_detect:
        spread_pattern = r"\.\.\.(\w+)"
        for match in re.finditer(spread_pattern, query):
            frag_name = match.group(1)
            if frag_name not in fragment_names and reg.has(frag_name):
                fragment_names.append(frag_name)

    if not fragment_names:
        return query

    # Resolve dependencies
    resolved = reg.resolve_dependencies(fragment_names)

    # Build the complete query
    fragment_defs = "\n\n".join(f.to_graphql() for f in resolved)

    return f"{query.strip()}\n\n{fragment_defs}"


def create_fragment_inline(
    name: str,
    on_type: str,
    fields: str | list[str],
    dependencies: list[str] | None = None,
) -> Fragment:
    """Create a fragment without registration.

    Args:
        name: The fragment name.
        on_type: The type the fragment is on.
        fields: The fragment fields (string or list of field names).
        dependencies: Other fragments this fragment depends on.

    Returns:
        Fragment instance.

    Example:
        >>> frag = create_fragment_inline(
        ...     "UserBasic",
        ...     on_type="User",
        ...     fields=["id", "name"]
        ... )
    """
    if isinstance(fields, list):
        fields_str = "\n".join(f"  {f}" for f in fields)
    else:
        fields_str = fields

    return Fragment(
        name=name,
        on_type=on_type,
        fields=fields_str,
        dependencies=dependencies or [],
    )


def build_query_with_fragments(
    operation_type: str,
    operation_name: str,
    variables: dict[str, str] | None = None,
    selections: list[str] | None = None,
    fragments: list[Fragment] | None = None,
) -> str:
    """Build a complete GraphQL query with fragments.

    Args:
        operation_type: query, mutation, or subscription.
        operation_name: The operation name.
        variables: Variable definitions (name -> type).
        selections: Selection set items.
        fragments: Fragments to include.

    Returns:
        Complete GraphQL query string.

    Example:
        >>> query = build_query_with_fragments(
        ...     operation_type="query",
        ...     operation_name="GetUsers",
        ...     variables={"first": "Int!"},
        ...     selections=["users(first: $first) { ...UserFields }"],
        ...     fragments=[user_fields_fragment]
        ... )
    """
    parts = []

    # Build variable definitions
    var_str = ""
    if variables:
        var_defs = ", ".join(f"${name}: {type_}" for name, type_ in variables.items())
        var_str = f"({var_defs})"

    # Build selection set
    selection_str = ""
    if selections:
        selection_str = "\n  ".join(selections)

    # Build operation
    operation = f"{operation_type} {operation_name}{var_str} {{\n  {selection_str}\n}}"
    parts.append(operation)

    # Add fragments
    if fragments:
        for frag in fragments:
            parts.append(frag.to_graphql())

    return "\n\n".join(parts)


class QueryBuilder:
    """Builder for constructing GraphQL queries with fragments.

    Provides a fluent interface for building complex queries.

    Example:
        >>> query = QueryBuilder("GetProducts") \\
        ...     .add_variable("first", "Int!") \\
        ...     .add_selection("products(first: $first)") \\
        ...     .with_fragment("ProductFields") \\
        ...     .build()
    """

    def __init__(
        self,
        operation_name: str,
        operation_type: str = "query",
        registry: FragmentRegistry | None = None,
    ):
        """Initialize the query builder.

        Args:
            operation_name: The operation name.
            operation_type: query, mutation, or subscription.
            registry: Fragment registry to use.
        """
        self._name = operation_name
        self._type = operation_type
        self._variables: dict[str, str] = {}
        self._selections: list[str] = []
        self._fragments: list[str] = []
        self._registry = registry or _global_registry

    def add_variable(self, name: str, type_: str, default: Any = None) -> QueryBuilder:
        """Add a variable definition.

        Args:
            name: Variable name (without $).
            type_: GraphQL type string.
            default: Optional default value.

        Returns:
            Self for chaining.
        """
        type_def = type_
        if default is not None:
            type_def = f"{type_} = {_format_default(default)}"
        self._variables[name] = type_def
        return self

    def add_selection(self, selection: str) -> QueryBuilder:
        """Add a field selection.

        Args:
            selection: Field selection string.

        Returns:
            Self for chaining.
        """
        self._selections.append(selection)
        return self

    def add_field(
        self,
        name: str,
        args: dict[str, str] | None = None,
        subfields: list[str] | None = None,
    ) -> QueryBuilder:
        """Add a field with optional arguments and subfields.

        Args:
            name: Field name.
            args: Field arguments (arg name -> variable or literal).
            subfields: List of subfield names.

        Returns:
            Self for chaining.
        """
        field_str = name

        if args:
            args_str = ", ".join(f"{k}: {v}" for k, v in args.items())
            field_str = f"{name}({args_str})"

        if subfields:
            subfields_str = " ".join(subfields)
            field_str = f"{field_str} {{ {subfields_str} }}"

        self._selections.append(field_str)
        return self

    def with_fragment(self, name: str) -> QueryBuilder:
        """Include a fragment by name.

        Args:
            name: Fragment name.

        Returns:
            Self for chaining.
        """
        self._fragments.append(name)
        return self

    def build(self) -> str:
        """Build the complete query string.

        Returns:
            Complete GraphQL query with fragments.
        """
        # Build variable definitions
        var_str = ""
        if self._variables:
            var_defs = ", ".join(f"${name}: {type_}" for name, type_ in self._variables.items())
            var_str = f"({var_defs})"

        # Build selection set
        selection_str = "\n    ".join(self._selections)

        # Build operation
        query = f"{self._type} {self._name}{var_str} {{\n    {selection_str}\n}}"

        # Add fragments
        if self._fragments:
            resolved = self._registry.resolve_dependencies(self._fragments)
            fragment_defs = "\n\n".join(f.to_graphql() for f in resolved)
            query = f"{query}\n\n{fragment_defs}"

        return query


def _format_default(value: Any) -> str:
    """Format a default value for GraphQL.

    Args:
        value: The value to format.

    Returns:
        Formatted string.
    """
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)
