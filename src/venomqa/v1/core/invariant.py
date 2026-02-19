"""Invariant, Violation, and Severity."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from venomqa.v1.core.action import Action, ActionResult
    from venomqa.v1.core.state import State
    from venomqa.v1.core.transition import Transition
    from venomqa.v1.world import World


class Severity(Enum):
    """How serious a violation is."""

    CRITICAL = "critical"  # Data corruption, security breach
    HIGH = "high"  # Major feature broken
    MEDIUM = "medium"  # Partial functionality loss
    LOW = "low"  # Minor issues


class InvariantTiming(Enum):
    """When to check an invariant."""

    POST_ACTION = "post_action"  # After action executes (default)
    PRE_ACTION = "pre_action"  # Before action executes
    BOTH = "both"  # Before and after


@dataclass
class Invariant:
    """A rule that must always hold.

    Invariants can be checked at different times:
    - POST_ACTION (default): After each action
    - PRE_ACTION: Before each action
    - BOTH: Before and after each action

    Example:
        # Post-action invariant (default)
        Invariant(
            name="order_count_consistent",
            check=lambda world: db_count == api_count,
        )

        # Pre-action invariant
        Invariant(
            name="must_be_logged_in",
            check=lambda world: world.context.has("user_id"),
            timing=InvariantTiming.PRE_ACTION,
        )
    """

    name: str
    check: Callable[[World], bool | str]
    severity: Severity = Severity.MEDIUM
    message: str = ""
    timing: InvariantTiming = InvariantTiming.POST_ACTION

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Invariant):
            return NotImplemented
        return self.name == other.name


@dataclass
class ResponseAssertion:
    """An assertion about the action's response.

    Use this to specify expected responses for actions.

    Example:
        # Expect success
        ResponseAssertion(expected_status=[200, 201])

        # Expect failure
        ResponseAssertion(expected_status=[400, 404], expect_failure=True)

        # Custom check
        ResponseAssertion(
            check=lambda result: result.response.body.get("id") is not None
        )
    """

    expected_status: list[int] | None = None
    expect_failure: bool = False  # If True, action should fail (4xx/5xx)
    check: Callable[[ActionResult], bool] | None = None
    message: str = ""

    def validate(self, result: ActionResult) -> tuple[bool, str]:
        """Validate the action result against assertions.

        Returns:
            (passed, message) tuple.
        """
        status_explicitly_allowed = False
        if self.expected_status is not None:
            if result.response is None:
                return False, f"No response received, expected status {self.expected_status}"
            if result.response.status_code not in self.expected_status:
                return False, (
                    f"Expected status {self.expected_status}, "
                    f"got {result.response.status_code}"
                )
            # The status code is explicitly allowed — do not apply the
            # success/failure check below. `expected_status=[404]` alone
            # should make a 404 response pass without requiring expect_failure=True.
            status_explicitly_allowed = True

        if not status_explicitly_allowed:
            if self.expect_failure:
                if result.response and result.response.ok:
                    return False, f"Expected failure, but got success: {result.response.status_code}"
            else:
                if result.response and not result.response.ok:
                    return False, f"Expected success, got {result.response.status_code}"

        if self.check is not None:
            try:
                if not self.check(result):
                    return False, self.message or "Custom assertion failed"
            except Exception as e:
                return False, f"Assertion check raised exception: {e}"

        return True, ""


@dataclass
class Bug:
    """Structured bug description with expected vs actual behavior.

    A Bug captures the semantic meaning of a failure, making it clear
    what was expected and what actually happened. This is used by
    Violation to provide structured bug information alongside the
    free-text message.

    Example::

        bug = Bug(
            expected="Refund amount should never exceed charge amount",
            actual="Refunded $150 on a $100 charge",
            category="over-refund",
        )
        violation = Violation.create(invariant, state, bug=bug)

    Attributes:
        expected: What the system should have done.
        actual: What the system actually did.
        category: Optional category for grouping similar bugs
            (e.g., "data-leak", "over-refund", "auth-bypass").
    """

    expected: str
    actual: str
    category: str = ""

    @property
    def description(self) -> str:
        """Human-readable one-line description."""
        return f"Expected: {self.expected} | Actual: {self.actual}"

    def __str__(self) -> str:
        return self.description


@dataclass
class Violation:
    """A failed invariant check.

    Violations record both a free-text message and optional structured
    Bug data with expected/actual fields for programmatic analysis.

    Attributes:
        id: Unique identifier for this violation.
        invariant_name: Name of the invariant that was violated.
        state: The state in which the violation occurred.
        message: Free-text description of the violation.
        severity: How serious this violation is.
        action: The action that caused the violation (if any).
        action_result: The result of the action (if any).
        reproduction_path: Sequence of transitions to reproduce.
        timestamp: When the violation was detected.
        bug: Structured bug info with expected/actual fields.
    """

    id: str
    invariant_name: str
    state: State
    message: str
    severity: Severity
    action: Action | None = None
    action_result: ActionResult | None = None
    reproduction_path: list[Transition] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    bug: Bug | None = None

    @classmethod
    def create(
        cls,
        invariant: Invariant,
        state: State,
        action: Action | None = None,
        reproduction_path: list[Transition] | None = None,
        action_result: ActionResult | None = None,
        message_override: str = "",
        bug: Bug | None = None,
    ) -> Violation:
        """Create a violation from an invariant and state.

        Args:
            invariant: The invariant that was violated.
            state: The state in which the violation occurred.
            action: The action that triggered the violation.
            reproduction_path: Sequence of transitions to reproduce.
            action_result: The result of the triggering action.
            message_override: Override the invariant's default message.
            bug: Optional structured bug with expected/actual fields.

        Returns:
            A new Violation instance.
        """
        message = message_override or invariant.message
        # If bug is provided but no message, derive message from bug
        if bug and not message:
            message = bug.description
        return cls(
            id=f"v_{uuid.uuid4().hex[:12]}",
            invariant_name=invariant.name,
            state=state,
            message=message,
            severity=invariant.severity,
            action=action,
            action_result=action_result,
            reproduction_path=reproduction_path or [],
            bug=bug,
        )

    @property
    def expected(self) -> str | None:
        """What was expected (from the bug, if set)."""
        return self.bug.expected if self.bug else None

    @property
    def actual(self) -> str | None:
        """What actually happened (from the bug, if set)."""
        return self.bug.actual if self.bug else None

    @property
    def is_critical(self) -> bool:
        return self.severity == Severity.CRITICAL

    @property
    def reproduction_steps(self) -> list[str]:
        """Human-readable reproduction steps as a list of strings.

        Each entry describes one HTTP request in the sequence that reproduces
        the bug, e.g. ``'POST /todos {"title": "test"}'``.
        """
        import json as _json

        steps = []
        for transition in self.reproduction_path:
            result = transition.result
            if result and result.request:
                req = result.request
                body_str = ""
                if req.body:
                    try:
                        body_str = " " + _json.dumps(req.body, default=str)
                    except Exception:
                        body_str = f" {req.body}"
                url = req.url
                if "://" in url:
                    parts = url.split("://", 1)
                    after_scheme = parts[1]
                    slash_idx = after_scheme.find("/")
                    url = after_scheme[slash_idx:] if slash_idx != -1 else "/"
                steps.append(f"{req.method} {url}{body_str}")
            else:
                steps.append(f"[{transition.action_name}]")
        return steps
