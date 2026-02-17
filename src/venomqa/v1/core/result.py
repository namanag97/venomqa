"""ExplorationResult dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from venomqa.v1.core.graph import Graph
from venomqa.v1.core.invariant import Severity, Violation

if TYPE_CHECKING:
    from venomqa.v1.core.coverage import DimensionCoverage


@dataclass
class ExplorationResult:
    """The complete output of an exploration run."""

    graph: Graph
    violations: list[Violation] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    duration_ms: float = 0.0
    truncated_by_max_steps: bool = False
    dimension_coverage: DimensionCoverage | None = None

    @property
    def states_visited(self) -> int:
        """Number of unique states visited."""
        return self.graph.state_count

    @property
    def transitions_taken(self) -> int:
        """Number of transitions taken."""
        return self.graph.transition_count

    @property
    def actions_total(self) -> int:
        """Total number of available actions."""
        return self.graph.action_count

    @property
    def explored_count(self) -> int:
        """Number of (state, action) pairs explored."""
        return self.graph.explored_count

    @property
    def coverage_percent(self) -> float:
        """Percentage of reachable (state, action) pairs explored.

        Note: This metric can never reach 100% in growing state spaces because
        each new state adds N new (state, action) pairs to explore. Use
        action_coverage_percent for a more meaningful metric.
        """
        total_possible = self.states_visited * self.actions_total
        if total_possible == 0:
            return 100.0
        return (self.explored_count / total_possible) * 100

    @property
    def action_coverage_percent(self) -> float:
        """Percentage of actions that have been executed at least once.

        This is a more meaningful metric than coverage_percent because it
        answers: "Have we tried every action at least once?"
        """
        if self.actions_total == 0:
            return 100.0
        used_actions = self.graph.used_action_count
        return (used_actions / self.actions_total) * 100

    @property
    def exploration_efficiency(self) -> float:
        """Ratio of unique states discovered per transition.

        Higher is better. A value of 1.0 means every transition discovered
        a new state (no repeated states). Lower values indicate more
        backtracking/rollback (which is normal for BFS).
        """
        if self.transitions_taken == 0:
            return 1.0
        return self.states_visited / self.transitions_taken

    @property
    def unique_violations(self) -> list[Violation]:
        """Deduplicated violations — one per (invariant_name, action) pair.

        When the same underlying bug is triggered via many different paths (the
        most common case in DFS/BFS runs), this returns only the violation with
        the *shortest* reproduction path for each root cause.

        The full list is still available via ``result.violations``.

        Example: 49 violations for the same 409 conflict bug → 1 unique violation
        with the minimal 1-step path instead of a 15-step path.
        """
        seen: dict[tuple[str, str | None], Violation] = {}
        for v in self.violations:
            key = (v.invariant_name, v.action.name if v.action else None)
            existing = seen.get(key)
            if existing is None or len(v.reproduction_path) < len(existing.reproduction_path):
                seen[key] = v
        result = list(seen.values())
        _order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        result.sort(key=lambda v: (_order.get(v.severity.value, 9), v.invariant_name))
        return result

    @property
    def success(self) -> bool:
        """True if no violations were found."""
        return len(self.violations) == 0

    @property
    def critical_violations(self) -> list[Violation]:
        """List of critical severity violations."""
        return [v for v in self.violations if v.severity == Severity.CRITICAL]

    @property
    def high_violations(self) -> list[Violation]:
        """List of high severity violations."""
        return [v for v in self.violations if v.severity == Severity.HIGH]

    def finish(self) -> None:
        """Mark exploration as finished."""
        self.finished_at = datetime.now()
        self.duration_ms = (self.finished_at - self.started_at).total_seconds() * 1000

    def add_violation(self, violation: Violation) -> None:
        """Add a violation to the result."""
        self.violations.append(violation)

    def summary(self) -> dict[str, int | float | bool]:
        """Get a summary of the exploration."""
        return {
            "states_visited": self.states_visited,
            "transitions_taken": self.transitions_taken,
            "actions_total": self.actions_total,
            "actions_used": self.graph.used_action_count,
            "action_coverage_percent": round(self.action_coverage_percent, 2),
            "coverage_percent": round(self.action_coverage_percent, 2),  # alias for reporters
            "transition_coverage_percent": round(self.coverage_percent, 2),
            "truncated_by_max_steps": self.truncated_by_max_steps,
            "violations": len(self.violations),
            "unique_violations": len(self.unique_violations),
            "critical": len(self.critical_violations),
            "success": self.success,
            "duration_ms": round(self.duration_ms, 2),
        }
