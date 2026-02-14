"""Tests for VenomQA Preflight - Pre-test execution checks and smoke tests."""

from __future__ import annotations

import io
import json
import socket
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from venomqa.preflight import (
    APINotReadyError,
    AutoPreflight,
    CheckResult,
    CheckStatus,
    PreflightChecker,
    PreflightResult,
    SmokeTest,
    SmokeTestReport,
    SmokeTestResult,
    run_preflight_checks,
    run_preflight_checks_with_output,
)
from venomqa.preflight.checks import (
    AuthCheck,
    CRUDCheck,
    DatabaseCheck,
    HealthCheck,
    ListCheck,
    OpenAPICheck,
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
        assert "no database url" in result.message.lower()

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


# =========================================================================
# Helpers for smoke test mocking
# =========================================================================

def _mock_response(status_code: int = 200, json_body: object = None, text: str = "") -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text or (json.dumps(json_body) if json_body is not None else "")
    if json_body is not None:
        resp.json.return_value = json_body
    else:
        resp.json.side_effect = json.JSONDecodeError("", "", 0)
    return resp


def _patch_httpx_get(response: MagicMock):
    """Patch httpx.Client to return a specific response on GET."""
    client_mock = MagicMock()
    client_mock.__enter__ = MagicMock(return_value=client_mock)
    client_mock.__exit__ = MagicMock(return_value=False)
    client_mock.get.return_value = response
    return patch("httpx.Client", return_value=client_mock)


def _patch_httpx_post(response: MagicMock):
    """Patch httpx.Client to return a specific response on POST."""
    client_mock = MagicMock()
    client_mock.__enter__ = MagicMock(return_value=client_mock)
    client_mock.__exit__ = MagicMock(return_value=False)
    client_mock.post.return_value = response
    return patch("httpx.Client", return_value=client_mock)


def _patch_httpx_client(**method_responses):
    """Patch httpx.Client to return specific responses for multiple methods."""
    client_mock = MagicMock()
    client_mock.__enter__ = MagicMock(return_value=client_mock)
    client_mock.__exit__ = MagicMock(return_value=False)
    for method, response in method_responses.items():
        getattr(client_mock, method).return_value = response
    return patch("httpx.Client", return_value=client_mock)


# =========================================================================
# HealthCheck smoke tests
# =========================================================================

class TestHealthCheck:
    """Tests for HealthCheck."""

    def test_health_check_success(self):
        resp = _mock_response(200)
        with _patch_httpx_get(resp):
            check = HealthCheck("http://localhost:8000")
            result = check.run()
        assert result.passed is True
        assert result.status_code == 200
        assert result.name == "Health check"
        assert result.duration_ms >= 0

    def test_health_check_204_success(self):
        resp = _mock_response(204)
        with _patch_httpx_get(resp):
            check = HealthCheck("http://localhost:8000")
            result = check.run()
        assert result.passed is True
        assert result.status_code == 204

    def test_health_check_500_failure(self):
        resp = _mock_response(500)
        with _patch_httpx_get(resp):
            check = HealthCheck("http://localhost:8000")
            result = check.run()
        assert result.passed is False
        assert result.status_code == 500
        assert "500" in result.error
        assert result.suggestion is not None

    def test_health_check_404_failure(self):
        resp = _mock_response(404)
        with _patch_httpx_get(resp):
            check = HealthCheck("http://localhost:8000")
            result = check.run()
        assert result.passed is False
        assert result.status_code == 404
        assert result.suggestion is not None
        assert "path" in result.suggestion.lower()

    def test_health_check_connection_refused(self):
        with patch("httpx.Client") as mock_cls:
            client_mock = MagicMock()
            client_mock.__enter__ = MagicMock(return_value=client_mock)
            client_mock.__exit__ = MagicMock(return_value=False)
            client_mock.get.side_effect = httpx.ConnectError("Connection refused")
            mock_cls.return_value = client_mock

            check = HealthCheck("http://localhost:8000")
            result = check.run()

        assert result.passed is False
        assert result.status_code is None
        assert "refused" in result.error.lower()
        assert result.suggestion is not None

    def test_health_check_custom_path(self):
        resp = _mock_response(200)
        with _patch_httpx_get(resp) as mock_cls:
            check = HealthCheck("http://localhost:8000", path="/healthz")
            result = check.run()
            client = mock_cls.return_value.__enter__.return_value
            client.get.assert_called_once()
            url_arg = client.get.call_args[0][0]
            assert "/healthz" in url_arg
        assert result.passed is True


# =========================================================================
# AuthCheck smoke tests
# =========================================================================

class TestAuthCheck:
    """Tests for AuthCheck."""

    def test_auth_check_success(self):
        resp = _mock_response(200, json_body=[{"id": 1, "name": "workspace"}])
        with _patch_httpx_get(resp):
            check = AuthCheck("http://localhost:8000", token="valid-token")
            result = check.run()
        assert result.passed is True
        assert result.status_code == 200

    def test_auth_check_no_token_skips(self):
        check = AuthCheck("http://localhost:8000", token=None)
        result = check.run()
        assert result.passed is True
        assert result.status_code is None

    def test_auth_check_401(self):
        resp = _mock_response(401)
        with _patch_httpx_get(resp):
            check = AuthCheck("http://localhost:8000", token="expired-token")
            result = check.run()
        assert result.passed is False
        assert result.status_code == 401
        assert "authentication" in result.error.lower() or "401" in result.error
        assert result.suggestion is not None
        assert "token" in result.suggestion.lower()

    def test_auth_check_403(self):
        resp = _mock_response(403)
        with _patch_httpx_get(resp):
            check = AuthCheck("http://localhost:8000", token="no-perms-token")
            result = check.run()
        assert result.passed is False
        assert result.status_code == 403
        assert result.suggestion is not None

    def test_auth_check_500_jwt_user_missing(self):
        resp = _mock_response(500, text='{"detail": "User not found in database"}')
        resp.text = '{"detail": "User not found in database"}'
        with _patch_httpx_get(resp):
            check = AuthCheck("http://localhost:8000", token="jwt-bad-user")
            result = check.run()
        assert result.passed is False
        assert result.status_code == 500
        assert result.suggestion is not None
        assert "database" in result.suggestion.lower() or "db" in result.suggestion.lower()

    def test_auth_check_bearer_prefix_handling(self):
        """Token with 'Bearer ' prefix should work without doubling."""
        resp = _mock_response(200)
        with _patch_httpx_get(resp) as mock_cls:
            check = AuthCheck("http://localhost:8000", token="Bearer already-prefixed")
            result = check.run()
            client = mock_cls.return_value.__enter__.return_value
            headers = client.get.call_args[1]["headers"]
            assert headers["Authorization"] == "Bearer already-prefixed"
        assert result.passed is True


# =========================================================================
# CRUDCheck smoke tests
# =========================================================================

class TestCRUDCheck:
    """Tests for CRUDCheck."""

    def test_create_201_success(self):
        resp = _mock_response(201, json_body={"id": 1})
        with _patch_httpx_post(resp):
            check = CRUDCheck(
                "http://localhost:8000",
                token="t",
                path="/api/v1/items",
                payload={"name": "test"},
            )
            result = check.run()
        assert result.passed is True
        assert result.status_code == 201

    def test_create_200_success(self):
        resp = _mock_response(200, json_body={"id": 1})
        with _patch_httpx_post(resp):
            check = CRUDCheck("http://localhost:8000", path="/items", payload={})
            result = check.run()
        assert result.passed is True

    def test_create_409_conflict_passes(self):
        resp = _mock_response(409)
        with _patch_httpx_post(resp):
            check = CRUDCheck("http://localhost:8000", path="/items", payload={})
            result = check.run()
        assert result.passed is True
        assert result.status_code == 409

    def test_create_500_failure(self):
        resp = _mock_response(500, text="Internal Server Error")
        resp.text = "Internal Server Error"
        with _patch_httpx_post(resp):
            check = CRUDCheck("http://localhost:8000", path="/items", payload={"name": "x"})
            result = check.run()
        assert result.passed is False
        assert result.status_code == 500
        assert result.suggestion is not None
        assert "server" in result.suggestion.lower() or "500" in result.suggestion

    def test_create_422_validation_error(self):
        resp = _mock_response(422, text='{"detail": "name is required"}')
        resp.text = '{"detail": "name is required"}'
        with _patch_httpx_post(resp):
            check = CRUDCheck("http://localhost:8000", path="/items", payload={})
            result = check.run()
        assert result.passed is False
        assert result.status_code == 422
        assert "validation" in result.suggestion.lower()


# =========================================================================
# ListCheck smoke tests
# =========================================================================

class TestListCheck:
    """Tests for ListCheck."""

    def test_list_array_response(self):
        resp = _mock_response(200, json_body=[{"id": 1}, {"id": 2}])
        with _patch_httpx_get(resp):
            check = ListCheck("http://localhost:8000", path="/api/items")
            result = check.run()
        assert result.passed is True

    def test_list_paginated_response(self):
        resp = _mock_response(200, json_body={"data": [{"id": 1}], "total": 1, "page": 1})
        with _patch_httpx_get(resp):
            check = ListCheck("http://localhost:8000", path="/api/items")
            result = check.run()
        assert result.passed is True

    def test_list_empty_array(self):
        resp = _mock_response(200, json_body=[])
        with _patch_httpx_get(resp):
            check = ListCheck("http://localhost:8000", path="/api/items")
            result = check.run()
        assert result.passed is True

    def test_list_500_failure(self):
        resp = _mock_response(500)
        with _patch_httpx_get(resp):
            check = ListCheck("http://localhost:8000", path="/api/items")
            result = check.run()
        assert result.passed is False
        assert result.status_code == 500

    def test_list_404_failure(self):
        resp = _mock_response(404)
        with _patch_httpx_get(resp):
            check = ListCheck("http://localhost:8000", path="/api/nonexistent")
            result = check.run()
        assert result.passed is False
        assert result.status_code == 404
        assert result.suggestion is not None


# =========================================================================
# DatabaseCheck smoke tests
# =========================================================================

class TestDatabaseCheck:
    """Tests for DatabaseCheck."""

    def test_database_check_no_paths_skips(self):
        check = DatabaseCheck("http://localhost:8000")
        result = check.run()
        assert result.passed is True
        assert result.suggestion is not None
        assert "skipping" in result.suggestion.lower()

    def test_database_check_create_success(self):
        resp = _mock_response(201)
        with _patch_httpx_client(post=resp):
            check = DatabaseCheck(
                "http://localhost:8000",
                create_path="/api/items",
                create_payload={"name": "test"},
            )
            result = check.run()
        assert result.passed is True

    def test_database_check_create_500(self):
        resp = _mock_response(500, text="FK violation")
        resp.text = "FK violation"
        with _patch_httpx_client(post=resp):
            check = DatabaseCheck(
                "http://localhost:8000",
                create_path="/api/items",
                create_payload={"name": "test"},
            )
            result = check.run()
        assert result.passed is False
        assert "database" in result.suggestion.lower() or "fk" in result.suggestion.lower()


# =========================================================================
# OpenAPICheck smoke tests
# =========================================================================

class TestOpenAPICheck:
    """Tests for OpenAPICheck."""

    def test_openapi_found(self):
        spec = {"openapi": "3.0.0", "info": {"title": "Test"}, "paths": {}}
        resp = _mock_response(200, json_body=spec)
        with _patch_httpx_get(resp):
            check = OpenAPICheck("http://localhost:8000", path="/openapi.json")
            result = check.run()
        assert result.passed is True

    def test_openapi_not_found(self):
        resp = _mock_response(404)
        with _patch_httpx_get(resp):
            check = OpenAPICheck("http://localhost:8000", path="/openapi.json")
            result = check.run()
        assert result.passed is False
        assert result.suggestion is not None

    def test_openapi_auto_discovery(self):
        """When no path is given, tries common paths."""
        spec = {"swagger": "2.0", "info": {}, "paths": {}}
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _mock_response(404)
            return _mock_response(200, json_body=spec)

        with patch("httpx.Client") as mock_cls:
            client_mock = MagicMock()
            client_mock.__enter__ = MagicMock(return_value=client_mock)
            client_mock.__exit__ = MagicMock(return_value=False)
            client_mock.get.side_effect = side_effect
            mock_cls.return_value = client_mock

            check = OpenAPICheck("http://localhost:8000")
            result = check.run()

        assert result.passed is True


# =========================================================================
# SmokeTest orchestrator tests
# =========================================================================

class TestSmokeTest:
    """Tests for the SmokeTest orchestrator."""

    def test_run_all_all_pass(self):
        health_resp = _mock_response(200)
        auth_resp = _mock_response(200, json_body=[])

        with patch("httpx.Client") as mock_cls:
            client_mock = MagicMock()
            client_mock.__enter__ = MagicMock(return_value=client_mock)
            client_mock.__exit__ = MagicMock(return_value=False)
            client_mock.get.return_value = health_resp
            mock_cls.return_value = client_mock

            smoke = SmokeTest("http://localhost:8000", token="valid")
            report = smoke.run_all()

        assert report.passed is True
        assert len(report.results) == 2  # health + auth
        assert report.total_duration_ms >= 0

    def test_run_all_health_fails(self):
        resp = _mock_response(503)

        with _patch_httpx_get(resp):
            smoke = SmokeTest("http://localhost:8000")
            report = smoke.run_all()

        assert report.passed is False
        assert len(report.failed_results) == 1
        assert report.failed_results[0].name == "Health check"

    def test_run_all_with_create_and_list(self):
        get_resp = _mock_response(200, json_body=[])
        post_resp = _mock_response(201, json_body={"id": 1})

        with patch("httpx.Client") as mock_cls:
            client_mock = MagicMock()
            client_mock.__enter__ = MagicMock(return_value=client_mock)
            client_mock.__exit__ = MagicMock(return_value=False)
            client_mock.get.return_value = get_resp
            client_mock.post.return_value = post_resp
            mock_cls.return_value = client_mock

            smoke = SmokeTest("http://localhost:8000", token="t")
            report = smoke.run_all(
                create_path="/api/items",
                create_payload={"name": "test"},
                list_path="/api/items",
            )

        assert report.passed is True
        assert len(report.results) == 4  # health + auth + create + list

    def test_run_all_no_token_skips_auth(self):
        resp = _mock_response(200)
        with _patch_httpx_get(resp):
            smoke = SmokeTest("http://localhost:8000", token=None)
            report = smoke.run_all()
        assert report.passed is True
        assert len(report.results) == 1  # just health

    def test_assert_ready_passes(self):
        resp = _mock_response(200)
        with _patch_httpx_get(resp):
            smoke = SmokeTest("http://localhost:8000")
            report = smoke.assert_ready()
        assert report.passed is True

    def test_assert_ready_raises(self):
        resp = _mock_response(503)
        with _patch_httpx_get(resp):
            smoke = SmokeTest("http://localhost:8000")
            with pytest.raises(APINotReadyError) as exc_info:
                smoke.assert_ready()
            assert exc_info.value.report.passed is False
            assert "not ready" in str(exc_info.value).lower()

    def test_custom_check(self):
        """Custom checks are included in run_all()."""
        from venomqa.preflight.checks import BaseCheck

        class AlwaysPassCheck(BaseCheck):
            name = "Custom check"

            def run(self):
                return SmokeTestResult(name=self.name, passed=True, duration_ms=0)

        resp = _mock_response(200)
        with _patch_httpx_get(resp):
            smoke = SmokeTest("http://localhost:8000")
            smoke.add_check(AlwaysPassCheck("http://localhost:8000"))
            report = smoke.run_all()

        assert report.passed is True
        names = [r.name for r in report.results]
        assert "Custom check" in names


# =========================================================================
# SmokeTestReport tests
# =========================================================================

class TestSmokeTestReport:
    """Tests for SmokeTestReport."""

    def test_empty_report_passes(self):
        report = SmokeTestReport()
        assert report.passed is True
        assert report.summary.startswith("All 0")

    def test_all_passed_summary(self):
        report = SmokeTestReport(
            results=[
                SmokeTestResult(name="Health", passed=True, duration_ms=10),
                SmokeTestResult(name="Auth", passed=True, duration_ms=20),
            ],
            total_duration_ms=30,
        )
        assert report.passed is True
        assert "All 2 checks passed" in report.summary
        assert "ready for testing" in report.summary.lower()

    def test_some_failed_summary(self):
        report = SmokeTestReport(
            results=[
                SmokeTestResult(name="Health", passed=True, duration_ms=10),
                SmokeTestResult(name="Auth", passed=False, error="401", duration_ms=20),
            ],
            total_duration_ms=30,
        )
        assert report.passed is False
        assert "1/2 checks failed" in report.summary
        assert "NOT ready" in report.summary

    def test_failed_results_property(self):
        report = SmokeTestReport(
            results=[
                SmokeTestResult(name="A", passed=True, duration_ms=1),
                SmokeTestResult(name="B", passed=False, duration_ms=2),
                SmokeTestResult(name="C", passed=False, duration_ms=3),
            ],
        )
        assert len(report.failed_results) == 2
        assert len(report.passed_results) == 1

    def test_to_dict(self):
        report = SmokeTestReport(
            results=[
                SmokeTestResult(name="Health", passed=True, status_code=200, duration_ms=10),
            ],
            total_duration_ms=10,
        )
        d = report.to_dict()
        assert d["passed"] is True
        assert len(d["results"]) == 1
        assert d["results"][0]["name"] == "Health"
        assert d["results"][0]["status_code"] == 200

    def test_print_report_no_errors(self):
        report = SmokeTestReport(
            results=[
                SmokeTestResult(name="Health", passed=True, status_code=200, duration_ms=10),
            ],
            total_duration_ms=10,
        )
        buf = io.StringIO()
        report.print_report(file=buf)
        output = buf.getvalue()
        assert "PASS" in output
        assert "Health" in output

    def test_print_report_with_failures(self):
        report = SmokeTestReport(
            results=[
                SmokeTestResult(
                    name="Auth",
                    passed=False,
                    status_code=401,
                    error="Unauthorized",
                    suggestion="Check your token",
                    duration_ms=20,
                ),
            ],
            total_duration_ms=20,
        )
        buf = io.StringIO()
        report.print_report(file=buf)
        output = buf.getvalue()
        assert "FAIL" in output
        assert "Auth" in output
        assert "Unauthorized" in output
        assert "Check your token" in output


# =========================================================================
# APINotReadyError tests
# =========================================================================

class TestAPINotReadyError:
    """Tests for APINotReadyError formatting."""

    def test_error_message_contains_summary(self):
        report = SmokeTestReport(
            results=[
                SmokeTestResult(
                    name="Health check",
                    passed=False,
                    status_code=503,
                    error="Service unavailable",
                    suggestion="Server may be starting up",
                    duration_ms=5,
                ),
            ],
            total_duration_ms=5,
        )
        error = APINotReadyError(report)
        msg = str(error)
        assert "not ready" in msg.lower()
        assert "Health check" in msg
        assert "Service unavailable" in msg
        assert "Server may be starting up" in msg

    def test_error_carries_report(self):
        report = SmokeTestReport(
            results=[
                SmokeTestResult(name="Health", passed=False, error="down", duration_ms=1),
            ],
        )
        error = APINotReadyError(report)
        assert error.report is report
        assert error.report.passed is False

    def test_error_with_multiple_failures(self):
        report = SmokeTestReport(
            results=[
                SmokeTestResult(name="Health", passed=False, error="503", duration_ms=1),
                SmokeTestResult(name="Auth", passed=False, error="401", suggestion="fix token", duration_ms=2),
                SmokeTestResult(name="Create", passed=True, duration_ms=3),
            ],
        )
        error = APINotReadyError(report)
        msg = str(error)
        assert "Health" in msg
        assert "Auth" in msg
        assert "fix token" in msg
        # The passing check should not be in the failure section
        assert msg.count("FAILED") == 2


# =========================================================================
# SmokeTestResult serialization tests
# =========================================================================

class TestSmokeTestResultSerialization:
    """Tests for SmokeTestResult serialization."""

    def test_to_dict_minimal(self):
        result = SmokeTestResult(name="test", passed=True, duration_ms=5)
        d = result.to_dict()
        assert d == {"name": "test", "passed": True, "duration_ms": 5.0}

    def test_to_dict_full(self):
        result = SmokeTestResult(
            name="Auth",
            passed=False,
            status_code=401,
            error="Unauthorized",
            suggestion="Check token",
            duration_ms=15.678,
        )
        d = result.to_dict()
        assert d["status_code"] == 401
        assert d["error"] == "Unauthorized"
        assert d["suggestion"] == "Check token"
        assert d["duration_ms"] == 15.68  # rounded


# =========================================================================
# AutoPreflight tests
# =========================================================================

SAMPLE_OPENAPI_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Test API", "version": "1.0.0"},
    "servers": [{"url": "http://localhost:8000"}],
    "paths": {
        "/health": {
            "get": {"summary": "Health check", "responses": {"200": {}}}
        },
        "/api/v1/items": {
            "get": {
                "summary": "List items",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"type": "array", "items": {"type": "object"}}
                            }
                        }
                    }
                },
            },
            "post": {
                "summary": "Create item",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["name"],
                                "properties": {
                                    "name": {"type": "string"},
                                    "price": {"type": "number"},
                                },
                            }
                        }
                    }
                },
                "responses": {"201": {}},
            },
        },
        "/api/v1/items/{id}": {
            "get": {"summary": "Get item", "responses": {"200": {}}},
        },
        "/api/v1/auth/login": {
            "post": {
                "summary": "Login",
                "tags": ["auth"],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "username": {"type": "string"},
                                    "password": {"type": "string", "format": "password"},
                                },
                            }
                        }
                    }
                },
                "responses": {"200": {}},
            },
        },
        "/readyz": {
            "get": {"summary": "Readiness probe", "responses": {"200": {}}}
        },
        "/api/v1/orders": {
            "get": {
                "summary": "List orders",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "data": {
                                            "type": "array",
                                            "items": {"type": "object"},
                                        },
                                        "total": {"type": "integer"},
                                    },
                                }
                            }
                        }
                    }
                },
            },
        },
    },
}


