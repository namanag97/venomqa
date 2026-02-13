"""Tests for VenomQA Doctor - System health checks and diagnostics."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Tuple
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from venomqa.cli.doctor import (
    HealthCheck,
    check_config_file,
    check_docker,
    check_docker_compose,
    check_git,
    check_graphviz,
    check_journeys_directory,
    check_package,
    check_postgresql_client,
    check_python_version,
    doctor,
    get_health_checks,
    run_health_checks,
)


class TestHealthCheck:
    """Tests for the HealthCheck class."""

    def test_health_check_initialization(self):
        """Test HealthCheck can be initialized with name, function, and required flag."""
        def check_fn() -> Tuple[bool, str]:
            return True, "All good"

        check = HealthCheck("test_check", check_fn, required=True)

        assert check.name == "test_check"
        assert check.check_fn == check_fn
        assert check.required is True

    def test_health_check_default_required(self):
        """Test HealthCheck defaults to required=True."""
        check = HealthCheck("test", lambda: (True, "ok"))
        assert check.required is True

    def test_health_check_optional(self):
        """Test HealthCheck can be marked as optional."""
        check = HealthCheck("test", lambda: (True, "ok"), required=False)
        assert check.required is False

    def test_health_check_run_success(self):
        """Test HealthCheck.run() returns success tuple."""
        check = HealthCheck("test", lambda: (True, "Success message"))
        success, message = check.run()

        assert success is True
        assert message == "Success message"

    def test_health_check_run_failure(self):
        """Test HealthCheck.run() returns failure tuple."""
        check = HealthCheck("test", lambda: (False, "Failure message"))
        success, message = check.run()

        assert success is False
        assert message == "Failure message"

    def test_health_check_run_catches_exception(self):
        """Test HealthCheck.run() catches exceptions and returns failure."""
        def failing_check() -> Tuple[bool, str]:
            raise RuntimeError("Something went wrong")

        check = HealthCheck("test", failing_check)
        success, message = check.run()

        assert success is False
        assert "Something went wrong" in message


class TestCheckPythonVersion:
    """Tests for the check_python_version function."""

    def test_python_version_current(self):
        """Test check_python_version with current Python version."""
        success, message = check_python_version()

        # Since we're running tests, Python version should be >= 3.10
        assert success is True
        assert f"Python {sys.version_info.major}.{sys.version_info.minor}" in message

    def test_python_version_310(self):
        """Test check_python_version with Python 3.10."""
        # Create a mock version_info that behaves like the real one
        from types import SimpleNamespace

        mock_version = SimpleNamespace(
            major=3,
            minor=10,
            micro=0,
            releaselevel="final",
            serial=0,
        )
        # Make it comparable like a tuple
        mock_version.__ge__ = lambda self, other: (self.major, self.minor) >= other[:2]

        with patch.object(sys, "version_info", mock_version):
            success, message = check_python_version()

        assert success is True
        assert "Python 3.10" in message

    def test_python_version_312(self):
        """Test check_python_version with Python 3.12."""
        from types import SimpleNamespace

        mock_version = SimpleNamespace(
            major=3,
            minor=12,
            micro=1,
            releaselevel="final",
            serial=0,
        )
        mock_version.__ge__ = lambda self, other: (self.major, self.minor) >= other[:2]

        with patch.object(sys, "version_info", mock_version):
            success, message = check_python_version()

        assert success is True
        assert "Python 3.12.1" in message

    def test_python_version_too_old(self):
        """Test check_python_version fails with Python < 3.10."""
        from types import SimpleNamespace

        mock_version = SimpleNamespace(
            major=3,
            minor=9,
            micro=0,
            releaselevel="final",
            serial=0,
        )
        mock_version.__ge__ = lambda self, other: (self.major, self.minor) >= other[:2]

        with patch.object(sys, "version_info", mock_version):
            success, message = check_python_version()

        assert success is False
        assert "requires >= 3.10" in message


class TestCheckDocker:
    """Tests for the check_docker function."""

    @patch("shutil.which")
    def test_docker_not_in_path(self, mock_which):
        """Test check_docker when Docker is not in PATH."""
        mock_which.return_value = None
        success, message = check_docker()

        assert success is False
        assert "not found in PATH" in message

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_docker_version_fails(self, mock_run, mock_which):
        """Test check_docker when docker --version fails."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error")

        success, message = check_docker()

        assert success is False
        assert "check failed" in message

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_docker_daemon_not_running(self, mock_run, mock_which):
        """Test check_docker when Docker daemon is not running."""
        mock_which.return_value = "/usr/bin/docker"

        def run_side_effect(cmd, **kwargs):
            if cmd[1] == "--version":
                return MagicMock(returncode=0, stdout="Docker version 24.0.0")
            elif cmd[1] == "info":
                return MagicMock(returncode=1)
            return MagicMock(returncode=1)

        mock_run.side_effect = run_side_effect

        success, message = check_docker()

        assert success is False
        assert "daemon not running" in message

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_docker_running(self, mock_run, mock_which):
        """Test check_docker when Docker is fully functional."""
        mock_which.return_value = "/usr/bin/docker"

        def run_side_effect(cmd, **kwargs):
            if cmd[1] == "--version":
                return MagicMock(returncode=0, stdout="Docker version 24.0.0")
            elif cmd[1] == "info":
                return MagicMock(returncode=0)
            return MagicMock(returncode=0)

        mock_run.side_effect = run_side_effect

        success, message = check_docker()

        assert success is True
        assert "Docker version" in message


