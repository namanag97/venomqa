"""Core domain models for VenomQA."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from venomqa.core.context import ExecutionContext

if TYPE_CHECKING:
    from venomqa.client import Client


class Severity(Enum):
    """Issue severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


ActionCallable = Callable[["Client", ExecutionContext], Any]


@dataclass
class Step:
    """A single action in a journey with assertions."""

    name: str
    action: ActionCallable
    description: str = ""
    expect_failure: bool = False
    timeout: float | None = None
    retries: int = 0


@dataclass
class Checkpoint:
    """A savepoint for database state - enables rollback."""

    name: str


@dataclass
class Path:
    """A sequence of steps within a branch."""

    name: str
    steps: list[Step | Checkpoint]
    description: str = ""


@dataclass
class Branch:
    """Fork execution to explore multiple paths from a checkpoint."""

    checkpoint_name: str
    paths: list[Path]


@dataclass
class StepResult:
    """Result of executing a single step."""

    step_name: str
    success: bool
    started_at: datetime
    finished_at: datetime
    response: dict[str, Any] | None = None
    error: str | None = None
    request: dict[str, Any] | None = None
    duration_ms: float = 0.0


@dataclass
class PathResult:
    """Result of executing a path within a branch."""

    path_name: str
    success: bool
    step_results: list[StepResult] = field(default_factory=list)
    error: str | None = None


@dataclass
class BranchResult:
    """Result of executing all paths in a branch."""

    checkpoint_name: str
    path_results: list[PathResult] = field(default_factory=list)
    all_passed: bool = True

    def __post_init__(self) -> None:
        if self.path_results:
            self.all_passed = all(r.success for r in self.path_results)


@dataclass
class Issue:
    """Captured failure with full context."""

    journey: str
    path: str
    step: str
    error: str
    severity: Severity = Severity.HIGH
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    logs: list[str] = field(default_factory=list)
    suggestion: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        if not self.suggestion:
            self.suggestion = self._generate_suggestion()

    def _generate_suggestion(self) -> str:
        """Auto-generate fix suggestion based on error patterns."""
        error_lower = self.error.lower()
        suggestions: dict[str, str] = {
            "401": "Check authentication - token may be invalid or expired",
            "403": "Permission denied - check user roles and permissions",
            "404": "Endpoint not found - verify route registration and URL path",
            "422": "Validation error - check request body schema",
            "500": "Server error - check backend logs for exception traceback",
            "timeout": "Operation timed out - check if service is healthy",
            "connection refused": "Service not running - check Docker or network",
            "connection reset": "Connection closed - check service stability",
        }

        for pattern, suggestion in suggestions.items():
            if pattern in error_lower:
                return suggestion

        return "Review the error details and check system logs"


@dataclass
class JourneyResult:
    """Result of executing a complete journey."""

    journey_name: str
    success: bool
    started_at: datetime
    finished_at: datetime
    step_results: list[StepResult] = field(default_factory=list)
    branch_results: list[BranchResult] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def total_steps(self) -> int:
        return len(self.step_results)

    @property
    def passed_steps(self) -> int:
        return sum(1 for r in self.step_results if r.success)

    @property
    def total_paths(self) -> int:
        return sum(len(b.path_results) for b in self.branch_results)

    @property
    def passed_paths(self) -> int:
        return sum(1 for b in self.branch_results for p in b.path_results if p.success)


@dataclass
class Journey:
    """A complete user scenario from start to finish."""

    name: str
    steps: list[Step | Checkpoint | Branch]
    description: str = ""
    tags: list[str] = field(default_factory=list)
    timeout: float | None = None

    def __post_init__(self) -> None:
        self._validate_checkpoints()

    def _validate_checkpoints(self) -> None:
        """Ensure Branch checkpoint_names reference existing Checkpoints."""
        checkpoint_names = set()
        branch_refs = set()

        for step in self.steps:
            if isinstance(step, Checkpoint):
                checkpoint_names.add(step.name)
            elif isinstance(step, Branch):
                branch_refs.add(step.checkpoint_name)

        missing = branch_refs - checkpoint_names
        if missing:
            raise ValueError(
                f"Branch references undefined checkpoint(s): {missing}. "
                f"Available: {checkpoint_names}"
            )
