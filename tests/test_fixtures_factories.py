"""Tests for test data factories and fixtures."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from venomqa.core.context import ExecutionContext
from venomqa.core.models import (
    Branch,
    Checkpoint,
    Issue,
    Journey,
    JourneyResult,
    Path,
    PathResult,
    BranchResult,
    Severity,
    Step,
    StepResult,
)
from tests.conftest import MockClient, MockHTTPResponse, MockStateManager


class TestDataFactory:
    """Factory for creating test data."""

    @staticmethod
    def create_step(name: str = "test_step", **kwargs: Any) -> Step:
        def default_action(client, ctx):
            return client.get("/test")

        return Step(
            name=name,
            action=kwargs.get("action", default_action),
            description=kwargs.get("description", ""),
            expect_failure=kwargs.get("expect_failure", False),
            timeout=kwargs.get("timeout"),
            retries=kwargs.get("retries", 0),
        )

    @staticmethod
    def create_checkpoint(name: str = "test_checkpoint") -> Checkpoint:
        return Checkpoint(name=name)

    @staticmethod
    def create_path(name: str = "test_path", steps: list | None = None) -> Path:
        return Path(
            name=name,
            steps=steps or [],
            description="",
        )

    @staticmethod
    def create_branch(
        checkpoint_name: str = "test_checkpoint", paths: list | None = None
    ) -> Branch:
        return Branch(
            checkpoint_name=checkpoint_name,
            paths=paths or [],
        )

    @staticmethod
    def create_journey(
        name: str = "test_journey", steps: list | None = None, **kwargs: Any
    ) -> Journey:
        return Journey(
            name=name,
            steps=steps or [],
            description=kwargs.get("description", ""),
            tags=kwargs.get("tags", []),
            timeout=kwargs.get("timeout"),
        )

    @staticmethod
    def create_step_result(
        step_name: str = "test_step",
        success: bool = True,
        **kwargs: Any,
    ) -> StepResult:
        now = datetime.now()
        return StepResult(
            step_name=step_name,
            success=success,
            started_at=kwargs.get("started_at", now),
            finished_at=kwargs.get("finished_at", now),
            response=kwargs.get("response"),
            error=kwargs.get("error", "Test error" if not success else None),
            request=kwargs.get("request"),
            duration_ms=kwargs.get("duration_ms", 0.0),
        )

    @staticmethod
    def create_issue(
        journey: str = "test_journey",
        path: str = "main",
        step: str = "test_step",
        error: str = "Test error",
        severity: Severity = Severity.HIGH,
    ) -> Issue:
        return Issue(
            journey=journey,
            path=path,
            step=step,
            error=error,
            severity=severity,
        )

    @staticmethod
    def create_journey_result(
        journey_name: str = "test_journey",
        success: bool = True,
        **kwargs: Any,
    ) -> JourneyResult:
        now = datetime.now()
        return JourneyResult(
            journey_name=journey_name,
            success=success,
            started_at=kwargs.get("started_at", now),
            finished_at=kwargs.get("finished_at", now),
            step_results=kwargs.get("step_results", []),
            branch_results=kwargs.get("branch_results", []),
            issues=kwargs.get("issues", []),
            duration_ms=kwargs.get("duration_ms", 0.0),
        )


class TestStepFactory:
    """Tests for step factory methods."""

    def test_create_default_step(self) -> None:
        step = TestDataFactory.create_step()

        assert step.name == "test_step"
        assert step.description == ""
        assert step.expect_failure is False
        assert step.timeout is None
        assert step.retries == 0

    def test_create_step_with_custom_name(self) -> None:
        step = TestDataFactory.create_step(name="custom_step")

        assert step.name == "custom_step"

    def test_create_step_with_custom_action(self) -> None:
        custom_action = lambda c, ctx: c.post("/custom")
        step = TestDataFactory.create_step(action=custom_action)

        assert step.action is custom_action

    def test_create_step_with_expect_failure(self) -> None:
        step = TestDataFactory.create_step(expect_failure=True)

        assert step.expect_failure is True

    def test_create_step_with_timeout(self) -> None:
        step = TestDataFactory.create_step(timeout=30.0)

        assert step.timeout == 30.0

    def test_create_step_with_retries(self) -> None:
        step = TestDataFactory.create_step(retries=5)

        assert step.retries == 5


class TestCheckpointFactory:
    """Tests for checkpoint factory methods."""

    def test_create_default_checkpoint(self) -> None:
        checkpoint = TestDataFactory.create_checkpoint()

        assert checkpoint.name == "test_checkpoint"

    def test_create_checkpoint_with_custom_name(self) -> None:
        checkpoint = TestDataFactory.create_checkpoint(name="after_setup")

        assert checkpoint.name == "after_setup"


class TestPathFactory:
    """Tests for path factory methods."""

    def test_create_default_path(self) -> None:
        path = TestDataFactory.create_path()

        assert path.name == "test_path"
        assert path.steps == []

    def test_create_path_with_steps(self) -> None:
        steps = [
            TestDataFactory.create_step(name="step1"),
            TestDataFactory.create_step(name="step2"),
        ]
        path = TestDataFactory.create_path(steps=steps)

        assert len(path.steps) == 2
        assert path.steps[0].name == "step1"

    def test_create_path_with_checkpoint(self) -> None:
        checkpoint = TestDataFactory.create_checkpoint()
        path = TestDataFactory.create_path(steps=[checkpoint])

        assert len(path.steps) == 1
        assert isinstance(path.steps[0], Checkpoint)


class TestBranchFactory:
    """Tests for branch factory methods."""

    def test_create_default_branch(self) -> None:
        branch = TestDataFactory.create_branch()

        assert branch.checkpoint_name == "test_checkpoint"
        assert branch.paths == []

    def test_create_branch_with_paths(self) -> None:
        paths = [
            TestDataFactory.create_path(name="path1"),
            TestDataFactory.create_path(name="path2"),
        ]
        branch = TestDataFactory.create_branch(paths=paths)

        assert len(branch.paths) == 2

    def test_create_branch_with_custom_checkpoint(self) -> None:
        branch = TestDataFactory.create_branch(checkpoint_name="custom_checkpoint")

        assert branch.checkpoint_name == "custom_checkpoint"


class TestJourneyFactory:
    """Tests for journey factory methods."""

    def test_create_default_journey(self) -> None:
        journey = TestDataFactory.create_journey()

        assert journey.name == "test_journey"
        assert journey.steps == []
        assert journey.description == ""
        assert journey.tags == []

    def test_create_journey_with_steps(self) -> None:
        steps = [
            TestDataFactory.create_step(name="step1"),
            TestDataFactory.create_checkpoint(name="cp1"),
        ]
        journey = TestDataFactory.create_journey(steps=steps)

        assert len(journey.steps) == 2

    def test_create_journey_with_tags(self) -> None:
        journey = TestDataFactory.create_journey(tags=["integration", "smoke"])

        assert "integration" in journey.tags
        assert "smoke" in journey.tags

    def test_create_journey_with_description(self) -> None:
        journey = TestDataFactory.create_journey(description="Test journey description")

        assert journey.description == "Test journey description"

    def test_create_journey_with_timeout(self) -> None:
        journey = TestDataFactory.create_journey(timeout=60.0)

        assert journey.timeout == 60.0


class TestStepResultFactory:
    """Tests for step result factory methods."""

    def test_create_default_step_result(self) -> None:
        result = TestDataFactory.create_step_result()

        assert result.step_name == "test_step"
        assert result.success is True
        assert result.response is None
        assert result.error is None

    def test_create_failed_step_result(self) -> None:
        result = TestDataFactory.create_step_result(success=False, error="Failed")

        assert result.success is False
        assert result.error == "Failed"

    def test_create_step_result_with_response(self) -> None:
        response = {"status_code": 200, "body": {"id": 1}}
        result = TestDataFactory.create_step_result(response=response)

        assert result.response == response

    def test_create_step_result_with_request(self) -> None:
        request = {"method": "POST", "url": "/users", "body": {"name": "test"}}
        result = TestDataFactory.create_step_result(request=request)

        assert result.request == request

    def test_create_step_result_with_duration(self) -> None:
        result = TestDataFactory.create_step_result(duration_ms=150.5)

        assert result.duration_ms == 150.5


class TestIssueFactory:
    """Tests for issue factory methods."""

    def test_create_default_issue(self) -> None:
        issue = TestDataFactory.create_issue()

        assert issue.journey == "test_journey"
        assert issue.path == "main"
        assert issue.step == "test_step"
        assert issue.error == "Test error"
        assert issue.severity == Severity.HIGH

    def test_create_issue_with_custom_severity(self) -> None:
        issue = TestDataFactory.create_issue(severity=Severity.CRITICAL)

        assert issue.severity == Severity.CRITICAL

    def test_create_issue_with_request_response(self) -> None:
        issue = Issue(
            journey="test",
            path="main",
            step="step",
            error="error",
            request={"method": "GET"},
            response={"status_code": 500},
        )

        assert issue.request == {"method": "GET"}
        assert issue.response == {"status_code": 500}

    def test_create_issue_with_logs(self) -> None:
        issue = Issue(
            journey="test",
            path="main",
            step="step",
            error="error",
            logs=["Log line 1", "Log line 2"],
        )

        assert len(issue.logs) == 2


class TestJourneyResultFactory:
    """Tests for journey result factory methods."""

    def test_create_default_journey_result(self) -> None:
        result = TestDataFactory.create_journey_result()

        assert result.journey_name == "test_journey"
        assert result.success is True
        assert result.step_results == []
        assert result.branch_results == []
        assert result.issues == []

    def test_create_failed_journey_result(self) -> None:
        result = TestDataFactory.create_journey_result(success=False)

        assert result.success is False

    def test_create_journey_result_with_step_results(self) -> None:
        step_results = [
            TestDataFactory.create_step_result(step_name="step1"),
            TestDataFactory.create_step_result(step_name="step2"),
        ]
        result = TestDataFactory.create_journey_result(step_results=step_results)

        assert result.total_steps == 2
        assert result.passed_steps == 2

    def test_create_journey_result_with_issues(self) -> None:
        issues = [
            TestDataFactory.create_issue(step="step1"),
            TestDataFactory.create_issue(step="step2"),
        ]
        result = TestDataFactory.create_journey_result(
            success=False,
            issues=issues,
        )

        assert len(result.issues) == 2

    def test_journey_result_step_count_properties(self) -> None:
        step_results = [
            TestDataFactory.create_step_result(success=True),
            TestDataFactory.create_step_result(success=False),
            TestDataFactory.create_step_result(success=True),
        ]
        result = TestDataFactory.create_journey_result(step_results=step_results)

        assert result.total_steps == 3
        assert result.passed_steps == 2


class TestCompositeFactories:
    """Tests for creating complex test data structures."""

    def test_create_complete_journey_with_branch(self) -> None:
        steps = [
            TestDataFactory.create_step(name="setup"),
            TestDataFactory.create_checkpoint(name="after_setup"),
            TestDataFactory.create_branch(
                checkpoint_name="after_setup",
                paths=[
                    TestDataFactory.create_path(
                        name="happy_path",
                        steps=[TestDataFactory.create_step(name="success_action")],
                    ),
                    TestDataFactory.create_path(
                        name="error_path",
                        steps=[TestDataFactory.create_step(name="error_action")],
                    ),
                ],
            ),
        ]
        journey = TestDataFactory.create_journey(
            name="complete_journey",
            steps=steps,
            tags=["integration"],
        )

        assert journey.name == "complete_journey"
        assert len(journey.steps) == 3
        assert "integration" in journey.tags

    def test_create_failed_journey_result_complete(self) -> None:
        step_results = [
            TestDataFactory.create_step_result(step_name="step1", success=True),
            TestDataFactory.create_step_result(
                step_name="step2",
                success=False,
                error="HTTP 500",
            ),
        ]
        issues = [TestDataFactory.create_issue(step="step2", error="HTTP 500")]

        result = TestDataFactory.create_journey_result(
            journey_name="failed_journey",
            success=False,
            step_results=step_results,
            issues=issues,
            duration_ms=500.0,
        )

        assert result.success is False
        assert result.passed_steps == 1
        assert result.total_steps == 2
        assert len(result.issues) == 1
        assert result.duration_ms == 500.0


class TestMockClientFactory:
    """Tests for mock client factory usage."""

    def test_mock_client_with_responses(self, mock_client: MockClient) -> None:
        responses = [
            MockHTTPResponse(status_code=200, json_data={"id": 1}),
            MockHTTPResponse(status_code=201, json_data={"id": 2}),
            MockHTTPResponse(status_code=204, json_data=None),
        ]
        mock_client.set_responses(responses)

        r1 = mock_client.get("/1")
        r2 = mock_client.post("/2")
        r3 = mock_client.delete("/3")

        assert r1.status_code == 200
        assert r2.status_code == 201
        assert r3.status_code == 204

    def test_mock_client_history_tracking(self, mock_client: MockClient) -> None:
        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=200, json_data={}),
            ]
        )

        mock_client.get("/users")
        mock_client.post("/users", json={"name": "test"})

        assert len(mock_client.history) == 2

    def test_mock_client_auth_methods(self, mock_client: MockClient) -> None:
        mock_client.set_auth_token("test-token")
        assert mock_client._auth_token == "Bearer test-token"

        mock_client.clear_auth()
        assert mock_client._auth_token is None


class TestMockStateManagerFactory:
    """Tests for mock state manager factory usage."""

    def test_mock_state_manager_checkpoint_workflow(
        self, mock_state_manager: MockStateManager
    ) -> None:
        mock_state_manager.connect()
        mock_state_manager.checkpoint("cp1")
        mock_state_manager.checkpoint("cp2")

        assert "cp1" in mock_state_manager._checkpoints
        assert "cp2" in mock_state_manager._checkpoints

        mock_state_manager.rollback("cp1")
        mock_state_manager.release("cp1")

    def test_mock_state_manager_reset(self, mock_state_manager: MockStateManager) -> None:
        mock_state_manager.connect()
        mock_state_manager.checkpoint("cp1")
        mock_state_manager.checkpoint("cp2")

        mock_state_manager.reset()

        assert len(mock_state_manager._checkpoints) == 0


class TestExecutionContextFactory:
    """Tests for execution context usage."""

    def test_context_set_get(self) -> None:
        ctx = ExecutionContext()
        ctx.set("key1", "value1")

        assert ctx.get("key1") == "value1"
        assert ctx.get("nonexistent") is None
        assert ctx.get("nonexistent", "default") == "default"

    def test_context_required_key(self) -> None:
        ctx = ExecutionContext()

        with pytest.raises(KeyError):
            ctx.get_required("nonexistent")

    def test_context_dict_access(self) -> None:
        ctx = ExecutionContext()
        ctx["key"] = "value"

        assert ctx["key"] == "value"
        assert "key" in ctx

    def test_context_step_results(self) -> None:
        ctx = ExecutionContext()
        ctx.store_step_result("step1", {"data": "result"})

        assert ctx.get_step_result("step1") == {"data": "result"}
