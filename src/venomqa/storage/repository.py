"""Repository for VenomQA journey result persistence.

This module provides a high-level interface for storing and querying
journey execution results, enabling historical analysis, trend tracking,
and performance comparison.

Example:
    >>> from venomqa.storage import ResultsRepository
    >>> repo = ResultsRepository("sqlite:///venomqa_results.db")
    >>> repo.initialize()
    >>>
    >>> # Save results
    >>> run_id = repo.save_journey_result(journey_result)
    >>>
    >>> # Query history
    >>> stats = repo.get_dashboard_stats(days=30)
    >>> print(f"Pass rate: {stats['pass_rate']:.1f}%")
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from venomqa.storage.models import (
    SCHEMA_SQL,
    IssueRecord,
    JourneyRunRecord,
    RunStatus,
    StepResultRecord,
)

logger = logging.getLogger(__name__)


@dataclass
class TrendDataPoint:
    """A single data point for trend analysis.

    Attributes:
        date: Date for this data point.
        total_runs: Total number of test runs.
        passed_runs: Number of passed runs.
        failed_runs: Number of failed runs.
        avg_duration_ms: Average duration in milliseconds.
        pass_rate: Pass rate as percentage (0-100).
    """
    date: str
    total_runs: int = 0
    passed_runs: int = 0
    failed_runs: int = 0
    avg_duration_ms: float = 0.0
    pass_rate: float = 0.0


@dataclass
class DashboardStats:
    """Aggregate statistics for dashboard display.

    Provides a comprehensive overview of test execution history
    for dashboard visualization.
    """
    total_journeys: int = 0
    total_runs: int = 0
    total_passed: int = 0
    total_failed: int = 0
    pass_rate: float = 0.0
    avg_duration_ms: float = 0.0
    min_duration_ms: float = 0.0
    max_duration_ms: float = 0.0
    total_issues: int = 0
    critical_issues: int = 0
    high_issues: int = 0
    medium_issues: int = 0
    low_issues: int = 0
    trend_data: list[TrendDataPoint] = field(default_factory=list)
    top_failing_journeys: list[tuple[str, int]] = field(default_factory=list)
    slowest_journeys: list[tuple[str, float]] = field(default_factory=list)
    recent_runs: list[dict[str, Any]] = field(default_factory=list)


class ResultsRepository:
    """Repository for storing and querying journey results.

    Provides CRUD operations and analytics queries for journey
    execution results. Uses SQLite by default for simplicity.

    Attributes:
        connection_url: Database connection string.

    Example:
        >>> repo = ResultsRepository()
        >>> repo.initialize()
        >>>
        >>> # Save a journey result
        >>> run_id = repo.save_journey_result(result)
        >>>
        >>> # Get recent runs
        >>> runs = repo.list_runs(limit=10)
        >>> for run in runs:
        ...     print(f"{run.journey_name}: {run.status.value}")
    """

    def __init__(self, connection_url: str = "sqlite:///venomqa_results.db") -> None:
        """Initialize the repository.

        Args:
            connection_url: Database connection string. Supports:
                - sqlite:///path/to/database.db
                - sqlite://:memory: (in-memory, for testing)
        """
        self.connection_url = connection_url
        self._conn: sqlite3.Connection | None = None
        self._initialized = False

    def initialize(self) -> None:
        """Initialize the database connection and schema.

        Creates tables if they don't exist. Safe to call multiple times.
        """
        if self._initialized and self._conn:
            return

        db_path = self._parse_connection_url()

        # Ensure parent directory exists
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

        # Execute schema SQL
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

        self._initialized = True
        logger.info(f"Initialized results repository: {db_path}")

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            self._initialized = False

    def _parse_connection_url(self) -> str:
        """Parse connection URL to database path."""
        url = self.connection_url

        if url.startswith("sqlite:///"):
            return str(Path(url[10:]).expanduser().absolute())
        if url.startswith("sqlite://"):
            path = url[9:]
            if path == ":memory:":
                return path
            return str(Path(path).expanduser().absolute())
        return url

    def _ensure_initialized(self) -> None:
        """Ensure the repository is initialized."""
        if not self._initialized or not self._conn:
            self.initialize()

    def save_journey_result(
        self,
        result: Any,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Save a journey result to the database.

        Args:
            result: JourneyResult instance from journey execution.
            tags: Optional list of tags for categorization.
            metadata: Optional additional metadata.

        Returns:
            The ID of the saved journey run record.

        Example:
            >>> result = runner.run(journey)
            >>> run_id = repo.save_journey_result(result, tags=["smoke"])
        """
        self._ensure_initialized()

        if not self._conn:
            raise RuntimeError("Database not initialized")

        # Create journey run record
        run_record = JourneyRunRecord.from_journey_result(result, tags=tags, metadata=metadata)

        # Insert journey run
        self._conn.execute("""
            INSERT INTO journey_runs (
                id, journey_name, started_at, finished_at, status,
                duration_ms, total_steps, passed_steps, failed_steps,
                total_paths, passed_paths, failed_paths, tags, metadata, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_record.id,
            run_record.journey_name,
            run_record.started_at.isoformat() if run_record.started_at else None,
            run_record.finished_at.isoformat() if run_record.finished_at else None,
            run_record.status.value,
            run_record.duration_ms,
            run_record.total_steps,
            run_record.passed_steps,
            run_record.failed_steps,
            run_record.total_paths,
            run_record.passed_paths,
            run_record.failed_paths,
            run_record.tags,
            run_record.metadata,
            run_record.created_at.isoformat(),
        ))

        # Save step results
        for i, step_result in enumerate(result.step_results):
            step_record = StepResultRecord.from_step_result(
                step_result, run_record.id, step_order=i
            )
            self._conn.execute("""
                INSERT INTO step_results (
                    id, journey_run_id, step_name, path_name, status,
                    duration_ms, request, response, error, started_at,
                    finished_at, step_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                step_record.id,
                step_record.journey_run_id,
                step_record.step_name,
                step_record.path_name,
                step_record.status,
                step_record.duration_ms,
                step_record.request,
                step_record.response,
                step_record.error,
                step_record.started_at.isoformat() if step_record.started_at else None,
                step_record.finished_at.isoformat() if step_record.finished_at else None,
                step_record.step_order,
            ))

        # Save issues
        for issue in result.issues:
            issue_record = IssueRecord.from_issue(issue, run_record.id)
            self._conn.execute("""
                INSERT INTO issues (
                    id, journey_run_id, severity, message, context,
                    journey_name, path_name, step_name, suggestion,
                    request, response, logs, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                issue_record.id,
                issue_record.journey_run_id,
                issue_record.severity,
                issue_record.message,
                issue_record.context,
                issue_record.journey_name,
                issue_record.path_name,
                issue_record.step_name,
                issue_record.suggestion,
                issue_record.request,
                issue_record.response,
                issue_record.logs,
                issue_record.created_at.isoformat(),
            ))

        self._conn.commit()
        logger.debug(f"Saved journey result: {run_record.journey_name} (ID: {run_record.id})")

        return run_record.id

    def save_journey_results(
        self,
        results: list[Any],
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[str]:
        """Save multiple journey results.

        Args:
            results: List of JourneyResult instances.
            tags: Optional tags for all results.
            metadata: Optional metadata for all results.

        Returns:
            List of saved run IDs.
        """
        return [
            self.save_journey_result(result, tags=tags, metadata=metadata)
            for result in results
        ]

    def get_run(self, run_id: str) -> JourneyRunRecord | None:
        """Get a journey run by ID.

        Args:
            run_id: The ID of the run to retrieve.

        Returns:
            JourneyRunRecord if found, None otherwise.
        """
        self._ensure_initialized()

        if not self._conn:
            return None

        cursor = self._conn.execute(
            "SELECT * FROM journey_runs WHERE id = ?",
            (run_id,)
        )
        row = cursor.fetchone()

        if not row:
            return None

        return self._row_to_journey_run(row)

    def list_runs(
        self,
        limit: int = 50,
        journey_name: str | None = None,
        status: RunStatus | None = None,
        tags: list[str] | None = None,
        since: datetime | None = None,
    ) -> list[JourneyRunRecord]:
        """List journey runs with optional filtering.

        Args:
            limit: Maximum number of runs to return.
            journey_name: Filter by journey name.
            status: Filter by status.
            tags: Filter by tags (any match).
            since: Filter to runs after this timestamp.

        Returns:
            List of JourneyRunRecord objects, most recent first.
        """
        self._ensure_initialized()

        if not self._conn:
            return []

        query = "SELECT * FROM journey_runs WHERE 1=1"
        params: list[Any] = []

        if journey_name:
            query += " AND journey_name = ?"
            params.append(journey_name)

        if status:
            query += " AND status = ?"
            params.append(status.value)

        if since:
            query += " AND started_at >= ?"
            params.append(since.isoformat())

        if tags:
            tag_conditions = " OR ".join("tags LIKE ?" for _ in tags)
            query += f" AND ({tag_conditions})"
            params.extend(f'%"{tag}"%' for tag in tags)

        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        cursor = self._conn.execute(query, params)
        return [self._row_to_journey_run(row) for row in cursor.fetchall()]

    def get_step_results(self, run_id: str) -> list[StepResultRecord]:
        """Get step results for a journey run.

        Args:
            run_id: The ID of the journey run.

        Returns:
            List of StepResultRecord objects in execution order.
        """
        self._ensure_initialized()

        if not self._conn:
            return []

        cursor = self._conn.execute("""
            SELECT * FROM step_results
            WHERE journey_run_id = ?
            ORDER BY step_order ASC
        """, (run_id,))

        return [self._row_to_step_result(row) for row in cursor.fetchall()]

    def get_issues(
        self,
        run_id: str | None = None,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[IssueRecord]:
        """Get issues with optional filtering.

        Args:
            run_id: Filter by journey run ID.
            severity: Filter by severity level.
            limit: Maximum number of issues to return.

        Returns:
            List of IssueRecord objects.
        """
        self._ensure_initialized()

        if not self._conn:
            return []

        query = "SELECT * FROM issues WHERE 1=1"
        params: list[Any] = []

        if run_id:
            query += " AND journey_run_id = ?"
            params.append(run_id)

        if severity:
            query += " AND severity = ?"
            params.append(severity)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor = self._conn.execute(query, params)
        return [self._row_to_issue(row) for row in cursor.fetchall()]

    def get_trend_data(
        self,
        journey_name: str | None = None,
        days: int = 30,
    ) -> list[TrendDataPoint]:
        """Get daily trend data for visualization.

        Args:
            journey_name: Filter by journey name, or None for all.
            days: Number of days of history.

        Returns:
            List of TrendDataPoint objects, one per day.
        """
        self._ensure_initialized()

        if not self._conn:
            return []

        start_date = datetime.now() - timedelta(days=days)

        query = """
            SELECT
                date(started_at) as date,
                COUNT(*) as total_runs,
                SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed_runs,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_runs,
                AVG(duration_ms) as avg_duration_ms
            FROM journey_runs
            WHERE started_at >= ?
        """
        params: list[Any] = [start_date.isoformat()]

        if journey_name:
            query += " AND journey_name = ?"
            params.append(journey_name)

        query += " GROUP BY date(started_at) ORDER BY date ASC"

        cursor = self._conn.execute(query, params)

        trend_data = []
        for row in cursor.fetchall():
            total = row["total_runs"]
            passed = row["passed_runs"]
            trend_data.append(TrendDataPoint(
                date=row["date"],
                total_runs=total,
                passed_runs=passed,
                failed_runs=row["failed_runs"],
                avg_duration_ms=row["avg_duration_ms"] or 0.0,
                pass_rate=(passed / total * 100) if total > 0 else 0.0,
            ))

        return trend_data

    def get_dashboard_stats(self, days: int = 30) -> DashboardStats:
        """Get comprehensive dashboard statistics.

        Provides aggregate metrics for dashboard visualization including
        pass rates, timing statistics, issue breakdowns, and trends.

        Args:
            days: Number of days of history to include.

        Returns:
            DashboardStats with all metrics.
        """
        self._ensure_initialized()

        if not self._conn:
            return DashboardStats()

        start_date = datetime.now() - timedelta(days=days)

        # Basic stats
        cursor = self._conn.execute("""
            SELECT
                COUNT(DISTINCT journey_name) as total_journeys,
                COUNT(*) as total_runs,
                SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                AVG(duration_ms) as avg_duration,
                MIN(duration_ms) as min_duration,
                MAX(duration_ms) as max_duration
            FROM journey_runs
            WHERE started_at >= ?
        """, (start_date.isoformat(),))

        row = cursor.fetchone()

        total_runs = row["total_runs"] or 0
        passed = row["passed"] or 0

        stats = DashboardStats(
            total_journeys=row["total_journeys"] or 0,
            total_runs=total_runs,
            total_passed=passed,
            total_failed=row["failed"] or 0,
            pass_rate=(passed / total_runs * 100) if total_runs > 0 else 0.0,
            avg_duration_ms=row["avg_duration"] or 0.0,
            min_duration_ms=row["min_duration"] or 0.0,
            max_duration_ms=row["max_duration"] or 0.0,
        )

        # Issue counts
        cursor = self._conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) as critical,
                SUM(CASE WHEN severity = 'high' THEN 1 ELSE 0 END) as high,
                SUM(CASE WHEN severity = 'medium' THEN 1 ELSE 0 END) as medium,
                SUM(CASE WHEN severity = 'low' THEN 1 ELSE 0 END) as low
            FROM issues i
            JOIN journey_runs jr ON i.journey_run_id = jr.id
            WHERE jr.started_at >= ?
        """, (start_date.isoformat(),))

        row = cursor.fetchone()
        stats.total_issues = row["total"] or 0
        stats.critical_issues = row["critical"] or 0
        stats.high_issues = row["high"] or 0
        stats.medium_issues = row["medium"] or 0
        stats.low_issues = row["low"] or 0

        # Trend data
        stats.trend_data = self.get_trend_data(days=days)

        # Top failing journeys
        cursor = self._conn.execute("""
            SELECT journey_name, COUNT(*) as fail_count
            FROM journey_runs
            WHERE started_at >= ? AND status = 'failed'
            GROUP BY journey_name
            ORDER BY fail_count DESC
            LIMIT 10
        """, (start_date.isoformat(),))

        stats.top_failing_journeys = [
            (row["journey_name"], row["fail_count"])
            for row in cursor.fetchall()
        ]

        # Slowest journeys
        cursor = self._conn.execute("""
            SELECT journey_name, AVG(duration_ms) as avg_duration
            FROM journey_runs
            WHERE started_at >= ?
            GROUP BY journey_name
            ORDER BY avg_duration DESC
            LIMIT 10
        """, (start_date.isoformat(),))

        stats.slowest_journeys = [
            (row["journey_name"], row["avg_duration"])
            for row in cursor.fetchall()
        ]

        # Recent runs
        recent = self.list_runs(limit=10)
        stats.recent_runs = [run.to_dict() for run in recent]

        return stats

    def get_step_timing_stats(
        self,
        journey_name: str,
        days: int = 30,
    ) -> dict[str, dict[str, float]]:
        """Get timing statistics for each step in a journey.

        Args:
            journey_name: Name of the journey.
            days: Number of days of history.

        Returns:
            Dictionary mapping step names to timing stats.
        """
        self._ensure_initialized()

        if not self._conn:
            return {}

        start_date = datetime.now() - timedelta(days=days)

        cursor = self._conn.execute("""
            SELECT
                sr.step_name,
                AVG(sr.duration_ms) as avg_duration,
                MIN(sr.duration_ms) as min_duration,
                MAX(sr.duration_ms) as max_duration,
                COUNT(*) as run_count
            FROM step_results sr
            JOIN journey_runs jr ON sr.journey_run_id = jr.id
            WHERE jr.journey_name = ? AND jr.started_at >= ?
            GROUP BY sr.step_name
            ORDER BY avg_duration DESC
        """, (journey_name, start_date.isoformat()))

        return {
            row["step_name"]: {
                "avg": row["avg_duration"],
                "min": row["min_duration"],
                "max": row["max_duration"],
                "count": row["run_count"],
            }
            for row in cursor.fetchall()
        }

    def delete_old_runs(self, days: int = 90) -> int:
        """Delete runs older than specified days.

        Args:
            days: Delete runs older than this many days.

        Returns:
            Number of deleted runs.
        """
        self._ensure_initialized()

        if not self._conn:
            return 0

        cutoff_date = datetime.now() - timedelta(days=days)

        cursor = self._conn.execute("""
            DELETE FROM journey_runs
            WHERE started_at < ?
        """, (cutoff_date.isoformat(),))

        deleted = cursor.rowcount
        self._conn.commit()

        logger.info(f"Deleted {deleted} runs older than {days} days")
        return deleted

    def compare_runs(
        self,
        run_id_1: str,
        run_id_2: str,
    ) -> dict[str, Any]:
        """Compare two journey runs to identify differences.

        Useful for detecting regressions, improvements, and changes
        between test runs.

        Args:
            run_id_1: ID of the first (baseline) run.
            run_id_2: ID of the second (comparison) run.

        Returns:
            Dictionary containing:
            - run1/run2: Summary of each run
            - duration_diff_ms: Duration difference
            - duration_diff_pct: Duration change as percentage
            - step_comparison: Step-by-step comparison
            - resolved_issues: Issues fixed in run2
            - new_issues: New issues in run2
            - regression: True if run1 passed but run2 failed
            - improvement: True if run1 failed but run2 passed
        """
        self._ensure_initialized()

        run1 = self.get_run(run_id_1)
        run2 = self.get_run(run_id_2)

        if not run1 or not run2:
            missing = []
            if not run1:
                missing.append(run_id_1)
            if not run2:
                missing.append(run_id_2)
            return {"error": f"Run(s) not found: {', '.join(missing)}"}

        # Get steps and issues for each run
        steps1 = self.get_step_results(run_id_1)
        steps2 = self.get_step_results(run_id_2)
        issues1 = self.get_issues(run_id_1)
        issues2 = self.get_issues(run_id_2)

        # Duration comparison
        duration_diff = run2.duration_ms - run1.duration_ms
        duration_pct = (duration_diff / run1.duration_ms * 100) if run1.duration_ms > 0 else 0

        # Step comparison
        steps1_map = {s.step_name: s for s in steps1}
        steps2_map = {s.step_name: s for s in steps2}
        all_step_names = set(steps1_map.keys()) | set(steps2_map.keys())

        step_comparison = []
        for step_name in sorted(all_step_names):
            s1 = steps1_map.get(step_name)
            s2 = steps2_map.get(step_name)

            if s1 and s2:
                step_comparison.append({
                    "step_name": step_name,
                    "run1_status": s1.status,
                    "run2_status": s2.status,
                    "run1_duration_ms": s1.duration_ms,
                    "run2_duration_ms": s2.duration_ms,
                    "duration_diff_ms": s2.duration_ms - s1.duration_ms,
                    "status_changed": s1.status != s2.status,
                })
            elif s1:
                step_comparison.append({
                    "step_name": step_name,
                    "run1_status": s1.status,
                    "run2_status": None,
                    "removed": True,
                })
            else:
                step_comparison.append({
                    "step_name": step_name,
                    "run1_status": None,
                    "run2_status": s2.status if s2 else None,
                    "added": True,
                })

        # Issue comparison
        issues1_set = {(i.step_name, i.message) for i in issues1}
        issues2_set = {(i.step_name, i.message) for i in issues2}

        resolved_issues = issues1_set - issues2_set
        new_issues = issues2_set - issues1_set

        run1_status = run1.status.value
        run2_status = run2.status.value

        return {
            "run1": {
                "id": run1.id,
                "journey_name": run1.journey_name,
                "status": run1_status,
                "duration_ms": run1.duration_ms,
                "started_at": run1.started_at.isoformat() if run1.started_at else None,
                "total_steps": run1.total_steps,
                "passed_steps": run1.passed_steps,
                "failed_steps": run1.failed_steps,
            },
            "run2": {
                "id": run2.id,
                "journey_name": run2.journey_name,
                "status": run2_status,
                "duration_ms": run2.duration_ms,
                "started_at": run2.started_at.isoformat() if run2.started_at else None,
                "total_steps": run2.total_steps,
                "passed_steps": run2.passed_steps,
                "failed_steps": run2.failed_steps,
            },
            "duration_diff_ms": duration_diff,
            "duration_diff_pct": round(duration_pct, 2),
            "step_comparison": step_comparison,
            "resolved_issues": [
                {"step_name": s, "message": m} for s, m in resolved_issues
            ],
            "new_issues": [
                {"step_name": s, "message": m} for s, m in new_issues
            ],
            "regression": run1_status == "passed" and run2_status == "failed",
            "improvement": run1_status == "failed" and run2_status == "passed",
        }

    def _row_to_journey_run(self, row: sqlite3.Row) -> JourneyRunRecord:
        """Convert a database row to JourneyRunRecord."""
        return JourneyRunRecord(
            id=row["id"],
            journey_name=row["journey_name"],
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            status=RunStatus(row["status"]),
            duration_ms=row["duration_ms"],
            total_steps=row["total_steps"],
            passed_steps=row["passed_steps"],
            failed_steps=row["failed_steps"],
            total_paths=row["total_paths"],
            passed_paths=row["passed_paths"],
            failed_paths=row["failed_paths"],
            tags=row["tags"],
            metadata=row["metadata"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
        )

    def _row_to_step_result(self, row: sqlite3.Row) -> StepResultRecord:
        """Convert a database row to StepResultRecord."""
        return StepResultRecord(
            id=row["id"],
            journey_run_id=row["journey_run_id"],
            step_name=row["step_name"],
            path_name=row["path_name"],
            status=row["status"],
            duration_ms=row["duration_ms"],
            request=row["request"],
            response=row["response"],
            error=row["error"],
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            step_order=row["step_order"],
        )

    def _row_to_issue(self, row: sqlite3.Row) -> IssueRecord:
        """Convert a database row to IssueRecord."""
        return IssueRecord(
            id=row["id"],
            journey_run_id=row["journey_run_id"],
            severity=row["severity"],
            message=row["message"],
            context=row["context"],
            journey_name=row["journey_name"],
            path_name=row["path_name"],
            step_name=row["step_name"],
            suggestion=row["suggestion"],
            request=row["request"],
            response=row["response"],
            logs=row["logs"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
        )

    def __enter__(self) -> ResultsRepository:
        """Context manager entry."""
        self.initialize()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()
