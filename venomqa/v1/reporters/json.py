"""JSON reporter for machine-readable output."""

from __future__ import annotations

import json
from typing import Any

from venomqa.v1.core.result import ExplorationResult


class JSONReporter:
    """Formats ExplorationResult as JSON."""

    def __init__(self, indent: int | None = 2) -> None:
        self.indent = indent

    def report(self, result: ExplorationResult) -> str:
        """Generate JSON report."""
        data = self._to_dict(result)
        return json.dumps(data, indent=self.indent, default=str)

    def _to_dict(self, result: ExplorationResult) -> dict[str, Any]:
        return {
            "summary": {
                "states_visited": result.states_visited,
                "transitions_taken": result.transitions_taken,
                "actions_total": result.actions_total,
                "coverage_percent": round(result.coverage_percent, 2),
                "duration_ms": round(result.duration_ms, 2),
                "success": result.success,
            },
            "violations": [
                {
                    "id": v.id,
                    "invariant": v.invariant_name,
                    "message": v.message,
                    "severity": v.severity.value,
                    "state_id": v.state.id,
                    "action": v.action.name if v.action else None,
                    "reproduction_path": [
                        t.action_name for t in v.reproduction_path
                    ],
                    "timestamp": v.timestamp.isoformat(),
                }
                for v in result.violations
            ],
            "graph": {
                "states": [
                    {
                        "id": s.id,
                        "observations": {
                            name: obs.data
                            for name, obs in s.observations.items()
                        },
                    }
                    for s in result.graph.iter_states()
                ],
                "transitions": [
                    {
                        "id": t.id,
                        "from": t.from_state_id,
                        "to": t.to_state_id,
                        "action": t.action_name,
                        "success": t.result.success,
                        "duration_ms": t.result.duration_ms,
                    }
                    for t in result.graph.iter_transitions()
                ],
            },
            "started_at": result.started_at.isoformat(),
            "finished_at": result.finished_at.isoformat() if result.finished_at else None,
        }
