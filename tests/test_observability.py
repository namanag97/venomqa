"""Tests for metrics and logging observability in VenomQA."""

from __future__ import annotations

import logging
from datetime import datetime
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from venomqa.core.models import (
    Journey,
    JourneyResult,
    Severity,
    Step,
    StepResult,
)
from venomqa.runner import JourneyRunner
from tests.conftest import MockClient, MockHTTPResponse


class TestRequestHistory:
    """Tests for HTTP request history tracking."""

    def test_history_records_single_request(self, mock_client: MockClient) -> None:
        mock_client.get("/users/1")

        assert len(mock_client.history) == 1
        record = mock_client.history[0]
        assert record.method == "GET"
        assert "/users/1" in record.url

    def test_history_records_multiple_requests(self, mock_client: MockClient) -> None:
        mock_client.get("/users")
        mock_client.post("/users", json={"name": "test"})
        mock_client.get("/users/1")
        mock_client.delete("/users/1")

        assert len(mock_client.history) == 4
        methods = [r.method for r in mock_client.history]
        assert methods == ["GET", "POST", "GET", "DELETE"]

    def test_history_records_request_body(self, mock_client: MockClient) -> None:
        mock_client.post("/items", json={"name": "test_item", "quantity": 5})

        record = mock_client.last_request()
        assert record is not None
        assert record.request_body == {"name": "test_item", "quantity": 5}

    def test_history_records_response_status(self, mock_client: MockClient) -> None:
        mock_client.set_responses([MockHTTPResponse(status_code=201, json_data={"id": 1})])
        mock_client.post("/items", json={"name": "test"})

        record = mock_client.last_request()
        assert record is not None
        assert record.response_status == 201

    def test_history_records_headers(self, mock_client: MockClient) -> None:
        mock_client.get("/users", headers={"X-Custom-Header": "value"})

        record = mock_client.last_request()
        assert record is not None
        assert record.headers.get("X-Custom-Header") == "value"

    def test_history_records_duration(self, mock_client: MockClient) -> None:
        mock_client.get("/users")

        record = mock_client.last_request()
        assert record is not None
        assert record.duration_ms >= 0

    def test_clear_history(self, mock_client: MockClient) -> None:
        mock_client.get("/users")
        mock_client.get("/items")

        assert len(mock_client.history) == 2

        mock_client.clear_history()

        assert len(mock_client.history) == 0

    def test_get_history_returns_copy(self, mock_client: MockClient) -> None:
        mock_client.get("/users")

        history1 = mock_client.get_history()
        history2 = mock_client.get_history()

        assert history1 is not history2
        assert history1 == history2

    def test_last_request_returns_none_when_empty(self, mock_client: MockClient) -> None:
        assert mock_client.last_request() is None


class TestStepResultMetrics:
    """Tests for step result metrics."""

    def test_step_result_has_duration(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="metrics_test",
            steps=[Step(name="fetch", action=lambda c, ctx: c.get("/users"))],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})])

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.step_results[0].duration_ms >= 0

    def test_step_result_has_timestamps(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="timestamps_test",
            steps=[Step(name="fetch", action=lambda c, ctx: c.get("/users"))],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})])

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        step_result = result.step_results[0]
        assert isinstance(step_result.started_at, datetime)
        assert isinstance(step_result.finished_at, datetime)
        assert step_result.finished_at >= step_result.started_at

    def test_journey_result_has_total_duration(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="duration_test",
            steps=[
                Step(name="fetch1", action=lambda c, ctx: c.get("/users")),
                Step(name="fetch2", action=lambda c, ctx: c.get("/items")),
            ],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=200, json_data={}),
                MockHTTPResponse(status_code=200, json_data={}),
            ]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.duration_ms >= 0

    def test_journey_result_aggregates_step_counts(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="counts_test",
            steps=[
                Step(name="step1", action=lambda c, ctx: c.get("/1")),
                Step(name="step2", action=lambda c, ctx: c.get("/2")),
                Step(name="step3", action=lambda c, ctx: c.get("/3")),
            ],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=200, json_data={}),
                MockHTTPResponse(status_code=500, json_data={}),
                MockHTTPResponse(status_code=200, json_data={}),
            ]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.total_steps == 3
        assert result.passed_steps == 2


class TestJourneyResultMetrics:
    """Tests for journey result metrics."""

    def test_journey_success_flag(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="success_test",
            steps=[Step(name="fetch", action=lambda c, ctx: c.get("/users"))],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})])

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is True

    def test_journey_failure_flag(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="failure_test",
            steps=[Step(name="fetch", action=lambda c, ctx: c.get("/users"))],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=500, json_data={})])

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is False

    def test_journey_result_timestamps(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="timestamps_test",
            steps=[Step(name="fetch", action=lambda c, ctx: c.get("/users"))],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})])

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert isinstance(result.started_at, datetime)
        assert isinstance(result.finished_at, datetime)
        assert result.finished_at >= result.started_at

    def test_journey_issues_count(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="issues_count",
            steps=[
                Step(name="fail1", action=lambda c, ctx: c.get("/fail")),
                Step(name="fail2", action=lambda c, ctx: c.get("/fail")),
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


class TestLogging:
    """Tests for logging functionality."""

    def test_runner_logs_journey_start(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="logging_test",
            steps=[Step(name="fetch", action=lambda c, ctx: c.get("/users"))],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})])

        with patch("venomqa.runner.logger") as mock_logger:
            runner = JourneyRunner(client=mock_client)
            runner.run(journey)

            mock_logger.info.assert_called()

    def test_runner_logs_step_execution(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="step_logging",
            steps=[Step(name="test_step", action=lambda c, ctx: c.get("/test"))],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})])

        with patch("venomqa.runner.logger") as mock_logger:
            runner = JourneyRunner(client=mock_client)
            runner.run(journey)

            debug_calls = [str(call) for call in mock_logger.debug.call_args_list]
            assert any("test_step" in str(call) for call in debug_calls)

    def test_runner_logs_failures(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="failure_logging",
            steps=[Step(name="fail_step", action=lambda c, ctx: c.get("/fail"))],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=500, json_data={})])

        with patch("venomqa.runner.logger") as mock_logger:
            runner = JourneyRunner(client=mock_client)
            runner.run(journey)

            mock_logger.warning.assert_called()

    def test_issue_logging(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="issue_logging",
            steps=[Step(name="fail", action=lambda c, ctx: c.get("/fail"))],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=500, json_data={})])

        with patch("venomqa.runner.logger") as mock_logger:
            runner = JourneyRunner(client=mock_client)
            runner.run(journey)

            warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
            assert any("Issue" in str(call) for call in warning_calls)