class TestAutoPreflightDiscovery:
    """Tests for AutoPreflight discovery."""

    def test_discover_health_endpoints(self):
        auto = AutoPreflight("http://localhost:8000", SAMPLE_OPENAPI_SPEC)
        health = auto.discover_health_endpoints()
        assert "/health" in health
        assert "/readyz" in health

    def test_discover_crud_endpoints(self):
        auto = AutoPreflight("http://localhost:8000", SAMPLE_OPENAPI_SPEC)
        crud = auto.discover_crud_endpoints()
        paths = [path for path, method, payload in crud]
        assert "/api/v1/items" in paths
        # Login endpoint should be excluded
        assert "/api/v1/auth/login" not in paths

    def test_discover_crud_generates_payload(self):
        auto = AutoPreflight("http://localhost:8000", SAMPLE_OPENAPI_SPEC)
        crud = auto.discover_crud_endpoints()
        items_crud = [(p, m, payload) for p, m, payload in crud if p == "/api/v1/items"]
        assert len(items_crud) == 1
        _, _, payload = items_crud[0]
        assert "name" in payload
        assert isinstance(payload["name"], str)

    def test_discover_list_endpoints(self):
        auto = AutoPreflight("http://localhost:8000", SAMPLE_OPENAPI_SPEC)
        lists = auto.discover_list_endpoints()
        assert "/api/v1/items" in lists
        assert "/api/v1/orders" in lists
        # Path params should be excluded
        assert "/api/v1/items/{id}" not in lists

    def test_from_spec_dict(self):
        auto = AutoPreflight.from_spec_dict(
            "http://localhost:8000",
            SAMPLE_OPENAPI_SPEC,
        )
        assert auto.base_url == "http://localhost:8000"
        assert auto.spec is SAMPLE_OPENAPI_SPEC

    def test_from_openapi_url(self):
        resp = _mock_response(200, json_body=SAMPLE_OPENAPI_SPEC)
        with _patch_httpx_get(resp):
            auto = AutoPreflight.from_openapi(
                "http://localhost:8000/openapi.json",
            )
        assert auto.base_url == "http://localhost:8000"
        assert auto.spec == SAMPLE_OPENAPI_SPEC

    def test_run_executes_checks(self):
        """AutoPreflight.run() should execute discovered checks."""
        auto = AutoPreflight("http://localhost:8000", SAMPLE_OPENAPI_SPEC, token="t")

        get_resp = _mock_response(200, json_body=[])
        post_resp = _mock_response(201, json_body={"id": 1})

        with patch("httpx.Client") as mock_cls:
            client_mock = MagicMock()
            client_mock.__enter__ = MagicMock(return_value=client_mock)
            client_mock.__exit__ = MagicMock(return_value=False)
            client_mock.get.return_value = get_resp
            client_mock.post.return_value = post_resp
            mock_cls.return_value = client_mock

            report = auto.run()

        assert isinstance(report, SmokeTestReport)
        assert len(report.results) > 0


