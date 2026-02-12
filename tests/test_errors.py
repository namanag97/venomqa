"""Tests for error handling and recovery in VenomQA."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from venomqa.core.context import ExecutionContext
from venomqa.core.models import (
    Branch,
    Checkpoint,
    Issue,
    Journey,
    JourneyResult,
    Path,
    Severity,
    Step,
    StepResult,
)
from venomqa.errors import StateNotConnectedError
from venomqa.runner import JourneyRunner
from tests.conftest import MockClient, MockHTTPResponse, MockStateManager


class TestErrorRecovery:
    """Tests for error recovery scenarios."""

    def test_step_exception_causes_journey_failure(self, mock_client: MockClient) -> None:
        def exploding_action(client, ctx):
            raise RuntimeError("Unexpected error")

        journey = Journey(
            name="error_journey",
            steps=[Step(name="explode", action=exploding_action)],
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is False
        assert len(result.issues) == 1
        assert "Unexpected error" in result.issues[0].error

    def test_multiple_step_failures_all_captured(self, mock_client: MockClient) -> None:
        def fail_action(client, ctx):
            return client.get("/fail")

        journey = Journey(
            name="multi_fail",
            steps=[
                Step(name="fail1", action=fail_action),
                Step(name="fail2", action=fail_action),
                Step(name="fail3", action=fail_action),
            ],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=500, json_data={}),
                MockHTTPResponse(status_code=500, json_data={}),
                MockHTTPResponse(status_code=500, json_data={}),
            ]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is False
        assert len(result.issues) == 3

    def test_recovery_after_failed_branch_path(self, mock_client: MockClient) -> None:
        checkpoint = Checkpoint(name="start")
        branch = Branch(
            checkpoint_name="start",
            paths=[
                Path(
                    name="fail_path",
                    steps=[Step(name="fail", action=lambda c, ctx: c.get("/fail"))],
                ),
                Path(
                    name="success_path",
                    steps=[Step(name="success", action=lambda c, ctx: c.get("/success"))],
                ),
            ],
        )

        journey = Journey(name="recovery_test", steps=[checkpoint, branch])

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=500, json_data={}),
                MockHTTPResponse(status_code=200, json_data={}),
            ]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is False
        assert result.passed_paths == 1
        assert result.total_paths == 2

    def test_connection_error_handling(self, mock_client: MockClient) -> None:
        def action(client, ctx):
            mock_client.history.append(
                type(
                    "RequestRecord",
                    (),
                    {
                        "method": "GET",
                        "url": "http://test/fail",
                        "request_body": None,
                        "response_status": 0,
                        "response_body": None,
                        "headers": {},
                        "duration_ms": 0,
                        "timestamp": datetime.now(),
                        "error": "Connection refused",
                    },
                )()
            )
            raise ConnectionError("Connection refused")

        journey = Journey(name="conn_error", steps=[Step(name="request", action=action)])

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is False
        assert len(result.issues) == 1

    def test_timeout_error_handling(self, mock_client: MockClient) -> None:
        def timeout_action(client, ctx):
            raise TimeoutError("Request timed out after 30s")

        journey = Journey(name="timeout_test", steps=[Step(name="timeout", action=timeout_action)])

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is False
        assert "timed out" in result.issues[0].error.lower()


class TestHTTPErrorCodes:
    """Tests for HTTP error code handling."""

    def test_400_bad_request(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="bad_request",
            steps=[
                Step(
                    name="request", action=lambda c, ctx: c.post("/items", json={"invalid": "data"})
                )
            ],
        )

        mock_client.set_responses(
            [MockHTTPResponse(status_code=400, json_data={"error": "Bad Request"})]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is False
        assert result.step_results[0].response["status_code"] == 400

    def test_401_unauthorized(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="unauthorized",
            steps=[Step(name="request", action=lambda c, ctx: c.get("/protected"))],
        )

        mock_client.set_responses(
            [MockHTTPResponse(status_code=401, json_data={"error": "Unauthorized"})]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is False
        assert "401" in result.issues[0].error

    def test_403_forbidden(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="forbidden",
            steps=[Step(name="request", action=lambda c, ctx: c.delete("/admin/users/1"))],
        )

        mock_client.set_responses(
            [MockHTTPResponse(status_code=403, json_data={"error": "Forbidden"})]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is False

    def test_404_not_found(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="not_found",
            steps=[Step(name="request", action=lambda c, ctx: c.get("/nonexistent"))],
        )

        mock_client.set_responses(
            [MockHTTPResponse(status_code=404, json_data={"error": "Not Found"})]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is False

    def test_422_validation_error(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="validation",
            steps=[Step(name="request", action=lambda c, ctx: c.post("/items", json={"name": ""}))],
        )

        mock_client.set_responses(
            [MockHTTPResponse(status_code=422, json_data={"errors": ["name is required"]})]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is False

    def test_500_server_error(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="server_error",
            steps=[Step(name="request", action=lambda c, ctx: c.get("/crash"))],
        )

        mock_client.set_responses(
            [MockHTTPResponse(status_code=500, json_data={"error": "Internal Server Error"})]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is False

    def test_503_service_unavailable(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="unavailable",
            steps=[Step(name="request", action=lambda c, ctx: c.get("/service"))],
        )

        mock_client.set_responses(
            [MockHTTPResponse(status_code=503, json_data={"error": "Service Unavailable"})]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is False


class TestExpectedFailure:
    """Tests for expected failure handling."""

    def test_expect_failure_with_actual_failure(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="expected_fail",
            steps=[
                Step(
                    name="should_fail",
                    action=lambda c, ctx: c.get("/nonexistent"),
                    expect_failure=True,
                )
            ],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=404, json_data={})])

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is True

    def test_expect_failure_with_success(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="unexpected_success",
            steps=[
                Step(
                    name="should_fail", action=lambda c, ctx: c.get("/exists"), expect_failure=True
                )
            ],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})])

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is False
        assert "Expected failure but step succeeded" in result.issues[0].error

    def test_expect_failure_with_exception(self, mock_client: MockClient) -> None:
        def raise_error(client, ctx):
            raise ValueError("Test error")

        journey = Journey(
            name="exception_expected",
            steps=[Step(name="raises", action=raise_error, expect_failure=True)],
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is True


class TestIssueGeneration:
    """Tests for issue generation and suggestions."""

    def test_issue_has_auto_generated_suggestion(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="suggestion_test",
            steps=[Step(name="fail", action=lambda c, ctx: c.get("/fail"))],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=500, json_data={})])

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.issues[0].suggestion != ""
        assert result.issues[0].suggestion != "Review the error details and check system logs"

    def test_issue_suggestion_for_401(self) -> None:
        issue = Issue(
            journey="test",
            path="main",
            step="auth",
            error="HTTP 401 Unauthorized",
        )

        assert "authentication" in issue.suggestion.lower()

    def test_issue_suggestion_for_404(self) -> None:
        issue = Issue(
            journey="test",
            path="main",
            step="fetch",
            error="HTTP 404 Not Found",
        )

        assert "not found" in issue.suggestion.lower() or "route" in issue.suggestion.lower()

    def test_issue_suggestion_for_timeout(self) -> None:
        issue = Issue(
            journey="test",
            path="main",
            step="slow",
            error="Request timed out",
        )

        assert "timeout" in issue.suggestion.lower() or "timed out" in issue.suggestion.lower()

    def test_issue_suggestion_for_connection_refused(self) -> None:
        issue = Issue(
            journey="test",
            path="main",
            step="connect",
            error="Connection refused",
        )

        assert "running" in issue.suggestion.lower() or "docker" in issue.suggestion.lower()


class TestFailFast:
    """Tests for fail-fast behavior."""

    def test_fail_fast_stops_on_first_error(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="fail_fast",
            steps=[
                Step(name="fail1", action=lambda c, ctx: c.get("/fail")),
                Step(name="success", action=lambda c, ctx: c.get("/success")),
            ],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=500, json_data={}),
                MockHTTPResponse(status_code=200, json_data={}),
            ]
        )

        runner = JourneyRunner(client=mock_client, fail_fast=True)
        result = runner.run(journey)

        assert result.success is False
        assert len(result.step_results) == 1

    def test_no_fail_fast_continues_all_steps(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="continue",
            steps=[
                Step(name="fail1", action=lambda c, ctx: c.get("/fail")),
                Step(name="fail2", action=lambda c, ctx: c.get("/fail")),
            ],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=500, json_data={}),
                MockHTTPResponse(status_code=500, json_data={}),
            ]
        )

        runner = JourneyRunner(client=mock_client, fail_fast=False)
        result = runner.run(journey)

        assert len(result.step_results) == 2


class TestStateManagerErrors:
    """Tests for state manager error handling."""

    def test_rollback_nonexistent_checkpoint(self, mock_client: MockClient) -> None:
        state_manager = MockStateManager()
        state_manager.connect()

        with pytest.raises(ValueError, match="not found"):
            state_manager.rollback("nonexistent")

    def test_state_manager_not_connected_error(self) -> None:
        from venomqa.state.base import BaseStateManager

        class TestStateManager(BaseStateManager):
            def connect(self):
                pass

            def disconnect(self):
                pass

            def checkpoint(self, name):
                self._ensure_connected()

            def rollback(self, name):
                pass

            def release(self, name):
                pass

            def reset(self):
                pass

        manager = TestStateManager(connection_url="test://test")

        with pytest.raises(StateNotConnectedError, match="not connected"):
            manager.checkpoint("test")


class TestMalformedResponses:
    """Tests for handling malformed or unexpected responses."""

    def test_malformed_json_response(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="malformed",
            steps=[Step(name="request", action=lambda c, ctx: c.get("/data"))],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=200, text="not valid json {{{")])

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is True

    def test_empty_response_body(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="empty",
            steps=[Step(name="request", action=lambda c, ctx: c.get("/empty"))],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=204, json_data=None)])

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is True

    def test_html_error_page(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="html_error",
            steps=[Step(name="request", action=lambda c, ctx: c.get("/error"))],
        )

        mock_client.set_responses(
            [MockHTTPResponse(status_code=500, text="<html><body>Error</body></html>")]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is False
