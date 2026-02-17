"""Action and ActionResult dataclasses."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from venomqa.v1.core.context import Context
    from venomqa.v1.core.state import State


@dataclass
class HTTPRequest:
    """Represents an HTTP request."""

    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None

    def __str__(self) -> str:
        return f"{self.method} {self.url}"


@dataclass
class HTTPResponse:
    """Represents an HTTP response."""

    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 400

    def json(self) -> Any:
        """Return body as JSON (assumes body is already parsed)."""
        return self.body


@dataclass
class ActionResult:
    """Result of executing an action."""

    success: bool
    request: HTTPRequest
    response: HTTPResponse | None = None
    error: str | None = None
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_response(
        cls,
        request: HTTPRequest,
        response: HTTPResponse,
        duration_ms: float = 0.0,
    ) -> ActionResult:
        """Create a successful result from a response."""
        return cls(
            success=response.ok,
            request=request,
            response=response,
            duration_ms=duration_ms,
        )

    @classmethod
    def from_error(cls, request: HTTPRequest, error: str) -> ActionResult:
        """Create a failed result from an error."""
        return cls(
            success=False,
            request=request,
            error=error,
        )


# Type alias for action preconditions
Precondition = Callable[["State"], bool]


def precondition_has_context(*keys: str) -> Precondition:
    """Create a State-compatible precondition that requires context keys.

    Because preconditions receive a State (not a World), context checking requires
    a workaround: attach the required keys as metadata on the callable. The Agent
    can call this precondition with a dummy State and it will always return True;
    the REAL check is done in World.act() / Agent._step() when context is available.

    For now, use this as a documentation marker and pair it with @requires_context
    from the DSL decorators, which enforces the check at action invocation time.

    Example::

        create_repo_action = Action(
            name="create_repo",
            execute=create_repo,
            preconditions=[precondition_has_context("user_login")],
        )

    The precondition returns True always when checked against State (so the action
    is always eligible). The actual guard happens inside the action function via
    ``context.get_required("user_login")``.

    A future version will give preconditions access to the full World so they can
    check context directly.
    """
    def check(state: State) -> bool:  # noqa: ARG001
        # Always eligible from State perspective; real check is at invocation time.
        return True

    check.__name__ = f"has_context({', '.join(keys)})"
    check._required_context_keys = keys  # type: ignore[attr-defined]
    return check

# Import ResponseAssertion at runtime to avoid circular import
def _get_response_assertion_type():
    from venomqa.v1.core.invariant import ResponseAssertion
    return ResponseAssertion


@dataclass
class Action:
    """An action that changes the world state.

    Actions can optionally receive a Context for sharing data:

        # Simple action (no context)
        def get_items(api):
            return ActionResult.from_response(api.get("/items"))

        # Action with context
        def create_order(api, context):
            user_id = context.get("user_id")
            response = api.post("/orders", json={"user_id": user_id})
            context.set("order_id", response.json()["id"])
            return ActionResult.from_response(response)

    Response assertions:
        Action(
            name="create_user",
            execute=create_user,
            expected_status=[201],  # Shorthand for ResponseAssertion
        )

        Action(
            name="delete_nonexistent",
            execute=delete_user,
            expect_failure=True,  # Expect 4xx/5xx
        )

    The framework automatically detects whether your action accepts context.
    """

    name: str
    execute: Callable[..., ActionResult]
    preconditions: list[Precondition] = field(default_factory=list)
    description: str = ""
    tags: list[str] = field(default_factory=list)
    expected_status: list[int] | None = None
    expect_failure: bool = False
    response_assertion: Any = None  # ResponseAssertion, avoid circular import
    _accepts_context: bool | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Detect if execute function accepts context parameter."""
        if self._accepts_context is None:
            try:
                sig = inspect.signature(self.execute)
                params = list(sig.parameters.keys())
                # Check if function has 2+ params or has 'context' param
                self._accepts_context = len(params) >= 2 or "context" in params
            except (ValueError, TypeError):
                # Can't inspect (e.g., built-in), assume no context
                self._accepts_context = False

    def invoke(self, api: Any, context: Context) -> ActionResult:
        """Execute the action, passing context if accepted.

        This is the preferred way to call an action from the framework.
        It handles both context-aware and simple actions.
        """
        if self._accepts_context:
            return self.execute(api, context)
        else:
            return self.execute(api)

    def can_execute(self, state: State) -> bool:
        """Check if all preconditions are satisfied."""
        return all(p(state) for p in self.preconditions)

    def validate_result(self, result: ActionResult) -> tuple[bool, str]:
        """Validate the action result against assertions.

        Returns:
            (passed, message) tuple.
        """
        # Use explicit response_assertion if provided
        if self.response_assertion is not None:
            return self.response_assertion.validate(result)

        # Build assertion from shorthand properties
        if self.expected_status is not None or self.expect_failure:
            from venomqa.v1.core.invariant import ResponseAssertion
            assertion = ResponseAssertion(
                expected_status=self.expected_status,
                expect_failure=self.expect_failure,
            )
            return assertion.validate(result)

        # No assertions - always pass
        return True, ""

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Action):
            return NotImplemented
        return self.name == other.name
