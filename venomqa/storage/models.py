"""Database models for VenomQA result persistence.

This module defines the database schema using dataclasses that can be used
with SQLite or other SQL databases. The schema supports storing complete
journey execution results including steps, invariant checks, and issues.

Schema:
    journey_runs: Main table for journey execution records
    step_results: Individual step results linked to journey runs
    invariant_checks: Invariant validation results
    issues: Captured issues with full context
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class RunStatus(Enum):
    """Status of a journey run."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class JourneyRunRecord:
    """Record of a journey execution.

    Attributes:
        id: Unique identifier for this run.
        journey_name: Name of the journey that was executed.
        started_at: Timestamp when the journey started.
        finished_at: Timestamp when the journey completed.
        status: Overall status of the run (passed/failed/error).
        duration_ms: Total execution duration in milliseconds.
        total_steps: Total number of steps executed.
        passed_steps: Number of steps that passed.
        failed_steps: Number of steps that failed.
        total_paths: Total number of branch paths executed.
        passed_paths: Number of paths that passed.
        failed_paths: Number of paths that failed.
        tags: JSON-encoded list of journey tags.
        metadata: JSON-encoded additional metadata.
        created_at: Timestamp when this record was created.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    journey_name: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: RunStatus = RunStatus.PENDING
    duration_ms: float = 0.0
    total_steps: int = 0
    passed_steps: int = 0
    failed_steps: int = 0
    total_paths: int = 0
    passed_paths: int = 0
    failed_paths: int = 0
    tags: str = "[]"
    metadata: str = "{}"
    created_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_journey_result(
        cls,
        result: Any,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> JourneyRunRecord:
        """Create a JourneyRunRecord from a JourneyResult.

        Args:
            result: JourneyResult instance from journey execution.
            tags: Optional list of tags for categorization.
            metadata: Optional additional metadata.

        Returns:
            JourneyRunRecord populated from the result.
        """
        status = RunStatus.PASSED if result.success else RunStatus.FAILED

        return cls(
            journey_name=result.journey_name,
            started_at=result.started_at,
            finished_at=result.finished_at,
            status=status,
            duration_ms=result.duration_ms,
            total_steps=result.total_steps,
            passed_steps=result.passed_steps,
            failed_steps=result.failed_steps,
            total_paths=result.total_paths,
            passed_paths=result.passed_paths,
            failed_paths=result.failed_paths,
            tags=json.dumps(tags or []),
            metadata=json.dumps(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert record to dictionary."""
        return {
            "id": self.id,
            "journey_name": self.journey_name,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "total_steps": self.total_steps,
            "passed_steps": self.passed_steps,
            "failed_steps": self.failed_steps,
            "total_paths": self.total_paths,
            "passed_paths": self.passed_paths,
            "failed_paths": self.failed_paths,
            "tags": json.loads(self.tags),
            "metadata": json.loads(self.metadata),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class StepResultRecord:
    """Record of a step execution result.

    Attributes:
        id: Unique identifier for this step result.
        journey_run_id: Foreign key to the parent journey run.
        step_name: Name of the step that was executed.
        path_name: Name of the path (for branch steps, 'main' otherwise).
        status: Status of the step (passed/failed).
        duration_ms: Step execution duration in milliseconds.
        request: JSON-encoded request data.
        response: JSON-encoded response data.
        error: Error message if step failed.
        started_at: Timestamp when step started.
        finished_at: Timestamp when step completed.
        step_order: Order of this step in the execution sequence.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    journey_run_id: str = ""
    step_name: str = ""
    path_name: str = "main"
    status: str = "pending"
    duration_ms: float = 0.0
    request: str = "{}"
    response: str = "{}"
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    step_order: int = 0

    @classmethod
    def from_step_result(
        cls,
        result: Any,
        journey_run_id: str,
        path_name: str = "main",
        step_order: int = 0,
    ) -> StepResultRecord:
        """Create a StepResultRecord from a StepResult.

        Args:
            result: StepResult instance from step execution.
            journey_run_id: ID of the parent journey run.
            path_name: Name of the path this step belongs to.
            step_order: Order of execution within the journey.

        Returns:
            StepResultRecord populated from the result.
        """
        status = "passed" if result.success else "failed"

        return cls(
            journey_run_id=journey_run_id,
            step_name=result.step_name,
            path_name=path_name,
            status=status,
            duration_ms=result.duration_ms,
            request=json.dumps(result.request) if result.request else "{}",
            response=json.dumps(result.response) if result.response else "{}",
            error=result.error,
            started_at=result.started_at,
            finished_at=result.finished_at,
            step_order=step_order,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert record to dictionary."""
        return {
            "id": self.id,
            "journey_run_id": self.journey_run_id,
            "step_name": self.step_name,
            "path_name": self.path_name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "request": json.loads(self.request),
            "response": json.loads(self.response),
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "step_order": self.step_order,
        }


@dataclass
class InvariantCheckRecord:
    """Record of an invariant check result.

    Attributes:
        id: Unique identifier for this invariant check.
        journey_run_id: Foreign key to the parent journey run.
        invariant_name: Name/description of the invariant.
        passed: Whether the invariant check passed.
        expected: JSON-encoded expected value.
        actual: JSON-encoded actual value.
        message: Additional message or error details.
        checked_at: Timestamp when the invariant was checked.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    journey_run_id: str = ""
    invariant_name: str = ""
    passed: bool = False
    expected: str = "{}"
    actual: str = "{}"
    message: str | None = None
    checked_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_invariant_result(
        cls,
        journey_run_id: str,
        name: str,
        passed: bool,
        expected: Any = None,
        actual: Any = None,
        message: str | None = None,
    ) -> InvariantCheckRecord:
        """Create an InvariantCheckRecord from check results.

        Args:
            journey_run_id: ID of the parent journey run.
            name: Name of the invariant.
            passed: Whether the check passed.
            expected: Expected value.
            actual: Actual value found.
            message: Optional message or error details.

        Returns:
            InvariantCheckRecord populated from the results.
        """
        return cls(
            journey_run_id=journey_run_id,
            invariant_name=name,
            passed=passed,
            expected=json.dumps(expected) if expected is not None else "null",
            actual=json.dumps(actual) if actual is not None else "null",
            message=message,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert record to dictionary."""
        return {
            "id": self.id,
            "journey_run_id": self.journey_run_id,
            "invariant_name": self.invariant_name,
            "passed": self.passed,
            "expected": json.loads(self.expected),
            "actual": json.loads(self.actual),
            "message": self.message,
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
        }


@dataclass
class IssueRecord:
    """Record of a captured issue.

    Attributes:
        id: Unique identifier for this issue.
        journey_run_id: Foreign key to the parent journey run.
        severity: Severity level (critical/high/medium/low/info).
        message: Error message or description.
        context: JSON-encoded context data.
        journey_name: Name of the journey where issue occurred.
        path_name: Name of the path where issue occurred.
        step_name: Name of the step where issue occurred.
        suggestion: Suggested fix for the issue.
        request: JSON-encoded request data.
        response: JSON-encoded response data.
        logs: JSON-encoded list of log entries.
        created_at: Timestamp when the issue was captured.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    journey_run_id: str = ""
    severity: str = "high"
    message: str = ""
    context: str = "{}"
    journey_name: str = ""
    path_name: str = "main"
    step_name: str = ""
    suggestion: str = ""
    request: str = "{}"
    response: str = "{}"
    logs: str = "[]"
    created_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_issue(
        cls,
        issue: Any,
        journey_run_id: str,
    ) -> IssueRecord:
        """Create an IssueRecord from an Issue.

        Args:
            issue: Issue instance from journey execution.
            journey_run_id: ID of the parent journey run.

        Returns:
            IssueRecord populated from the issue.
        """
        severity = issue.severity.value if hasattr(issue.severity, "value") else str(issue.severity)

        return cls(
            journey_run_id=journey_run_id,
            severity=severity,
            message=issue.error,
            journey_name=issue.journey,
            path_name=issue.path,
            step_name=issue.step,
            suggestion=issue.suggestion,
            request=json.dumps(issue.request) if issue.request else "{}",
            response=json.dumps(issue.response) if issue.response else "{}",
            logs=json.dumps(issue.logs) if issue.logs else "[]",
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert record to dictionary."""
        return {
            "id": self.id,
            "journey_run_id": self.journey_run_id,
            "severity": self.severity,
            "message": self.message,
            "context": json.loads(self.context),
            "journey_name": self.journey_name,
            "path_name": self.path_name,
            "step_name": self.step_name,
            "suggestion": self.suggestion,
            "request": json.loads(self.request),
            "response": json.loads(self.response),
            "logs": json.loads(self.logs),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# SQL Schema definitions for table creation
SCHEMA_SQL = """
-- Journey runs table
CREATE TABLE IF NOT EXISTS journey_runs (
    id TEXT PRIMARY KEY,
    journey_name TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    duration_ms REAL DEFAULT 0.0,
    total_steps INTEGER DEFAULT 0,
    passed_steps INTEGER DEFAULT 0,
    failed_steps INTEGER DEFAULT 0,
    total_paths INTEGER DEFAULT 0,
    passed_paths INTEGER DEFAULT 0,
    failed_paths INTEGER DEFAULT 0,
    tags TEXT DEFAULT '[]',
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);

-- Step results table
CREATE TABLE IF NOT EXISTS step_results (
    id TEXT PRIMARY KEY,
    journey_run_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    path_name TEXT DEFAULT 'main',
    status TEXT NOT NULL DEFAULT 'pending',
    duration_ms REAL DEFAULT 0.0,
    request TEXT DEFAULT '{}',
    response TEXT DEFAULT '{}',
    error TEXT,
    started_at TEXT,
    finished_at TEXT,
    step_order INTEGER DEFAULT 0,
    FOREIGN KEY (journey_run_id) REFERENCES journey_runs(id) ON DELETE CASCADE
);

-- Invariant checks table
CREATE TABLE IF NOT EXISTS invariant_checks (
    id TEXT PRIMARY KEY,
    journey_run_id TEXT NOT NULL,
    invariant_name TEXT NOT NULL,
    passed INTEGER NOT NULL DEFAULT 0,
    expected TEXT DEFAULT '{}',
    actual TEXT DEFAULT '{}',
    message TEXT,
    checked_at TEXT NOT NULL,
    FOREIGN KEY (journey_run_id) REFERENCES journey_runs(id) ON DELETE CASCADE
);

-- Issues table
CREATE TABLE IF NOT EXISTS issues (
    id TEXT PRIMARY KEY,
    journey_run_id TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'high',
    message TEXT NOT NULL,
    context TEXT DEFAULT '{}',
    journey_name TEXT,
    path_name TEXT DEFAULT 'main',
    step_name TEXT,
    suggestion TEXT,
    request TEXT DEFAULT '{}',
    response TEXT DEFAULT '{}',
    logs TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (journey_run_id) REFERENCES journey_runs(id) ON DELETE CASCADE
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_journey_runs_journey_name ON journey_runs(journey_name);
CREATE INDEX IF NOT EXISTS idx_journey_runs_started_at ON journey_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_journey_runs_status ON journey_runs(status);
CREATE INDEX IF NOT EXISTS idx_step_results_journey_run_id ON step_results(journey_run_id);
CREATE INDEX IF NOT EXISTS idx_step_results_step_name ON step_results(step_name);
CREATE INDEX IF NOT EXISTS idx_invariant_checks_journey_run_id ON invariant_checks(journey_run_id);
CREATE INDEX IF NOT EXISTS idx_issues_journey_run_id ON issues(journey_run_id);
CREATE INDEX IF NOT EXISTS idx_issues_severity ON issues(severity);
"""
