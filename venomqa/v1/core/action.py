"""Action and ActionResult dataclasses."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from venomqa.v1.core.state import State
    from venomqa.v1.core.context import Context


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


@dataclass
class Action:
    """An action that changes the world state."""

    name: str
    execute: Callable[..., ActionResult]
    preconditions: list[Precondition] = field(default_factory=list)
    description: str = ""
    tags: list[str] = field(default_factory=list)

    def can_execute(self, state: "State") -> bool:
        """Check if all preconditions are satisfied."""
        return all(p(state) for p in self.preconditions)

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Action):
            return NotImplemented
        return self.name == other.name
