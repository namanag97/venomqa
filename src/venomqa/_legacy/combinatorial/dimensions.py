"""Dimension definitions for combinatorial state testing.

A Dimension represents one axis of variation in the system under test.
Each dimension has a name and a finite set of valid values.

Example:
    >>> from venomqa.combinatorial import Dimension, DimensionSpace
    >>>
    >>> auth = Dimension("auth", ["anon", "user", "admin"])
    >>> status = Dimension("entity_status", ["active", "archived"])
    >>> count = Dimension("count", [0, 1, "many"])
    >>>
    >>> space = DimensionSpace([auth, status, count])
    >>> print(space.total_combinations)  # 3 * 2 * 3 = 18
"""

from __future__ import annotations

import itertools
from collections.abc import Hashable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DimensionValue:
    """A single value within a dimension.

    Wraps a raw value with metadata for display and state generation.

    Attributes:
        dimension_name: Name of the parent dimension.
        value: The actual value (must be hashable for use in sets/dicts).
        label: Human-readable label for this value. Defaults to str(value).
        description: Optional extended description.
        setup_data: Optional dict of data needed to set up this value.
    """

    dimension_name: str
    value: Hashable
    label: str = ""
    description: str = ""
    setup_data: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)

    def __post_init__(self) -> None:
        if not self.label:
            object.__setattr__(self, "label", str(self.value))

    def __repr__(self) -> str:
        return f"{self.dimension_name}={self.value}"


@dataclass
class Dimension:
    """A single axis of variation in the system under test.

    Dimensions define what varies in combinatorial testing. Examples:
    - Authentication level: anon, user, admin
    - Data state: empty, one, many
    - Feature flag: enabled, disabled

    Attributes:
        name: Unique identifier for this dimension.
        values: List of valid values for this dimension.
        description: Human-readable description.
        default_value: Default value when not explicitly set. If None,
            the first value in the list is used.

    Example:
        >>> auth = Dimension("auth", ["anon", "user", "admin"])
        >>> auth.dimension_values  # Returns list of DimensionValue objects
    """

    name: str
    values: list[Hashable]
    description: str = ""
    default_value: Hashable | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Dimension name cannot be empty")
        if not self.values:
            raise ValueError(f"Dimension '{self.name}' must have at least one value")
        if len(self.values) != len(set(self.values)):
            raise ValueError(
                f"Dimension '{self.name}' contains duplicate values: {self.values}"
            )
        if self.default_value is not None and self.default_value not in self.values:
            raise ValueError(
                f"Default value '{self.default_value}' not in dimension '{self.name}' "
                f"values: {self.values}"
            )

    @property
    def dimension_values(self) -> list[DimensionValue]:
        """Get all values as DimensionValue objects."""
        return [
            DimensionValue(dimension_name=self.name, value=v)
            for v in self.values
        ]

    @property
    def size(self) -> int:
        """Number of values in this dimension."""
        return len(self.values)

    def get_default(self) -> Hashable:
        """Get the default value for this dimension."""
        if self.default_value is not None:
            return self.default_value
        return self.values[0]

    def __repr__(self) -> str:
        return f"Dimension({self.name!r}, values={self.values})"


@dataclass
class Combination:
    """A specific assignment of values to dimensions.

    Represents one point in the dimension space -- one specific test
    configuration to exercise.

    Attributes:
        values: Mapping of dimension name to assigned value.

    Example:
        >>> combo = Combination({"auth": "admin", "count": "many", "status": "active"})
        >>> combo["auth"]  # "admin"
        >>> combo.node_id  # "auth=admin__count=many__status=active"
    """

    values: dict[str, Hashable]

    def __getitem__(self, key: str) -> Hashable:
        return self.values[key]

    def __contains__(self, key: str) -> bool:
        return key in self.values

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    @property
    def node_id(self) -> str:
        """Generate a stable, unique node ID from this combination.

        Values are sorted by dimension name for deterministic ordering.
        """
        parts = sorted(self.values.items())
        return "__".join(f"{k}={v}" for k, v in parts)

    @property
    def description(self) -> str:
        """Generate a human-readable description."""
        parts = sorted(self.values.items())
        return ", ".join(f"{k}={v}" for k, v in parts)

    def differs_by_one(self, other: Combination) -> str | None:
        """Check if two combinations differ in exactly one dimension.

        Returns:
            The name of the differing dimension, or None if they differ
            in zero or more than one dimension.
        """
        if set(self.values.keys()) != set(other.values.keys()):
            return None

        differing = [
            k for k in self.values
            if self.values[k] != other.values[k]
        ]

        if len(differing) == 1:
            return differing[0]
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dictionary."""
        return dict(self.values)

    def __hash__(self) -> int:
        return hash(tuple(sorted(self.values.items())))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Combination):
            return NotImplemented
        return self.values == other.values

    def __repr__(self) -> str:
        return f"Combination({self.description})"


class DimensionSpace:
    """The full space of all possible dimension value combinations.

    The DimensionSpace is the Cartesian product of all dimensions.
    It provides methods for enumerating, filtering, and sampling
    from the space.

    Attributes:
        dimensions: The list of dimensions defining this space.

    Example:
        >>> space = DimensionSpace([
        ...     Dimension("auth", ["anon", "user", "admin"]),
        ...     Dimension("count", [0, 1, "many"]),
        ... ])
        >>> print(space.total_combinations)  # 9
        >>> all_combos = space.all_combinations()  # List of 9 Combination objects
    """

    def __init__(self, dimensions: list[Dimension]) -> None:
        if not dimensions:
            raise ValueError("DimensionSpace requires at least one dimension")

        names = [d.name for d in dimensions]
        if len(names) != len(set(names)):
            duplicates = [n for n in names if names.count(n) > 1]
            raise ValueError(f"Duplicate dimension names: {set(duplicates)}")

        self.dimensions = list(dimensions)
        self._dim_by_name: dict[str, Dimension] = {d.name: d for d in dimensions}

    @property
    def dimension_names(self) -> list[str]:
        """Get ordered list of dimension names."""
        return [d.name for d in self.dimensions]

    @property
    def total_combinations(self) -> int:
        """Total number of combinations in the full Cartesian product."""
        result = 1
        for d in self.dimensions:
            result *= d.size
        return result

    def get_dimension(self, name: str) -> Dimension:
        """Get a dimension by name.

        Raises:
            KeyError: If dimension not found.
        """
        if name not in self._dim_by_name:
            raise KeyError(
                f"Dimension '{name}' not found. "
                f"Available: {self.dimension_names}"
            )
        return self._dim_by_name[name]

    def all_combinations(self) -> list[Combination]:
        """Generate all combinations in the Cartesian product.

        Warning: This can be very large for many dimensions with many values.
        For large spaces, use pairwise generation instead.

        Returns:
            List of all possible Combination objects.
        """
        value_lists = [d.values for d in self.dimensions]
        names = self.dimension_names

        return [
            Combination(dict(zip(names, combo, strict=False)))
            for combo in itertools.product(*value_lists)
        ]

    def default_combination(self) -> Combination:
        """Get the combination using default values for all dimensions."""
        return Combination({
            d.name: d.get_default()
            for d in self.dimensions
        })

    def __repr__(self) -> str:
        dims = ", ".join(f"{d.name}({d.size})" for d in self.dimensions)
        return f"DimensionSpace([{dims}], total={self.total_combinations})"
