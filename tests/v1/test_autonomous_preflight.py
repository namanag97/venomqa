"""Tests for venomqa.autonomous.preflight module."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from venomqa.autonomous.preflight import (
    CheckResult,
    FIXES,
    PreflightCheckResult,
    PreflightReport,
    PreflightRunner,
)


class TestCheckResult:
    """Tests for the CheckResult enum."""

    def test_enum_values(self):
        """Test all expected enum values exist."""
        assert CheckResult.PASS.value == "pass"
        assert CheckResult.FAIL.value == "fail"
        assert CheckResult.WARN.value == "warn"
        assert CheckResult.SKIP.value == "skip"


class TestPreflightCheckResult:
    """Tests for the PreflightCheckResult dataclass."""

    def test_passed_property_pass(self):
        """Test passed property for PASS result."""
        result = PreflightCheckResult(
            name="Test",
            result=CheckResult.PASS,
            message="OK",
        )
        assert result.passed is True
        assert result.failed is False

    def test_passed_property_warn(self):
        """Test passed property for WARN result."""
        result = PreflightCheckResult(
            name="Test",
            result=CheckResult.WARN,
            message="Warning",
        )
        assert result.passed is True
        assert result.failed is False

    def test_passed_property_skip(self):
        """Test passed property for SKIP result."""
        result = PreflightCheckResult(
            name="Test",
            result=CheckResult.SKIP,
            message="Skipped",
        )
        assert result.passed is True
        assert result.failed is False

    def test_failed_property(self):
        """Test failed property for FAIL result."""
        result = PreflightCheckResult(
            name="Test",
            result=CheckResult.FAIL,
            message="Failed",
        )
        assert result.passed is False
        assert result.failed is True


class TestPreflightReport:
    """Tests for the PreflightReport dataclass."""

    def test_empty_report_passes(self):
        """Test empty report is considered passed."""
        report = PreflightReport()
        assert report.passed is True
        assert len(report.failed_checks) == 0

    def test_all_pass(self):
        """Test report with all passing checks."""
        report = PreflightReport()
        report.add(PreflightCheckResult("Test1", CheckResult.PASS, "OK"))
        report.add(PreflightCheckResult("Test2", CheckResult.PASS, "OK"))
        assert report.passed is True

    def test_one_failure(self):
        """Test report with one failure."""
        report = PreflightReport()
        report.add(PreflightCheckResult("Test1", CheckResult.PASS, "OK"))
        report.add(PreflightCheckResult("Test2", CheckResult.FAIL, "Failed"))
        assert report.passed is False
        assert len(report.failed_checks) == 1
        assert report.failed_checks[0].name == "Test2"

    def test_warnings_pass(self):
        """Test report with warnings still passes."""
        report = PreflightReport()
        report.add(PreflightCheckResult("Test1", CheckResult.PASS, "OK"))
        report.add(PreflightCheckResult("Test2", CheckResult.WARN, "Warning"))
        assert report.passed is True
        assert len(report.warning_checks) == 1


class TestFixesDictionary:
    """Tests for the FIXES dictionary."""

    def test_all_expected_fixes_exist(self):
        """Test all expected fix suggestions exist."""
        expected_keys = [
            "docker_not_installed",
            "docker_not_running",
            "compose_not_found",
            "compose_invalid",
            "openapi_invalid",
            "api_not_reachable",
            "api_auth_required",
            "db_connection_failed",
        ]
        for key in expected_keys:
            assert key in FIXES, f"Missing fix suggestion for: {key}"
            assert len(FIXES[key]) > 10, f"Fix suggestion too short: {key}"

    def test_fixes_are_strings(self):
        """Test all fixes are non-empty strings."""
        for key, value in FIXES.items():
            assert isinstance(value, str)
            assert len(value) > 0


class TestPreflightRunner:
    """Tests for the PreflightRunner class."""

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_check_docker_installed(self, mock_run, mock_which):
        """Test Docker check when installed and running."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = MagicMock(returncode=0, stdout="Docker version 24.0.0")

        runner = PreflightRunner()
        result = runner._check_docker()

        assert result.result == CheckResult.PASS
        assert "Docker" in result.message or "version" in result.message.lower()

    @patch("shutil.which")
    def test_check_docker_not_installed(self, mock_which):
        """Test Docker check when not installed."""
        mock_which.return_value = None

        runner = PreflightRunner()
        result = runner._check_docker()

        assert result.result == CheckResult.FAIL
        assert result.fix_suggestion is not None

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_check_docker_not_running(self, mock_run, mock_which):
        """Test Docker check when installed but not running."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = MagicMock(returncode=1)

        runner = PreflightRunner()
        result = runner._check_docker()

        assert result.result == CheckResult.FAIL
        assert "not running" in result.message.lower() or "daemon" in result.message.lower()

    @patch("subprocess.run")
    def test_check_docker_compose_v2(self, mock_run):
        """Test Docker Compose v2 check."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Docker Compose version v2.20.0",
        )

        runner = PreflightRunner()
        result = runner._check_docker_compose()

        assert result.result == CheckResult.PASS

    def test_check_compose_valid(self):
        """Test compose file validation with valid file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            compose_file = Path(tmpdir) / "docker-compose.yml"
            compose_file.write_text("""
