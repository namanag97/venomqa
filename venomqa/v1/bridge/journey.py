"""Bridge: old Journey to new Journey converter."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from venomqa.v1.dsl.journey import Journey, Step, Checkpoint, Branch, Path
from venomqa.v1.core.invariant import Invariant, Severity


@runtime_checkable
class LegacyJourney(Protocol):
    """Protocol for the old Journey interface."""

    name: str
    steps: list[Any]

    def get_actions(self) -> list[Any]:
        ...

    def get_invariants(self) -> list[Any]:
        ...


@runtime_checkable
class LegacyStep(Protocol):
    """Protocol for the old Step interface."""

    name: str
    action: Any
    description: str


@runtime_checkable
class LegacyCheckpoint(Protocol):
    """Protocol for the old Checkpoint interface."""

    name: str


@runtime_checkable
class LegacyInvariant(Protocol):
    """Protocol for the old Invariant interface."""

    name: str
    check: Any
    message: str
    severity: str


def adapt_journey(legacy: LegacyJourney) -> Journey:
    """Convert a legacy Journey to the new Journey DSL.

    Args:
        legacy: The old Journey instance.

    Returns:
        A new Journey with converted steps and invariants.

    Example:
        from venomqa.v1.bridge import adapt_journey

        old_journey = OldJourney(...)
        new_journey = adapt_journey(old_journey)
        result = explore("http://localhost:8000", new_journey)
    """
    new_steps: list[Step | Checkpoint | Branch] = []

    for old_step in legacy.steps:
        if hasattr(old_step, "action"):
            # It's a step
            new_steps.append(Step(
                name=old_step.name,
                action=old_step.action,
                description=getattr(old_step, "description", ""),
            ))
        elif hasattr(old_step, "name") and not hasattr(old_step, "action"):
            # It's a checkpoint
            new_steps.append(Checkpoint(name=old_step.name))

    # Convert invariants
    new_invariants: list[Invariant] = []
    if hasattr(legacy, "get_invariants"):
        for old_inv in legacy.get_invariants():
            severity = _convert_severity(getattr(old_inv, "severity", "medium"))
            new_invariants.append(Invariant(
                name=old_inv.name,
                check=old_inv.check,
                message=getattr(old_inv, "message", ""),
                severity=severity,
            ))

    return Journey(
        name=legacy.name,
        steps=new_steps,
        invariants=new_invariants,
    )


def _convert_severity(severity_str: str) -> Severity:
    """Convert string severity to Severity enum."""
    mapping = {
        "critical": Severity.CRITICAL,
        "high": Severity.HIGH,
        "medium": Severity.MEDIUM,
        "low": Severity.LOW,
    }
    return mapping.get(severity_str.lower(), Severity.MEDIUM)
