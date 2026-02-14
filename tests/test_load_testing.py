"""Tests for load testing capabilities in VenomQA."""

from __future__ import annotations

import json
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from venomqa.core.models import Journey, JourneyResult, Step, StepResult
from venomqa.performance.load_tester import (
    LoadPattern,
    LoadTestAssertions,
    LoadTestConfig,
    LoadTester,
    LoadTestMetrics,
    LoadTestResult,
    RequestSample,
    TimeSeries,
    benchmark_journey,
    run_quick_load_test,
)
from tests.conftest import MockClient, MockHTTPResponse


class TestLoadTestConfig:
    """Tests for LoadTestConfig."""

    def test_basic_config_creation(self) -> None:
        """Test creating a basic config."""
        config = LoadTestConfig(
            duration_seconds=60,
            concurrent_users=10,
            ramp_up_seconds=5,
        )
        assert config.duration_seconds == 60
        assert config.concurrent_users == 10
        assert config.ramp_up_seconds == 5

    def test_config_validation_duration(self) -> None:
        """Test that duration must be positive."""
        with pytest.raises(ValueError, match="duration_seconds must be positive"):
            LoadTestConfig(duration_seconds=0)

        with pytest.raises(ValueError, match="duration_seconds must be positive"):
            LoadTestConfig(duration_seconds=-1)

    def test_config_validation_users(self) -> None:
        """Test that users must be at least 1."""
        with pytest.raises(ValueError, match="concurrent_users must be >= 1"):
            LoadTestConfig(concurrent_users=0)

    def test_config_validation_ramp_up(self) -> None:
        """Test that ramp_up must be non-negative."""
        with pytest.raises(ValueError, match="ramp_up_seconds must be >= 0"):
            LoadTestConfig(ramp_up_seconds=-1)

    def test_config_validation_think_time(self) -> None:
        """Test think time validation."""
        with pytest.raises(ValueError, match="think_time_min must be >= 0"):
            LoadTestConfig(think_time_min=-1)

        with pytest.raises(ValueError, match="think_time_max .* must be >= think_time_min"):
            LoadTestConfig(think_time_min=5, think_time_max=2)

    def test_config_from_dict_basic(self) -> None:
        """Test creating config from dictionary."""
        data = {
            "users": 50,
            "duration": "30s",
            "ramp_up": "10s",
        }
        config = LoadTestConfig.from_dict(data)
        assert config.concurrent_users == 50
        assert config.duration_seconds == 30
        assert config.ramp_up_seconds == 10

    def test_config_from_dict_duration_formats(self) -> None:
        """Test various duration format parsing."""
        # Seconds
        config = LoadTestConfig.from_dict({"duration": "60s"})
        assert config.duration_seconds == 60

        # Minutes
        config = LoadTestConfig.from_dict({"duration": "2m"})
        assert config.duration_seconds == 120

        # Hours
        config = LoadTestConfig.from_dict({"duration": "1h"})
        assert config.duration_seconds == 3600

        # Milliseconds
        config = LoadTestConfig.from_dict({"duration": "500ms"})
        assert config.duration_seconds == 0.5

        # Plain number (seconds)
        config = LoadTestConfig.from_dict({"duration": 45})
        assert config.duration_seconds == 45

    def test_config_from_dict_think_time_range(self) -> None:
        """Test parsing think time range."""
        config = LoadTestConfig.from_dict({"think_time": "1-3s"})
        assert config.think_time_min == 1.0
        assert config.think_time_max == 3.0

        config = LoadTestConfig.from_dict({"think_time": "0.5-1.5s"})
        assert config.think_time_min == 0.5
        assert config.think_time_max == 1.5

        # Single value
        config = LoadTestConfig.from_dict({"think_time": "2s"})
        assert config.think_time_min == 2.0
        assert config.think_time_max == 2.0

    def test_config_from_dict_pattern(self) -> None:
        """Test pattern parsing."""
        config = LoadTestConfig.from_dict({"pattern": "ramp_up"})
        assert config.pattern == LoadPattern.RAMP_UP

        config = LoadTestConfig.from_dict({"pattern": "spike"})
        assert config.pattern == LoadPattern.SPIKE

        # Invalid pattern falls back to constant
        config = LoadTestConfig.from_dict({"pattern": "invalid"})
        assert config.pattern == LoadPattern.CONSTANT


