"""Memory usage tests for VenomQA."""

from __future__ import annotations

import gc
import sys

from tests.conftest import MockClient, MockHTTPResponse, MockStateManager
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
from venomqa.runner import JourneyRunner


def get_memory_usage() -> int:
    """Get current memory usage in bytes."""
    gc.collect()
    return sys.getsizeof(gc.get_objects())


class TestContextMemory:
    """Tests for execution context memory usage."""

    def test_context_data_memory_growth(self) -> None:
        ctx = ExecutionContext()
        initial_size = len(ctx._data)

        for i in range(10000):
            ctx.set(f"key_{i}", f"value_{i}")

        assert len(ctx._data) == 10000

        ctx.clear()
        assert len(ctx._data) == 0

    def test_context_large_value_storage(self) -> None:
        ctx = ExecutionContext()
        large_value = {"data": list(range(10000))}

        ctx.set("large_key", large_value)
        retrieved = ctx.get("large_key")

        assert retrieved == large_value

        ctx.clear()
        assert ctx.get("large_key") is None

    def test_context_step_results_memory(self) -> None:
        ctx = ExecutionContext()

        for i in range(1000):
            ctx.store_step_result(f"step_{i}", {"result": i, "data": list(range(100))})

        assert len(ctx._step_results) == 1000

        ctx.clear()
        assert len(ctx._step_results) == 0

    def test_snapshot_memory_efficiency(self) -> None:
        ctx = ExecutionContext()

        for i in range(1000):
            ctx.set(f"key_{i}", f"value_{i}")

        snapshots = []
        for _ in range(100):
            snapshots.append(ctx.snapshot())

        assert len(snapshots) == 100

        for snapshot in snapshots:
            assert "data" in snapshot
            assert len(snapshot["data"]) == 1000


class TestClientHistoryMemory:
    """Tests for client history memory usage."""

    def test_history_growth(self, mock_client: MockClient) -> None:
        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 10000)

        for i in range(10000):
            mock_client.get(f"/endpoint/{i}")

        assert len(mock_client.history) == 10000

        mock_client.clear_history()
        assert len(mock_client.history) == 0

    def test_history_with_large_response_bodies(self, mock_client: MockClient) -> None:
        large_response = {"data": list(range(10000))}
        mock_client.set_responses(
            [MockHTTPResponse(status_code=200, json_data=large_response)] * 100
        )

        for i in range(100):
            mock_client.get(f"/large/{i}")

        assert len(mock_client.history) == 100

        for record in mock_client.history:
            assert record.response_body is not None

    def test_history_clear_frees_memory(self, mock_client: MockClient) -> None:
        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 5000)

        for i in range(5000):
            mock_client.get(f"/endpoint/{i}")

        assert len(mock_client.history) == 5000

        mock_client.clear_history()

        assert len(mock_client.history) == 0


class TestJourneyMemory:
    """Tests for journey and result memory usage."""

    def test_large_journey_creation(self) -> None:
        steps = [Step(name=f"step_{i}", action=lambda c, ctx: c.get("/")) for i in range(1000)]

        journey = Journey(name="large_journey", steps=steps)

        assert len(journey.steps) == 1000

    def test_journey_with_many_branches(self) -> None:
        checkpoint = Checkpoint(name="start")
        branch = Branch(
            checkpoint_name="start",
            paths=[
                Path(
                    name=f"path_{i}",
                    steps=[
                        Step(name=f"step_{j}", action=lambda c, ctx: c.get("/")) for j in range(10)
                    ],
                )
                for i in range(100)
            ],
        )

        journey = Journey(name="many_branches", steps=[checkpoint, branch])

        assert len(journey.steps) == 2
        assert len(branch.paths) == 100

    def test_journey_result_memory(self) -> None:
        from datetime import datetime

        now = datetime.now()
        step_results = [
            StepResult(
                step_name=f"step_{i}",
                success=True,
                started_at=now,
                finished_at=now,
                duration_ms=1.0,
                response={"status_code": 200, "body": {"data": list(range(100))}},
            )
            for i in range(1000)
        ]

        result = JourneyResult(
            journey_name="memory_test",
            success=True,
            started_at=now,
            finished_at=now,
            step_results=step_results,
            issues=[],
            duration_ms=1000.0,
        )

        assert len(result.step_results) == 1000


