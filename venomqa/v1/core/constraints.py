"""StateConstraint protocol and built-in constraints for hyperedge validation."""

from __future__ import annotations

from typing import Any, Protocol

from venomqa.v1.core.hyperedge import Hyperedge


class StateConstraint(Protocol):
    """Protocol for constraints on hyperedge combinations.

    A constraint checks whether a given Hyperedge represents a valid / possible
    state of the system.  Invalid combinations can be excluded from the
    unexplored combo set in ``DimensionNoveltyStrategy``.
    """

    @property
    def name(self) -> str:
        ...

    def is_valid(self, edge: Hyperedge) -> bool:
        """Return True if the hyperedge satisfies this constraint."""
        ...


# ---------------------------------------------------------------------------
# Built-in constraints
# ---------------------------------------------------------------------------

class AnonHasNoRole:
    """Anonymous users must not have a non-NONE role."""

    name = "anon_has_no_role"

    def is_valid(self, edge: Hyperedge) -> bool:
        from venomqa.v1.core.dimensions import AuthStatus, UserRole
        auth = edge.get("auth")
        role = edge.get("role")
        if auth == AuthStatus.ANON and role is not None and role != UserRole.NONE:
            return False
        return True


class AuthHasRole:
    """Authenticated users must have a non-NONE role."""

    name = "auth_has_role"

    def is_valid(self, edge: Hyperedge) -> bool:
        from venomqa.v1.core.dimensions import AuthStatus, UserRole
        auth = edge.get("auth")
        role = edge.get("role")
        if auth == AuthStatus.AUTH and role == UserRole.NONE:
            return False
        return True


class FreeCannotExceedUsage:
    """Free-plan users cannot have EXCEEDED usage."""

    name = "free_cannot_exceed_usage"

    def is_valid(self, edge: Hyperedge) -> bool:
        from venomqa.v1.core.dimensions import PlanType, UsageClass
        plan = edge.get("plan")
        usage = edge.get("usage")
        if plan == PlanType.FREE and usage == UsageClass.EXCEEDED:
            return False
        return True


class LambdaConstraint:
    """Ad-hoc constraint defined by a callable."""

    def __init__(self, name: str, check: Any) -> None:
        self._name = name
        self._check = check

    @property
    def name(self) -> str:
        return self._name

    def is_valid(self, edge: Hyperedge) -> bool:
        return bool(self._check(edge))


def constraint(name: str, check: Any) -> LambdaConstraint:
    """Shorthand factory for LambdaConstraint."""
    return LambdaConstraint(name=name, check=check)


# Default set of constraints applied if none are provided
DEFAULT_CONSTRAINTS: list[Any] = [
    AnonHasNoRole(),
    AuthHasRole(),
    FreeCannotExceedUsage(),
]
