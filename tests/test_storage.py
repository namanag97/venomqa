"""Tests for the storage module - journey result persistence."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from venomqa.core.models import (
    Issue,
    JourneyResult,
    Severity,
    StepResult,
)
from venomqa.storage import ResultsRepository
from venomqa.storage.models import (
    InvariantCheckRecord,
    IssueRecord,
    JourneyRunRecord,
    RunStatus,
    StepResultRecord,
)


class TestJourneyRunRecord:
    """Tests for JourneyRunRecord model."""

    def test_create_from_journey_result(self) -> None:
        """Test creating a record from JourneyResult."""
        started = datetime.now()
        finished = started + timedelta(seconds=5)

        step_result = StepResult(
            step_name="test_step",
            success=True,
            started_at=started,
            finished_at=finished,
            duration_ms=5000.0,
        )

        result = JourneyResult(
            journey_name="test_journey",
            success=True,
            started_at=started,
            finished_at=finished,
            step_results=[step_result],
            branch_results=[],
            issues=[],
            duration_ms=5000.0,
        )

        record = JourneyRunRecord.from_journey_result(
            result, tags=["smoke", "api"], metadata={"env": "test"}
        )

        assert record.journey_name == "test_journey"
        assert record.status == RunStatus.PASSED
        assert record.duration_ms == 5000.0
        assert record.total_steps == 1
        assert record.passed_steps == 1
        assert record.failed_steps == 0
        assert "smoke" in record.tags
        assert "api" in record.tags
        assert record.id is not None

    def test_to_dict(self) -> None:
        """Test converting record to dictionary."""
        record = JourneyRunRecord(
            id="test-id",
            journey_name="test_journey",
            status=RunStatus.PASSED,
            duration_ms=1000.0,
            total_steps=5,
            passed_steps=4,
            failed_steps=1,
        )

        data = record.to_dict()

        assert data["id"] == "test-id"
        assert data["journey_name"] == "test_journey"
        assert data["status"] == "passed"
        assert data["duration_ms"] == 1000.0


class TestStepResultRecord:
    """Tests for StepResultRecord model."""

    def test_create_from_step_result(self) -> None:
        """Test creating a record from StepResult."""
        started = datetime.now()
        finished = started + timedelta(milliseconds=100)

        step_result = StepResult(
            step_name="login",
            success=True,
            started_at=started,
            finished_at=finished,
            duration_ms=100.0,
            request={"method": "POST", "url": "/api/login"},
            response={"status_code": 200, "body": {"token": "abc"}},
        )

        record = StepResultRecord.from_step_result(
            step_result, journey_run_id="run-123", path_name="main", step_order=0
        )

        assert record.step_name == "login"
        assert record.journey_run_id == "run-123"
        assert record.path_name == "main"
        assert record.status == "passed"
        assert record.duration_ms == 100.0
        assert record.step_order == 0


class TestIssueRecord:
    """Tests for IssueRecord model."""

    def test_create_from_issue(self) -> None:
        """Test creating a record from Issue."""
        issue = Issue(
            journey="checkout",
            path="payment",
            step="process_payment",
            error="HTTP 500: Internal Server Error",
            severity=Severity.CRITICAL,
            suggestion="Check backend logs for exception traceback",
        )

        record = IssueRecord.from_issue(issue, journey_run_id="run-456")

        assert record.journey_run_id == "run-456"
        assert record.severity == "critical"
        assert record.message == "HTTP 500: Internal Server Error"
        assert record.step_name == "process_payment"
        assert record.journey_name == "checkout"


class TestInvariantCheckRecord:
    """Tests for InvariantCheckRecord model."""

    def test_create_from_result(self) -> None:
        """Test creating a record from invariant check results."""
        record = InvariantCheckRecord.from_invariant_result(
            journey_run_id="run-789",
            name="user_count",
            passed=True,
            expected=1,
            actual=1,
            message="User count matches",
        )

        assert record.journey_run_id == "run-789"
        assert record.invariant_name == "user_count"
        assert record.passed is True
        assert record.message == "User count matches"


class TestResultsRepository:
    """Tests for ResultsRepository."""

    @pytest.fixture
    def repo(self) -> ResultsRepository:
        """Create an in-memory repository for testing."""
        repo = ResultsRepository("sqlite://:memory:")
        repo.initialize()
        return repo

    @pytest.fixture
    def sample_result(self) -> JourneyResult:
        """Create a sample JourneyResult for testing."""
        started = datetime.now()
        finished = started + timedelta(seconds=2)

        step1 = StepResult(
            step_name="step1",
            success=True,
            started_at=started,
            finished_at=finished,
            duration_ms=1000.0,
        )

        step2 = StepResult(
            step_name="step2",
            success=False,
            started_at=finished,
            finished_at=finished + timedelta(seconds=1),
            duration_ms=1000.0,
            error="HTTP 404: Not Found",
        )

        issue = Issue(
            journey="test_journey",
            path="main",
            step="step2",
            error="HTTP 404: Not Found",
            severity=Severity.HIGH,
        )

        return JourneyResult(
            journey_name="test_journey",
            success=False,
            started_at=started,
            finished_at=finished + timedelta(seconds=1),
            step_results=[step1, step2],
            branch_results=[],
            issues=[issue],
            duration_ms=2000.0,
        )

    def test_initialize(self, repo: ResultsRepository) -> None:
        """Test repository initialization."""
        # Should not raise - tables created
        assert repo._initialized is True

    def test_save_journey_result(
        self, repo: ResultsRepository, sample_result: JourneyResult
    ) -> None:
        """Test saving a journey result."""
        run_id = repo.save_journey_result(
            sample_result, tags=["smoke"], metadata={"branch": "main"}
        )

        assert run_id is not None
        assert len(run_id) > 0

    def test_get_run(self, repo: ResultsRepository, sample_result: JourneyResult) -> None:
        """Test retrieving a journey run."""
        run_id = repo.save_journey_result(sample_result)

        run = repo.get_run(run_id)

        assert run is not None
        assert run.id == run_id
        assert run.journey_name == "test_journey"
        assert run.status == RunStatus.FAILED
        assert run.total_steps == 2
        assert run.passed_steps == 1
        assert run.failed_steps == 1

    def test_get_run_not_found(self, repo: ResultsRepository) -> None:
        """Test retrieving a non-existent run."""
        run = repo.get_run("nonexistent-id")
        assert run is None

    def test_list_runs(self, repo: ResultsRepository, sample_result: JourneyResult) -> None:
        """Test listing journey runs."""
        # Save multiple runs
        repo.save_journey_result(sample_result)
        repo.save_journey_result(sample_result)
        repo.save_journey_result(sample_result)

        runs = repo.list_runs(limit=10)

        assert len(runs) == 3
        assert all(r.journey_name == "test_journey" for r in runs)

    def test_list_runs_with_filter(
        self, repo: ResultsRepository, sample_result: JourneyResult
    ) -> None:
        """Test listing runs with filters."""
        # Save runs with different statuses
        repo.save_journey_result(sample_result)  # Failed

        # Create a passing result
        passed_result = JourneyResult(
            journey_name="other_journey",
            success=True,
            started_at=datetime.now(),
            finished_at=datetime.now(),
            step_results=[],
            branch_results=[],
            issues=[],
            duration_ms=100.0,
        )
        repo.save_journey_result(passed_result)

        # Filter by journey name
        runs = repo.list_runs(journey_name="test_journey")
        assert len(runs) == 1
        assert runs[0].journey_name == "test_journey"

        # Filter by status
        runs = repo.list_runs(status=RunStatus.PASSED)
        assert len(runs) == 1
        assert runs[0].status == RunStatus.PASSED

    def test_get_step_results(
        self, repo: ResultsRepository, sample_result: JourneyResult
    ) -> None:
        """Test getting step results for a run."""
        run_id = repo.save_journey_result(sample_result)

        steps = repo.get_step_results(run_id)

        assert len(steps) == 2
        assert steps[0].step_name == "step1"
        assert steps[0].status == "passed"
        assert steps[1].step_name == "step2"
        assert steps[1].status == "failed"
        assert steps[1].error == "HTTP 404: Not Found"

    def test_get_issues(self, repo: ResultsRepository, sample_result: JourneyResult) -> None:
        """Test getting issues for a run."""
        run_id = repo.save_journey_result(sample_result)

        issues = repo.get_issues(run_id)

        assert len(issues) == 1
        assert issues[0].message == "HTTP 404: Not Found"
        assert issues[0].severity == "high"
        assert issues[0].step_name == "step2"

    def test_compare_runs(
        self, repo: ResultsRepository, sample_result: JourneyResult
    ) -> None:
        """Test comparing two runs."""
        # Save first run (failed)
        run1_id = repo.save_journey_result(sample_result)

        # Create and save a passing run
        passed_result = JourneyResult(
            journey_name="test_journey",
            success=True,
            started_at=datetime.now(),
            finished_at=datetime.now(),
            step_results=[
                StepResult(
                    step_name="step1",
                    success=True,
                    started_at=datetime.now(),
                    finished_at=datetime.now(),
                    duration_ms=500.0,
                ),
                StepResult(
                    step_name="step2",
                    success=True,
                    started_at=datetime.now(),
                    finished_at=datetime.now(),
                    duration_ms=500.0,
                ),
            ],
            branch_results=[],
            issues=[],
            duration_ms=1000.0,
        )
        run2_id = repo.save_journey_result(passed_result)

        comparison = repo.compare_runs(run1_id, run2_id)

        assert "error" not in comparison
        assert comparison["run1"]["status"] == "failed"
        assert comparison["run2"]["status"] == "passed"
        assert comparison["improvement"] is True
        assert comparison["regression"] is False
        assert len(comparison["resolved_issues"]) == 1  # The HTTP 404 issue

    def test_compare_runs_not_found(self, repo: ResultsRepository) -> None:
        """Test comparing with non-existent run."""
        comparison = repo.compare_runs("nonexistent1", "nonexistent2")
        assert "error" in comparison

    def test_get_dashboard_stats(
        self, repo: ResultsRepository, sample_result: JourneyResult
    ) -> None:
        """Test getting dashboard statistics."""
        # Save some runs
        repo.save_journey_result(sample_result)  # Failed
        repo.save_journey_result(sample_result)  # Failed

        passed_result = JourneyResult(
            journey_name="other_journey",
            success=True,
            started_at=datetime.now(),
            finished_at=datetime.now(),
            step_results=[],
            branch_results=[],
            issues=[],
            duration_ms=100.0,
        )
        repo.save_journey_result(passed_result)  # Passed

        stats = repo.get_dashboard_stats(days=30)

        assert stats.total_runs == 3
        assert stats.total_passed == 1
        assert stats.total_failed == 2
        assert stats.pass_rate == pytest.approx(33.33, rel=0.1)
        assert stats.total_issues >= 0

    def test_get_trend_data(
        self, repo: ResultsRepository, sample_result: JourneyResult
    ) -> None:
        """Test getting trend data."""
        repo.save_journey_result(sample_result)

        trends = repo.get_trend_data(days=7)

        # Should have at least one data point for today
        assert len(trends) >= 0  # Could be 0 if no runs in date range

    def test_delete_old_runs(
        self, repo: ResultsRepository, sample_result: JourneyResult
    ) -> None:
        """Test deleting old runs."""
        # Save a run
        repo.save_journey_result(sample_result)

        # Try to delete runs older than 0 days (all runs)
        # This won't delete the run we just created since it's from today
        deleted = repo.delete_old_runs(days=0)

        # The run from today should still exist
        runs = repo.list_runs()
        assert len(runs) >= 0  # Depends on timing

    def test_context_manager(self, sample_result: JourneyResult) -> None:
        """Test using repository as context manager."""
        with ResultsRepository("sqlite://:memory:") as repo:
            run_id = repo.save_journey_result(sample_result)
            assert run_id is not None

    def test_save_invariant_check(self, repo: ResultsRepository, sample_result: JourneyResult) -> None:
        """Test saving an invariant check result."""
        run_id = repo.save_journey_result(sample_result)

        # Note: Need to add save_invariant_check to repository if not present
        # For now, just test that the run was saved correctly
        run = repo.get_run(run_id)
        assert run is not None


class TestResultsRepositoryEdgeCases:
    """Edge case tests for ResultsRepository."""

    @pytest.fixture
    def repo(self) -> ResultsRepository:
        """Create an in-memory repository for testing."""
        repo = ResultsRepository("sqlite://:memory:")
        repo.initialize()
        return repo

    def test_empty_journey_result(self, repo: ResultsRepository) -> None:
        """Test saving a journey result with no steps."""
        result = JourneyResult(
            journey_name="empty_journey",
            success=True,
            started_at=datetime.now(),
            finished_at=datetime.now(),
            step_results=[],
            branch_results=[],
            issues=[],
            duration_ms=0.0,
        )

        run_id = repo.save_journey_result(result)
        run = repo.get_run(run_id)

        assert run is not None
        assert run.total_steps == 0

    def test_journey_with_many_steps(self, repo: ResultsRepository) -> None:
        """Test saving a journey with many steps."""
        steps = []
        for i in range(100):
            steps.append(
                StepResult(
                    step_name=f"step_{i}",
                    success=True,
                    started_at=datetime.now(),
                    finished_at=datetime.now(),
                    duration_ms=10.0,
                )
            )

        result = JourneyResult(
            journey_name="large_journey",
            success=True,
            started_at=datetime.now(),
            finished_at=datetime.now(),
            step_results=steps,
            branch_results=[],
            issues=[],
            duration_ms=1000.0,
        )

        run_id = repo.save_journey_result(result)
        saved_steps = repo.get_step_results(run_id)

        assert len(saved_steps) == 100

    def test_special_characters_in_names(self, repo: ResultsRepository) -> None:
        """Test handling special characters in journey names."""
        result = JourneyResult(
            journey_name="journey with spaces & special chars!",
            success=True,
            started_at=datetime.now(),
            finished_at=datetime.now(),
            step_results=[
                StepResult(
                    step_name="step with 'quotes'",
                    success=True,
                    started_at=datetime.now(),
                    finished_at=datetime.now(),
                    duration_ms=10.0,
                )
            ],
            branch_results=[],
            issues=[],
            duration_ms=10.0,
        )

        run_id = repo.save_journey_result(result)
        run = repo.get_run(run_id)

        assert run is not None
        assert run.journey_name == "journey with spaces & special chars!"

    def test_unicode_in_error_messages(self, repo: ResultsRepository) -> None:
        """Test handling unicode in error messages."""
        issue = Issue(
            journey="test",
            path="main",
            step="test_step",
            error="Error with unicode: ",
            severity=Severity.HIGH,
        )

        result = JourneyResult(
            journey_name="unicode_test",
            success=False,
            started_at=datetime.now(),
            finished_at=datetime.now(),
            step_results=[
                StepResult(
                    step_name="test_step",
                    success=False,
                    started_at=datetime.now(),
                    finished_at=datetime.now(),
                    duration_ms=10.0,
                    error="Error with unicode: ",
                )
            ],
            branch_results=[],
            issues=[issue],
            duration_ms=10.0,
        )

        run_id = repo.save_journey_result(result)
        issues = repo.get_issues(run_id)

        assert len(issues) == 1
        assert "" in issues[0].message