class TestContextObservability:
    """Tests for execution context observability."""

    def test_context_stores_step_results(self, mock_client: MockClient) -> None:
        from venomqa.core.context import ExecutionContext

        ctx = ExecutionContext()
        ctx.store_step_result("step1", {"data": "value"})

        assert ctx.get_step_result("step1") == {"data": "value"}

    def test_context_snapshot_and_restore(self, mock_client: MockClient) -> None:
        from venomqa.core.context import ExecutionContext

        ctx = ExecutionContext()
        ctx.set("key1", "value1")
        ctx.set("key2", "value2")

        snapshot = ctx.snapshot()

        ctx.set("key1", "modified")
        ctx.set("key3", "value3")

        ctx.restore(snapshot)

        assert ctx.get("key1") == "value1"
        assert ctx.get("key2") == "value2"
        assert ctx.get("key3") is None

    def test_context_to_dict(self, mock_client: MockClient) -> None:
        from venomqa.core.context import ExecutionContext

        ctx = ExecutionContext()
        ctx.set("key1", "value1")

        data = ctx.to_dict()

        assert "data" in data
        assert data["data"]["key1"] == "value1"


class TestHTTPClientObservability:
    """Tests for HTTP client observability features."""

    def test_auth_token_tracking(self, mock_client: MockClient) -> None:
        mock_client.set_auth_token("test-token-123")

        assert mock_client._auth_token == "Bearer test-token-123"

    def test_auth_token_with_custom_scheme(self, mock_client: MockClient) -> None:
        mock_client.set_auth_token("test-token", scheme="Token")

        assert mock_client._auth_token == "Token test-token"

    def test_clear_auth(self, mock_client: MockClient) -> None:
        mock_client.set_auth_token("test-token")
        mock_client.clear_auth()

        assert mock_client._auth_token is None

    def test_request_with_auth_header(self, mock_client: MockClient) -> None:
        mock_client.set_auth_token("secret-token")
        mock_client.get("/protected")

        last_request = mock_client.last_request()
        assert last_request is not None


class TestIssueMetrics:
    """Tests for issue-related metrics."""

    def test_issue_severity_levels(self) -> None:
        from venomqa.core.models import Issue

        severities = [
            Severity.CRITICAL,
            Severity.HIGH,
            Severity.MEDIUM,
            Severity.LOW,
            Severity.INFO,
        ]

        for severity in severities:
            issue = Issue(
                journey="test",
                path="main",
                step="test",
                error="error",
                severity=severity,
            )
            assert issue.severity == severity

    def test_issue_has_timestamp(self) -> None:
        from venomqa.core.models import Issue

        issue = Issue(
            journey="test",
            path="main",
            step="test",
            error="error",
        )

        assert isinstance(issue.timestamp, datetime)

    def test_issue_request_response_captured(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="capture_test",
            steps=[
                Step(name="post", action=lambda c, ctx: c.post("/items", json={"name": "test"}))
            ],
        )

        mock_client.set_responses(
            [MockHTTPResponse(status_code=422, json_data={"errors": ["validation failed"]})]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        issue = result.issues[0]
        assert issue.request is not None
        assert issue.response is not None

    def test_issue_logs_captured(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="logs_test",
            steps=[Step(name="fail", action=lambda c, ctx: c.get("/fail"))],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=500, json_data={})])

        runner = JourneyRunner(client=mock_client, capture_logs=True)
        result = runner.run(journey)

        assert isinstance(result.issues[0].logs, list)


class TestPerformanceMetrics:
    """Tests for performance-related metrics."""

    def test_step_timing_accuracy(self, mock_client: MockClient) -> None:
        import time

        def slow_action(client, ctx):
            time.sleep(0.01)
            return client.get("/slow")

        journey = Journey(
            name="timing_test",
            steps=[Step(name="slow", action=slow_action)],
        )

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})])

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.step_results[0].duration_ms >= 10

    def test_multiple_steps_cumulative_time(self, mock_client: MockClient) -> None:
        journey = Journey(
            name="cumulative_test",
            steps=[
                Step(name="step1", action=lambda c, ctx: c.get("/1")),
                Step(name="step2", action=lambda c, ctx: c.get("/2")),
                Step(name="step3", action=lambda c, ctx: c.get("/3")),
            ],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=200, json_data={}),
                MockHTTPResponse(status_code=200, json_data={}),
                MockHTTPResponse(status_code=200, json_data={}),
            ]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        step_total = sum(s.duration_ms for s in result.step_results)
        assert result.duration_ms >= step_total