class TestLoadTestMetrics:
    """Tests for LoadTestMetrics."""

    def test_record_successful_sample(self) -> None:
        """Test recording a successful sample."""
        metrics = LoadTestMetrics()
        sample = RequestSample(
            timestamp=time.time(),
            duration_ms=100.0,
            success=True,
            journey_name="test",
        )
        metrics.record(sample)

        assert metrics.total_requests == 1
        assert metrics.successful_requests == 1
        assert metrics.failed_requests == 0
        assert metrics.min_duration_ms == 100.0
        assert metrics.max_duration_ms == 100.0

    def test_record_failed_sample(self) -> None:
        """Test recording a failed sample with error tracking."""
        metrics = LoadTestMetrics()
        sample = RequestSample(
            timestamp=time.time(),
            duration_ms=50.0,
            success=False,
            error="Connection refused",
            journey_name="test",
        )
        metrics.record(sample)

        assert metrics.total_requests == 1
        assert metrics.successful_requests == 0
        assert metrics.failed_requests == 1
        assert "Connection refused" in metrics.error_breakdown
        assert metrics.error_breakdown["Connection refused"] == 1

    def test_record_multiple_samples(self) -> None:
        """Test recording multiple samples."""
        metrics = LoadTestMetrics()

        for i in range(10):
            sample = RequestSample(
                timestamp=time.time(),
                duration_ms=50.0 + i * 10,
                success=i % 2 == 0,
                error="Error" if i % 2 != 0 else None,
                journey_name="test",
            )
            metrics.record(sample)

        assert metrics.total_requests == 10
        assert metrics.successful_requests == 5
        assert metrics.failed_requests == 5
        assert metrics.min_duration_ms == 50.0
        assert metrics.max_duration_ms == 140.0

    def test_get_snapshot(self) -> None:
        """Test getting a metrics snapshot."""
        metrics = LoadTestMetrics()

        for i in range(5):
            sample = RequestSample(
                timestamp=time.time(),
                duration_ms=100.0,
                success=True,
                journey_name="test",
            )
            metrics.record(sample)

        snapshot = metrics.get_snapshot()

        assert snapshot["total_requests"] == 5
        assert snapshot["successful_requests"] == 5
        assert snapshot["failed_requests"] == 0
        assert snapshot["success_rate_pct"] == 100.0
        assert snapshot["error_rate_pct"] == 0.0
        assert snapshot["avg_duration_ms"] == 100.0

    def test_capture_time_series_point(self) -> None:
        """Test capturing time series data points."""
        metrics = LoadTestMetrics()
        metrics.active_users = 5

        # Record some samples
        for i in range(10):
            sample = RequestSample(
                timestamp=time.time(),
                duration_ms=50.0 + i * 5,
                success=True,
                journey_name="test",
            )
            metrics.record(sample)

        # Capture time series point
        metrics.capture_time_series_point()

        assert len(metrics.time_series) == 1
        ts = metrics.time_series[0]
        assert ts.requests_count == 10
        assert ts.success_count == 10
        assert ts.error_count == 0
        assert ts.active_users == 5

    def test_thread_safety(self) -> None:
        """Test that metrics are thread-safe."""
        metrics = LoadTestMetrics()
        errors = []

        def worker(worker_id: int) -> None:
            try:
                for i in range(100):
                    sample = RequestSample(
                        timestamp=time.time(),
                        duration_ms=float(i),
                        success=True,
                        journey_name="test",
                    )
                    metrics.record(sample)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert metrics.total_requests == 1000