class TestCheckDockerCompose:
    """Tests for the check_docker_compose function."""

    @patch("subprocess.run")
    def test_docker_compose_v2(self, mock_run):
        """Test check_docker_compose finds Docker Compose v2."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Docker Compose version v2.20.0",
        )

        success, message = check_docker_compose()

        assert success is True
        assert "Docker Compose" in message

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_docker_compose_v1_fallback(self, mock_which, mock_run):
        """Test check_docker_compose falls back to docker-compose v1."""

        def run_side_effect(cmd, **kwargs):
            if cmd[0] == "docker" and cmd[1] == "compose":
                return MagicMock(returncode=1)
            elif cmd[0] == "docker-compose":
                return MagicMock(
                    returncode=0,
                    stdout="docker-compose version 1.29.2",
                )
            return MagicMock(returncode=1)

        mock_run.side_effect = run_side_effect
        mock_which.return_value = "/usr/bin/docker-compose"

        success, message = check_docker_compose()

        assert success is True
        assert "docker-compose" in message

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_docker_compose_not_found(self, mock_which, mock_run):
        """Test check_docker_compose when neither version is found."""
        mock_run.return_value = MagicMock(returncode=1)
        mock_which.return_value = None

        success, message = check_docker_compose()

        assert success is False
        assert "not found" in message


class TestCheckPackage:
    """Tests for the check_package function."""

    def test_check_installed_package(self):
        """Test check_package with an installed package."""
        success, message = check_package("click")

        assert success is True
        assert "click" in message

    def test_check_missing_package(self):
        """Test check_package with a missing package."""
        success, message = check_package("nonexistent_package_xyz")

        assert success is False
        assert "not installed" in message

    def test_check_package_with_version(self):
        """Test check_package returns version when available."""
        # rich has __version__
        success, message = check_package("rich")

        assert success is True
        assert "rich" in message


class TestCheckGraphviz:
    """Tests for the check_graphviz function."""

    @patch("shutil.which")
    def test_graphviz_not_installed(self, mock_which):
        """Test check_graphviz when not installed."""
        mock_which.return_value = None

        success, message = check_graphviz()

        assert success is False
        assert "not installed" in message
        assert "optional" in message

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_graphviz_installed(self, mock_run, mock_which):
        """Test check_graphviz when installed."""
        mock_which.return_value = "/usr/bin/dot"
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="dot - graphviz version 2.43.0",
        )

        success, message = check_graphviz()

        assert success is True
        assert "graphviz" in message.lower()


class TestCheckPostgresqlClient:
    """Tests for the check_postgresql_client function."""

    @patch("shutil.which")
    def test_psql_not_installed(self, mock_which):
        """Test check_postgresql_client when not installed."""
        mock_which.return_value = None

        success, message = check_postgresql_client()

        assert success is False
        assert "not found" in message
        assert "optional" in message

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_psql_installed(self, mock_run, mock_which):
        """Test check_postgresql_client when installed."""
        mock_which.return_value = "/usr/bin/psql"
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="psql (PostgreSQL) 15.3",
        )

        success, message = check_postgresql_client()

        assert success is True
        assert "psql" in message


class TestCheckGit:
    """Tests for the check_git function."""

    @patch("shutil.which")
    def test_git_not_installed(self, mock_which):
        """Test check_git when not installed."""
        mock_which.return_value = None

        success, message = check_git()

        assert success is False
        assert "not found" in message

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_git_installed(self, mock_run, mock_which):
        """Test check_git when installed."""
        mock_which.return_value = "/usr/bin/git"
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="git version 2.40.0",
        )

        success, message = check_git()

        assert success is True
        assert "git" in message.lower()


class TestCheckConfigFile:
    """Tests for the check_config_file function."""

    def test_config_file_not_found(self, tmp_path, monkeypatch):
        """Test check_config_file when no config file exists."""
        monkeypatch.chdir(tmp_path)

        success, message = check_config_file()

        assert success is False
        assert "No venomqa.yaml found" in message

    def test_config_file_found(self, tmp_path, monkeypatch):
        """Test check_config_file when venomqa.yaml exists."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "venomqa.yaml").write_text("base_url: http://localhost:8000")

        success, message = check_config_file()

        assert success is True
        assert "venomqa.yaml" in message

    def test_config_file_alternate_name(self, tmp_path, monkeypatch):
        """Test check_config_file with alternate config file names."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "venomqa.yml").write_text("base_url: http://localhost:8000")

        success, message = check_config_file()

        assert success is True
        assert "venomqa.yml" in message


class TestCheckJourneysDirectory:
    """Tests for the check_journeys_directory function."""

    def test_journeys_dir_not_found(self, tmp_path, monkeypatch):
        """Test check_journeys_directory when directory doesn't exist."""
        monkeypatch.chdir(tmp_path)

        success, message = check_journeys_directory()

        assert success is False
        assert "not found" in message

    def test_journeys_dir_empty(self, tmp_path, monkeypatch):
        """Test check_journeys_directory when directory is empty."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "journeys").mkdir()

        success, message = check_journeys_directory()

        assert success is False
        assert "no journey files found" in message

    def test_journeys_dir_with_files(self, tmp_path, monkeypatch):
        """Test check_journeys_directory when directory has journey files."""
        monkeypatch.chdir(tmp_path)
        journeys_dir = tmp_path / "journeys"
        journeys_dir.mkdir()
        (journeys_dir / "test_journey.py").write_text("# journey")
        (journeys_dir / "another_journey.py").write_text("# journey")

        success, message = check_journeys_directory()

        assert success is True
        assert "2 journey file(s)" in message

    def test_journeys_dir_ignores_underscore_files(self, tmp_path, monkeypatch):
        """Test check_journeys_directory ignores files starting with underscore."""
        monkeypatch.chdir(tmp_path)
        journeys_dir = tmp_path / "journeys"
        journeys_dir.mkdir()
        (journeys_dir / "__init__.py").write_text("")
        (journeys_dir / "_utils.py").write_text("")
        (journeys_dir / "real_journey.py").write_text("# journey")

        success, message = check_journeys_directory()

        assert success is True
        assert "1 journey file(s)" in message


class TestGetHealthChecks:
    """Tests for the get_health_checks function."""

    def test_returns_list_of_health_checks(self):
        """Test get_health_checks returns a list of HealthCheck instances."""
        checks = get_health_checks()

        assert isinstance(checks, list)
        assert len(checks) > 0
        assert all(isinstance(c, HealthCheck) for c in checks)

    def test_required_checks_are_first(self):
        """Test that required checks come before optional checks."""
        checks = get_health_checks()

        # Find the first optional check
        first_optional_idx = None
        for i, check in enumerate(checks):
            if not check.required:
                first_optional_idx = i
                break

        if first_optional_idx is not None:
            # All checks before the first optional should be required
            for i in range(first_optional_idx):
                assert checks[i].required is True

    def test_includes_essential_checks(self):
        """Test that essential checks are included."""
        checks = get_health_checks()
        check_names = [c.name for c in checks]

        assert "Python Version" in check_names
        assert "Docker" in check_names
        assert "Docker Compose" in check_names


class TestRunHealthChecks:
    """Tests for the run_health_checks function."""

    def test_run_health_checks_all_pass(self):
        """Test run_health_checks when all checks pass."""
        checks = [
            HealthCheck("check1", lambda: (True, "passed"), required=True),
            HealthCheck("check2", lambda: (True, "passed"), required=False),
        ]

        passed, failed_required, failed_optional = run_health_checks(checks)

        assert passed == 2
        assert failed_required == 0
        assert failed_optional == 0

    def test_run_health_checks_required_fails(self):
        """Test run_health_checks when a required check fails."""
        checks = [
            HealthCheck("check1", lambda: (False, "failed"), required=True),
            HealthCheck("check2", lambda: (True, "passed"), required=False),
        ]

        passed, failed_required, failed_optional = run_health_checks(checks)

        assert passed == 1
        assert failed_required == 1
        assert failed_optional == 0

    def test_run_health_checks_optional_fails(self):
        """Test run_health_checks when an optional check fails."""
        checks = [
            HealthCheck("check1", lambda: (True, "passed"), required=True),
            HealthCheck("check2", lambda: (False, "failed"), required=False),
        ]

        passed, failed_required, failed_optional = run_health_checks(checks)

        assert passed == 1
        assert failed_required == 0
        assert failed_optional == 1


class TestDoctorCommand:
    """Tests for the doctor CLI command."""

    def test_doctor_command_exits_with_0_on_success(self):
        """Test doctor command exits with 0 when all required checks pass."""
        runner = CliRunner()

        # Mock all checks to pass
        with patch(
            "venomqa.cli.doctor.get_health_checks",
            return_value=[
                HealthCheck("test", lambda: (True, "ok"), required=True),
            ],
        ):
            result = runner.invoke(doctor)

        assert result.exit_code == 0

    def test_doctor_command_exits_with_1_on_failure(self):
        """Test doctor command exits with 1 when a required check fails."""
        runner = CliRunner()

        # Mock a required check to fail
        with patch(
            "venomqa.cli.doctor.get_health_checks",
            return_value=[
                HealthCheck("test", lambda: (False, "failed"), required=True),
            ],
        ):
            result = runner.invoke(doctor)

        assert result.exit_code == 1

    def test_doctor_command_json_output(self):
        """Test doctor command with --json flag outputs valid JSON."""
        runner = CliRunner()

        with patch(
            "venomqa.cli.doctor.get_health_checks",
            return_value=[
                HealthCheck("test1", lambda: (True, "ok"), required=True),
                HealthCheck("test2", lambda: (False, "failed"), required=False),
            ],
        ):
            result = runner.invoke(doctor, ["--json"])

        # Should be valid JSON
        output = json.loads(result.output)

        assert "checks" in output
        assert "summary" in output
        assert len(output["checks"]) == 2
        assert output["summary"]["passed"] == 1
        assert output["summary"]["failed_optional"] == 1
        assert output["summary"]["ready"] is True

    def test_doctor_command_json_output_on_failure(self):
        """Test doctor command with --json flag shows failures correctly."""
        runner = CliRunner()

        with patch(
            "venomqa.cli.doctor.get_health_checks",
            return_value=[
                HealthCheck("test", lambda: (False, "failed"), required=True),
            ],
        ):
            result = runner.invoke(doctor, ["--json"])

        output = json.loads(result.output)

        assert output["summary"]["failed_required"] == 1
        assert output["summary"]["ready"] is False
        assert result.exit_code == 1

    def test_doctor_command_shows_fix_suggestions_on_failure(self):
        """Test doctor command shows fix suggestions when checks fail."""
        runner = CliRunner()

        with patch(
            "venomqa.cli.doctor.get_health_checks",
            return_value=[
                HealthCheck("test", lambda: (False, "failed"), required=True),
            ],
        ):
            result = runner.invoke(doctor)

        assert "To fix:" in result.output or "pip install" in result.output


class TestDoctorIntegration:
    """Integration tests for the doctor system."""

    def test_doctor_runs_all_checks(self):
        """Test that doctor runs all registered health checks."""
        runner = CliRunner()

        result = runner.invoke(doctor, ["--json"])

        if result.exit_code not in (0, 1):
            pytest.fail(f"Unexpected exit code: {result.exit_code}")

        output = json.loads(result.output)
        checks = get_health_checks()

        assert len(output["checks"]) == len(checks)

    def test_doctor_check_names_match(self):
        """Test that JSON output check names match registered checks."""
        runner = CliRunner()

        result = runner.invoke(doctor, ["--json"])
        output = json.loads(result.output)

        expected_names = {c.name for c in get_health_checks()}
        actual_names = {c["name"] for c in output["checks"]}

        assert expected_names == actual_names
