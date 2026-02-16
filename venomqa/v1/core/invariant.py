"""Invariant, Violation, and Severity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Callable
import uuid

if TYPE_CHECKING:
    from venomqa.v1.core.state import State
    from venomqa.v1.core.action import Action
    from venomqa.v1.core.transition import Transition
    from venomqa.v1.world import World


class Severity(Enum):
    """How serious a violation is."""

    CRITICAL = "critical"  # Data corruption, security breach
    HIGH = "high"  # Major feature broken
    MEDIUM = "medium"  # Partial functionality loss
    LOW = "low"  # Minor issues


@dataclass
class Invariant:
    """A rule that must always hold."""

    name: str
    check: Callable[["World"], bool]
    message: str = ""
    severity: Severity = Severity.MEDIUM

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Invariant):
            return NotImplemented
        return self.name == other.name


@dataclass
class Violation:
    """A failed invariant check."""

    id: str
    invariant_name: str
    state: "State"
    message: str
    severity: Severity
    action: "Action | None" = None
    reproduction_path: list["Transition"] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(
        cls,
        invariant: Invariant,
        state: "State",
        action: "Action | None" = None,
        reproduction_path: list["Transition"] | None = None,
    ) -> Violation:
        """Create a violation from an invariant and state."""
        return cls(
            id=f"v_{uuid.uuid4().hex[:12]}",
            invariant_name=invariant.name,
            state=state,
            message=invariant.message,
            severity=invariant.severity,
            action=action,
            reproduction_path=reproduction_path or [],
        )

    @property
    def is_critical(self) -> bool:
        return self.severity == Severity.CRITICAL
