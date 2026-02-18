"""Preflight checks for autonomous mode.

Validates environment before starting containers:
- Docker daemon running
- Docker Compose available
- Compose file valid
- OpenAPI spec valid
- API reachable (if already running)
- Database connection (if detected)
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class CheckResult(Enum):
    """Result of a preflight check."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


@dataclass
class PreflightCheckResult:
    """Result of a single preflight check."""

    name: str
    result: CheckResult
    message: str
    fix_suggestion: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.result in (CheckResult.PASS, CheckResult.WARN, CheckResult.SKIP)

    @property
    def failed(self) -> bool:
        return self.result == CheckResult.FAIL


@dataclass
class PreflightReport:
    """Aggregated report of all preflight checks."""

    checks: list[PreflightCheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """All checks passed (no FAIL results)."""
        return not any(c.failed for c in self.checks)

    @property
    def failed_checks(self) -> list[PreflightCheckResult]:
        """Get list of failed checks."""
        return [c for c in self.checks if c.failed]

    @property
    def warning_checks(self) -> list[PreflightCheckResult]:
        """Get list of warning checks."""
        return [c for c in self.checks if c.result == CheckResult.WARN]

    def add(self, check: PreflightCheckResult) -> None:
        """Add a check result."""
        self.checks.append(check)


# Simple fix commands - ONE action each
FIXES = {
    "docker_not_installed": "Install Docker Desktop: https://docker.com/get-started",
    "docker_not_running": "Open Docker Desktop",
    "compose_not_found": "Install Docker Desktop (includes Compose)",
    "compose_invalid": "Fix syntax: docker compose config",
    "openapi_invalid": "Add 'openapi: 3.0.0' and 'paths:' to your spec",
    "api_not_reachable": "VenomQA will start it. Use --skip-preflight to continue.",
    "api_auth_required": "venomqa --api-key YOUR_KEY",
    "db_connection_failed": "venomqa --db-password YOUR_PASSWORD",
}


class PreflightRunner:
    """Runs preflight checks before autonomous exploration.

    Usage:
        runner = PreflightRunner(
            compose_path=Path("docker-compose.yml"),
            openapi_path=Path("openapi.yaml"),
        )
        report = runner.run_all()
        if not report.passed:
            for check in report.failed_checks:
                print(f"{check.name}: {check.fix_suggestion}")
    """

    def __init__(
        self,
        *,
        compose_path: Path | None = None,
        openapi_path: Path | None = None,
        api_url: str | None = None,
        credentials: Any | None = None,  # Credentials object
        check_api_auth: bool = True,
        check_database: bool = True,
    ) -> None:
        self.compose_path = compose_path
        self.openapi_path = openapi_path
        self.api_url = api_url
        self.credentials = credentials
        self._check_api_auth = check_api_auth
        self._check_database = check_database

    def run_all(self) -> PreflightReport:
        """Run all preflight checks."""
        report = PreflightReport()

        # Core infrastructure checks (required)
        report.add(self._check_docker())
        report.add(self._check_docker_compose())

        # If docker isn't working, skip remaining checks
        if any(c.failed for c in report.checks):
            return report

        # Compose file check
        if self.compose_path:
            report.add(self._check_compose_valid())

        # OpenAPI spec check
        if self.openapi_path:
            report.add(self._check_openapi_valid())

        # API checks (optional - API might not be running yet)
        if self.api_url:
            api_check = self._check_api_reachable()
            report.add(api_check)

            # Only check auth if API is reachable
            if api_check.result == CheckResult.PASS and self._check_api_auth:
                report.add(self._check_api_auth_status())

        return report

    def _check_docker(self) -> PreflightCheckResult:
        """Check if Docker is installed and daemon is running."""
        # Check if docker binary exists
        if not shutil.which("docker"):
            return PreflightCheckResult(
                name="Docker",
                result=CheckResult.FAIL,
                message="Docker not found in PATH",
                fix_suggestion=FIXES["docker_not_installed"],
            )

        # Check if daemon is running
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode != 0:
                return PreflightCheckResult(
                    name="Docker",
                    result=CheckResult.FAIL,
                    message="Docker daemon not running",
                    fix_suggestion=FIXES["docker_not_running"],
                )
        except subprocess.TimeoutExpired:
            return PreflightCheckResult(
                name="Docker",
                result=CheckResult.FAIL,
                message="Docker daemon not responding (timeout)",
                fix_suggestion=FIXES["docker_not_running"],
            )
        except Exception as e:
            return PreflightCheckResult(
                name="Docker",
                result=CheckResult.FAIL,
                message=f"Docker check failed: {e}",
                fix_suggestion=FIXES["docker_not_running"],
            )

        # Get version info
        try:
            version_result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            version = version_result.stdout.strip()
        except Exception:
            version = "Docker running"

        return PreflightCheckResult(
            name="Docker",
            result=CheckResult.PASS,
            message=version,
        )

    def _check_docker_compose(self) -> PreflightCheckResult:
        """Check if Docker Compose is available (v2 or v1)."""
        # Try docker compose (v2)
        try:
            result = subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return PreflightCheckResult(
                    name="Docker Compose",
                    result=CheckResult.PASS,
                    message=result.stdout.strip(),
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Try docker-compose (v1)
        if shutil.which("docker-compose"):
            try:
                result = subprocess.run(
                    ["docker-compose", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    return PreflightCheckResult(
                        name="Docker Compose",
                        result=CheckResult.PASS,
                        message=result.stdout.strip(),
                    )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        return PreflightCheckResult(
            name="Docker Compose",
            result=CheckResult.FAIL,
            message="Docker Compose not found",
            fix_suggestion=FIXES["compose_not_found"],
        )

    def _check_compose_valid(self) -> PreflightCheckResult:
        """Check if docker-compose.yml is valid YAML and has services."""
        if not self.compose_path or not self.compose_path.exists():
            return PreflightCheckResult(
                name="Compose File",
                result=CheckResult.SKIP,
                message="No compose file to validate",
            )

        try:
            with open(self.compose_path) as f:
                config = yaml.safe_load(f)

            if not isinstance(config, dict):
                return PreflightCheckResult(
                    name="Compose File",
                    result=CheckResult.FAIL,
                    message="Compose file is not a valid YAML dictionary",
                    fix_suggestion=FIXES["compose_invalid"],
                )

            services = config.get("services", {})
            if not services:
                return PreflightCheckResult(
                    name="Compose File",
                    result=CheckResult.WARN,
                    message="Compose file has no services defined",
                    fix_suggestion=FIXES["compose_invalid"],
                )

            return PreflightCheckResult(
                name="Compose File",
                result=CheckResult.PASS,
                message=f"Valid ({len(services)} service(s))",
                details={"services": list(services.keys())},
            )

        except yaml.YAMLError as e:
            return PreflightCheckResult(
                name="Compose File",
                result=CheckResult.FAIL,
                message=f"YAML parse error: {e}",
                fix_suggestion=FIXES["compose_invalid"],
            )
        except Exception as e:
            return PreflightCheckResult(
                name="Compose File",
                result=CheckResult.FAIL,
                message=f"Error reading file: {e}",
                fix_suggestion=FIXES["compose_invalid"],
            )

    def _check_openapi_valid(self) -> PreflightCheckResult:
        """Check if OpenAPI spec is valid and has endpoints."""
        if not self.openapi_path or not self.openapi_path.exists():
            return PreflightCheckResult(
                name="OpenAPI Spec",
                result=CheckResult.SKIP,
                message="No OpenAPI spec to validate",
            )

        try:
            with open(self.openapi_path) as f:
                if self.openapi_path.suffix == ".json":
                    import json

                    spec = json.load(f)
                else:
                    spec = yaml.safe_load(f)

            if not isinstance(spec, dict):
                return PreflightCheckResult(
                    name="OpenAPI Spec",
                    result=CheckResult.FAIL,
                    message="OpenAPI spec is not a valid dictionary",
                    fix_suggestion=FIXES["openapi_invalid"],
                )

            # Check for openapi or swagger version
            version = spec.get("openapi") or spec.get("swagger")
            if not version:
                return PreflightCheckResult(
                    name="OpenAPI Spec",
                    result=CheckResult.FAIL,
                    message="Missing 'openapi' or 'swagger' version field",
                    fix_suggestion=FIXES["openapi_invalid"],
                )

            paths = spec.get("paths", {})
            if not paths:
                return PreflightCheckResult(
                    name="OpenAPI Spec",
                    result=CheckResult.WARN,
                    message=f"OpenAPI {version} - no paths defined",
                    fix_suggestion=FIXES["openapi_invalid"],
                )

            # Count endpoints
            endpoint_count = sum(
                len([m for m in path.keys() if m in ("get", "post", "put", "patch", "delete")])
                for path in paths.values()
                if isinstance(path, dict)
            )

            return PreflightCheckResult(
                name="OpenAPI Spec",
                result=CheckResult.PASS,
                message=f"OpenAPI {version} ({endpoint_count} endpoint(s))",
                details={"version": version, "endpoints": endpoint_count},
            )

        except yaml.YAMLError as e:
            return PreflightCheckResult(
                name="OpenAPI Spec",
                result=CheckResult.FAIL,
                message=f"YAML parse error: {e}",
                fix_suggestion=FIXES["openapi_invalid"],
            )
        except Exception as e:
            return PreflightCheckResult(
                name="OpenAPI Spec",
                result=CheckResult.FAIL,
                message=f"Error reading spec: {e}",
                fix_suggestion=FIXES["openapi_invalid"],
            )

    def _check_api_reachable(self) -> PreflightCheckResult:
        """Check if API is reachable (if already running)."""
        if not self.api_url:
            return PreflightCheckResult(
                name="API Reachable",
                result=CheckResult.SKIP,
                message="No API URL to check",
            )

        try:
            import httpx

            # Try common health check endpoints
            for path in ["/health", "/healthz", "/", "/api/health"]:
                try:
                    url = self.api_url.rstrip("/") + path
                    response = httpx.get(url, timeout=5.0)
                    # Any response (even 404) means API is up
                    if response.status_code < 500:
                        return PreflightCheckResult(
                            name="API Reachable",
                            result=CheckResult.PASS,
                            message=f"API responding at {self.api_url}",
                            details={"status_code": response.status_code},
                        )
                except httpx.HTTPError:
                    continue

            return PreflightCheckResult(
                name="API Reachable",
                result=CheckResult.WARN,
                message=f"API not responding at {self.api_url}",
                fix_suggestion=FIXES["api_not_reachable"],
            )

        except ImportError:
            return PreflightCheckResult(
                name="API Reachable",
                result=CheckResult.SKIP,
                message="httpx not available for API check",
            )
        except Exception as e:
            return PreflightCheckResult(
                name="API Reachable",
                result=CheckResult.WARN,
                message=f"Could not reach API: {e}",
                fix_suggestion=FIXES["api_not_reachable"],
            )

    def _check_api_auth_status(self) -> PreflightCheckResult:
        """Check if API requires authentication and if we have credentials."""
        if not self.api_url:
            return PreflightCheckResult(
                name="API Auth",
                result=CheckResult.SKIP,
                message="No API URL to check auth",
            )

        try:
            import httpx

            # Make request without auth
            for path in ["/", "/api", "/health"]:
                try:
                    url = self.api_url.rstrip("/") + path
                    response = httpx.get(url, timeout=5.0)

                    if response.status_code == 401:
                        # Auth required - check if we have credentials
                        if self.credentials and self.credentials.has_api_auth():
                            return PreflightCheckResult(
                                name="API Auth",
                                result=CheckResult.PASS,
                                message=f"Auth required, credentials provided ({self.credentials.auth_type.value})",
                            )
                        else:
                            return PreflightCheckResult(
                                name="API Auth",
                                result=CheckResult.FAIL,
                                message="API requires authentication (401)",
                                fix_suggestion=FIXES["api_auth_required"],
                            )

                    elif response.status_code == 403:
                        return PreflightCheckResult(
                            name="API Auth",
                            result=CheckResult.FAIL,
                            message="API access forbidden (403)",
                            fix_suggestion=FIXES["api_auth_required"],
                        )

                    elif response.status_code < 400:
                        return PreflightCheckResult(
                            name="API Auth",
                            result=CheckResult.PASS,
                            message="API accessible (no auth required)",
                        )

                except httpx.HTTPError:
                    continue

            return PreflightCheckResult(
                name="API Auth",
                result=CheckResult.WARN,
                message="Could not determine auth requirements",
            )

        except ImportError:
            return PreflightCheckResult(
                name="API Auth",
                result=CheckResult.SKIP,
                message="httpx not available",
            )
        except Exception as e:
            return PreflightCheckResult(
                name="API Auth",
                result=CheckResult.WARN,
                message=f"Auth check failed: {e}",
            )


def display_preflight_report(report: PreflightReport, verbose: bool = False) -> None:
    """Display preflight report - simple output with one fix per failure."""
    try:
        from rich.console import Console

        console = Console()

        for check in report.checks:
            if check.result == CheckResult.PASS:
                console.print(f"       [green]✓[/green] {check.name}")
            elif check.result == CheckResult.FAIL:
                console.print(f"       [red]✗[/red] {check.name}")
                if check.fix_suggestion:
                    console.print(f"         [bold]Fix:[/bold] {check.fix_suggestion}")

    except ImportError:
        for check in report.checks:
            if check.result == CheckResult.PASS:
                print(f"  OK: {check.name}")
            elif check.result == CheckResult.FAIL:
                print(f"  FAIL: {check.name}")
                if check.fix_suggestion:
                    print(f"    Fix: {check.fix_suggestion}")
