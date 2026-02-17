"""Constraints for filtering invalid dimension combinations.

Constraints define rules about which combinations are invalid and should
be excluded from test generation. This prevents testing impossible or
meaningless states.

Example:
    >>> from venomqa.combinatorial import Constraint, ConstraintSet, Combination
    >>>
    >>> # Anonymous users cannot access archived entities
    >>> c1 = Constraint(
    ...     name="anon_no_archive",
    ...     predicate=lambda d: not (d["auth"] == "anon" and d["status"] == "archived"),
    ...     description="Anonymous users cannot access archived entities"
    ... )
    >>>
    >>> # Admin is required when count is 'many'
    >>> c2 = Constraint(
    ...     name="many_needs_admin",
    ...     predicate=lambda d: not (d["count"] == "many" and d["auth"] == "anon"),
    ...     description="Many items requires at least user auth"
    ... )
    >>>
    >>> constraint_set = ConstraintSet([c1, c2])
    >>> combo = Combination({"auth": "anon", "status": "archived", "count": 0})
    >>> constraint_set.is_valid(combo)  # False (violates c1)
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Hashable
from dataclasses import dataclass, field
from typing import Any

from venomqa.combinatorial.dimensions import Combination

logger = logging.getLogger(__name__)

# Type alias for constraint predicates.
# A predicate receives a dict mapping dimension names to values and returns
# True if the combination is VALID (allowed).
ConstraintPredicate = Callable[[dict[str, Hashable]], bool]


@dataclass
class Constraint:
    """A rule that filters out invalid combinations.

    The predicate function receives a dictionary of dimension name to value
    and returns True if the combination is VALID (should be kept).

    Returning False means the combination is invalid and will be excluded.

    Attributes:
        name: Unique identifier for this constraint.
        predicate: Function returning True for valid combinations.
        description: Human-readable explanation of why this constraint exists.
        dimensions: Optional list of dimension names this constraint applies to.
            If provided, the constraint is only checked when all listed
            dimensions are present.

    Example:
        >>> constraint = Constraint(
        ...     name="no_anon_admin_ops",
        ...     predicate=lambda d: not (d["auth"] == "anon" and d["op"] == "admin_op"),
        ...     description="Anonymous users cannot perform admin operations",
        ...     dimensions=["auth", "op"],
        ... )
    """

    name: str
    predicate: ConstraintPredicate
    description: str = ""
    dimensions: list[str] | None = None

    def is_valid(self, combination: Combination | dict[str, Hashable]) -> bool:
        """Check if a combination satisfies this constraint.

        Args:
            combination: A Combination or dict of dimension values.

        Returns:
            True if the combination is valid (passes the constraint).
        """
        if isinstance(combination, Combination):
            values = combination.values
        else:
            values = combination

        # If specific dimensions are listed, only check when all are present
        if self.dimensions:
            if not all(d in values for d in self.dimensions):
                return True  # Not applicable, treat as valid

        try:
            return self.predicate(values)
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(
                f"Constraint '{self.name}' raised {type(e).__name__}: {e}. "
                f"Treating combination as invalid."
            )
            return False

    def __repr__(self) -> str:
        return f"Constraint({self.name!r})"


def exclude(
    name: str,
    description: str = "",
    dimensions: list[str] | None = None,
    **values: Any,
) -> Constraint:
    """Create a constraint that excludes a specific value combination.

    Convenience function for the common case of "these dimension values
    together are invalid."

    Args:
        name: Constraint name.
        description: Why this combination is invalid.
        dimensions: Optional dimension scope.
        **values: Dimension name=value pairs to exclude.

    Returns:
        A Constraint that rejects combinations matching all given values.

    Example:
        >>> c = exclude("no_anon_archive", auth="anon", status="archived")
        >>> c.is_valid({"auth": "anon", "status": "archived"})  # False
        >>> c.is_valid({"auth": "user", "status": "archived"})  # True
    """
    excluded_pairs = dict(values)

    def predicate(d: dict[str, Hashable]) -> bool:
        return not all(
            d.get(k) == v for k, v in excluded_pairs.items()
        )

    return Constraint(
        name=name,
        predicate=predicate,
        description=description or f"Exclude combination: {excluded_pairs}",
        dimensions=dimensions or list(excluded_pairs.keys()),
    )


def require(
    name: str,
    if_condition: dict[str, Hashable],
    then_condition: dict[str, Hashable],
    description: str = "",
) -> Constraint:
    """Create an implication constraint: if X then Y must hold.

    Args:
        name: Constraint name.
        if_condition: The antecedent (trigger) condition.
        then_condition: The consequent (required) condition.
        description: Why this implication exists.

    Returns:
        A Constraint encoding "if all if_condition match, then at least
        one then_condition must also match."

    Example:
        >>> # If auth is 'admin', then permission_level must be 'full'
        >>> c = require(
        ...     "admin_full_perms",
        ...     if_condition={"auth": "admin"},
        ...     then_condition={"permission_level": "full"},
        ... )
    """
    all_dims = list(set(list(if_condition.keys()) + list(then_condition.keys())))

    def predicate(d: dict[str, Hashable]) -> bool:
        # Check if the 'if' condition matches
        if_matches = all(d.get(k) == v for k, v in if_condition.items())
        if not if_matches:
            return True  # Antecedent not met, constraint is vacuously true

        # If the antecedent matches, the consequent must also match
        return all(d.get(k) == v for k, v in then_condition.items())

    return Constraint(
        name=name,
        predicate=predicate,
        description=description or f"If {if_condition} then {then_condition}",
        dimensions=all_dims,
    )


def at_most_one(
    name: str,
    conditions: list[dict[str, Hashable]],
    description: str = "",
) -> Constraint:
    """Create a constraint that at most one of the conditions can be true.

    Args:
        name: Constraint name.
        conditions: List of condition dicts. At most one can match.
        description: Why this mutual exclusion exists.

    Returns:
        A Constraint enforcing mutual exclusion.

    Example:
        >>> # Cannot be both premium and trial
        >>> c = at_most_one(
        ...     "exclusive_tier",
        ...     conditions=[
        ...         {"tier": "premium"},
        ...         {"tier": "trial"},
        ...     ]
        ... )
    """
    all_dims: set[str] = set()
    for cond in conditions:
        all_dims.update(cond.keys())

    def predicate(d: dict[str, Hashable]) -> bool:
        matching = sum(
            1 for cond in conditions
            if all(d.get(k) == v for k, v in cond.items())
        )
        return matching <= 1

    return Constraint(
        name=name,
        predicate=predicate,
        description=description or f"At most one of {conditions}",
        dimensions=list(all_dims),
    )


@dataclass
class ConstraintSet:
    """A collection of constraints applied together.

    The ConstraintSet validates combinations against all contained
    constraints. A combination is valid only if ALL constraints pass.

    Attributes:
        constraints: List of Constraint objects.

    Example:
        >>> cs = ConstraintSet([
        ...     exclude("no_anon_archive", auth="anon", status="archived"),
        ...     require("admin_perms", {"auth": "admin"}, {"perms": "full"}),
        ... ])
        >>> cs.is_valid(Combination({"auth": "anon", "status": "archived"}))
        False
    """

    constraints: list[Constraint] = field(default_factory=list)

    def add(self, constraint: Constraint) -> None:
        """Add a constraint to the set."""
        self.constraints.append(constraint)

    def is_valid(self, combination: Combination | dict[str, Hashable]) -> bool:
        """Check if a combination passes all constraints.

        Args:
            combination: A Combination or dict of dimension values.

        Returns:
            True if all constraints are satisfied.
        """
        return all(c.is_valid(combination) for c in self.constraints)

    def violated_by(
        self, combination: Combination | dict[str, Hashable]
    ) -> list[Constraint]:
        """Get list of constraints violated by a combination.

        Args:
            combination: A Combination or dict of dimension values.

        Returns:
            List of Constraint objects that are violated.
        """
        return [c for c in self.constraints if not c.is_valid(combination)]

    def filter(self, combinations: list[Combination]) -> list[Combination]:
        """Filter a list of combinations, keeping only valid ones.

        Args:
            combinations: List of combinations to filter.

        Returns:
            List of combinations that satisfy all constraints.
        """
        return [c for c in combinations if self.is_valid(c)]

    def __len__(self) -> int:
        return len(self.constraints)

    def __repr__(self) -> str:
        return f"ConstraintSet({len(self.constraints)} constraints)"
