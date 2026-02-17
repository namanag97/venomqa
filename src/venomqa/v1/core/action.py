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

    # ── Convenience proxies — so actions can treat ActionResult like a response ──

    @property
    def status_code(self) -> int:
        """HTTP status code of the response (proxy for result.response.status_code).

        Returns 0 if the request failed (timeout, connection refused, etc.).
        This allows safe checks like `if resp.status_code == 500:` without crashing.
        """
        if self.response is None:
            return 0  # Network error, timeout, etc.
        return self.response.status_code

    @property
    def headers(self) -> dict[str, str]:
        """Response headers (proxy for result.response.headers).

        Returns empty dict if the request failed. Useful for checking content-type.
        """
        if self.response is None:
            return {}
        return self.response.headers

    @property
    def ok(self) -> bool:
        """True if response status is 2xx/3xx (proxy for result.response.ok)."""
        if self.response is None:
            return False
        return self.response.ok

    def json(self) -> Any:
        """Return response body as parsed JSON (proxy for result.response.json()).

        Allows actions to be used naturally: resp = api.get("/x"); resp.json()
        """
        if self.response is None:
            raise AttributeError("ActionResult has no response (request errored)")
        return self.response.json()

    @property
    def text(self) -> str:
        """Response body as string (proxy for str(result.response.body))."""
        if self.response is None:
            return ""
        body = self.response.body
        return body if isinstance(body, str) else str(body) if body is not None else ""

    # ── Validation helpers — make it easy to write correct actions ──

    def expect_status(self, *expected: int) -> ActionResult:
        """Assert the response has one of the expected status codes.

        Raises AssertionError if status doesn't match. Returns self for chaining.

        Example::

            def create_item(api, context):
                resp = api.post("/items", json={"name": "widget"})
                resp.expect_status(201)  # raises if not 201
                context.set("item_id", resp.json()["id"])
                return resp
        """
        if self.response is None:
            raise AssertionError(f"Request failed (no response): {self.error}")
        if self.response.status_code not in expected:
            expected_str = ", ".join(str(s) for s in expected)
            raise AssertionError(
                f"Expected status [{expected_str}], got {self.response.status_code}: {self.text}"
            )
        return self

    def expect_success(self) -> ActionResult:
        """Assert the response is successful (2xx/3xx).

        Raises AssertionError if not successful. Returns self for chaining.

        Example::

            def get_items(api, context):
                resp = api.get("/items")
                resp.expect_success()  # raises if not 2xx/3xx
                return resp
        """
        if not self.ok:
            raise AssertionError(
                f"Request failed: {self.status_code if self.response else 'no response'} - {self.text}"
            )
        return self

    def expect_json(self) -> Any:
        """Assert the response is valid JSON and return the parsed body.

        Raises AssertionError if response is not JSON. Returns parsed body.

        Example::

            def list_items(api, context):
                resp = api.get("/items")
                resp.expect_status(200)
                items = resp.expect_json()  # raises if not JSON
                context.set("items", items)
                return resp
        """
        if self.response is None:
            raise AssertionError(f"Request failed (no response): {self.error}")
        body = self.response.body
        if not isinstance(body, (dict, list)):
            raise AssertionError(f"Expected JSON response, got: {type(body).__name__}")
        return body

    def expect_json_field(self, *fields: str) -> dict[str, Any]:
        """Assert the response JSON has required fields and return it.

        Raises AssertionError if any field is missing. Returns the JSON body.

        Example::

            def create_item(api, context):
                resp = api.post("/items", json={"name": "widget"})
                resp.expect_status(201)
                data = resp.expect_json_field("id", "name")  # raises if missing
                context.set("item_id", data["id"])
                return resp
        """
        data = self.expect_json()
        if not isinstance(data, dict):
            raise AssertionError(f"Expected JSON object, got {type(data).__name__}: {data}")
        missing = [f for f in fields if f not in data]
        if missing:
            raise AssertionError(f"Response missing fields {missing}: {data}")
        return data

    def expect_json_list(self) -> list[Any]:
        """Assert the response is a JSON array and return it.

        Raises AssertionError if response is not a list. Returns the list.

        Example::

            def list_items(api, context):
                resp = api.get("/items")
                resp.expect_status(200)
                items = resp.expect_json_list()  # raises if not array
                context.set("items", items)
                return resp
        """
        data = self.expect_json()
        if not isinstance(data, list):
            raise AssertionError(f"Expected JSON array, got {type(data).__name__}: {data}")
        return data


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

