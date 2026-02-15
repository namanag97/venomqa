"""Tests for core domain models."""

from __future__ import annotations

from datetime import datetime

import pytest

from venomqa.core.context import ExecutionContext
from venomqa.core.models import (
    Branch,
    BranchResult,
    Checkpoint,
    Issue,
    Journey,
    JourneyResult,
    Path,
    PathResult,
    Severity,
    Step,
    StepResult,
)
from venomqa.errors import JourneyValidationError
from .conftest import MockClient, MockHTTPResponse


class TestStep:
    """Tests for Step model."""

    def test_step_creation(self) -> None:
        def action(client, ctx):
            return client.get("/test")

        step = Step(name="test_step", action=action, description="Test step")

        assert step.name == "test_step"
        assert step.description == "Test step"
        assert step.expect_failure is False
        assert step.timeout is None
        assert step.retries == 0

    def test_step_with_options(self) -> None:
        def action(client, ctx):
            return client.get("/test")

        step = Step(
            name="test_step",
            action=action,
            description="Test step",
            expect_failure=True,
            timeout=30.0,
            retries=3,
        )

        assert step.expect_failure is True
        assert step.timeout == 30.0
        assert step.retries == 3

    def test_step_action_execution(
        self, mock_client: MockClient, context: ExecutionContext
    ) -> None:
        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={"id": 1})])

        def action(client, ctx):
            return client.get("/users/1")

        step = Step(name="get_user", action=action)
        result = step.action(mock_client, context)

        assert result.status_code == 200
        assert len(mock_client.history) == 1


class TestCheckpoint:
    """Tests for Checkpoint model."""

    def test_checkpoint_creation(self) -> None:
        checkpoint = Checkpoint(name="after_setup")
        assert checkpoint.name == "after_setup"

    def test_checkpoint_is_pydantic_model(self) -> None:
        checkpoint = Checkpoint(name="test")
        assert hasattr(Checkpoint, "model_fields")


class TestPath:
    """Tests for Path model."""

    def test_path_creation(self, sample_step: Step) -> None:
        path = Path(name="test_path", steps=[sample_step], description="Test path")

        assert path.name == "test_path"
        assert len(path.steps) == 1
        assert path.description == "Test path"

    def test_path_with_multiple_steps(self) -> None:
        def action1(client, ctx):
            return client.get("/users")

        def action2(client, ctx):
            return client.post("/users")

        steps = [
            Step(name="list_users", action=action1),
            Step(name="create_user", action=action2),
        ]
        path = Path(name="multi_step", steps=steps)

        assert len(path.steps) == 2

    def test_path_with_checkpoint(self, sample_step: Step, sample_checkpoint: Checkpoint) -> None:
        path = Path(
            name="path_with_checkpoint",
            steps=[sample_step, sample_checkpoint],
        )

        assert len(path.steps) == 2
        assert isinstance(path.steps[1], Checkpoint)


class TestBranch:
    """Tests for Branch model."""

    def test_branch_creation(self, sample_checkpoint: Checkpoint, sample_path: Path) -> None:
        branch = Branch(
            checkpoint_name=sample_checkpoint.name,
            paths=[sample_path],
        )

        assert branch.checkpoint_name == sample_checkpoint.name
        assert len(branch.paths) == 1

    def test_branch_with_multiple_paths(self, sample_checkpoint: Checkpoint) -> None:
        def action1(client, ctx):
            return client.get("/users")

        def action2(client, ctx):
            return client.delete("/users/1")

        path1 = Path(name="read_path", steps=[Step(name="read", action=action1)])
        path2 = Path(name="delete_path", steps=[Step(name="delete", action=action2)])

        branch = Branch(
            checkpoint_name=sample_checkpoint.name,
            paths=[path1, path2],
        )

        assert len(branch.paths) == 2
        assert branch.paths[0].name == "read_path"
        assert branch.paths[1].name == "delete_path"