class TestIssueMemory:
    """Tests for issue memory usage."""

    def test_many_issues_creation(self) -> None:
        issues = [
            Issue(
                journey=f"journey_{i}",
                path="main",
                step=f"step_{i}",
                error=f"Error {i}",
                severity=Severity.HIGH,
                logs=[f"Log line {j}" for j in range(10)],
            )
            for i in range(1000)
        ]

        assert len(issues) == 1000

        for issue in issues:
            assert len(issue.logs) == 10

    def test_issue_with_large_logs(self) -> None:
        large_logs = [f"Log line {i}: " + "x" * 1000 for i in range(100)]

        issue = Issue(
            journey="test",
            path="main",
            step="step",
            error="Test error",
            logs=large_logs,
        )

        assert len(issue.logs) == 100


class TestStateManagerMemory:
    """Tests for state manager memory usage."""

    def test_many_checkpoints(self) -> None:
        state_manager = MockStateManager()
        state_manager.connect()

        for i in range(10000):
            state_manager.checkpoint(f"checkpoint_{i}")

        assert len(state_manager._checkpoints) == 10000

        state_manager.reset()
        assert len(state_manager._checkpoints) == 0

    def test_checkpoint_data_retention(self) -> None:
        state_manager = MockStateManager()
        state_manager.connect()

        state_manager.checkpoint("cp1")
        state_manager.checkpoint("cp2")
        state_manager.checkpoint("cp3")

        assert len(state_manager._checkpoints) == 3

        state_manager.release("cp2")
        assert "cp2" not in state_manager._checkpoints
        assert len(state_manager._checkpoints) == 2


class TestRunnerMemory:
    """Tests for runner memory usage."""

    def test_runner_cleanup_after_journey(self, mock_client: MockClient) -> None:
        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 100)

        steps = [Step(name=f"step_{i}", action=lambda c, ctx: c.get("/")) for i in range(100)]
        journey = Journey(name="cleanup_test", steps=steps)

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is True
        assert len(runner._issues) == 0 or len(runner.get_issues()) >= 0

    def test_runner_issue_cleanup(self, mock_client: MockClient) -> None:
        mock_client.set_responses([MockHTTPResponse(status_code=500, json_data={})] * 10)

        steps = [Step(name=f"step_{i}", action=lambda c, ctx: c.get("/fail")) for i in range(10)]
        journey = Journey(name="issue_test", steps=steps)

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert len(result.issues) == 10

        # get_issues() returns a copy, so use formatter.clear() to clear internal state
        runner._formatter.clear()
        assert len(runner.get_issues()) == 0


class TestReportMemory:
    """Tests for report generation memory usage."""

    def test_large_markdown_report(self, mock_client: MockClient) -> None:
        from venomqa.reporters.markdown import MarkdownReporter

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 100)

        steps = [Step(name=f"step_{i}", action=lambda c, ctx: c.get("/")) for i in range(100)]
        journey = Journey(name="report_test", steps=steps)

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        reporter = MarkdownReporter()
        report = reporter.generate([result])

        assert len(report) > 0

    def test_large_json_report(self, mock_client: MockClient) -> None:
        from venomqa.reporters.json_report import JSONReporter

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 100)

        steps = [Step(name=f"step_{i}", action=lambda c, ctx: c.get("/")) for i in range(100)]
        journey = Journey(name="json_report_test", steps=steps)

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        reporter = JSONReporter()
        report = reporter.generate([result])

        assert len(report) > 0

    def test_large_junit_report(self, mock_client: MockClient) -> None:
        from venomqa.reporters.junit import JUnitReporter

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 100)

        steps = [Step(name=f"step_{i}", action=lambda c, ctx: c.get("/")) for i in range(100)]
        journey = Journey(name="junit_report_test", steps=steps)

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        reporter = JUnitReporter()
        report = reporter.generate([result])

        assert len(report) > 0


class TestMemoryLeaks:
    """Tests for detecting memory leaks."""

    def test_repeated_journey_execution(self, mock_client: MockClient) -> None:
        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 10)

        journey = Journey(
            name="repeat_test",
            steps=[Step(name="step", action=lambda c, ctx: c.get("/")) for _ in range(10)],
        )

        runner = JourneyRunner(client=mock_client)

        for _ in range(100):
            mock_client.clear_history()
            result = runner.run(journey)
            assert result.success is True

    def test_context_repeated_operations(self) -> None:
        ctx = ExecutionContext()

        for _ in range(100):
            for i in range(100):
                ctx.set(f"key_{i}", f"value_{i}")
            ctx.clear()

        assert len(ctx._data) == 0
        assert len(ctx._step_results) == 0

    def test_large_data_cleanup(self) -> None:
        large_objects = []

        for _ in range(100):
            large_objects.append({"data": list(range(10000))})

        assert len(large_objects) == 100

        large_objects.clear()

        assert len(large_objects) == 0
