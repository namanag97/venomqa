"""Storage module for persisting VenomQA journey results.

This module provides database persistence for journey execution results,
enabling historical analysis, comparison, and trend tracking.

Quick Start:
    >>> from venomqa.storage import ResultsRepository
    >>>
    >>> # Using ResultsRepository
    >>> repo = ResultsRepository()
    >>> repo.initialize()
    >>> run_id = repo.save_journey_result(journey_result)
    >>> runs = repo.list_runs(limit=10)
    >>>
    >>> # Get dashboard statistics
    >>> stats = repo.get_dashboard_stats(days=30)
    >>> print(f"Pass rate: {stats.pass_rate:.1f}%")

Features:
    - Persist journey results to SQLite (default) or custom DB
    - Query historical runs with filtering
    - Compare two runs to identify regressions
    - Track trends and statistics over time
    - CLI commands for history browsing
"""

from venomqa.storage.models import (
    InvariantCheckRecord,
    IssueRecord,
    JourneyRunRecord,
    RunStatus,
    StepResultRecord,
)
from venomqa.storage.repository import (
    DashboardStats,
    ResultsRepository,
    TrendDataPoint,
)

__all__ = [
    # Repository (primary API)
    "ResultsRepository",
    "DashboardStats",
    "TrendDataPoint",
    # Models
    "JourneyRunRecord",
    "StepResultRecord",
    "InvariantCheckRecord",
    "IssueRecord",
    "RunStatus",
]
