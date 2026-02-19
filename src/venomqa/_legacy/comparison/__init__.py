"""Comparison module for VenomQA run analysis and diffing.

This module provides tools for comparing VenomQA test runs, detecting
differences in step status, timing, and response data. It supports
baseline management for regression detection and trend analysis.

Key Features:
    - Run comparison: Compare two test runs to find changes
    - JSON diffing: Deep comparison of response bodies
    - Baseline management: Save and compare against baseline runs
    - Snapshot testing: Save and verify API response snapshots
    - Trend analysis: Track pass rates and timing over time

Example:
    >>> from venomqa.comparison import RunComparator, BaselineManager
    >>>
    >>> # Compare two runs
    >>> comparator = RunComparator()
    >>> diff = comparator.compare(run_123, run_456)
    >>> print(diff.status_changes)  # Steps that changed status
    >>>
    >>> # Baseline comparison
    >>> baseline = BaselineManager("./baselines")
    >>> baseline.save(run_result, "checkout_flow")
    >>> diff = baseline.compare(new_run, "checkout_flow")
    >>> if diff.has_regressions:
    ...     print("Regression detected!")

See Also:
    - RunComparator: Main comparison engine
    - ComparisonResult: Structured comparison output
    - BaselineManager: Baseline save/load/compare
    - SnapshotManager: API response snapshots
    - TrendAnalyzer: Historical trend analysis
"""

from venomqa.comparison.diff import (
    ComparisonResult,
    DiffConfig,
    JSONDiff,
    ResponseDiff,
    RunComparator,
    StatusChange,
    StepComparison,
    TimingDiff,
)
from venomqa.comparison.report import (
    BaselineManager,
    ComparisonHTMLReporter,
    ComparisonReporter,
    SnapshotManager,
    TrendAnalyzer,
    TrendData,
    TrendPoint,
)

__all__ = [
    # Core comparison
    "RunComparator",
    "ComparisonResult",
    "StepComparison",
    "StatusChange",
    "TimingDiff",
    "ResponseDiff",
    "JSONDiff",
    "DiffConfig",
    # Baseline management
    "BaselineManager",
    # Snapshot testing
    "SnapshotManager",
    # Trend analysis
    "TrendAnalyzer",
    "TrendData",
    "TrendPoint",
    # Reporting
    "ComparisonReporter",
    "ComparisonHTMLReporter",
]