class TestJourney:
    """Tests for Journey model."""

    def test_journey_creation(self, sample_step: Step) -> None:
        journey = Journey(
            name="test_journey",
            steps=[sample_step],
            description="Test journey",
            tags=["test", "smoke"],
        )

        assert journey.name == "test_journey"
        assert len(journey.steps) == 1
        assert journey.description == "Test journey"
        assert "test" in journey.tags
        assert "smoke" in journey.tags
        assert journey.timeout is None

    def test_journey_with_timeout(self, sample_step: Step) -> None:
        journey = Journey(
            name="timed_journey",
            steps=[sample_step],
            timeout=60.0,
        )

        assert journey.timeout == 60.0

    def test_journey_validates_checkpoint_references(
        self, sample_step: Step, sample_checkpoint: Checkpoint
    ) -> None:
        branch = Branch(checkpoint_name="nonexistent", paths=[])

        with pytest.raises(JourneyValidationError, match="undefined checkpoint"):
            Journey(name="invalid", steps=[branch])

    def test_journey_accepts_valid_checkpoint_reference(
        self, sample_checkpoint: Checkpoint, sample_path: Path
    ) -> None:
        branch = Branch(checkpoint_name=sample_checkpoint.name, paths=[sample_path])

        journey = Journey(
            name="valid",
            steps=[sample_checkpoint, branch],
        )

        assert journey.name == "valid"
        assert len(journey.steps) == 2

    def test_journey_default_tags(self, sample_step: Step) -> None:
        journey = Journey(name="no_tags", steps=[sample_step])
        assert journey.tags == []


class TestStepResult:
    """Tests for StepResult model."""

    def test_step_result_creation(self) -> None:
        now = datetime.now()
        result = StepResult(
            step_name="test_step",
            success=True,
            started_at=now,
            finished_at=now,
            response={"status_code": 200},
            duration_ms=100.0,
        )

        assert result.step_name == "test_step"
        assert result.success is True
        assert result.response == {"status_code": 200}
        assert result.error is None
        assert result.duration_ms == 100.0

    def test_step_result_with_error(self) -> None:
        now = datetime.now()
        result = StepResult(
            step_name="failed_step",
            success=False,
            started_at=now,
            finished_at=now,
            error="HTTP 500",
            duration_ms=50.0,
        )

        assert result.success is False
        assert result.error == "HTTP 500"


class TestPathResult:
    """Tests for PathResult model."""

    def test_path_result_creation(self) -> None:
        result = PathResult(path_name="test_path", success=True)

        assert result.path_name == "test_path"
        assert result.success is True
        assert result.step_results == []
        assert result.error is None

    def test_path_result_with_step_results(self) -> None:
        now = datetime.now()
        step_result = StepResult(
            step_name="step1",
            success=True,
            started_at=now,
            finished_at=now,
        )
        result = PathResult(
            path_name="test_path",
            success=True,
            step_results=[step_result],
        )

        assert len(result.step_results) == 1


class TestBranchResult:
    """Tests for BranchResult model."""

    def test_branch_result_creation(self) -> None:
        result = BranchResult(checkpoint_name="after_setup")

        assert result.checkpoint_name == "after_setup"
        assert result.path_results == []
        assert result.all_passed is True

    def test_branch_result_with_failed_paths(self) -> None:
        failed_path = PathResult(path_name="failed", success=False)
        result = BranchResult(
            checkpoint_name="test",
            path_results=[failed_path],
        )

        assert result.all_passed is False


class TestIssue:
    """Tests for Issue model."""

    def test_issue_creation(self) -> None:
        issue = Issue(
            journey="test_journey",
            path="main",
            step="get_user",
            error="HTTP 404",
        )

        assert issue.journey == "test_journey"
        assert issue.path == "main"
        assert issue.step == "get_user"
        assert issue.error == "HTTP 404"
        assert issue.severity == Severity.HIGH

    def test_issue_auto_generates_suggestion(self) -> None:
        issue_401 = Issue(
            journey="test",
            path="main",
            step="auth",
            error="HTTP 401 Unauthorized",
        )
        assert "authentication" in issue_401.suggestion.lower()

        issue_404 = Issue(
            journey="test",
            path="main",
            step="get",
            error="HTTP 404 Not Found",
        )
        assert "route" in issue_404.suggestion.lower() or "found" in issue_404.suggestion.lower()

        issue_500 = Issue(
            journey="test",
            path="main",
            step="get",
            error="HTTP 500 Internal Server Error",
        )
        assert "server" in issue_500.suggestion.lower()

    def test_issue_custom_suggestion(self) -> None:
        issue = Issue(
            journey="test",
            path="main",
            step="custom",
            error="Custom error",
            suggestion="Check the config file",
        )

        assert issue.suggestion == "Check the config file"

    def test_issue_default_values(self) -> None:
        issue = Issue(
            journey="test",
            path="main",
            step="test",
            error="Error",
        )

        assert issue.logs == []
        assert issue.request is None
        assert issue.response is None


