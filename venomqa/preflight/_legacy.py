"""VenomQA Preflight - Pre-test execution checks.

This module provides programmatic preflight checks that can be run
before executing tests to ensure the environment is properly configured.

Preflight checks include:
- Python version validation (>= 3.10)
- Required dependencies installed
- Docker availability (optional)
- Configuration file validation
- Target API reachability
- Database connection (if configured)
- Journeys directory validation
"""

from __future__ import annotations

import importlib.metadata
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx


class CheckStatus(Enum):
    """Status of a preflight check."""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class CheckResult:
    """Result of a single preflight check."""

    name: str
    status: CheckStatus
    message: str
    duration_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class PreflightResult:
    """Aggregated result of all preflight checks."""

    passed: list[CheckResult] = field(default_factory=list)
    failed: list[CheckResult] = field(default_factory=list)
    warnings: list[CheckResult] = field(default_factory=list)
    skipped: list[CheckResult] = field(default_factory=list)
    total_duration_ms: float = 0.0

    @property
    def success(self) -> bool:
        """Return True if all required checks passed."""
        return len(self.failed) == 0

    @property
    def total_checks(self) -> int:
        """Return total number of checks run."""
        return len(self.passed) + len(self.failed) + len(self.warnings) + len(self.skipped)

    def add(self, result: CheckResult) -> None:
        """Add a check result to the appropriate list."""
        if result.status == CheckStatus.PASSED:
            self.passed.append(result)
        elif result.status == CheckStatus.FAILED:
            self.failed.append(result)
        elif result.status == CheckStatus.WARNING:
            self.warnings.append(result)
        else:
            self.skipped.append(result)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "total_checks": self.total_checks,
            "total_duration_ms": self.total_duration_ms,
            "passed": [
                {
                    "name": r.name,
                    "message": r.message,
                    "duration_ms": r.duration_ms,
                }
                for r in self.passed
            ],
            "failed": [
                {
                    "name": r.name,
                    "message": r.message,
                    "duration_ms": r.duration_ms,
                    "details": r.details,
                }
                for r in self.failed
            ],
            "warnings": [
                {
                    "name": r.name,
                    "message": r.message,
                    "duration_ms": r.duration_ms,
                }
                for r in self.warnings
            ],
            "skipped": [
                {
                    "name": r.name,
                    "message": r.message,
                }
                for r in self.skipped
            ],
        }


