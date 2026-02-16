"""Transition dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import uuid

from venomqa.v1.core.action import ActionResult


@dataclass(frozen=True)
class Transition:
    """Records a state change: from_state -> action -> to_state."""

    id: str
    from_state_id: str
    action_name: str
    to_state_id: str
    result: ActionResult
    timestamp: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(
        cls,
        from_state_id: str,
        action_name: str,
        to_state_id: str,
        result: ActionResult,
    ) -> Transition:
        """Create a new transition with auto-generated ID."""
        return cls(
            id=f"t_{uuid.uuid4().hex[:12]}",
            from_state_id=from_state_id,
            action_name=action_name,
            to_state_id=to_state_id,
            result=result,
        )

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Transition):
            return NotImplemented
        return self.id == other.id