class TestLoadTestAssertions:
    """Tests for LoadTestAssertions."""

    def test_p99_assertion_pass(self) -> None:
        """Test P99 assertion passes."""
        assertions = LoadTestAssertions(max_p99_ms=500)
        result = MagicMock(spec=LoadTestResult)
        result.percentiles = {"p99": 450}
        result.error_rate = 0.0
        result.throughput = 100.0
        result.metrics = {}

        passed, failures = assertions.validate(result)
        assert passed is True
        assert len(failures) == 0

    def test_p99_assertion_fail(self) -> None:
        """Test P99 assertion fails."""
        assertions = LoadTestAssertions(max_p99_ms=500)
        result = MagicMock(spec=LoadTestResult)
        result.percentiles = {"p99": 600}
        result.error_rate = 0.0
        result.throughput = 100.0
        result.metrics = {}

        passed, failures = assertions.validate(result)
        assert passed is False
        assert len(failures) == 1
        assert "P99 latency" in failures[0]

    def test_error_rate_assertion(self) -> None:
        """Test error rate assertion."""
        assertions = LoadTestAssertions(max_error_rate_percent=1.0)
        result = MagicMock(spec=LoadTestResult)
        result.percentiles = {}
        result.error_rate = 2.0
        result.throughput = 100.0
        result.metrics = {}

        passed, failures = assertions.validate(result)
        assert passed is False
        assert "Error rate" in failures[0]

    def test_throughput_assertion(self) -> None:
        """Test throughput assertion."""
        assertions = LoadTestAssertions(min_throughput_rps=100)
        result = MagicMock(spec=LoadTestResult)
        result.percentiles = {}
        result.error_rate = 0.0
        result.throughput = 50.0
        result.metrics = {}

        passed, failures = assertions.validate(result)
        assert passed is False
        assert "Throughput" in failures[0]

    def test_multiple_assertions(self) -> None:
        """Test multiple assertions at once."""
        assertions = LoadTestAssertions(
            max_p99_ms=500,
            max_error_rate_percent=1.0,
            min_throughput_rps=100,
        )
        result = MagicMock(spec=LoadTestResult)
        result.percentiles = {"p99": 600}
        result.error_rate = 2.0
        result.throughput = 50.0
        result.metrics = {}

        passed, failures = assertions.validate(result)
        assert passed is False
        assert len(failures) == 3

    def test_assert_valid_raises(self) -> None:
        """Test assert_valid raises AssertionError."""
        assertions = LoadTestAssertions(max_p99_ms=500)
        result = MagicMock(spec=LoadTestResult)
        result.percentiles = {"p99": 600}
        result.error_rate = 0.0
        result.throughput = 100.0
        result.metrics = {}

        with pytest.raises(AssertionError, match="Load test assertions failed"):
            assertions.assert_valid(result)

    def test_from_dict(self) -> None:
        """Test creating assertions from dict."""
        data = {
            "p99": 500,
            "error_rate": 1.0,
            "throughput": 100,
        }
        assertions = LoadTestAssertions.from_dict(data)
        assert assertions.max_p99_ms == 500
        assert assertions.max_error_rate_percent == 1.0
        assert assertions.min_throughput_rps == 100


