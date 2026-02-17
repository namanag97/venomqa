"""ExplorationResult dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from venomqa.v1.core.graph import Graph
from venomqa.v1.core.invariant import Violation, Severity

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
    dimension_coverage: "DimensionCoverage | None" = None

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
        """Percentage of reachable (state, action) pairs explored."""
        total_possible = self.states_visited * self.actions_total
        if total_possible == 0:
            return 100.0
        return (self.explored_count / total_possible) * 100

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
            "coverage_percent": round(self.coverage_percent, 2),
            "violations": len(self.violations),
            "critical": len(self.critical_violations),
            "success": self.success,
            "duration_ms": round(self.duration_ms, 2),
        }
