"""Tests for VenomQA comparison module."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta

import pytest

from venomqa.comparison import (
    BaselineManager,
    ComparisonHTMLReporter,
    ComparisonReporter,
    ComparisonResult,
    DiffConfig,
    JSONDiff,
    RunComparator,
    SnapshotManager,
    StatusChange,
    TrendAnalyzer,
    TrendData,
    TrendPoint,
)
from venomqa.comparison.diff import ChangeType, DiffType
from venomqa.core.models import (
    Issue,
    JourneyResult,
    Severity,
    StepResult,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_step_result() -> StepResult:
    """Create a sample step result for testing."""
    now = datetime.now()
    return StepResult(
        step_name="test_step",
        success=True,
        started_at=now,
        finished_at=now + timedelta(milliseconds=100),
        duration_ms=100.0,
        response={"status_code": 200, "body": {"id": 1, "name": "Test"}},
    )


@pytest.fixture
def sample_failed_step_result() -> StepResult:
    """Create a sample failed step result."""
    now = datetime.now()
    return StepResult(
        step_name="failed_step",
        success=False,
        started_at=now,
        finished_at=now + timedelta(milliseconds=50),
        duration_ms=50.0,
        error="HTTP 500",
        response={"status_code": 500, "body": {"error": "Internal Server Error"}},
    )


@pytest.fixture
def sample_journey_result() -> JourneyResult:
    """Create a sample journey result."""
    now = datetime.now()
    return JourneyResult(
        journey_name="test_journey",
        success=True,
        started_at=now,
        finished_at=now + timedelta(milliseconds=500),
        step_results=[
            StepResult(
                step_name="step1",
                success=True,
                started_at=now,
                finished_at=now + timedelta(milliseconds=100),
                duration_ms=100.0,
                response={"status_code": 200, "body": {"id": 1}},
            ),
            StepResult(
                step_name="step2",
                success=True,
                started_at=now + timedelta(milliseconds=100),
                finished_at=now + timedelta(milliseconds=200),
                duration_ms=100.0,
                response={"status_code": 200, "body": {"id": 2}},
            ),
        ],
        duration_ms=500.0,
    )


@pytest.fixture
def sample_failed_journey_result() -> JourneyResult:
    """Create a sample failed journey result."""
    now = datetime.now()
    return JourneyResult(
        journey_name="test_journey",
        success=False,
        started_at=now,
        finished_at=now + timedelta(milliseconds=300),
        step_results=[
            StepResult(
                step_name="step1",
                success=True,
                started_at=now,
                finished_at=now + timedelta(milliseconds=100),
                duration_ms=100.0,
            ),
            StepResult(
                step_name="step2",
                success=False,
                started_at=now + timedelta(milliseconds=100),
                finished_at=now + timedelta(milliseconds=200),
                duration_ms=100.0,
                error="HTTP 500",
            ),
        ],
        issues=[
            Issue(
                journey="test_journey",
                path="main",
                step="step2",
                error="HTTP 500",
                severity=Severity.HIGH,
            )
        ],
        duration_ms=300.0,
    )


# ============================================================================
# JSON Diff Tests
# ============================================================================


class TestJSONDiff:
    """Tests for JSON comparison functionality."""

    def test_compare_identical(self) -> None:
        """Test comparing identical JSON structures."""
        diff = JSONDiff()
        old = {"name": "test", "value": 123}
        new = {"name": "test", "value": 123}

        items = diff.compare(old, new)

        # Should have no diffs (unchanged items not included by default)
        assert len(items) == 0

    def test_compare_changed_value(self) -> None:
        """Test detecting changed values."""
        diff = JSONDiff()
        old = {"name": "test", "value": 100}
        new = {"name": "test", "value": 200}

        items = diff.compare(old, new)

        assert len(items) == 1
        assert items[0].path == "value"
        assert items[0].diff_type == DiffType.CHANGED
        assert items[0].old_value == 100
        assert items[0].new_value == 200

    def test_compare_added_field(self) -> None:
        """Test detecting added fields."""
        diff = JSONDiff()
        old = {"name": "test"}
        new = {"name": "test", "value": 123}

        items = diff.compare(old, new)

        assert len(items) == 1
        assert items[0].path == "value"
        assert items[0].diff_type == DiffType.ADDED
        assert items[0].new_value == 123

    def test_compare_removed_field(self) -> None:
        """Test detecting removed fields."""
        diff = JSONDiff()
        old = {"name": "test", "value": 123}
        new = {"name": "test"}

        items = diff.compare(old, new)

        assert len(items) == 1
        assert items[0].path == "value"
        assert items[0].diff_type == DiffType.REMOVED
        assert items[0].old_value == 123

    def test_compare_nested_objects(self) -> None:
        """Test comparing nested objects."""
        diff = JSONDiff()
        old = {"user": {"name": "John", "age": 25}}
        new = {"user": {"name": "John", "age": 30}}

        items = diff.compare(old, new)

        assert len(items) == 1
        assert items[0].path == "user.age"
        assert items[0].old_value == 25
        assert items[0].new_value == 30

    def test_compare_arrays(self) -> None:
        """Test comparing arrays."""
        diff = JSONDiff()
        old = {"items": [1, 2, 3]}
        new = {"items": [1, 2, 4]}

        items = diff.compare(old, new)

        assert len(items) == 1
        assert items[0].path == "items[2]"
        assert items[0].old_value == 3
        assert items[0].new_value == 4

    def test_compare_array_length_change(self) -> None:
        """Test comparing arrays with different lengths."""
        diff = JSONDiff()
        old = {"items": [1, 2]}
        new = {"items": [1, 2, 3]}

        items = diff.compare(old, new)

        assert len(items) == 1
        assert items[0].path == "items[2]"
        assert items[0].diff_type == DiffType.ADDED
        assert items[0].new_value == 3

    def test_compare_type_change(self) -> None:
        """Test detecting type changes."""
        diff = JSONDiff()
        old = {"value": "123"}
        new = {"value": 123}

        items = diff.compare(old, new)

        assert len(items) == 1
        assert items[0].diff_type == DiffType.TYPE_CHANGED

    def test_ignore_patterns(self) -> None:
        """Test ignoring fields by pattern."""
        config = DiffConfig(ignore_patterns=["*.timestamp", "*.id"])
        diff = JSONDiff(config)

        old = {"id": 1, "timestamp": "2024-01-01", "name": "old"}
        new = {"id": 2, "timestamp": "2024-01-02", "name": "new"}

        items = diff.compare(old, new)

        # Only name should be detected as changed
        assert len(items) == 1
        assert items[0].path == "name"

    def test_ignore_fields(self) -> None:
        """Test ignoring exact field names."""
        config = DiffConfig(ignore_fields={"created_at", "updated_at"})
        diff = JSONDiff(config)

        old = {"created_at": "2024-01-01", "name": "old"}
        new = {"created_at": "2024-01-02", "name": "new"}

        items = diff.compare(old, new)

        assert len(items) == 1
        assert items[0].path == "name"

    def test_include_unchanged(self) -> None:
        """Test including unchanged items."""
        config = DiffConfig(include_unchanged=True)
        diff = JSONDiff(config)

        old = {"name": "test"}
        new = {"name": "test"}

        items = diff.compare(old, new)

        assert len(items) == 1
        assert items[0].diff_type == DiffType.UNCHANGED

    def test_normalize_whitespace(self) -> None:
        """Test whitespace normalization in strings."""
        config = DiffConfig(normalize_whitespace=True)
        diff = JSONDiff(config)

        old = {"text": "hello   world"}
        new = {"text": "hello world"}

        items = diff.compare(old, new)

        # Should be no difference with normalization
        assert len(items) == 0

    def test_compare_unordered_arrays(self) -> None:
        """Test comparing arrays ignoring order."""
        config = DiffConfig(ignore_order=True)
        diff = JSONDiff(config)

        old = {"items": [1, 2, 3]}
        new = {"items": [3, 1, 2]}

        items = diff.compare(old, new)

        # Should be no difference when ignoring order
        assert len(items) == 0


# ============================================================================
# Run Comparator Tests
# ============================================================================


class TestRunComparator:
    """Tests for RunComparator."""

    def test_compare_identical_runs(
        self,
        sample_journey_result: JourneyResult,
    ) -> None:
        """Test comparing identical runs."""
        comparator = RunComparator()
        result = comparator.compare(
            [sample_journey_result],
            [sample_journey_result],
        )

        assert not result.has_regressions
        assert not result.has_improvements
        assert len(result.added_steps) == 0
        assert len(result.removed_steps) == 0

    def test_detect_regression(
        self,
        sample_journey_result: JourneyResult,
        sample_failed_journey_result: JourneyResult,
    ) -> None:
        """Test detecting regression (pass to fail)."""
        comparator = RunComparator()
        result = comparator.compare(
            [sample_journey_result],
            [sample_failed_journey_result],
        )

        assert result.has_regressions
        assert result.regression_count == 1
        regressions = result.get_regressions()
        assert len(regressions) == 1
        assert regressions[0].step_name == "step2"
        assert regressions[0].change_type == ChangeType.PASS_TO_FAIL

    def test_detect_improvement(
        self,
        sample_journey_result: JourneyResult,
        sample_failed_journey_result: JourneyResult,
    ) -> None:
        """Test detecting improvement (fail to pass)."""
        comparator = RunComparator()
        result = comparator.compare(
            [sample_failed_journey_result],  # old: failed
            [sample_journey_result],  # new: passed
        )

        assert result.has_improvements
        assert result.improvement_count == 1
        improvements = result.get_improvements()
        assert len(improvements) == 1
        assert improvements[0].step_name == "step2"
        assert improvements[0].change_type == ChangeType.FAIL_TO_PASS

    def test_detect_added_step(self) -> None:
        """Test detecting added steps."""
        now = datetime.now()
        old_result = JourneyResult(
            journey_name="test",
            success=True,
            started_at=now,
            finished_at=now,
            step_results=[
                StepResult(
                    step_name="step1",
                    success=True,
                    started_at=now,
                    finished_at=now,
                    duration_ms=100.0,
                ),
            ],
            duration_ms=100.0,
        )

        new_result = JourneyResult(
            journey_name="test",
            success=True,
            started_at=now,
            finished_at=now,
            step_results=[
                StepResult(
                    step_name="step1",
                    success=True,
                    started_at=now,
                    finished_at=now,
                    duration_ms=100.0,
                ),
                StepResult(
                    step_name="step2",
                    success=True,
                    started_at=now,
                    finished_at=now,
                    duration_ms=100.0,
                ),
            ],
            duration_ms=200.0,
        )

        comparator = RunComparator()
        result = comparator.compare([old_result], [new_result])

        assert len(result.added_steps) == 1
        assert "step2" in result.added_steps[0]

    def test_detect_removed_step(self) -> None:
        """Test detecting removed steps."""
        now = datetime.now()
        old_result = JourneyResult(
            journey_name="test",
            success=True,
            started_at=now,
            finished_at=now,
            step_results=[
                StepResult(
                    step_name="step1",
                    success=True,
                    started_at=now,
                    finished_at=now,
                    duration_ms=100.0,
                ),
                StepResult(
                    step_name="step2",
                    success=True,
                    started_at=now,
                    finished_at=now,
                    duration_ms=100.0,
                ),
            ],
            duration_ms=200.0,
        )

        new_result = JourneyResult(
            journey_name="test",
            success=True,
            started_at=now,
            finished_at=now,
            step_results=[
                StepResult(
                    step_name="step1",
                    success=True,
                    started_at=now,
                    finished_at=now,
                    duration_ms=100.0,
                ),
            ],
            duration_ms=100.0,
        )

        comparator = RunComparator()
        result = comparator.compare([old_result], [new_result])

        assert len(result.removed_steps) == 1
        assert "step2" in result.removed_steps[0]

    def test_detect_timing_change(self) -> None:
        """Test detecting significant timing changes."""
        now = datetime.now()
        old_result = JourneyResult(
            journey_name="test",
            success=True,
            started_at=now,
            finished_at=now,
            step_results=[
                StepResult(
                    step_name="step1",
                    success=True,
                    started_at=now,
                    finished_at=now,
                    duration_ms=100.0,
                ),
            ],
            duration_ms=100.0,
        )

        new_result = JourneyResult(
            journey_name="test",
            success=True,
            started_at=now,
            finished_at=now,
            step_results=[
                StepResult(
                    step_name="step1",
                    success=True,
                    started_at=now,
                    finished_at=now,
                    duration_ms=200.0,  # 100% slower
                ),
            ],
            duration_ms=200.0,
        )

        config = DiffConfig(timing_threshold_percent=10.0)
        comparator = RunComparator(config)
        result = comparator.compare([old_result], [new_result])

        assert result.has_timing_degradation
        assert len(result.timing_diffs) == 1
        assert result.timing_diffs[0].diff_percent == 100.0

    def test_detect_response_change(self) -> None:
        """Test detecting response body changes."""
        now = datetime.now()
        old_result = JourneyResult(
            journey_name="test",
            success=True,
            started_at=now,
            finished_at=now,
            step_results=[
                StepResult(
                    step_name="step1",
                    success=True,
                    started_at=now,
                    finished_at=now,
                    duration_ms=100.0,
                    response={"status_code": 200, "body": {"name": "old"}},
                ),
            ],
            duration_ms=100.0,
        )

        new_result = JourneyResult(
            journey_name="test",
            success=True,
            started_at=now,
            finished_at=now,
            step_results=[
                StepResult(
                    step_name="step1",
                    success=True,
                    started_at=now,
                    finished_at=now,
                    duration_ms=100.0,
                    response={"status_code": 200, "body": {"name": "new"}},
                ),
            ],
            duration_ms=100.0,
        )

        comparator = RunComparator()
        result = comparator.compare([old_result], [new_result])

        assert len(result.response_diffs) == 1
        assert result.response_diffs[0].has_changes
        assert len(result.response_diffs[0].body_diffs) > 0


# ============================================================================
# Baseline Manager Tests
# ============================================================================


class TestBaselineManager:
    """Tests for BaselineManager."""

    def test_save_and_load(
        self,
        sample_journey_result: JourneyResult,
    ) -> None:
        """Test saving and loading baselines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BaselineManager(tmpdir)

            # Save baseline
            path = manager.save([sample_journey_result], "test_baseline")
            assert path.exists()

            # Load baseline
            data = manager.load("test_baseline")
            assert data is not None
            assert len(data) == 1
            assert data[0]["journey_name"] == "test_journey"

    def test_list_baselines(
        self,
        sample_journey_result: JourneyResult,
    ) -> None:
        """Test listing baselines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BaselineManager(tmpdir)

            manager.save([sample_journey_result], "baseline1")
            manager.save([sample_journey_result], "baseline2")

            baselines = manager.list_baselines()
            assert len(baselines) == 2
            names = [b["name"] for b in baselines]
            assert "baseline1" in names
            assert "baseline2" in names

    def test_delete_baseline(
        self,
        sample_journey_result: JourneyResult,
    ) -> None:
        """Test deleting baselines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BaselineManager(tmpdir)

            manager.save([sample_journey_result], "test_baseline")
            assert manager.delete("test_baseline")
            assert manager.load("test_baseline") is None

    def test_delete_nonexistent(self) -> None:
        """Test deleting non-existent baseline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BaselineManager(tmpdir)
            assert not manager.delete("nonexistent")

    def test_compare_against_baseline(
        self,
        sample_journey_result: JourneyResult,
        sample_failed_journey_result: JourneyResult,
    ) -> None:
        """Test comparing against a saved baseline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BaselineManager(tmpdir)

            # Save passing result as baseline
            manager.save([sample_journey_result], "baseline")

            # Compare failing result against baseline
            result = manager.compare([sample_failed_journey_result], "baseline")

            assert result is not None
            assert result.has_regressions

    def test_compare_against_nonexistent_baseline(
        self,
        sample_journey_result: JourneyResult,
    ) -> None:
        """Test comparing against non-existent baseline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BaselineManager(tmpdir)
            result = manager.compare([sample_journey_result], "nonexistent")
            assert result is None


# ============================================================================
# Snapshot Manager Tests
# ============================================================================


class TestSnapshotManager:
    """Tests for SnapshotManager."""

    def test_save_and_load(self) -> None:
        """Test saving and loading snapshots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(tmpdir)

            response = {"id": 1, "name": "Test", "items": [1, 2, 3]}
            path = manager.save("test_response", response)

            assert path.exists()

            loaded = manager.load("test_response")
            assert loaded == response

    def test_compare_matching(self) -> None:
        """Test comparing matching responses."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(tmpdir)

            response = {"id": 1, "name": "Test"}
            manager.save("test_response", response)

            result = manager.compare("test_response", response)

            assert result["matches"]
            assert result["snapshot_exists"]
            assert len(result["diffs"]) == 0

    def test_compare_different(self) -> None:
        """Test comparing different responses."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(tmpdir)

            expected = {"id": 1, "name": "Test"}
            actual = {"id": 1, "name": "Different"}

            manager.save("test_response", expected)
            result = manager.compare("test_response", actual)

            assert not result["matches"]
            assert len(result["diffs"]) > 0

    def test_compare_nonexistent(self) -> None:
        """Test comparing against non-existent snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(tmpdir)

            result = manager.compare("nonexistent", {"id": 1})

            assert not result["matches"]
            assert not result["snapshot_exists"]

    def test_update_snapshot(self) -> None:
        """Test updating an existing snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(tmpdir)

            manager.save("test", {"version": 1})
            manager.update("test", {"version": 2})

            loaded = manager.load("test")
            assert loaded == {"version": 2}

    def test_list_snapshots(self) -> None:
        """Test listing snapshots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(tmpdir)

            manager.save("snapshot1", {"id": 1})
            manager.save("snapshot2", {"id": 2})

            snapshots = manager.list_snapshots()
            assert len(snapshots) == 2

    def test_delete_snapshot(self) -> None:
        """Test deleting a snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(tmpdir)

            manager.save("test", {"id": 1})
            assert manager.delete("test")
            assert manager.load("test") is None