class PreflightChecker:
    """Runs preflight checks before test execution."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the preflight checker.

        Args:
            config: VenomQA configuration dictionary.
        """
        self.config = config
        self.result = PreflightResult()
        self._checks: list[tuple[str, Callable[[], CheckResult], bool]] = []

        # Register default checks
        self._register_default_checks()

    def _register_default_checks(self) -> None:
        """Register the default set of preflight checks."""
        # Python version check (required)
        self.register_check(
            "python_version",
            self._check_python_version,
            required=True,
        )

        # Required dependencies check (required)
        self.register_check(
            "required_dependencies",
            self._check_required_dependencies,
            required=True,
        )

        # Config validation (required)
        self.register_check(
            "config_validation",
            self._check_config_validation,
            required=True,
        )

        # Target API check (required)
        self.register_check(
            "target_api",
            self._check_target_api,
            required=True,
        )

        # Docker availability check (optional)
        self.register_check(
            "docker",
            self._check_docker,
            required=False,
        )

        # Docker compose file check (required if docker_compose_file is set)
        if self.config.get("docker_compose_file"):
            self.register_check(
                "docker_compose_file",
                self._check_docker_compose_file,
                required=True,
            )

        # Docker services check (required if docker_compose_file is set)
        if self.config.get("docker_compose_file"):
            self.register_check(
                "docker_services",
                self._check_docker_services,
                required=True,
            )

        # Database check (optional, only if db_url is set)
        if self.config.get("db_url"):
            self.register_check(
                "database",
                self._check_database,
                required=False,
            )

        # Journeys directory check (required)
        self.register_check(
            "journeys_directory",
            self._check_journeys_directory,
            required=True,
        )

    def register_check(
        self,
        name: str,
        check_fn: Callable[[], CheckResult],
        required: bool = True,
    ) -> None:
        """Register a custom preflight check.

        Args:
            name: Name of the check.
            check_fn: Function that performs the check and returns a CheckResult.
            required: Whether this check must pass for preflight to succeed.
        """
        self._checks.append((name, check_fn, required))

    def run(self) -> PreflightResult:
        """Run all registered preflight checks.

        Returns:
            PreflightResult containing all check results.
        """
        start_time = time.perf_counter()

        for name, check_fn, required in self._checks:
            try:
                result = check_fn()
            except Exception as e:
                result = CheckResult(
                    name=name,
                    status=CheckStatus.FAILED,
                    message=f"Check raised exception: {e}",
                    details={"exception": str(e)},
                )

            # Downgrade required failures to failures, optional failures to warnings
            if result.status == CheckStatus.FAILED and not required:
                result = CheckResult(
                    name=result.name,
                    status=CheckStatus.WARNING,
                    message=result.message,
                    duration_ms=result.duration_ms,
                    details=result.details,
                )

            self.result.add(result)

        self.result.total_duration_ms = (time.perf_counter() - start_time) * 1000
        return self.result

    def _check_python_version(self) -> CheckResult:
        """Check if Python version meets minimum requirements (>= 3.10)."""
        start_time = time.perf_counter()

        version = sys.version_info
        version_str = f"{version.major}.{version.minor}.{version.micro}"
        duration_ms = (time.perf_counter() - start_time) * 1000

        if version >= (3, 10):
            return CheckResult(
                name="python_version",
                status=CheckStatus.PASSED,
                message=f"Python {version_str}",
                duration_ms=duration_ms,
                details={"version": version_str},
            )

        return CheckResult(
            name="python_version",
            status=CheckStatus.FAILED,
            message=f"Python {version_str} is not supported (requires >= 3.10)",
            duration_ms=duration_ms,
            details={"version": version_str, "required": "3.10"},
        )

    def _check_required_dependencies(self) -> CheckResult:
        """Check if all required Python dependencies are installed."""
        start_time = time.perf_counter()

        required_packages = [
            ("httpx", "httpx"),
            ("pydantic", "pydantic"),
            ("click", "click"),
            ("rich", "rich"),
            ("yaml", "pyyaml"),
        ]

        missing = []
        installed = []

        for import_name, package_name in required_packages:
            try:
                __import__(import_name)
                try:
                    version = importlib.metadata.version(package_name)
                except importlib.metadata.PackageNotFoundError:
                    version = "installed"
                installed.append(f"{package_name}=={version}")
            except ImportError:
                missing.append(package_name)

        duration_ms = (time.perf_counter() - start_time) * 1000

        if missing:
            return CheckResult(
                name="required_dependencies",
                status=CheckStatus.FAILED,
                message=f"Missing packages: {', '.join(missing)}",
                duration_ms=duration_ms,
                details={"missing": missing, "installed": installed},
            )

        return CheckResult(
            name="required_dependencies",
            status=CheckStatus.PASSED,
            message=f"All {len(installed)} required packages installed",
            duration_ms=duration_ms,
            details={"installed": installed},
        )

    def _check_docker(self) -> CheckResult:
        """Check if Docker is installed and the daemon is running."""
        start_time = time.perf_counter()

        if not shutil.which("docker"):
            duration_ms = (time.perf_counter() - start_time) * 1000
            return CheckResult(
                name="docker",
                status=CheckStatus.WARNING,
                message="Docker not found in PATH (optional)",
                duration_ms=duration_ms,
            )

        try:
            # Check Docker version
            version_result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if version_result.returncode != 0:
                duration_ms = (time.perf_counter() - start_time) * 1000
                return CheckResult(
                    name="docker",
                    status=CheckStatus.WARNING,
                    message="Docker command failed",
                    duration_ms=duration_ms,
                )

            docker_version = version_result.stdout.strip()

            # Check if daemon is running
            info_result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=10,
            )

            duration_ms = (time.perf_counter() - start_time) * 1000

            if info_result.returncode == 0:
                return CheckResult(
                    name="docker",
                    status=CheckStatus.PASSED,
                    message=docker_version,
                    duration_ms=duration_ms,
                    details={"version": docker_version, "daemon_running": True},
                )
            else:
                return CheckResult(
                    name="docker",
                    status=CheckStatus.WARNING,
                    message="Docker installed but daemon not running",
                    duration_ms=duration_ms,
                    details={"version": docker_version, "daemon_running": False},
                )

        except subprocess.TimeoutExpired:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return CheckResult(
                name="docker",
                status=CheckStatus.WARNING,
                message="Docker check timed out",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return CheckResult(
                name="docker",
                status=CheckStatus.WARNING,
                message=f"Could not check Docker: {e}",
                duration_ms=duration_ms,
            )

    def _check_target_api(self) -> CheckResult:
        """Check if the target API is reachable."""
        base_url = self.config.get("base_url", "http://localhost:8000")
        timeout = self.config.get("timeout", 30)

        start_time = time.perf_counter()

        try:
            # Parse the URL and try to connect
            parsed = urlparse(base_url)
            host = parsed.hostname or "localhost"
            port = parsed.port or (443 if parsed.scheme == "https" else 80)

            # First try a simple socket connection
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(min(timeout, 5))
            try:
                sock.connect((host, port))
                sock.close()
            except (socket.timeout, socket.error, OSError) as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                return CheckResult(
                    name="target_api",
                    status=CheckStatus.FAILED,
                    message=f"Cannot connect to {base_url}: {e}",
                    duration_ms=duration_ms,
                    details={"host": host, "port": port, "error": str(e)},
                )

            # Try an HTTP request
            try:
                with httpx.Client(timeout=min(timeout, 10)) as client:
                    response = client.get(base_url)
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    return CheckResult(
                        name="target_api",
                        status=CheckStatus.PASSED,
                        message=f"API reachable at {base_url} (HTTP {response.status_code})",
                        duration_ms=duration_ms,
                        details={"status_code": response.status_code},
                    )
            except httpx.HTTPError as e:
                # Socket connected but HTTP failed - could be normal (e.g., 404)
                duration_ms = (time.perf_counter() - start_time) * 1000
                return CheckResult(
                    name="target_api",
                    status=CheckStatus.PASSED,
                    message=f"API reachable at {base_url} (connection OK, HTTP error: {e})",
                    duration_ms=duration_ms,
                )

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return CheckResult(
                name="target_api",
                status=CheckStatus.FAILED,
                message=f"Failed to check API: {e}",
                duration_ms=duration_ms,
                details={"error": str(e)},
            )

    def _check_docker_compose_file(self) -> CheckResult:
        """Check if the Docker Compose file exists and is valid."""
        docker_compose_file = self.config.get("docker_compose_file", "docker-compose.qa.yml")
        start_time = time.perf_counter()

        compose_path = Path(docker_compose_file)

        if not compose_path.exists():
            duration_ms = (time.perf_counter() - start_time) * 1000
            return CheckResult(
                name="docker_compose_file",
                status=CheckStatus.FAILED,
                message=f"Docker Compose file not found: {docker_compose_file}",
                duration_ms=duration_ms,
            )

        # Validate the file can be parsed
        try:
            result = subprocess.run(
                ["docker", "compose", "-f", str(compose_path), "config", "--quiet"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            duration_ms = (time.perf_counter() - start_time) * 1000

            if result.returncode == 0:
                return CheckResult(
                    name="docker_compose_file",
                    status=CheckStatus.PASSED,
                    message=f"Docker Compose file valid: {docker_compose_file}",
                    duration_ms=duration_ms,
                )
            else:
                return CheckResult(
                    name="docker_compose_file",
                    status=CheckStatus.FAILED,
                    message=f"Docker Compose file invalid: {result.stderr}",
                    duration_ms=duration_ms,
                    details={"stderr": result.stderr},
                )
        except subprocess.TimeoutExpired:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return CheckResult(
                name="docker_compose_file",
                status=CheckStatus.WARNING,
                message="Docker Compose validation timed out",
                duration_ms=duration_ms,
            )
        except FileNotFoundError:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return CheckResult(
                name="docker_compose_file",
                status=CheckStatus.FAILED,
                message="Docker is not installed or not in PATH",
                duration_ms=duration_ms,
            )

    def _check_docker_services(self) -> CheckResult:
        """Check if required Docker services are running."""
        docker_compose_file = self.config.get("docker_compose_file", "docker-compose.qa.yml")
        start_time = time.perf_counter()

        compose_path = Path(docker_compose_file)

        if not compose_path.exists():
            duration_ms = (time.perf_counter() - start_time) * 1000
            return CheckResult(
                name="docker_services",
                status=CheckStatus.SKIPPED,
                message="Docker Compose file not found, skipping service check",
                duration_ms=duration_ms,
            )

        try:
            result = subprocess.run(
                ["docker", "compose", "-f", str(compose_path), "ps", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            duration_ms = (time.perf_counter() - start_time) * 1000

            if result.returncode != 0:
                return CheckResult(
                    name="docker_services",
                    status=CheckStatus.WARNING,
                    message="Could not check Docker services",
                    duration_ms=duration_ms,
                    details={"stderr": result.stderr},
                )

            # Try to parse the JSON output
            import json

            try:
                services = json.loads(result.stdout) if result.stdout.strip() else []
            except json.JSONDecodeError:
                # Fall back to line-by-line parsing
                lines = result.stdout.strip().split("\n")
                services = []
                for line in lines:
                    if line.strip():
                        try:
                            services.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

            if not services:
                return CheckResult(
                    name="docker_services",
                    status=CheckStatus.WARNING,
                    message="No Docker services running (run 'docker compose up -d')",
                    duration_ms=duration_ms,
                )

            running = sum(1 for s in services if s.get("State") == "running")
            total = len(services)

            if running == total:
                return CheckResult(
                    name="docker_services",
                    status=CheckStatus.PASSED,
                    message=f"All {total} Docker services running",
                    duration_ms=duration_ms,
                    details={"running": running, "total": total},
                )
            else:
                return CheckResult(
                    name="docker_services",
                    status=CheckStatus.WARNING,
                    message=f"Only {running}/{total} Docker services running",
                    duration_ms=duration_ms,
                    details={"running": running, "total": total},
                )

        except subprocess.TimeoutExpired:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return CheckResult(
                name="docker_services",
                status=CheckStatus.WARNING,
                message="Docker services check timed out",
                duration_ms=duration_ms,
            )
        except FileNotFoundError:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return CheckResult(
                name="docker_services",
                status=CheckStatus.FAILED,
                message="Docker is not installed or not in PATH",
                duration_ms=duration_ms,
            )

    def _check_database(self) -> CheckResult:
        """Check if the database is reachable."""
        db_url = self.config.get("db_url")
        start_time = time.perf_counter()

        if not db_url:
            return CheckResult(
                name="database",
                status=CheckStatus.SKIPPED,
                message="No database URL configured",
                duration_ms=0.0,
            )

        # Parse the database URL
        parsed = urlparse(db_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 5432

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((host, port))
            sock.close()
            duration_ms = (time.perf_counter() - start_time) * 1000
            return CheckResult(
                name="database",
                status=CheckStatus.PASSED,
                message=f"Database reachable at {host}:{port}",
                duration_ms=duration_ms,
            )
        except (socket.timeout, socket.error, OSError) as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return CheckResult(
                name="database",
                status=CheckStatus.FAILED,
                message=f"Cannot connect to database at {host}:{port}: {e}",
                duration_ms=duration_ms,
                details={"host": host, "port": port, "error": str(e)},
            )

    def _check_config_validation(self) -> CheckResult:
        """Validate the configuration structure."""
        start_time = time.perf_counter()

        try:
            from venomqa.config.validators import validate_config

            validate_config(self.config)
            duration_ms = (time.perf_counter() - start_time) * 1000
            return CheckResult(
                name="config_validation",
                status=CheckStatus.PASSED,
                message="Configuration is valid",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return CheckResult(
                name="config_validation",
                status=CheckStatus.FAILED,
                message=f"Configuration validation failed: {e}",
                duration_ms=duration_ms,
                details={"error": str(e)},
            )

    def _check_journeys_directory(self) -> CheckResult:
        """Check if journeys directory exists with journey files."""
        start_time = time.perf_counter()
        journeys_dir = Path("journeys")

        if not journeys_dir.exists():
            duration_ms = (time.perf_counter() - start_time) * 1000
            return CheckResult(
                name="journeys_directory",
                status=CheckStatus.FAILED,
                message="journeys/ directory not found",
                duration_ms=duration_ms,
            )

        journey_files = list(journeys_dir.glob("*.py"))
        journey_files = [f for f in journey_files if not f.name.startswith("_")]

        duration_ms = (time.perf_counter() - start_time) * 1000

        if not journey_files:
            return CheckResult(
                name="journeys_directory",
                status=CheckStatus.WARNING,
                message="journeys/ exists but no journey files found",
                duration_ms=duration_ms,
            )

        return CheckResult(
            name="journeys_directory",
            status=CheckStatus.PASSED,
            message=f"Found {len(journey_files)} journey file(s)",
            duration_ms=duration_ms,
            details={"files": [f.name for f in journey_files]},
        )


def run_preflight_checks(config: dict[str, Any]) -> PreflightResult:
    """Run preflight checks before test execution.

    This is the main entry point for running preflight checks programmatically.

    Args:
        config: VenomQA configuration dictionary.

    Returns:
        PreflightResult containing all check results.

    Example:
        >>> from venomqa.preflight import run_preflight_checks
        >>> from venomqa.config import load_config
        >>>
        >>> config = load_config()
        >>> result = run_preflight_checks(config)
        >>> if not result.success:
        ...     for check in result.failed:
        ...         print(f"FAILED: {check.name} - {check.message}")
    """
    checker = PreflightChecker(config)
    return checker.run()


def run_preflight_checks_with_output(
    config: dict[str, Any],
    console: Any | None = None,
) -> PreflightResult:
    """Run preflight checks with console output.

    Args:
        config: VenomQA configuration dictionary.
        console: Optional Rich console for output. Creates one if not provided.

    Returns:
        PreflightResult containing all check results.
    """
    from rich.console import Console
    from rich.table import Table

    if console is None:
        console = Console()

    console.print("\n[bold blue]Preflight Checks[/bold blue]")
    console.print("-" * 40)

    checker = PreflightChecker(config)
    result = checker.run()

    table = Table(show_header=False, box=None)
    table.add_column("Status", width=8)
    table.add_column("Check", width=20)
    table.add_column("Result")

    for check in result.passed:
        table.add_row(
            "[green]PASSED[/green]",
            check.name,
            f"[green]{check.message}[/green]",
        )

    for check in result.warnings:
        table.add_row(
            "[yellow]WARNING[/yellow]",
            check.name,
            f"[yellow]{check.message}[/yellow]",
        )

    for check in result.failed:
        table.add_row(
            "[red]FAILED[/red]",
            check.name,
            f"[red]{check.message}[/red]",
        )

    for check in result.skipped:
        table.add_row(
            "[dim]SKIPPED[/dim]",
            check.name,
            f"[dim]{check.message}[/dim]",
        )

    console.print(table)
    console.print()

    if result.success:
        console.print("[green]All preflight checks passed![/green]")
    else:
        console.print(f"[red]{len(result.failed)} preflight check(s) failed[/red]")

    console.print(f"[dim]Total time: {result.total_duration_ms:.2f}ms[/dim]")

    return result