class TestJourneyResult:
    """Tests for JourneyResult model."""

    def test_journey_result_creation(self) -> None:
        now = datetime.now()
        result = JourneyResult(
            journey_name="test_journey",
            success=True,
            started_at=now,
            finished_at=now,
        )

        assert result.journey_name == "test_journey"
        assert result.success is True
        assert result.step_results == []
        assert result.branch_results == []
        assert result.issues == []

    def test_journey_result_total_steps(self) -> None:
        now = datetime.now()
        step_results = [
            StepResult(step_name="s1", success=True, started_at=now, finished_at=now),
            StepResult(
                step_name="s2", success=False, started_at=now, finished_at=now, error="Failed"
            ),
            StepResult(step_name="s3", success=True, started_at=now, finished_at=now),
        ]
        result = JourneyResult(
            journey_name="test",
            success=False,
            started_at=now,
            finished_at=now,
            step_results=step_results,
        )

        assert result.total_steps == 3
        assert result.passed_steps == 2

    def test_journey_result_total_paths(self) -> None:
        now = datetime.now()
        branch_results = [
            BranchResult(
                checkpoint_name="cp1",
                path_results=[
                    PathResult(path_name="p1", success=True),
                    PathResult(path_name="p2", success=False),
                ],
            ),
            BranchResult(
                checkpoint_name="cp2",
                path_results=[
                    PathResult(path_name="p3", success=True),
                ],
            ),
        ]
        result = JourneyResult(
            journey_name="test",
            success=False,
            started_at=now,
            finished_at=now,
            branch_results=branch_results,
        )

        assert result.total_paths == 3
        assert result.passed_paths == 2

    def test_journey_result_duration(self) -> None:
        now = datetime.now()
        later = datetime.now()
        result = JourneyResult(
            journey_name="test",
            success=True,
            started_at=now,
            finished_at=later,
            duration_ms=500.0,
        )

        assert result.duration_ms == 500.0


class TestSeverity:
    """Tests for Severity enum."""

    def test_severity_values(self) -> None:
        assert Severity.CRITICAL.value == "critical"
        assert Severity.HIGH.value == "high"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.LOW.value == "low"
        assert Severity.INFO.value == "info"

    def test_severity_comparison(self) -> None:
        assert Severity.CRITICAL.value != Severity.LOW.value