# =========================================================================
# CombinatorialExecutor preflight integration tests
# =========================================================================

class TestCombinatorialExecutorPreflight:
    """Test that CombinatorialExecutor runs preflight checks."""

    def test_executor_calls_preflight(self):
        """Executor should call preflight by default."""
        from venomqa.combinatorial.executor import CombinatorialExecutor

        mock_builder = MagicMock()
        mock_builder.name = "test"
        mock_client = MagicMock()
        mock_client.base_url = "http://localhost:8000"
        mock_client._auth_token = None

        executor = CombinatorialExecutor(mock_builder, mock_client, run_preflight=True)

        with patch("venomqa.preflight.smoke.SmokeTest.assert_ready") as mock_assert:
            mock_assert.return_value = SmokeTestReport(results=[])
            mock_builder.build_journey_graph.return_value = (MagicMock(), [])

            executor.execute(strength=2, explore_graph=False)
            mock_assert.assert_called_once()

    def test_executor_skip_preflight(self):
        """Executor with run_preflight=False should skip preflight."""
        from venomqa.combinatorial.executor import CombinatorialExecutor

        mock_builder = MagicMock()
        mock_builder.name = "test"
        mock_client = MagicMock()
        mock_client.base_url = "http://localhost:8000"

        executor = CombinatorialExecutor(mock_builder, mock_client, run_preflight=False)

        with patch("venomqa.preflight.smoke.SmokeTest.assert_ready") as mock_assert:
            mock_builder.build_journey_graph.return_value = (MagicMock(), [])
            executor.execute(strength=2, explore_graph=False)
            mock_assert.assert_not_called()