# ============================================================================
# Trend Analyzer Tests
# ============================================================================


class TestTrendAnalyzer:
    """Tests for TrendAnalyzer."""

    def test_record_and_get_trend(
        self,
        sample_journey_result: JourneyResult,
    ) -> None:
        """Test recording and retrieving trend data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            analyzer = TrendAnalyzer(tmpdir)

            analyzer.record(sample_journey_result, "run-001")

            trend = analyzer.get_trend("test_journey")

            assert trend.journey_name == "test_journey"
            assert len(trend.points) == 1
            assert trend.points[0].run_id == "run-001"
            assert trend.points[0].pass_rate == 100.0

    def test_trend_direction(self) -> None:
        """Test determining trend direction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            TrendAnalyzer(tmpdir)

            # Create improving trend
            trend = TrendData(
                journey_name="test",
                points=[
                    TrendPoint(
                        run_id=f"run-{i}",
                        timestamp=datetime.now() + timedelta(hours=i),
                        pass_rate=50.0 + i * 10,  # 50, 60, 70, 80, 90
                        total_steps=10,
                        passed_steps=int(5 + i),
                        failed_steps=int(5 - i),
                        total_duration_ms=1000.0,
                        avg_step_duration_ms=100.0,
                    )
                    for i in range(5)
                ],
            )

            assert trend.pass_rate_trend == "improving"

    def test_timing_trend(self) -> None:
        """Test timing trend detection."""
        trend = TrendData(
            journey_name="test",
            points=[
                TrendPoint(
                    run_id=f"run-{i}",
                    timestamp=datetime.now() + timedelta(hours=i),
                    pass_rate=100.0,
                    total_steps=10,
                    passed_steps=10,
                    failed_steps=0,
                    total_duration_ms=1000.0 + i * 200,  # Getting slower
                    avg_step_duration_ms=100.0 + i * 20,
                )
                for i in range(5)
            ],
        )

        assert trend.timing_trend == "slowing"

    def test_check_degradation(self) -> None:
        """Test degradation detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            analyzer = TrendAnalyzer(tmpdir, degradation_threshold=10.0)

            # Create degrading trend
            trend = TrendData(
                journey_name="test",
                points=[
                    TrendPoint(
                        run_id=f"run-{i}",
                        timestamp=datetime.now() + timedelta(hours=i),
                        pass_rate=90.0 - i * 10,  # 90, 80, 70, 60, 50
                        total_steps=10,
                        passed_steps=int(9 - i),
                        failed_steps=int(1 + i),
                        total_duration_ms=1000.0,
                        avg_step_duration_ms=100.0,
                    )
                    for i in range(5)
                ],
            )

            # Save trend data
            trend_file = analyzer._trend_file("test")
            with open(trend_file, "w") as f:
                json.dump(trend.to_dict(), f)

            result = analyzer.check_degradation("test")

            assert result["pass_rate_degrading"]
            assert len(result["alerts"]) > 0

    def test_average_pass_rate(self) -> None:
        """Test average pass rate calculation."""
        trend = TrendData(
            journey_name="test",
            points=[
                TrendPoint(
                    run_id=f"run-{i}",
                    timestamp=datetime.now() + timedelta(hours=i),
                    pass_rate=float(i * 20 + 20),  # 20, 40, 60, 80, 100
                    total_steps=10,
                    passed_steps=i * 2 + 2,
                    failed_steps=10 - (i * 2 + 2),
                    total_duration_ms=1000.0,
                    avg_step_duration_ms=100.0,
                )
                for i in range(5)
            ],
        )

        # Average of all: (20 + 40 + 60 + 80 + 100) / 5 = 60
        assert trend.average_pass_rate() == 60.0

        # Average of last 3: (60 + 80 + 100) / 3 = 80
        assert trend.average_pass_rate(last_n=3) == 80.0


# ============================================================================
# Comparison Reporter Tests
# ============================================================================


class TestComparisonReporter:
    """Tests for comparison report generation."""

    def test_text_report_generation(self) -> None:
        """Test generating text comparison reports."""
        result = ComparisonResult(
            old_run_id="baseline",
            new_run_id="current",
            status_changes=[
                StatusChange(
                    step_name="step1",
                    path_name="main",
                    journey_name="test",
                    change_type=ChangeType.PASS_TO_FAIL,
                    new_error="HTTP 500",
                ),
            ],
        )

        reporter = ComparisonReporter()
        report = reporter.generate(result)

        assert "VenomQA Comparison Report" in report
        assert "baseline" in report
        assert "current" in report
        assert "Regressions" in report.upper() or "REGRESSIONS" in report
        assert "step1" in report

    def test_html_report_generation(self) -> None:
        """Test generating HTML comparison reports."""
        result = ComparisonResult(
            old_run_id="baseline",
            new_run_id="current",
            status_changes=[
                StatusChange(
                    step_name="step1",
                    path_name="main",
                    journey_name="test",
                    change_type=ChangeType.PASS_TO_FAIL,
                    new_error="HTTP 500",
                ),
            ],
        )

        reporter = ComparisonHTMLReporter()
        report = reporter.generate(result)

        assert "<!DOCTYPE html>" in report
        assert "VenomQA Comparison Report" in report
        assert "baseline" in report
        assert "step1" in report


# ============================================================================
# Comparison Result Tests
# ============================================================================


class TestComparisonResult:
    """Tests for ComparisonResult model."""

    def test_has_regressions(self) -> None:
        """Test regression detection property."""
        result = ComparisonResult(
            old_run_id="old",
            new_run_id="new",
            status_changes=[
                StatusChange(
                    step_name="step1",
                    path_name="main",
                    journey_name="test",
                    change_type=ChangeType.PASS_TO_FAIL,
                ),
            ],
        )

        assert result.has_regressions
        assert result.regression_count == 1

    def test_has_improvements(self) -> None:
        """Test improvement detection property."""
        result = ComparisonResult(
            old_run_id="old",
            new_run_id="new",
            status_changes=[
                StatusChange(
                    step_name="step1",
                    path_name="main",
                    journey_name="test",
                    change_type=ChangeType.FAIL_TO_PASS,
                ),
            ],
        )

        assert result.has_improvements
        assert result.improvement_count == 1

    def test_summary(self) -> None:
        """Test summary generation."""
        result = ComparisonResult(
            old_run_id="old",
            new_run_id="new",
            status_changes=[
                StatusChange(
                    step_name="step1",
                    path_name="main",
                    journey_name="test",
                    change_type=ChangeType.PASS_TO_FAIL,
                    new_error="Error",
                ),
            ],
            added_steps=["new_step"],
        )

        summary = result.summary()

        assert "old -> new" in summary
        assert "Regressions" in summary
        assert "step1" in summary

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        result = ComparisonResult(
            old_run_id="old",
            new_run_id="new",
        )

        data = result.to_dict()

        assert data["old_run_id"] == "old"
        assert data["new_run_id"] == "new"
        assert "compared_at" in data
        assert "has_regressions" in data


# ============================================================================
# Integration Tests
# ============================================================================


class TestComparisonIntegration:
    """Integration tests for the comparison module."""

    def test_full_comparison_workflow(self) -> None:
        """Test a complete comparison workflow."""
        now = datetime.now()

        # Create two journey results with differences
        baseline_result = JourneyResult(
            journey_name="checkout",
            success=True,
            started_at=now,
            finished_at=now + timedelta(seconds=1),
            step_results=[
                StepResult(
                    step_name="login",
                    success=True,
                    started_at=now,
                    finished_at=now + timedelta(milliseconds=100),
                    duration_ms=100.0,
                    response={"status_code": 200, "body": {"token": "abc"}},
                ),
                StepResult(
                    step_name="add_to_cart",
                    success=True,
                    started_at=now + timedelta(milliseconds=100),
                    finished_at=now + timedelta(milliseconds=200),
                    duration_ms=100.0,
                ),
                StepResult(
                    step_name="checkout",
                    success=True,
                    started_at=now + timedelta(milliseconds=200),
                    finished_at=now + timedelta(milliseconds=300),
                    duration_ms=100.0,
                ),
            ],
            duration_ms=1000.0,
        )

        current_result = JourneyResult(
            journey_name="checkout",
            success=False,
            started_at=now,
            finished_at=now + timedelta(seconds=2),
            step_results=[
                StepResult(
                    step_name="login",
                    success=True,
                    started_at=now,
                    finished_at=now + timedelta(milliseconds=150),  # Slower
                    duration_ms=150.0,
                    response={"status_code": 200, "body": {"token": "xyz"}},  # Different
                ),
                StepResult(
                    step_name="add_to_cart",
                    success=True,
                    started_at=now + timedelta(milliseconds=150),
                    finished_at=now + timedelta(milliseconds=250),
                    duration_ms=100.0,
                ),
                StepResult(
                    step_name="checkout",
                    success=False,  # Regression
                    started_at=now + timedelta(milliseconds=250),
                    finished_at=now + timedelta(milliseconds=350),
                    duration_ms=100.0,
                    error="Payment failed",
                ),
            ],
            issues=[
                Issue(
                    journey="checkout",
                    path="main",
                    step="checkout",
                    error="Payment failed",
                    severity=Severity.HIGH,
                )
            ],
            duration_ms=2000.0,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            # Save baseline
            baseline_manager = BaselineManager(tmpdir)
            baseline_manager.save([baseline_result], "v1.0")

            # Compare current against baseline
            comparison = baseline_manager.compare([current_result], "v1.0")

            assert comparison is not None
            assert comparison.has_regressions
            assert comparison.regression_count == 1

            regressions = comparison.get_regressions()
            assert len(regressions) == 1
            assert regressions[0].step_name == "checkout"
            assert regressions[0].new_error == "Payment failed"

            # Generate reports
            text_reporter = ComparisonReporter()
            text_report = text_reporter.generate(comparison)
            assert "checkout" in text_report
            assert "Payment failed" in text_report

            html_reporter = ComparisonHTMLReporter()
            html_report = html_reporter.generate(comparison)
            assert "<!DOCTYPE html>" in html_report
            assert "checkout" in html_report

    def test_snapshot_workflow(self) -> None:
        """Test complete snapshot workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(tmpdir)

            # Initial response
            response_v1 = {
                "users": [
                    {"id": 1, "name": "John", "email": "john@example.com"},
                    {"id": 2, "name": "Jane", "email": "jane@example.com"},
                ],
                "total": 2,
                "timestamp": "2024-01-01T00:00:00Z",
            }

            # Save snapshot
            manager.save("get_users", response_v1)

            # Compare identical response
            result = manager.compare("get_users", response_v1)
            assert result["matches"]

            # Compare with changes (ignoring timestamp)
            response_v2 = {
                "users": [
                    {"id": 1, "name": "John", "email": "john@example.com"},
                    {"id": 2, "name": "Jane", "email": "jane.new@example.com"},  # Changed
                ],
                "total": 2,
                "timestamp": "2024-01-02T00:00:00Z",  # Different timestamp
            }

            # Without ignore patterns, should detect changes
            result = manager.compare("get_users", response_v2)
            assert not result["matches"]
            assert len(result["diffs"]) > 0

            # Update snapshot
            manager.update("get_users", response_v2)
            result = manager.compare("get_users", response_v2)
            assert result["matches"]

    def test_trend_workflow(self) -> None:
        """Test complete trend analysis workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            analyzer = TrendAnalyzer(tmpdir)

            # Simulate multiple runs with varying results
            now = datetime.now()

            for i in range(10):
                pass_rate = 90 + (i % 3) * 5  # Varies between 90, 95, 100
                passed = int(10 * pass_rate / 100)

                result = JourneyResult(
                    journey_name="daily_test",
                    success=pass_rate == 100,
                    started_at=now + timedelta(days=i),
                    finished_at=now + timedelta(days=i, minutes=5),
                    step_results=[
                        StepResult(
                            step_name=f"step_{j}",
                            success=j < passed,
                            started_at=now + timedelta(days=i, seconds=j),
                            finished_at=now + timedelta(days=i, seconds=j + 1),
                            duration_ms=100.0,
                            error=None if j < passed else "Failed",
                        )
                        for j in range(10)
                    ],
                    duration_ms=5000.0,
                )

                analyzer.record(result, f"run-{i:03d}")

            # Get trend data
            trend = analyzer.get_trend("daily_test")

            assert trend.journey_name == "daily_test"
            assert len(trend.points) == 10
            assert trend.average_pass_rate() > 0

            # Check all trends
            all_trends = analyzer.get_all_trends()
            assert "daily_test" in all_trends
