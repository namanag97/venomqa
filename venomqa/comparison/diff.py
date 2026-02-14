"""Core diffing logic for VenomQA run comparison.

This module provides the core comparison engine for analyzing differences
between VenomQA test runs. It supports deep JSON comparison, timing analysis,
and status change detection.

Example:
    >>> from venomqa.comparison.diff import RunComparator, DiffConfig
    >>>
    >>> config = DiffConfig(
    ...     ignore_patterns=["*.timestamp", "*.id"],
    ...     timing_threshold_percent=10.0,
    ... )
    >>> comparator = RunComparator(config)
    >>> diff = comparator.compare(baseline_run, current_run)
    >>> print(diff.summary())
"""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from venomqa.core.models import JourneyResult, StepResult


class ChangeType(Enum):
    """Types of changes detected between runs."""

    PASS_TO_FAIL = "pass_to_fail"
    FAIL_TO_PASS = "fail_to_pass"
    ADDED = "added"
    REMOVED = "removed"
    UNCHANGED = "unchanged"
    MODIFIED = "modified"


class DiffType(Enum):
    """Types of JSON diff operations."""

    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    TYPE_CHANGED = "type_changed"
    UNCHANGED = "unchanged"


@dataclass
class DiffConfig:
    """Configuration for comparison behavior.

    Attributes:
        ignore_patterns: Glob patterns for paths to ignore (e.g., "*.timestamp").
        ignore_fields: Exact field names to ignore in comparisons.
        timing_threshold_percent: Threshold for timing change alerts (default: 10%).
        timing_threshold_ms: Absolute threshold for timing changes in ms.
        normalize_whitespace: Whether to normalize whitespace in string comparisons.
        ignore_order: Whether to ignore array element order in comparisons.
        max_depth: Maximum depth for recursive comparison.
        include_unchanged: Whether to include unchanged items in output.
    """

    ignore_patterns: list[str] = field(default_factory=lambda: [
        "*.timestamp",
        "*.created_at",
        "*.updated_at",
        "*.id",
        "*._id",
        "*.uuid",
        "*.token",
        "*.session_id",
        "*.request_id",
        "*.correlation_id",
    ])
    ignore_fields: set[str] = field(default_factory=lambda: {
        "timestamp", "created_at", "updated_at", "id", "_id",
        "uuid", "token", "session_id", "request_id", "correlation_id",
    })
    timing_threshold_percent: float = 10.0
    timing_threshold_ms: float = 100.0
    normalize_whitespace: bool = True
    ignore_order: bool = False
    max_depth: int = 50
    include_unchanged: bool = False


@dataclass
class JSONDiffItem:
    """A single difference found in JSON comparison.

    Attributes:
        path: JSON path to the differing value (e.g., "user.address.city").
        diff_type: Type of difference (added, removed, changed).
        old_value: Value in the baseline/old data.
        new_value: Value in the current/new data.
    """

    path: str
    diff_type: DiffType
    old_value: Any = None
    new_value: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "path": self.path,
            "type": self.diff_type.value,
            "old_value": self.old_value,
            "new_value": self.new_value,
        }