class TestJourneyValidation:
    """Tests for Journey.validate() method (TD-005)."""

    def test_validate_empty_journey(self) -> None:
        """Validate catches empty journey with no steps."""
        journey = Journey(name="empty_journey", steps=[])
        issues = journey.validate()

        assert len(issues) == 1
        assert "no steps" in issues[0].lower()

    def test_validate_returns_empty_for_valid_journey(self, sample_step: Step) -> None:
        """Validate returns empty list for valid journey."""
        journey = Journey(name="valid", steps=[sample_step])
        issues = journey.validate()

        assert issues == []

    def test_validate_duplicate_step_names_in_main_path(self) -> None:
        """Validate catches duplicate step names in main path."""
        def action(client, ctx):
            return client.get("/test")

        journey = Journey(
            name="duplicate_steps",
            steps=[
                Step(name="get_user", action=action),
                Step(name="get_user", action=action),  # Duplicate
            ],
        )
        issues = journey.validate()

        assert len(issues) == 1
        assert "duplicate" in issues[0].lower()
        assert "get_user" in issues[0]

    def test_validate_duplicate_step_names_across_branches(self) -> None:
        """Validate catches duplicate step names across branches and main path."""
        def action(client, ctx):
            return client.get("/test")

        checkpoint = Checkpoint(name="cp1")
        branch = Branch(
            checkpoint_name="cp1",
            paths=[
                Path(
                    name="path1",
                    steps=[Step(name="shared_name", action=action)],
                ),
                Path(
                    name="path2",
                    steps=[Step(name="shared_name", action=action)],  # Duplicate
                ),
            ],
        )

        journey = Journey(
            name="dup_across_branches",
            steps=[
                Step(name="setup", action=action),
                checkpoint,
                branch,
            ],
        )
        issues = journey.validate()

        assert len(issues) == 1
        assert "duplicate" in issues[0].lower()
        assert "shared_name" in issues[0]

    def test_validate_branch_without_paths(self) -> None:
        """Validate catches branches with no paths defined."""
        def action(client, ctx):
            return client.get("/test")

        checkpoint = Checkpoint(name="cp1")
        branch = Branch(checkpoint_name="cp1", paths=[])

        journey = Journey(
            name="empty_branch",
            steps=[
                Step(name="setup", action=action),
                checkpoint,
                branch,
            ],
        )
        issues = journey.validate()

        assert len(issues) == 1
        assert "no paths" in issues[0].lower()
        assert "cp1" in issues[0]

    def test_validate_path_without_steps(self) -> None:
        """Validate catches paths with no steps defined."""
        def action(client, ctx):
            return client.get("/test")

        checkpoint = Checkpoint(name="cp1")
        branch = Branch(
            checkpoint_name="cp1",
            paths=[
                Path(name="empty_path", steps=[]),
            ],
        )

        journey = Journey(
            name="empty_path_journey",
            steps=[
                Step(name="setup", action=action),
                checkpoint,
                branch,
            ],
        )
        issues = journey.validate()

        assert len(issues) == 1
        assert "no steps" in issues[0].lower()
        assert "empty_path" in issues[0]

    def test_validate_multiple_issues(self) -> None:
        """Validate reports all issues found, not just the first."""
        def action(client, ctx):
            return client.get("/test")

        checkpoint = Checkpoint(name="cp1")
        branch = Branch(
            checkpoint_name="cp1",
            paths=[
                Path(name="path1", steps=[]),  # Empty path
                Path(
                    name="path2",
                    steps=[Step(name="dup", action=action)],
                ),
                Path(
                    name="path3",
                    steps=[Step(name="dup", action=action)],  # Duplicate
                ),
            ],
        )

        journey = Journey(
            name="multi_issue",
            steps=[
                Step(name="setup", action=action),
                checkpoint,
                branch,
            ],
        )
        issues = journey.validate()

        # Should have at least 2 issues (empty path + duplicate)
        assert len(issues) >= 2

    def test_validate_or_raise_raises_on_issues(self) -> None:
        """validate_or_raise() raises JourneyValidationError for invalid journey."""
        journey = Journey(name="empty", steps=[])

        with pytest.raises(JourneyValidationError) as exc_info:
            journey.validate_or_raise()

        assert "validation issue" in str(exc_info.value).lower()

    def test_validate_or_raise_passes_for_valid(self, sample_step: Step) -> None:
        """validate_or_raise() does not raise for valid journey."""
        journey = Journey(name="valid", steps=[sample_step])

        # Should not raise
        journey.validate_or_raise()

    def test_validate_complex_nested_structure(self) -> None:
        """Validate handles complex nested branch structures."""
        def action(client, ctx):
            return client.get("/test")

        checkpoint1 = Checkpoint(name="cp1")
        checkpoint2 = Checkpoint(name="cp2")

        branch1 = Branch(
            checkpoint_name="cp1",
            paths=[
                Path(
                    name="path1",
                    steps=[
                        Step(name="step_in_path1", action=action),
                        checkpoint2,
                    ],
                ),
                Path(
                    name="path2",
                    steps=[Step(name="step_in_path2", action=action)],
                ),
            ],
        )

        journey = Journey(
            name="complex_nested",
            steps=[
                Step(name="setup", action=action),
                checkpoint1,
                branch1,
            ],
        )
        issues = journey.validate()

        assert issues == []

    def test_validate_callable_action(self) -> None:
        """Validate accepts callable actions."""
        def valid_action(client, ctx):
            return client.get("/test")

        journey = Journey(
            name="callable_action",
            steps=[Step(name="test", action=valid_action)],
        )
        issues = journey.validate()

        assert issues == []

    def test_validate_string_action_reference(self) -> None:
        """Validate accepts string action references."""
        journey = Journey(
            name="string_action",
            steps=[Step(name="test", action="my_plugin.my_action")],
        )
        issues = journey.validate()

        # String references are valid (resolved at runtime)
        assert issues == []
