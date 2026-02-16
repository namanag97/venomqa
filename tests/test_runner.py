"""Tests for journey runner with step execution, branching, and context."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from venomqa.core.context import ExecutionContext
from venomqa.core.models import (
    Branch,
    BranchResult,
    Checkpoint,
    Journey,
    JourneyResult,
    Path,
    PathResult,
    Severity,
    Step,
    StepResult,
)
from venomqa.runner import JourneyRunner, MissingStateManagerError
from .conftest import MockClient, MockHTTPResponse, MockStateManager


class TestJourneyRunner:
    """Tests for JourneyRunner."""

    def test_runner_initialization(self, mock_client: MockClient) -> None:
        runner = JourneyRunner(
            client=mock_client,
            parallel_paths=4,
            fail_fast=True,
            capture_logs=False,
        )

        assert runner.client is mock_client
        assert runner.parallel_paths == 4
        assert runner.fail_fast is True
        assert runner.capture_logs is False

    def test_run_simple_journey(
        self, mock_client: MockClient, sample_journey_simple: Journey
    ) -> None:
        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=201, json_data={"id": 1}),
                MockHTTPResponse(status_code=200, json_data={"id": 1, "name": "Test"}),
            ]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(sample_journey_simple)

        assert result.success is True
        assert result.journey_name == "simple_journey"
        assert len(result.step_results) == 2
        assert result.total_steps == 2

    def test_run_journey_with_failure(
        self, mock_client: MockClient, sample_journey_simple: Journey
    ) -> None:
        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=201, json_data={"id": 1}),
                MockHTTPResponse(status_code=404, json_data={"error": "Not found"}),
            ]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(sample_journey_simple)

        assert result.success is False
        assert result.passed_steps == 1
        assert result.total_steps == 2
        assert len(result.issues) == 1

    def test_run_journey_with_state_manager(
        self, mock_client: MockClient, sample_journey_simple: Journey
    ) -> None:
        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=200, json_data={}),
                MockHTTPResponse(status_code=200, json_data={}),
            ]
        )

        state_manager = MockStateManager()
        runner = JourneyRunner(client=mock_client, state_manager=state_manager)

        result = runner.run(sample_journey_simple)

        assert state_manager.is_connected() is False

    def test_fail_fast_stops_on_failure(self, mock_client: MockClient) -> None:
        def action1(client, ctx):
            return client.get("/step1")

        def action2(client, ctx):
            return client.get("/step2")

        def action3(client, ctx):
            return client.get("/step3")

        journey = Journey(
            name="fail_fast_test",
            steps=[
                Step(name="step1", action=action1),
                Step(name="step2", action=action2),
                Step(name="step3", action=action3),
            ],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=200, json_data={}),
                MockHTTPResponse(status_code=500, json_data={}),
                MockHTTPResponse(status_code=200, json_data={}),
            ]
        )

        runner = JourneyRunner(client=mock_client, fail_fast=True)
        result = runner.run(journey)

        assert result.success is False
        assert len(result.step_results) == 2

    def test_no_fail_fast_continues_on_failure(self, mock_client: MockClient) -> None:
        def action1(client, ctx):
            return client.get("/step1")

        def action2(client, ctx):
            return client.get("/step2")

        journey = Journey(
            name="continue_on_failure",
            steps=[
                Step(name="step1", action=action1),
                Step(name="step2", action=action2),
            ],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=500, json_data={}),
                MockHTTPResponse(status_code=200, json_data={}),
            ]
        )

        runner = JourneyRunner(client=mock_client, fail_fast=False)
        result = runner.run(journey)

        assert result.success is False
        assert len(result.step_results) == 2

    def test_context_passing_between_steps(self, mock_client: MockClient) -> None:
        captured_context = {}

        def action1(client, ctx):
            ctx.set("user_id", 123)
            ctx.set("user_name", "Test User")
            return client.post("/users", json={"name": "Test User"})

        def action2(client, ctx):
            captured_context["user_id"] = ctx.get("user_id")
            captured_context["user_name"] = ctx.get("user_name")
            user_id = ctx.get("user_id")
            return client.get(f"/users/{user_id}")

        journey = Journey(
            name="context_test",
            steps=[
                Step(name="create_user", action=action1),
                Step(name="get_user", action=action2),
            ],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=201, json_data={"id": 123}),
                MockHTTPResponse(status_code=200, json_data={"id": 123, "name": "Test User"}),
            ]
        )

        runner = JourneyRunner(client=mock_client)
        runner.run(journey)

        assert captured_context["user_id"] == 123
        assert captured_context["user_name"] == "Test User"


class TestBranching:
    """Tests for branch execution with rollback."""

    def test_branch_execution(self, mock_client: MockClient) -> None:
        def create_action(client, ctx):
            return client.post("/items", json={"name": "item"})

        def read_action(client, ctx):
            return client.get("/items/1")

        def delete_action(client, ctx):
            return client.delete("/items/1")

        checkpoint = Checkpoint(name="after_create")
        branch = Branch(
            checkpoint_name="after_create",
            paths=[
                Path(name="read_path", steps=[Step(name="read", action=read_action)]),
                Path(name="delete_path", steps=[Step(name="delete", action=delete_action)]),
            ],
        )

        journey = Journey(
            name="branch_test",
            steps=[
                Step(name="create", action=create_action),
                checkpoint,
                branch,
            ],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=201, json_data={"id": 1}),
                MockHTTPResponse(status_code=200, json_data={"id": 1}),
                MockHTTPResponse(status_code=204, json_data={}),
            ]
        )

        state_manager = MockStateManager()
        runner = JourneyRunner(client=mock_client, state_manager=state_manager)
        result = runner.run(journey)

        assert result.success is True
        assert len(result.branch_results) == 1
        assert result.branch_results[0].all_passed is True
        assert result.total_paths == 2

    def test_branch_with_failed_path(self, mock_client: MockClient) -> None:
        def create_action(client, ctx):
            return client.post("/items", json={})

        def success_action(client, ctx):
            return client.get("/items")

        def fail_action(client, ctx):
            return client.delete("/items/999")

        checkpoint = Checkpoint(name="after_create")
        branch = Branch(
            checkpoint_name="after_create",
            paths=[
                Path(name="success_path", steps=[Step(name="success", action=success_action)]),
                Path(name="fail_path", steps=[Step(name="fail", action=fail_action)]),
            ],
        )

        journey = Journey(
            name="branch_fail_test",
            steps=[
                Step(name="create", action=create_action),
                checkpoint,
                branch,
            ],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=201, json_data={}),
                MockHTTPResponse(status_code=200, json_data=[]),
                MockHTTPResponse(status_code=404, json_data={"error": "Not found"}),
            ]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is False
        assert result.branch_results[0].all_passed is False
        assert result.passed_paths == 1
        assert result.total_paths == 2

    def test_branch_rollback_between_paths(self, mock_client: MockClient) -> None:
        checkpoint = Checkpoint(name="initial")
        branch = Branch(
            checkpoint_name="initial",
            paths=[
                Path(name="path1", steps=[Step(name="step1", action=lambda c, ctx: c.get("/1"))]),
                Path(name="path2", steps=[Step(name="step2", action=lambda c, ctx: c.get("/2"))]),
            ],
        )

        journey = Journey(name="rollback_test", steps=[checkpoint, branch])

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=200, json_data={}),
                MockHTTPResponse(status_code=200, json_data={}),
            ]
        )

        state_manager = MockStateManager()
        runner = JourneyRunner(client=mock_client, state_manager=state_manager)
        result = runner.run(journey)

        assert result.success is True

    def test_context_snapshot_in_branch(self, mock_client: MockClient) -> None:
        context_values = []

        def create_action(client, ctx):
            ctx.set("shared_value", "initial")
            return client.post("/items", json={})

        def path1_action(client, ctx):
            ctx.set("path_value", "path1")
            context_values.append(("path1", ctx.get("shared_value")))
            return client.get("/items")

        def path2_action(client, ctx):
            ctx.set("path_value", "path2")
            context_values.append(("path2", ctx.get("shared_value")))
            return client.get("/items")

        checkpoint = Checkpoint(name="after_create")
        branch = Branch(
            checkpoint_name="after_create",
            paths=[
                Path(name="path1", steps=[Step(name="p1_step", action=path1_action)]),
                Path(name="path2", steps=[Step(name="p2_step", action=path2_action)]),
            ],
        )

        journey = Journey(
            name="context_snapshot_test",
            steps=[Step(name="create", action=create_action), checkpoint, branch],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=201, json_data={}),
                MockHTTPResponse(status_code=200, json_data={}),
                MockHTTPResponse(status_code=200, json_data={}),
            ]
        )

        runner = JourneyRunner(client=mock_client)
        runner.run(journey)

        assert ("path1", "initial") in context_values
        assert ("path2", "initial") in context_values


class TestParallelExecution:
    """Tests for parallel path execution."""

    def test_parallel_paths_execution(self, mock_client: MockClient) -> None:
        checkpoint = Checkpoint(name="initial")
        branch = Branch(
            checkpoint_name="initial",
            paths=[
                Path(name="path_a", steps=[Step(name="a", action=lambda c, ctx: c.get("/a"))]),
                Path(name="path_b", steps=[Step(name="b", action=lambda c, ctx: c.get("/b"))]),
                Path(name="path_c", steps=[Step(name="c", action=lambda c, ctx: c.get("/c"))]),
            ],
        )

        journey = Journey(name="parallel_test", steps=[checkpoint, branch])

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=200, json_data={}),
                MockHTTPResponse(status_code=200, json_data={}),
                MockHTTPResponse(status_code=200, json_data={}),
            ]
        )

        runner = JourneyRunner(client=mock_client, parallel_paths=3)
        result = runner.run(journey)

        assert result.success is True
        assert result.total_paths == 3

    def test_sequential_paths_by_default(self, mock_client: MockClient) -> None:
        execution_order = []

        def track_action(path_name):
            def action(client, ctx):
                execution_order.append(path_name)
                return client.get(f"/{path_name}")

            return action

        checkpoint = Checkpoint(name="initial")
        branch = Branch(
            checkpoint_name="initial",
            paths=[
                Path(name="first", steps=[Step(name="first", action=track_action("first"))]),
                Path(name="second", steps=[Step(name="second", action=track_action("second"))]),
            ],
        )

        journey = Journey(name="sequential_test", steps=[checkpoint, branch])

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=200, json_data={}),
                MockHTTPResponse(status_code=200, json_data={}),
            ]
        )

        runner = JourneyRunner(client=mock_client, parallel_paths=1)
        runner.run(journey)

        assert execution_order == ["first", "second"]


class TestStepExecution:
    """Tests for individual step execution."""

    def test_step_result_capture(self, mock_client: MockClient) -> None:
        def action(client, ctx):
            return client.post("/users", json={"name": "Test"})

        journey = Journey(
            name="result_capture_test",
            steps=[Step(name="create_user", action=action)],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(
                    status_code=201,
                    json_data={"id": 42, "name": "Test"},
                    headers={"Location": "/users/42"},
                )
            ]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is True
        step_result = result.step_results[0]
        assert step_result.step_name == "create_user"
        assert step_result.success is True
        assert step_result.response is not None
        assert step_result.response["status_code"] == 201

    def test_step_with_expected_failure(self, mock_client: MockClient) -> None:
        def failing_action(client, ctx):
            return client.delete("/nonexistent")

        journey = Journey(
            name="expected_failure_test",
            steps=[Step(name="delete_nonexistent", action=failing_action, expect_failure=True)],
        )

        mock_client.set_responses(
            [MockHTTPResponse(status_code=404, json_data={"error": "Not found"})]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is True

    def test_step_exception_handling(self, mock_client: MockClient) -> None:
        def exploding_action(client, ctx):
            raise ValueError("Something went wrong!")

        journey = Journey(
            name="exception_test",
            steps=[Step(name="explode", action=exploding_action)],
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is False
        assert len(result.issues) == 1
        assert "Something went wrong!" in result.issues[0].error

    def test_checkpoint_in_journey(self, mock_client: MockClient) -> None:
        def action(client, ctx):
            return client.get("/test")

        state_manager = MockStateManager()

        journey = Journey(
            name="checkpoint_test",
            steps=[
                Step(name="step1", action=action),
                Checkpoint(name="midpoint"),
                Step(name="step2", action=action),
            ],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=200, json_data={}),
                MockHTTPResponse(status_code=200, json_data={}),
            ]
        )

        runner = JourneyRunner(client=mock_client, state_manager=state_manager)
        runner.run(journey)

        assert "midpoint" in state_manager._checkpoints


class TestIssueCapture:
    """Tests for issue capturing during execution."""

    def test_issue_captured_on_failure(self, mock_client: MockClient) -> None:
        def action(client, ctx):
            return client.get("/fail")

        journey = Journey(name="issue_test", steps=[Step(name="fail_step", action=action)])

        mock_client.set_responses(
            [MockHTTPResponse(status_code=500, json_data={"error": "Internal Server Error"})]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.journey == "issue_test"
        assert issue.step == "fail_step"
        assert issue.severity == Severity.HIGH

    def test_issue_request_response_captured(self, mock_client: MockClient) -> None:
        def action(client, ctx):
            return client.post("/items", json={"name": "test"})

        journey = Journey(name="request_test", steps=[Step(name="post_item", action=action)])

        mock_client.set_responses(
            [MockHTTPResponse(status_code=422, json_data={"error": "Validation failed"})]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        issue = result.issues[0]
        assert issue.request is not None
        assert issue.response is not None
        assert issue.response["status_code"] == 422

    def test_multiple_issues_captured(self, mock_client: MockClient) -> None:
        def action1(client, ctx):
            return client.get("/fail1")

        def action2(client, ctx):
            return client.get("/fail2")

        journey = Journey(
            name="multi_issue_test",
            steps=[
                Step(name="fail1", action=action1),
                Step(name="fail2", action=action2),
            ],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=500, json_data={}),
                MockHTTPResponse(status_code=404, json_data={}),
            ]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert len(result.issues) == 2

    def test_get_issues_returns_copy(self, mock_client: MockClient) -> None:
        def action(client, ctx):
            return client.get("/fail")

        journey = Journey(name="copy_test", steps=[Step(name="fail", action=action)])

        mock_client.set_responses([MockHTTPResponse(status_code=500, json_data={})])

        runner = JourneyRunner(client=mock_client)
        runner.run(journey)

        issues1 = runner.get_issues()
        issues2 = runner.get_issues()

        assert issues1 is not issues2


class TestStateManagerRequirement:
    """Tests for StateManager requirement enforcement."""

    def test_checkpoint_without_state_manager_raises_error(
        self, mock_client: MockClient
    ) -> None:
        """Checkpoint without StateManager should raise MissingStateManagerError."""
        def action(client, ctx):
            return client.get("/test")

        journey = Journey(
            name="checkpoint_test",
            steps=[
                Step(name="step1", action=action),
                Checkpoint(name="midpoint"),
            ],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})])

        runner = JourneyRunner(client=mock_client)  # No state_manager

        with pytest.raises(MissingStateManagerError) as exc_info:
            runner.run(journey)

        assert "midpoint" in str(exc_info.value.message)
        assert "StateManager" in str(exc_info.value.message)

    def test_branch_without_state_manager_raises_error(
        self, mock_client: MockClient
    ) -> None:
        """Branch without StateManager should raise MissingStateManagerError."""
        def action(client, ctx):
            return client.get("/test")

        checkpoint = Checkpoint(name="test_checkpoint")
        branch = Branch(
            checkpoint_name="test_checkpoint",
            paths=[
                Path(name="path1", steps=[Step(name="p1", action=action)]),
            ],
        )

        journey = Journey(
            name="branch_test",
            steps=[
                Step(name="setup", action=action),
                checkpoint,
                branch,
            ],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})])

        runner = JourneyRunner(client=mock_client)  # No state_manager

        with pytest.raises(MissingStateManagerError) as exc_info:
            runner.run(journey)

        # Error should mention the checkpoint or StateManager
        assert "StateManager" in str(exc_info.value.message)

    def test_checkpoint_with_state_manager_works(
        self, mock_client: MockClient
    ) -> None:
        """Checkpoint with StateManager should work normally."""
        def action(client, ctx):
            return client.get("/test")

        journey = Journey(
            name="checkpoint_test",
            steps=[
                Step(name="step1", action=action),
                Checkpoint(name="midpoint"),
                Step(name="step2", action=action),
            ],
        )

        mock_client.set_responses([
            MockHTTPResponse(status_code=200, json_data={}),
            MockHTTPResponse(status_code=200, json_data={}),
        ])

        state_manager = MockStateManager()
        runner = JourneyRunner(client=mock_client, state_manager=state_manager)
        result = runner.run(journey)

        assert result.success is True
        assert "midpoint" in state_manager._checkpoints


class TestDependencyInjection:
    """Tests for dependency injection in JourneyRunner."""

    def test_custom_action_resolver(self, mock_client: MockClient) -> None:
        """Custom ActionResolver should be used for resolving string actions."""
        from venomqa.runner.resolver import DictActionResolver

        def custom_action(client, ctx):
            ctx.set("custom_called", True)
            return client.get("/custom")

        resolver = DictActionResolver({"my.action": custom_action})

        journey = Journey(
            name="resolver_test",
            steps=[Step(name="custom_step", action="my.action")],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})])

        runner = JourneyRunner(client=mock_client, action_resolver=resolver)
        result = runner.run(journey)

        assert result.success is True

    def test_custom_issue_formatter(self, mock_client: MockClient) -> None:
        """Custom IssueFormatter should be used for issue creation."""
        from venomqa.runner.formatter import IssueFormatter

        formatter = IssueFormatter()

        def failing_action(client, ctx):
            return client.get("/fail")

        journey = Journey(
            name="formatter_test",
            steps=[Step(name="fail_step", action=failing_action)],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=500, json_data={})])

        runner = JourneyRunner(client=mock_client, issue_formatter=formatter)
        result = runner.run(journey)

        # Issues should be in both the result and the formatter
        assert len(result.issues) == 1
        assert len(formatter.get_issues()) == 1
        assert result.issues[0].step == "fail_step"