class JSONDiff:
    """Deep JSON comparison utility.

    Compares two JSON-like structures and produces detailed diffs
    with path highlighting and configurable ignore patterns.

    Example:
        >>> diff = JSONDiff(config)
        >>> items = diff.compare(old_json, new_json)
        >>> for item in items:
        ...     print(f"{item.path}: {item.diff_type.value}")
    """

    def __init__(self, config: DiffConfig | None = None) -> None:
        """Initialize JSON diff with optional configuration.

        Args:
            config: Configuration for diff behavior. Uses defaults if None.
        """
        self.config = config or DiffConfig()

    def compare(
        self,
        old: Any,
        new: Any,
        path: str = "",
    ) -> list[JSONDiffItem]:
        """Compare two JSON-like structures.

        Args:
            old: The baseline/old data structure.
            new: The current/new data structure.
            path: Current path in the structure (for recursion).

        Returns:
            List of JSONDiffItem objects describing all differences.
        """
        items: list[JSONDiffItem] = []
        self._compare_recursive(old, new, path, items, depth=0)
        return items

    def _should_ignore(self, path: str) -> bool:
        """Check if a path should be ignored based on config."""
        # Check exact field names
        field_name = path.split(".")[-1] if path else ""
        if field_name in self.config.ignore_fields:
            return True

        # Check glob patterns
        for pattern in self.config.ignore_patterns:
            if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(field_name, pattern):
                return True

        return False

    def _compare_recursive(
        self,
        old: Any,
        new: Any,
        path: str,
        items: list[JSONDiffItem],
        depth: int,
    ) -> None:
        """Recursively compare two values."""
        if depth > self.config.max_depth:
            return

        if self._should_ignore(path):
            return

        # Type changed
        if type(old) is not type(new):
            items.append(JSONDiffItem(
                path=path or "(root)",
                diff_type=DiffType.TYPE_CHANGED,
                old_value=old,
                new_value=new,
            ))
            return

        # None comparison
        if old is None and new is None:
            if self.config.include_unchanged:
                items.append(JSONDiffItem(
                    path=path or "(root)",
                    diff_type=DiffType.UNCHANGED,
                    old_value=old,
                    new_value=new,
                ))
            return

        # Dictionary comparison
        if isinstance(old, dict) and isinstance(new, dict):
            self._compare_dicts(old, new, path, items, depth)
            return

        # List comparison
        if isinstance(old, list) and isinstance(new, list):
            self._compare_lists(old, new, path, items, depth)
            return

        # String comparison with normalization
        if isinstance(old, str) and isinstance(new, str):
            old_cmp = old
            new_cmp = new
            if self.config.normalize_whitespace:
                old_cmp = " ".join(old.split())
                new_cmp = " ".join(new.split())

            if old_cmp != new_cmp:
                items.append(JSONDiffItem(
                    path=path or "(root)",
                    diff_type=DiffType.CHANGED,
                    old_value=old,
                    new_value=new,
                ))
            elif self.config.include_unchanged:
                items.append(JSONDiffItem(
                    path=path or "(root)",
                    diff_type=DiffType.UNCHANGED,
                    old_value=old,
                    new_value=new,
                ))
            return

        # Primitive comparison
        if old != new:
            items.append(JSONDiffItem(
                path=path or "(root)",
                diff_type=DiffType.CHANGED,
                old_value=old,
                new_value=new,
            ))
        elif self.config.include_unchanged:
            items.append(JSONDiffItem(
                path=path or "(root)",
                diff_type=DiffType.UNCHANGED,
                old_value=old,
                new_value=new,
            ))

    def _compare_dicts(
        self,
        old: dict[str, Any],
        new: dict[str, Any],
        path: str,
        items: list[JSONDiffItem],
        depth: int,
    ) -> None:
        """Compare two dictionaries."""
        all_keys = set(old.keys()) | set(new.keys())

        for key in sorted(all_keys):
            key_path = f"{path}.{key}" if path else key

            if self._should_ignore(key_path):
                continue

            if key not in old:
                items.append(JSONDiffItem(
                    path=key_path,
                    diff_type=DiffType.ADDED,
                    old_value=None,
                    new_value=new[key],
                ))
            elif key not in new:
                items.append(JSONDiffItem(
                    path=key_path,
                    diff_type=DiffType.REMOVED,
                    old_value=old[key],
                    new_value=None,
                ))
            else:
                self._compare_recursive(
                    old[key], new[key], key_path, items, depth + 1
                )

    def _compare_lists(
        self,
        old: list[Any],
        new: list[Any],
        path: str,
        items: list[JSONDiffItem],
        depth: int,
    ) -> None:
        """Compare two lists."""
        if self.config.ignore_order:
            # Compare as sets for unordered comparison
            self._compare_lists_unordered(old, new, path, items, depth)
        else:
            # Compare by index
            max_len = max(len(old), len(new))
            for i in range(max_len):
                index_path = f"{path}[{i}]"

                if i >= len(old):
                    items.append(JSONDiffItem(
                        path=index_path,
                        diff_type=DiffType.ADDED,
                        old_value=None,
                        new_value=new[i],
                    ))
                elif i >= len(new):
                    items.append(JSONDiffItem(
                        path=index_path,
                        diff_type=DiffType.REMOVED,
                        old_value=old[i],
                        new_value=None,
                    ))
                else:
                    self._compare_recursive(
                        old[i], new[i], index_path, items, depth + 1
                    )

    def _compare_lists_unordered(
        self,
        old: list[Any],
        new: list[Any],
        path: str,
        items: list[JSONDiffItem],
        depth: int,
    ) -> None:
        """Compare lists ignoring order."""
        # Simple approach: convert to string representation for comparison
        old_set = {json.dumps(item, sort_keys=True, default=str) for item in old}
        new_set = {json.dumps(item, sort_keys=True, default=str) for item in new}

        removed = old_set - new_set
        added = new_set - old_set

        for item_str in removed:
            item = json.loads(item_str)
            items.append(JSONDiffItem(
                path=f"{path}[]",
                diff_type=DiffType.REMOVED,
                old_value=item,
                new_value=None,
            ))

        for item_str in added:
            item = json.loads(item_str)
            items.append(JSONDiffItem(
                path=f"{path}[]",
                diff_type=DiffType.ADDED,
                old_value=None,
                new_value=item,
            ))