class TestLoadTestResult:
    """Tests for LoadTestResult."""

    def test_to_dict(self) -> None:
        """Test converting result to dictionary."""
        config = LoadTestConfig(duration_seconds=60, concurrent_users=10)
        result = LoadTestResult(
            config=config,
            metrics={"total_requests": 100},
            started_at=datetime.now(),
            finished_at=datetime.now(),
            duration_seconds=60.0,
            percentiles={"p50": 100, "p99": 500},
            throughput=50.0,
            error_rate=1.0,
        )

        data = result.to_dict()
        assert data["config"]["concurrent_users"] == 10
        assert data["throughput_rps"] == 50.0
        assert data["error_rate_pct"] == 1.0
        assert data["percentiles"]["p99"] == 500

    def test_get_summary(self) -> None:
        """Test getting summary string."""
        config = LoadTestConfig(duration_seconds=60, concurrent_users=10)
        result = LoadTestResult(
            config=config,
            metrics={
                "total_requests": 100,
                "successful_requests": 99,
                "failed_requests": 1,
                "min_duration_ms": 50,
                "avg_duration_ms": 100,
                "max_duration_ms": 500,
            },
            started_at=datetime.now(),
            finished_at=datetime.now(),
            duration_seconds=60.0,
            percentiles={"p50": 100, "p99": 500},
            throughput=50.0,
            error_rate=1.0,
        )

        summary = result.get_summary()
        assert "LOAD TEST SUMMARY" in summary
        assert "Total Requests: 100" in summary
        assert "Throughput: 50.00 req/s" in summary
        assert "Error Rate: 1.00%" in summary

    def test_save_report_json(self) -> None:
        """Test saving report as JSON."""
        config = LoadTestConfig(duration_seconds=60, concurrent_users=10)
        result = LoadTestResult(
            config=config,
            metrics={"total_requests": 100},
            started_at=datetime.now(),
            finished_at=datetime.now(),
            duration_seconds=60.0,
            throughput=50.0,
            error_rate=1.0,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.json"
            result.save_report(path, format="json")

            assert path.exists()
            with open(path) as f:
                data = json.load(f)
                assert data["throughput_rps"] == 50.0

    def test_save_report_markdown(self) -> None:
        """Test saving report as Markdown."""
        config = LoadTestConfig(duration_seconds=60, concurrent_users=10)
        result = LoadTestResult(
            config=config,
            metrics={
                "total_requests": 100,
                "successful_requests": 99,
                "failed_requests": 1,
                "min_duration_ms": 50,
                "avg_duration_ms": 100,
                "max_duration_ms": 500,
            },
            started_at=datetime.now(),
            finished_at=datetime.now(),
            duration_seconds=60.0,
            throughput=50.0,
            error_rate=1.0,
            percentiles={"p50": 100, "p99": 500},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.md"
            result.save_report(path, format="markdown")

            assert path.exists()
            content = path.read_text()
            assert "# Load Test Report" in content
            assert "| Throughput | 50.00 req/s |" in content

    def test_save_report_html(self) -> None:
        """Test saving report as HTML."""
        config = LoadTestConfig(duration_seconds=60, concurrent_users=10)
        result = LoadTestResult(
            config=config,
            metrics={"total_requests": 100},
            started_at=datetime.now(),
            finished_at=datetime.now(),
            duration_seconds=60.0,
            throughput=50.0,
            error_rate=1.0,
            percentiles={"p50": 100, "p99": 500},
            time_series=[
                TimeSeries(
                    timestamp=time.time(),
                    elapsed_seconds=10,
                    requests_count=10,
                    success_count=10,
                    error_count=0,
                    active_users=5,
                    rps=1.0,
                    avg_response_ms=100,
                    p50_ms=100,
                    p95_ms=200,
                    p99_ms=300,
                )
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.html"
            result.save_report(path, format="html")

            assert path.exists()
            content = path.read_text()
            assert "<!DOCTYPE html>" in content
            assert "Load Test Report" in content
            assert "chart.js" in content.lower()


class TestLoadTester:
    """Tests for LoadTester."""

    def test_basic_load_test(self, mock_client: MockClient) -> None:
        """Test running a basic load test."""
        from venomqa.runner import JourneyRunner

        steps = [Step(name="test_step", action=lambda c, ctx: c.get("/api"))]
        journey = Journey(name="test_journey", steps=steps)

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 100)

        config = LoadTestConfig(
            duration_seconds=1.0,
            concurrent_users=2,
            ramp_up_seconds=0.0,
        )
        tester = LoadTester(config)
        result = tester.run(journey, lambda: JourneyRunner(client=mock_client))

        assert result.duration_seconds >= 1.0
        assert result.metrics["total_requests"] > 0
        assert "p50" in result.percentiles
        assert "p99" in result.percentiles
        assert result.throughput > 0

    def test_load_test_with_ramp_up(self, mock_client: MockClient) -> None:
        """Test load test with ramp-up."""
        from venomqa.runner import JourneyRunner

        steps = [Step(name="test_step", action=lambda c, ctx: c.get("/api"))]
        journey = Journey(name="test_journey", steps=steps)

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 100)

        config = LoadTestConfig(
            duration_seconds=1.0,
            concurrent_users=4,
            ramp_up_seconds=0.5,
        )
        tester = LoadTester(config)
        result = tester.run(journey, lambda: JourneyRunner(client=mock_client))

        assert result.duration_seconds >= 1.0
        assert result.metrics["total_requests"] > 0

    def test_load_test_with_think_time(self, mock_client: MockClient) -> None:
        """Test load test with think time."""
        from venomqa.runner import JourneyRunner

        steps = [Step(name="test_step", action=lambda c, ctx: c.get("/api"))]
        journey = Journey(name="test_journey", steps=steps)

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 100)

        config = LoadTestConfig(
            duration_seconds=1.0,
            concurrent_users=2,
            think_time_min=0.1,
            think_time_max=0.2,
        )
        tester = LoadTester(config)
        result = tester.run(journey, lambda: JourneyRunner(client=mock_client))

        # With think time, fewer requests should be made
        assert result.metrics["total_requests"] > 0
        # Requests should be throttled
        assert result.throughput < 100  # Much lower due to think time

    def test_load_test_with_errors(self, mock_client: MockClient) -> None:
        """Test load test with some errors."""
        from venomqa.runner import JourneyRunner

        steps = [Step(name="test_step", action=lambda c, ctx: c.get("/api"))]
        journey = Journey(name="test_journey", steps=steps)

        # Mix of success and failure responses
        responses = [
            MockHTTPResponse(status_code=200, json_data={}) if i % 3 != 0
            else MockHTTPResponse(status_code=500, json_data={})
            for i in range(100)
        ]
        mock_client.set_responses(responses)

        config = LoadTestConfig(
            duration_seconds=0.5,
            concurrent_users=2,
        )
        tester = LoadTester(config)
        result = tester.run(journey, lambda: JourneyRunner(client=mock_client))

        assert result.metrics["failed_requests"] > 0
        assert result.error_rate > 0
        assert len(result.error_breakdown) > 0

    def test_load_test_stop(self, mock_client: MockClient) -> None:
        """Test stopping a load test early."""
        from venomqa.runner import JourneyRunner

        steps = [Step(name="test_step", action=lambda c, ctx: c.get("/api"))]
        journey = Journey(name="test_journey", steps=steps)

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 1000)

        config = LoadTestConfig(
            duration_seconds=10.0,  # Long duration
            concurrent_users=2,
        )
        tester = LoadTester(config)

        # Stop after a short time
        def stop_after_delay():
            time.sleep(0.5)
            tester.stop()

        stop_thread = threading.Thread(target=stop_after_delay)
        stop_thread.start()

        result = tester.run(journey, lambda: JourneyRunner(client=mock_client))
        stop_thread.join()

        # Should stop before full duration
        assert result.duration_seconds < 10.0

    def test_progress_callback(self, mock_client: MockClient) -> None:
        """Test progress callback is called."""
        from venomqa.runner import JourneyRunner

        steps = [Step(name="test_step", action=lambda c, ctx: c.get("/api"))]
        journey = Journey(name="test_journey", steps=steps)

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 100)

        progress_updates = []

        def progress_callback(metrics):
            progress_updates.append(metrics.get_snapshot())

        config = LoadTestConfig(
            duration_seconds=1.0,
            concurrent_users=2,
            sample_interval=0.2,
        )
        tester = LoadTester(config, progress_callback=progress_callback)
        result = tester.run(journey, lambda: JourneyRunner(client=mock_client))

        # Should have received some progress updates
        assert len(progress_updates) > 0

    def test_time_series_collection(self, mock_client: MockClient) -> None:
        """Test time series data is collected."""
        from venomqa.runner import JourneyRunner

        steps = [Step(name="test_step", action=lambda c, ctx: c.get("/api"))]
        journey = Journey(name="test_journey", steps=steps)

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 100)

        config = LoadTestConfig(
            duration_seconds=1.5,
            concurrent_users=2,
            sample_interval=0.5,
        )
        tester = LoadTester(config)
        result = tester.run(journey, lambda: JourneyRunner(client=mock_client))

        # Should have time series data points
        assert len(result.time_series) > 0


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_run_quick_load_test(self, mock_client: MockClient) -> None:
        """Test run_quick_load_test function."""
        from venomqa.runner import JourneyRunner

        steps = [Step(name="test_step", action=lambda c, ctx: c.get("/api"))]
        journey = Journey(name="test_journey", steps=steps)

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 50)

        result = run_quick_load_test(
            journey,
            lambda: JourneyRunner(client=mock_client),
            duration_seconds=0.5,
            concurrent_users=2,
        )

        assert result.duration_seconds >= 0.5
        assert result.metrics["total_requests"] > 0

    def test_benchmark_journey(self, mock_client: MockClient) -> None:
        """Test benchmark_journey function."""
        from venomqa.runner import JourneyRunner

        steps = [Step(name="test_step", action=lambda c, ctx: c.get("/api"))]
        journey = Journey(name="test_journey", steps=steps)

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 50)

        result = benchmark_journey(
            journey,
            lambda: JourneyRunner(client=mock_client),
            iterations=10,
            warmup_iterations=2,
        )

        assert result["iterations"] == 10
        assert "avg_time_ms" in result
        assert "p50_ms" in result
        assert "p99_ms" in result
        assert "throughput_per_sec" in result


class TestLoadPattern:
    """Tests for LoadPattern enum."""

    def test_pattern_values(self) -> None:
        """Test pattern values."""
        assert LoadPattern.CONSTANT.value == "constant"
        assert LoadPattern.RAMP_UP.value == "ramp_up"
        assert LoadPattern.SPIKE.value == "spike"
        assert LoadPattern.STRESS.value == "stress"
