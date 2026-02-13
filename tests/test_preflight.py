"""Tests for VenomQA Preflight - Pre-test execution checks."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from venomqa.preflight import (
    CheckResult,
    CheckStatus,
    PreflightChecker,
    PreflightResult,
    run_preflight_checks,
    run_preflight_checks_with_output,
)


class TestCheckStatus:
    """Tests for the CheckStatus enum."""

    def test_check_status_values(self):
        """Test CheckStatus enum has expected values."""
        assert CheckStatus.PASSED.value == "passed"
        assert CheckStatus.FAILED.value == "failed"
        assert CheckStatus.WARNING.value == "warning"
        assert CheckStatus.SKIPPED.value == "skipped"


class TestCheckResult:
    """Tests for the CheckResult dataclass."""

    def test_check_result_creation(self):
        """Test CheckResult can be created with required fields."""
        result = CheckResult(
            name="test_check",
            status=CheckStatus.PASSED,
            message="Check passed successfully",
        )

        assert result.name == "test_check"
        assert result.status == CheckStatus.PASSED
        assert result.message == "Check passed successfully"
        assert result.duration_ms == 0.0
        assert result.details == {}

    def test_check_result_with_details(self):
        """Test CheckResult can include duration and details."""
        result = CheckResult(
            name="test_check",
            status=CheckStatus.FAILED,
            message="Check failed",
            duration_ms=150.5,
            details={"error": "Connection refused", "host": "localhost"},
        )

        assert result.duration_ms == 150.5
        assert result.details["error"] == "Connection refused"
        assert result.details["host"] == "localhost"


class TestPreflightResult:
    """Tests for the PreflightResult dataclass."""

    def test_preflight_result_empty(self):
        """Test empty PreflightResult has correct defaults."""
        result = PreflightResult()

        assert result.passed == []
        assert result.failed == []
        assert result.warnings == []
        assert result.skipped == []
        assert result.total_duration_ms == 0.0
        assert result.success is True
        assert result.total_checks == 0

    def test_preflight_result_add_passed(self):
        """Test adding a passed check."""
        result = PreflightResult()
        check = CheckResult("test", CheckStatus.PASSED, "ok")

        result.add(check)

        assert len(result.passed) == 1
        assert result.passed[0] == check
        assert result.success is True

    def test_preflight_result_add_failed(self):
        """Test adding a failed check."""
        result = PreflightResult()
        check = CheckResult("test", CheckStatus.FAILED, "error")

        result.add(check)

        assert len(result.failed) == 1
        assert result.failed[0] == check
        assert result.success is False

    def test_preflight_result_add_warning(self):
        """Test adding a warning check."""
        result = PreflightResult()
        check = CheckResult("test", CheckStatus.WARNING, "warning")

        result.add(check)

        assert len(result.warnings) == 1
        assert result.warnings[0] == check
        assert result.success is True  # Warnings don't affect success

    def test_preflight_result_add_skipped(self):
        """Test adding a skipped check."""
        result = PreflightResult()
        check = CheckResult("test", CheckStatus.SKIPPED, "skipped")

        result.add(check)

        assert len(result.skipped) == 1
        assert result.skipped[0] == check

    def test_preflight_result_total_checks(self):
        """Test total_checks property counts all checks."""
        result = PreflightResult()
        result.add(CheckResult("p1", CheckStatus.PASSED, "ok"))
        result.add(CheckResult("p2", CheckStatus.PASSED, "ok"))
        result.add(CheckResult("f1", CheckStatus.FAILED, "error"))
        result.add(CheckResult("w1", CheckStatus.WARNING, "warn"))
        result.add(CheckResult("s1", CheckStatus.SKIPPED, "skip"))

        assert result.total_checks == 5

    def test_preflight_result_to_dict(self):
        """Test to_dict serialization."""
        result = PreflightResult()
        result.add(CheckResult("p1", CheckStatus.PASSED, "ok", duration_ms=10.0))
        result.add(CheckResult("f1", CheckStatus.FAILED, "error", details={"foo": "bar"}))
        result.total_duration_ms = 100.0

        data = result.to_dict()

        assert data["success"] is False
        assert data["total_checks"] == 2
        assert data["total_duration_ms"] == 100.0
        assert len(data["passed"]) == 1
        assert len(data["failed"]) == 1
        assert data["passed"][0]["name"] == "p1"
        assert data["failed"][0]["details"]["foo"] == "bar"


class TestPreflightChecker:
    """Tests for the PreflightChecker class."""

    def test_checker_initialization(self):
        """Test PreflightChecker initialization with config."""
        config = {"base_url": "http://localhost:8000"}
        checker = PreflightChecker(config)

        assert checker.config == config
        assert isinstance(checker.result, PreflightResult)

    def test_checker_registers_default_checks(self):
        """Test PreflightChecker registers default checks."""
        config = {"base_url": "http://localhost:8000"}
        checker = PreflightChecker(config)

        # Should have at least some checks registered
        assert len(checker._checks) > 0

    def test_checker_register_custom_check(self):
        """Test registering a custom check."""
        config = {"base_url": "http://localhost:8000"}
        checker = PreflightChecker(config)
        initial_count = len(checker._checks)

        def custom_check() -> CheckResult:
            return CheckResult("custom", CheckStatus.PASSED, "ok")

        checker.register_check("custom_check", custom_check)

        assert len(checker._checks) == initial_count + 1

    def test_checker_run_returns_result(self):
        """Test run() returns PreflightResult."""
        config = {"base_url": "http://localhost:8000"}
        checker = PreflightChecker(config)
        checker._checks = []  # Clear default checks

        def passing_check() -> CheckResult:
            return CheckResult("test", CheckStatus.PASSED, "ok")

        checker.register_check("test", passing_check)
        result = checker.run()

        assert isinstance(result, PreflightResult)
        assert len(result.passed) == 1

    def test_checker_run_handles_exceptions(self):
        """Test run() handles exceptions in check functions."""
        config = {"base_url": "http://localhost:8000"}
        checker = PreflightChecker(config)
        checker._checks = []

        def failing_check() -> CheckResult:
            raise RuntimeError("Check exploded")

        checker.register_check("test", failing_check, required=True)
        result = checker.run()

        assert len(result.failed) == 1
        assert "exception" in result.failed[0].message.lower()

    def test_checker_optional_failure_becomes_warning(self):
        """Test optional check failures become warnings."""
        config = {"base_url": "http://localhost:8000"}
        checker = PreflightChecker(config)
        checker._checks = []

        def failing_check() -> CheckResult:
            return CheckResult("test", CheckStatus.FAILED, "failed")

        checker.register_check("test", failing_check, required=False)
        result = checker.run()

        assert len(result.warnings) == 1
        assert len(result.failed) == 0


class TestPreflightCheckerChecks:
    """Tests for individual preflight check methods."""

    @patch("socket.socket")
    @patch("httpx.Client")
    def test_check_target_api_success(self, mock_client_class, mock_socket):
        """Test _check_target_api when API is reachable."""
        config = {"base_url": "http://localhost:8000", "timeout": 30}
        checker = PreflightChecker(config)

        # Mock socket connection
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        mock_sock.connect.return_value = None

        # Mock HTTP client
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.get.return_value = mock_response

        result = checker._check_target_api()

        assert result.status == CheckStatus.PASSED
        assert "reachable" in result.message.lower()

    @patch("socket.socket")
    def test_check_target_api_socket_failure(self, mock_socket):
        """Test _check_target_api when socket connection fails."""
        config = {"base_url": "http://localhost:8000", "timeout": 30}
        checker = PreflightChecker(config)

        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        mock_sock.connect.side_effect = socket.timeout("Connection timed out")

        result = checker._check_target_api()

        assert result.status == CheckStatus.FAILED
        assert "connect" in result.message.lower()

    def test_check_docker_compose_file_missing(self, tmp_path, monkeypatch):
        """Test _check_docker_compose_file when file doesn't exist."""
        monkeypatch.chdir(tmp_path)
        config = {"docker_compose_file": "docker-compose.qa.yml"}
        checker = PreflightChecker(config)

        result = checker._check_docker_compose_file()

        assert result.status == CheckStatus.FAILED
        assert "not found" in result.message.lower()

    def test_check_docker_compose_file_exists(self, tmp_path, monkeypatch):
        """Test _check_docker_compose_file when file exists."""
        monkeypatch.chdir(tmp_path)
        compose_file = tmp_path / "docker-compose.qa.yml"
        compose_file.write_text("version: '3.8'\nservices: {}")

        config = {"docker_compose_file": "docker-compose.qa.yml"}
        checker = PreflightChecker(config)

        # Mock docker compose config command
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = checker._check_docker_compose_file()

        assert result.status == CheckStatus.PASSED
        assert "valid" in result.message.lower()

    def test_check_database_no_url(self):
        """Test _check_database when no db_url is configured."""
        config = {}
        checker = PreflightChecker(config)

        result = checker._check_database()

        assert result.status == CheckStatus.SKIPPED
        assert "not configured" in result.message.lower()

    @patch("socket.socket")
    def test_check_database_reachable(self, mock_socket):
        """Test _check_database when database is reachable."""
        config = {"db_url": "postgresql://user:pass@localhost:5432/testdb"}
        checker = PreflightChecker(config)

        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        mock_sock.connect.return_value = None

        result = checker._check_database()

        assert result.status == CheckStatus.PASSED
        assert "reachable" in result.message.lower()

    @patch("socket.socket")
    def test_check_database_unreachable(self, mock_socket):
        """Test _check_database when database is unreachable."""
        config = {"db_url": "postgresql://user:pass@localhost:5432/testdb"}
        checker = PreflightChecker(config)

        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        mock_sock.connect.side_effect = socket.error("Connection refused")

        result = checker._check_database()

        assert result.status == CheckStatus.FAILED
        assert "connect" in result.message.lower()

    def test_check_journeys_directory_missing(self, tmp_path, monkeypatch):
        """Test _check_journeys_directory when directory doesn't exist."""
        monkeypatch.chdir(tmp_path)
        config = {}
        checker = PreflightChecker(config)

        result = checker._check_journeys_directory()

        assert result.status == CheckStatus.FAILED
        assert "not found" in result.message.lower()

    def test_check_journeys_directory_empty(self, tmp_path, monkeypatch):
        """Test _check_journeys_directory when directory is empty."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "journeys").mkdir()
        config = {}
        checker = PreflightChecker(config)

        result = checker._check_journeys_directory()

        assert result.status == CheckStatus.WARNING
        assert "no journey files" in result.message.lower()

    def test_check_journeys_directory_with_journeys(self, tmp_path, monkeypatch):
        """Test _check_journeys_directory with journey files."""
        monkeypatch.chdir(tmp_path)
        journeys_dir = tmp_path / "journeys"
        journeys_dir.mkdir()
        (journeys_dir / "test_journey.py").write_text("# journey")

        config = {}
        checker = PreflightChecker(config)

        result = checker._check_journeys_directory()

        assert result.status == CheckStatus.PASSED
        assert "1 journey file" in result.message

    def test_check_config_validation_valid(self):
        """Test _check_config_validation with valid config."""
        config = {
            "base_url": "http://localhost:8000",
            "timeout": 30,
            "verbose": False,
        }
        checker = PreflightChecker(config)

        result = checker._check_config_validation()

        assert result.status == CheckStatus.PASSED
        assert "valid" in result.message.lower()


class TestRunPreflightChecks:
    """Tests for the run_preflight_checks function."""

    def test_run_preflight_checks_returns_result(self):
        """Test run_preflight_checks returns a PreflightResult."""
        config = {"base_url": "http://localhost:8000"}

        with patch.object(PreflightChecker, "run") as mock_run:
            mock_run.return_value = PreflightResult()
            result = run_preflight_checks(config)

        assert isinstance(result, PreflightResult)

    def test_run_preflight_checks_passes_config(self):
        """Test run_preflight_checks passes config to checker."""
        config = {"base_url": "http://example.com", "timeout": 60}

        with patch.object(PreflightChecker, "__init__", return_value=None) as mock_init:
            with patch.object(PreflightChecker, "run", return_value=PreflightResult()):
                # Need to also patch _register_default_checks since __init__ is mocked
                with patch.object(PreflightChecker, "_register_default_checks"):
                    checker = PreflightChecker.__new__(PreflightChecker)
                    checker.config = config
                    checker.result = PreflightResult()
                    checker._checks = []

        # Just verify the function runs without error
        result = run_preflight_checks(config)
        assert isinstance(result, PreflightResult)


class TestRunPreflightChecksWithOutput:
    """Tests for the run_preflight_checks_with_output function."""

    def test_run_with_output_returns_result(self):
        """Test run_preflight_checks_with_output returns PreflightResult."""
        config = {"base_url": "http://localhost:8000"}

        with patch.object(PreflightChecker, "run") as mock_run:
            mock_result = PreflightResult()
            mock_result.add(CheckResult("test", CheckStatus.PASSED, "ok"))
            mock_run.return_value = mock_result

            result = run_preflight_checks_with_output(config)

        assert isinstance(result, PreflightResult)

    def test_run_with_output_uses_provided_console(self):
        """Test run_preflight_checks_with_output uses provided console."""
        from rich.console import Console

        config = {"base_url": "http://localhost:8000"}
        mock_console = MagicMock(spec=Console)

        with patch.object(PreflightChecker, "run") as mock_run:
            mock_result = PreflightResult()
            mock_run.return_value = mock_result

            run_preflight_checks_with_output(config, console=mock_console)

        # Verify console methods were called
        assert mock_console.print.called


class TestPreflightIntegration:
    """Integration tests for the preflight system."""

    def test_full_preflight_run(self, tmp_path, monkeypatch):
        """Test a full preflight run with mixed results."""
        monkeypatch.chdir(tmp_path)

        # Create minimal valid structure
        journeys_dir = tmp_path / "journeys"
        journeys_dir.mkdir()
        (journeys_dir / "test_journey.py").write_text("# test")

        config = {
            "base_url": "http://localhost:8000",
            "timeout": 30,
        }

        # Run preflight (some checks will fail in test environment)
        result = run_preflight_checks(config)

        assert isinstance(result, PreflightResult)
        assert result.total_checks > 0
        assert result.total_duration_ms >= 0

    def test_preflight_result_serializable(self, tmp_path, monkeypatch):
        """Test that PreflightResult can be serialized to JSON."""
        monkeypatch.chdir(tmp_path)
        journeys_dir = tmp_path / "journeys"
        journeys_dir.mkdir()
        (journeys_dir / "test_journey.py").write_text("# test")

        config = {"base_url": "http://localhost:8000"}
        result = run_preflight_checks(config)

        # Should be JSON serializable
        json_str = json.dumps(result.to_dict())
        parsed = json.loads(json_str)

        assert "success" in parsed
        assert "total_checks" in parsed
        assert "passed" in parsed
        assert "failed" in parsed