@dataclass
class StatusChange:
    """Represents a status change for a step between runs.

    Attributes:
        step_name: Name of the step.
        path_name: Name of the path (or "main" for main path).
        journey_name: Name of the journey.
        change_type: Type of status change.
        old_error: Error message from old run (if failed).
        new_error: Error message from new run (if failed).
    """

    step_name: str
    path_name: str
    journey_name: str
    change_type: ChangeType
    old_error: str | None = None
    new_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "step_name": self.step_name,
            "path_name": self.path_name,
            "journey_name": self.journey_name,
            "change_type": self.change_type.value,
            "old_error": self.old_error,
            "new_error": self.new_error,
        }


@dataclass
class TimingDiff:
    """Represents a timing difference for a step.

    Attributes:
        step_name: Name of the step.
        path_name: Name of the path.
        journey_name: Name of the journey.
        old_duration_ms: Duration in old run.
        new_duration_ms: Duration in new run.
        diff_ms: Difference in milliseconds (new - old).
        diff_percent: Percentage change.
        is_significant: Whether the change exceeds threshold.
    """

    step_name: str
    path_name: str
    journey_name: str
    old_duration_ms: float
    new_duration_ms: float
    diff_ms: float
    diff_percent: float
    is_significant: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "step_name": self.step_name,
            "path_name": self.path_name,
            "journey_name": self.journey_name,
            "old_duration_ms": self.old_duration_ms,
            "new_duration_ms": self.new_duration_ms,
            "diff_ms": self.diff_ms,
            "diff_percent": self.diff_percent,
            "is_significant": self.is_significant,
        }


@dataclass
class ResponseDiff:
    """Represents response differences for a step.

    Attributes:
        step_name: Name of the step.
        path_name: Name of the path.
        journey_name: Name of the journey.
        status_code_changed: Whether HTTP status code changed.
        old_status_code: Status code from old run.
        new_status_code: Status code from new run.
        body_diffs: List of JSON diff items for response body.
        header_diffs: List of JSON diff items for headers.
    """

    step_name: str
    path_name: str
    journey_name: str
    status_code_changed: bool = False
    old_status_code: int | None = None
    new_status_code: int | None = None
    body_diffs: list[JSONDiffItem] = field(default_factory=list)
    header_diffs: list[JSONDiffItem] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Check if there are any response changes."""
        return self.status_code_changed or bool(self.body_diffs) or bool(self.header_diffs)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "step_name": self.step_name,
            "path_name": self.path_name,
            "journey_name": self.journey_name,
            "status_code_changed": self.status_code_changed,
            "old_status_code": self.old_status_code,
            "new_status_code": self.new_status_code,
            "body_diffs": [d.to_dict() for d in self.body_diffs],
            "header_diffs": [d.to_dict() for d in self.header_diffs],
        }


@dataclass
class StepComparison:
    """Complete comparison result for a single step.

    Attributes:
        step_name: Name of the step.
        path_name: Name of the path.
        journey_name: Name of the journey.
        status_change: Status change information if any.
        timing_diff: Timing difference if any.
        response_diff: Response differences if any.
    """

    step_name: str
    path_name: str
    journey_name: str
    status_change: StatusChange | None = None
    timing_diff: TimingDiff | None = None
    response_diff: ResponseDiff | None = None

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes for this step."""
        if self.status_change and self.status_change.change_type != ChangeType.UNCHANGED:
            return True
        if self.timing_diff and self.timing_diff.is_significant:
            return True
        if self.response_diff and self.response_diff.has_changes:
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "step_name": self.step_name,
            "path_name": self.path_name,
            "journey_name": self.journey_name,
            "status_change": self.status_change.to_dict() if self.status_change else None,
            "timing_diff": self.timing_diff.to_dict() if self.timing_diff else None,
            "response_diff": self.response_diff.to_dict() if self.response_diff else None,
            "has_changes": self.has_changes,
        }