services:
  api:
    image: myapp:latest
    ports:
      - "8000:8000"
  db:
    image: postgres:15
""")

            runner = PreflightRunner(compose_path=compose_file)
            result = runner._check_compose_valid()

            assert result.result == CheckResult.PASS
            assert "2 service" in result.message

    def test_check_compose_invalid_yaml(self):
        """Test compose file validation with invalid YAML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            compose_file = Path(tmpdir) / "docker-compose.yml"
            compose_file.write_text("invalid: yaml: content: [")

            runner = PreflightRunner(compose_path=compose_file)
            result = runner._check_compose_valid()

            assert result.result == CheckResult.FAIL
            assert result.fix_suggestion is not None

    def test_check_compose_no_services(self):
        """Test compose file validation with no services."""
        with tempfile.TemporaryDirectory() as tmpdir:
            compose_file = Path(tmpdir) / "docker-compose.yml"
            compose_file.write_text("version: '3'\n")

            runner = PreflightRunner(compose_path=compose_file)
            result = runner._check_compose_valid()

            assert result.result == CheckResult.WARN

    def test_check_openapi_valid(self):
        """Test OpenAPI spec validation with valid spec."""
        with tempfile.TemporaryDirectory() as tmpdir:
            openapi_file = Path(tmpdir) / "openapi.yaml"
            openapi_file.write_text("""
openapi: 3.0.0
info:
  title: Test API
  version: 1.0.0
paths:
  /health:
    get:
      summary: Health check
      responses:
        '200':
          description: OK
  /users:
    get:
      summary: List users
      responses:
        '200':
          description: List
    post:
      summary: Create user
      responses:
        '201':
          description: Created
""")

            runner = PreflightRunner(openapi_path=openapi_file)
            result = runner._check_openapi_valid()

            assert result.result == CheckResult.PASS
            assert "3 endpoint" in result.message

    def test_check_openapi_missing_version(self):
        """Test OpenAPI spec validation with missing version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            openapi_file = Path(tmpdir) / "openapi.yaml"
            openapi_file.write_text("""
info:
  title: Test API
paths: {}
""")

            runner = PreflightRunner(openapi_path=openapi_file)
            result = runner._check_openapi_valid()

            assert result.result == CheckResult.FAIL
            assert "openapi" in result.message.lower() or "swagger" in result.message.lower()

    def test_check_openapi_no_paths(self):
        """Test OpenAPI spec validation with no paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            openapi_file = Path(tmpdir) / "openapi.yaml"
            openapi_file.write_text("""
openapi: 3.0.0
info:
  title: Test API
  version: 1.0.0
paths: {}
""")

            runner = PreflightRunner(openapi_path=openapi_file)
            result = runner._check_openapi_valid()

            assert result.result == CheckResult.WARN

    def test_check_openapi_json_format(self):
        """Test OpenAPI spec validation with JSON format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            openapi_file = Path(tmpdir) / "openapi.json"
            openapi_file.write_text("""{
  "openapi": "3.0.0",
  "info": {"title": "Test", "version": "1.0"},
  "paths": {
    "/test": {"get": {"responses": {"200": {"description": "OK"}}}}
  }
}""")

            runner = PreflightRunner(openapi_path=openapi_file)
            result = runner._check_openapi_valid()

            assert result.result == CheckResult.PASS

    def test_skip_when_no_file(self):
        """Test checks skip gracefully when files don't exist."""
        runner = PreflightRunner()

        compose_result = runner._check_compose_valid()
        assert compose_result.result == CheckResult.SKIP

        openapi_result = runner._check_openapi_valid()
        assert openapi_result.result == CheckResult.SKIP

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_run_all_stops_on_docker_failure(self, mock_run, mock_which):
        """Test run_all stops early if Docker fails."""
        mock_which.return_value = None  # Docker not installed

        runner = PreflightRunner()
        report = runner.run_all()

        assert report.passed is False
        # Should have stopped early - only Docker check
        assert len(report.checks) <= 2

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_run_all_success(self, mock_run, mock_which):
        """Test successful run_all with valid config."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Docker version 24.0.0",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            compose_file = Path(tmpdir) / "docker-compose.yml"
            compose_file.write_text("services:\n  api:\n    image: test\n")

            openapi_file = Path(tmpdir) / "openapi.yaml"
            openapi_file.write_text("openapi: 3.0.0\npaths:\n  /:\n    get:\n      responses:\n        '200':\n          description: OK\n")

            runner = PreflightRunner(
                compose_path=compose_file,
                openapi_path=openapi_file,
            )
            report = runner.run_all()

            assert report.passed is True