def precondition_action_ran(*action_names: str) -> Precondition:
    """Create a precondition that gates an action on previous actions having run.

    The Agent checks whether all named actions have been executed at least once
    in the current exploration path (i.e., their names appear in the explored
    transition history from the current state). Actions that have never fired
    do not satisfy this precondition, so the gated action will be skipped until
    the prerequisite actions have run.

    Attach the required action names as ``_required_actions`` metadata on the
    callable; the Agent reads this attribute when filtering valid actions.

    Example::

        get_connection = Action(
            name="get_connection",
            execute=get_connection_fn,
            preconditions=[precondition_action_ran("create_connection")],
        )

    With this precondition, ``get_connection`` will only be attempted after
    ``create_connection`` has been executed at least once in the current path.
    """
    def check(state: State) -> bool:  # noqa: ARG001
        # Always eligible from State perspective; real check uses _required_actions.
        return True

    check.__name__ = f"action_ran({', '.join(action_names)})"
    check._required_actions = action_names  # type: ignore[attr-defined]
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

    Preconditions (guards) - three ways to specify:

        # Single callable (shorthand)
        Action(
            name="delete_repo",
            execute=delete_repo,
            precondition=lambda ctx: ctx.get("repo_id") is not None,
        )

        # Multiple preconditions
        Action(
            name="merge_pr",
            execute=merge_pr,
            preconditions=[
                lambda ctx: ctx.get("pr_id") is not None,
                lambda ctx: ctx.get("repo_id") is not None,
            ],
        )

        # String shorthand (requires another action to have run first)
        Action(
            name="get_connection",
            execute=get_connection,
            preconditions=["create_connection"],  # action name
        )

    The framework automatically detects whether your action accepts context.
    """

    name: str
    execute: Callable[..., ActionResult]
    precondition: Callable[[Any], bool] | None = None  # Single precondition (shorthand)
    preconditions: list[Precondition] = field(default_factory=list)
    description: str = ""
    tags: list[str] = field(default_factory=list)
    expected_status: list[int] | None = None
    expect_failure: bool = False
    response_assertion: Any = None  # ResponseAssertion, avoid circular import
    max_calls: int | None = None  # Max times this action can be called (prevents data explosion)
    _accepts_context: bool | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Detect context parameter and resolve precondition shorthands."""
        # Handle single precondition= shorthand: merge into preconditions list
        if self.precondition is not None:
            self.preconditions = [self.precondition] + list(self.preconditions)
            self.precondition = None  # Clear to avoid confusion

        # Resolve string shorthand: preconditions=["create_connection"] becomes
        # preconditions=[precondition_action_ran("create_connection")]
        # This matches the natural LLM/user intuition for action dependencies.
        resolved: list[Precondition] = []
        for p in self.preconditions:
            if isinstance(p, str):
                resolved.append(precondition_action_ran(p))
            elif callable(p):
                # Wrap context-based lambdas into State-compatible preconditions
                # Check if the callable accepts 'context' or 'ctx' (not State)
                try:
                    sig = inspect.signature(p)
                    params = list(sig.parameters.keys())
                    # If single param and it looks like context, wrap it
                    if len(params) == 1 and params[0] in ("context", "ctx", "c"):
                        # This is a context-based precondition lambda
                        original = p
                        def wrap(state: State, fn: Callable = original) -> bool:  # noqa: ARG001
                            return True  # Actual check in can_execute_with_context
                        wrap._context_precondition = original  # type: ignore[attr-defined]
                        resolved.append(wrap)
                        continue
                except (ValueError, TypeError):
                    pass
                resolved.append(p)
            else:
                resolved.append(p)
        self.preconditions = resolved

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
            result = self.execute(api, context)
        else:
            result = self.execute(api)

        if result is None:
            raise TypeError(
                f"Action '{self.name}' returned None. "
                "Actions must return an ActionResult. "
                "Did you forget 'return resp'?"
            )
        return result

    def can_execute(self, state: State) -> bool:
        """Check if all preconditions are satisfied (without context)."""
        return all(p(state) for p in self.preconditions)

    def can_execute_with_context(
        self,
        state: State,
        context: Context,
        executed_actions: set[str] | None = None,
    ) -> bool:
        """Check preconditions including context-aware and action-dependency ones.

        For preconditions created with precondition_has_context(), the
        _required_context_keys attribute is checked against the live Context.

        For preconditions created with precondition_action_ran(), the
        _required_actions attribute is checked against executed_actions
        (the set of action names that have fired at least once in this exploration).

        For all other preconditions, state-based evaluation is used.
        """
        for p in self.preconditions:
            required_keys = getattr(p, "_required_context_keys", None)
            if required_keys is not None:
                if not all(context.get(k) is not None for k in required_keys):
                    return False
                continue

            required_actions = getattr(p, "_required_actions", None)
            if required_actions is not None:
                ran = executed_actions or set()
                if not all(a in ran for a in required_actions):
                    return False
                continue

            if not p(state):
                return False
        return True

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