class ComparisonResult(BaseModel):
    """Complete comparison result between two runs.

    This model contains all differences found between two test runs,
    organized by category (status changes, timing, responses).

    Attributes:
        old_run_id: Identifier for the baseline/old run.
        new_run_id: Identifier for the current/new run.
        compared_at: Timestamp when comparison was performed.
        status_changes: List of steps that changed pass/fail status.
        timing_diffs: List of steps with significant timing changes.
        response_diffs: List of steps with response differences.
        added_steps: Steps present in new run but not in old.
        removed_steps: Steps present in old run but not in new.
        step_comparisons: Complete comparison data for each step.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    old_run_id: str = Field(..., description="ID of the baseline run")
    new_run_id: str = Field(..., description="ID of the comparison run")
    compared_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp of comparison",
    )
    status_changes: list[StatusChange] = Field(
        default_factory=list,
        description="Steps with status changes",
    )
    timing_diffs: list[TimingDiff] = Field(
        default_factory=list,
        description="Steps with timing changes",
    )
    response_diffs: list[ResponseDiff] = Field(
        default_factory=list,
        description="Steps with response changes",
    )
    added_steps: list[str] = Field(
        default_factory=list,
        description="Steps in new run but not old",
    )
    removed_steps: list[str] = Field(
        default_factory=list,
        description="Steps in old run but not new",
    )
    step_comparisons: list[StepComparison] = Field(
        default_factory=list,
        description="Full comparison data per step",
    )

    @property
    def has_regressions(self) -> bool:
        """Check if any steps regressed (pass to fail)."""
        return any(
            sc.change_type == ChangeType.PASS_TO_FAIL
            for sc in self.status_changes
        )

    @property
    def has_improvements(self) -> bool:
        """Check if any steps improved (fail to pass)."""
        return any(
            sc.change_type == ChangeType.FAIL_TO_PASS
            for sc in self.status_changes
        )

    @property
    def has_timing_degradation(self) -> bool:
        """Check if any steps have significant timing increases."""
        return any(
            td.is_significant and td.diff_ms > 0
            for td in self.timing_diffs
        )

    @property
    def regression_count(self) -> int:
        """Count of steps that regressed."""
        return sum(
            1 for sc in self.status_changes
            if sc.change_type == ChangeType.PASS_TO_FAIL
        )

    @property
    def improvement_count(self) -> int:
        """Count of steps that improved."""
        return sum(
            1 for sc in self.status_changes
            if sc.change_type == ChangeType.FAIL_TO_PASS
        )

    def get_regressions(self) -> list[StatusChange]:
        """Get all regressed steps (pass to fail)."""
        return [
            sc for sc in self.status_changes
            if sc.change_type == ChangeType.PASS_TO_FAIL
        ]

    def get_improvements(self) -> list[StatusChange]:
        """Get all improved steps (fail to pass)."""
        return [
            sc for sc in self.status_changes
            if sc.change_type == ChangeType.FAIL_TO_PASS
        ]

    def summary(self) -> str:
        """Generate a human-readable summary of the comparison."""
        lines = [
            f"Comparison: {self.old_run_id} -> {self.new_run_id}",
            f"Compared at: {self.compared_at.isoformat()}",
            "",
            "Status Changes:",
            f"  - Regressions (pass->fail): {self.regression_count}",
            f"  - Improvements (fail->pass): {self.improvement_count}",
            f"  - Added steps: {len(self.added_steps)}",
            f"  - Removed steps: {len(self.removed_steps)}",
            "",
            f"Timing Changes: {len([t for t in self.timing_diffs if t.is_significant])} significant",
            f"Response Changes: {len([r for r in self.response_diffs if r.has_changes])} steps",
        ]

        if self.has_regressions:
            lines.append("")
            lines.append("REGRESSIONS:")
            for reg in self.get_regressions():
                lines.append(f"  - {reg.journey_name}/{reg.path_name}/{reg.step_name}")
                if reg.new_error:
                    lines.append(f"    Error: {reg.new_error}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "old_run_id": self.old_run_id,
            "new_run_id": self.new_run_id,
            "compared_at": self.compared_at.isoformat(),
            "status_changes": [sc.to_dict() for sc in self.status_changes],
            "timing_diffs": [td.to_dict() for td in self.timing_diffs],
            "response_diffs": [rd.to_dict() for rd in self.response_diffs],
            "added_steps": self.added_steps,
            "removed_steps": self.removed_steps,
            "has_regressions": self.has_regressions,
            "has_improvements": self.has_improvements,
            "regression_count": self.regression_count,
            "improvement_count": self.improvement_count,
        }


class RunComparator:
    """Main comparison engine for VenomQA runs.

    Compares two JourneyResult objects or collections of results
    and produces a detailed ComparisonResult.

    Example:
        >>> comparator = RunComparator()
        >>> diff = comparator.compare(baseline_results, current_results)
        >>> if diff.has_regressions:
        ...     for reg in diff.get_regressions():
        ...         print(f"Regression: {reg.step_name}")
    """

    def __init__(self, config: DiffConfig | None = None) -> None:
        """Initialize the comparator.

        Args:
            config: Configuration for comparison behavior.
        """
        self.config = config or DiffConfig()
        self.json_diff = JSONDiff(self.config)

    def compare(
        self,
        old_results: list[JourneyResult] | JourneyResult,
        new_results: list[JourneyResult] | JourneyResult,
        old_run_id: str = "baseline",
        new_run_id: str = "current",
    ) -> ComparisonResult:
        """Compare two sets of journey results.

        Args:
            old_results: Baseline/old results (single or list).
            new_results: Current/new results (single or list).
            old_run_id: Identifier for the old run.
            new_run_id: Identifier for the new run.

        Returns:
            ComparisonResult with all detected differences.
        """
        # Normalize to lists
        if not isinstance(old_results, list):
            old_results = [old_results]
        if not isinstance(new_results, list):
            new_results = [new_results]

        result = ComparisonResult(
            old_run_id=old_run_id,
            new_run_id=new_run_id,
        )

        # Build step maps
        old_steps = self._build_step_map(old_results)
        new_steps = self._build_step_map(new_results)

        # Find all unique step keys
        all_keys = set(old_steps.keys()) | set(new_steps.keys())

        for key in sorted(all_keys):
            journey_name, path_name, step_name = self._parse_key(key)

            if key not in old_steps:
                # Step was added
                result.added_steps.append(key)
                result.status_changes.append(StatusChange(
                    step_name=step_name,
                    path_name=path_name,
                    journey_name=journey_name,
                    change_type=ChangeType.ADDED,
                ))
                continue

            if key not in new_steps:
                # Step was removed
                result.removed_steps.append(key)
                result.status_changes.append(StatusChange(
                    step_name=step_name,
                    path_name=path_name,
                    journey_name=journey_name,
                    change_type=ChangeType.REMOVED,
                ))
                continue

            # Compare existing steps
            old_step = old_steps[key]
            new_step = new_steps[key]

            comparison = self._compare_steps(
                old_step, new_step,
                journey_name, path_name, step_name,
            )
            result.step_comparisons.append(comparison)

            if comparison.status_change:
                result.status_changes.append(comparison.status_change)

            if comparison.timing_diff and comparison.timing_diff.is_significant:
                result.timing_diffs.append(comparison.timing_diff)

            if comparison.response_diff and comparison.response_diff.has_changes:
                result.response_diffs.append(comparison.response_diff)

        return result

    def _build_step_map(
        self,
        results: list[JourneyResult],
    ) -> dict[str, StepResult]:
        """Build a map of step key -> StepResult."""
        step_map: dict[str, StepResult] = {}

        for journey_result in results:
            journey_name = journey_result.journey_name

            # Main path steps
            for step in journey_result.step_results:
                key = f"{journey_name}:main:{step.step_name}"
                step_map[key] = step

            # Branch path steps
            for branch in journey_result.branch_results:
                for path_result in branch.path_results:
                    for step in path_result.step_results:
                        key = f"{journey_name}:{path_result.path_name}:{step.step_name}"
                        step_map[key] = step

        return step_map

    def _parse_key(self, key: str) -> tuple[str, str, str]:
        """Parse a step key into (journey_name, path_name, step_name)."""
        parts = key.split(":", 2)
        if len(parts) == 3:
            return parts[0], parts[1], parts[2]
        return "unknown", "unknown", key

    def _compare_steps(
        self,
        old_step: StepResult,
        new_step: StepResult,
        journey_name: str,
        path_name: str,
        step_name: str,
    ) -> StepComparison:
        """Compare two step results."""
        comparison = StepComparison(
            step_name=step_name,
            path_name=path_name,
            journey_name=journey_name,
        )

        # Status change
        comparison.status_change = self._compare_status(
            old_step, new_step, journey_name, path_name, step_name
        )

        # Timing diff
        comparison.timing_diff = self._compare_timing(
            old_step, new_step, journey_name, path_name, step_name
        )

        # Response diff
        comparison.response_diff = self._compare_response(
            old_step, new_step, journey_name, path_name, step_name
        )

        return comparison

    def _compare_status(
        self,
        old_step: StepResult,
        new_step: StepResult,
        journey_name: str,
        path_name: str,
        step_name: str,
    ) -> StatusChange:
        """Compare step status (pass/fail)."""
        if old_step.success and not new_step.success:
            change_type = ChangeType.PASS_TO_FAIL
        elif not old_step.success and new_step.success:
            change_type = ChangeType.FAIL_TO_PASS
        else:
            change_type = ChangeType.UNCHANGED

        return StatusChange(
            step_name=step_name,
            path_name=path_name,
            journey_name=journey_name,
            change_type=change_type,
            old_error=old_step.error,
            new_error=new_step.error,
        )

    def _compare_timing(
        self,
        old_step: StepResult,
        new_step: StepResult,
        journey_name: str,
        path_name: str,
        step_name: str,
    ) -> TimingDiff:
        """Compare step timing."""
        old_ms = old_step.duration_ms
        new_ms = new_step.duration_ms
        diff_ms = new_ms - old_ms

        # Calculate percentage change
        if old_ms > 0:
            diff_percent = (diff_ms / old_ms) * 100
        else:
            diff_percent = 100.0 if new_ms > 0 else 0.0

        # Determine significance
        is_significant = (
            abs(diff_percent) >= self.config.timing_threshold_percent
            or abs(diff_ms) >= self.config.timing_threshold_ms
        )

        return TimingDiff(
            step_name=step_name,
            path_name=path_name,
            journey_name=journey_name,
            old_duration_ms=old_ms,
            new_duration_ms=new_ms,
            diff_ms=diff_ms,
            diff_percent=diff_percent,
            is_significant=is_significant,
        )

    def _compare_response(
        self,
        old_step: StepResult,
        new_step: StepResult,
        journey_name: str,
        path_name: str,
        step_name: str,
    ) -> ResponseDiff:
        """Compare step responses."""
        diff = ResponseDiff(
            step_name=step_name,
            path_name=path_name,
            journey_name=journey_name,
        )

        old_response = old_step.response or {}
        new_response = new_step.response or {}

        # Status code comparison
        old_status = old_response.get("status_code")
        new_status = new_response.get("status_code")

        if old_status != new_status:
            diff.status_code_changed = True
            diff.old_status_code = old_status
            diff.new_status_code = new_status

        # Body comparison
        old_body = old_response.get("body")
        new_body = new_response.get("body")

        if old_body is not None or new_body is not None:
            diff.body_diffs = self.json_diff.compare(old_body, new_body)

        # Header comparison
        old_headers = old_response.get("headers", {})
        new_headers = new_response.get("headers", {})

        if old_headers or new_headers:
            diff.header_diffs = self.json_diff.compare(old_headers, new_headers)

        return diff

    def compare_json(
        self,
        old_json: Any,
        new_json: Any,
    ) -> list[JSONDiffItem]:
        """Utility method to compare two JSON structures directly.

        Args:
            old_json: Baseline JSON data.
            new_json: New JSON data.

        Returns:
            List of differences found.
        """
        return self.json_diff.compare(old_json, new_json)
