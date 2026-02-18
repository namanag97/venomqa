"""Transition - Records a state change."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from venomqa.v1.core.action import Action, ActionResult


@dataclass(frozen=True)
class Transition:
    """Records a state change: from_state -> action -> to_state.

    A Transition captures a single step in the exploration:
    - The state we started from
    - The action we took
    - The state we ended up in
    - The result of the action (HTTP response, etc.)

    Transitions are immutable (frozen) to ensure graph integrity.

    Attributes:
        id: Unique identifier for this transition.
        from_state_id: The state we started from.
        action_name: Name of the action that was executed.
        to_state_id: The state we ended up in.
        result: The ActionResult from executing the action.
        timestamp: When this transition occurred.
        duration_ms: How long the action took to execute (optional).
    """

    id: str
    from_state_id: str
    action_name: str
    to_state_id: str
    result: ActionResult
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: float | None = None  # NEW: Track action duration

    @classmethod
    def create(
        cls,
        from_state_id: str,
        action_name: str,
        to_state_id: str,
        result: ActionResult,
        duration_ms: float | None = None,
    ) -> Transition:
        """Create a new transition with auto-generated ID.

        Args:
            from_state_id: The starting state ID.
            action_name: Name of the action executed.
            to_state_id: The resulting state ID.
            result: The ActionResult from the action.
            duration_ms: Optional duration in milliseconds.

        Returns:
            A new Transition instance.
        """
        return cls(
            id=f"t_{uuid.uuid4().hex[:12]}",
            from_state_id=from_state_id,
            action_name=action_name,
            to_state_id=to_state_id,
            result=result,
            duration_ms=duration_ms,
        )

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Transition):
            return NotImplemented
        return self.id == other.id


__all__ = ["Transition"]
