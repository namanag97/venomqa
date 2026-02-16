"""Decorators for defining actions and invariants."""

from __future__ import annotations

from functools import wraps
from typing import Callable, TypeVar, Any

from venomqa.v1.core.action import Action, ActionResult, Precondition
from venomqa.v1.core.invariant import Invariant, Severity

F = TypeVar("F", bound=Callable[..., Any])


def action(
    name: str | None = None,
    description: str = "",
    tags: list[str] | None = None,
    preconditions: list[Precondition] | None = None,
) -> Callable[[Callable[..., ActionResult]], Action]:
    """Decorator to create an Action from a function.

    Example:
        @action(name="login", description="Log in a user", tags=["auth"])
        def login(api):
            return api.post("/login", json={"user": "test", "pass": "test"})
    """

    def decorator(func: Callable[..., ActionResult]) -> Action:
        action_name = name or func.__name__
        return Action(
            name=action_name,
            execute=func,
            preconditions=preconditions or [],
            description=description or func.__doc__ or "",
            tags=tags or [],
        )

    return decorator


def invariant(
    name: str | None = None,
    message: str = "",
    severity: Severity = Severity.MEDIUM,
) -> Callable[[Callable[..., bool]], Invariant]:
    """Decorator to create an Invariant from a function.

    Example:
        @invariant(
            name="order_count_matches",
            message="Database count must match API response",
            severity=Severity.CRITICAL,
        )
        def check_order_count(world):
            db_count = world.systems["db"].execute("SELECT COUNT(*) FROM orders")[0][0]
            api_count = len(world.api.get("/orders").response.json()["orders"])
            return db_count == api_count
    """

    def decorator(func: Callable[..., bool]) -> Invariant:
        inv_name = name or func.__name__
        return Invariant(
            name=inv_name,
            check=func,
            message=message or func.__doc__ or "",
            severity=severity,
        )

    return decorator
