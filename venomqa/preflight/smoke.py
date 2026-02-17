"""Core smoke test functionality.

SmokeTest is the main entry point for running quick API validation before
a full test suite. It orchestrates individual checks and produces a
consolidated report.

Example:
    >>> from venomqa.preflight import SmokeTest
    >>> smoke = SmokeTest("http://localhost:8000", token="eyJ...")
    >>> report = smoke.run_all()
    >>> report.print_report()
    >>> # Or fail fast:
    >>> smoke.assert_ready()
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Any

from venomqa.preflight.checks import (
    AuthCheck,
    BaseCheck,
    CRUDCheck,
    CustomHTTPCheck,
    HealthCheck,
    ListCheck,
    SmokeTestResult,
)
from venomqa.preflight.errors import APINotReadyError

# ---------------------------------------------------------------------------
# SmokeTestReport
# ---------------------------------------------------------------------------

@dataclass
class SmokeTestReport:
    """Aggregated results from a full smoke test run.

    Attributes:
        results: All individual check results.
        total_duration_ms: Wall-clock time for the entire run.
    """

    results: list[SmokeTestResult] = field(default_factory=list)
    total_duration_ms: float = 0.0

    @property
    def passed(self) -> bool:
        """True if every check passed."""
        return all(r.passed for r in self.results)

    @property
    def failed_results(self) -> list[SmokeTestResult]:
        """Return only the checks that failed."""
        return [r for r in self.results if not r.passed]

    @property
    def passed_results(self) -> list[SmokeTestResult]:
        """Return only the checks that passed."""
        return [r for r in self.results if r.passed]

    @property
    def summary(self) -> str:
        """One-line summary of the run."""
        total = len(self.results)
        len(self.passed_results)
        failed = len(self.failed_results)
        if self.passed:
            return (
                f"All {total} checks passed. "
                f"API is ready for testing. ({self.total_duration_ms:.0f}ms)"
            )
        return (
            f"{failed}/{total} checks failed. "
            f"API is NOT ready for testing. ({self.total_duration_ms:.0f}ms)"
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "passed": self.passed,
            "summary": self.summary,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "results": [r.to_dict() for r in self.results],
        }

    def print_report(self, file: Any = None) -> None:
        """Print a formatted report to the console.

        Uses ANSI colors when writing to a TTY, plain text otherwise.

        Args:
            file: Output stream. Defaults to sys.stdout.
        """
        out = file or sys.stdout
        use_color = hasattr(out, "isatty") and out.isatty()

        def _green(text: str) -> str:
            return f"\033[32m{text}\033[0m" if use_color else text

        def _red(text: str) -> str:
            return f"\033[31m{text}\033[0m" if use_color else text

        def _dim(text: str) -> str:
            return f"\033[2m{text}\033[0m" if use_color else text

        def _bold(text: str) -> str:
            return f"\033[1m{text}\033[0m" if use_color else text

        print("", file=out)
        print(_bold("VenomQA Preflight Smoke Test"), file=out)
        print("=" * 50, file=out)
        print("", file=out)

        for result in self.results:
            status_code_str = f" {result.status_code}" if result.status_code else ""
            duration_str = f"({result.duration_ms:.0f}ms)"

            if result.passed:
                mark = _green("[PASS]")
                detail = _dim(f"{status_code_str} {duration_str}")
                print(f"  {mark} {result.name}{detail}", file=out)
            else:
                mark = _red("[FAIL]")
                print(f"  {mark} {result.name}{status_code_str} {duration_str}", file=out)
                if result.error:
                    print(f"         {_red(result.error)}", file=out)
                if result.suggestion:
                    print(f"         Suggestion: {result.suggestion}", file=out)

        print("", file=out)
        if self.passed:
            print(_green(self.summary), file=out)
        else:
            print(_red(self.summary), file=out)
        print("", file=out)


# ---------------------------------------------------------------------------
# SmokeTest -- the main orchestrator
# ---------------------------------------------------------------------------

class SmokeTest:
    """Quick validation that an API is minimally functional.

    Runs a small set of HTTP checks to catch showstopper problems
    (server down, bad auth, broken DB) before investing time in a
    full test suite.

    Args:
        base_url: Root URL of the API (e.g. "http://localhost:8000").
        token: Optional Bearer token for authenticated checks.
        timeout: HTTP timeout in seconds for each check.
        auth_header: HTTP header name for the auth token (default ``Authorization``).
        auth_prefix: Prefix before the token value (default ``Bearer``).

    Example:
        >>> smoke = SmokeTest("http://localhost:8000", token="eyJ...")
        >>> report = smoke.run_all()
        >>> if not report.passed:
        ...     report.print_report()
        ...     raise SystemExit(1)

    Config-driven example:
        >>> smoke = SmokeTest.from_yaml("preflight.yaml")
        >>> report = smoke.run_all()
    """

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        timeout: float = 10.0,
        auth_header: str = "Authorization",
        auth_prefix: str = "Bearer",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.auth_header = auth_header
        self.auth_prefix = auth_prefix
        self.results: list[SmokeTestResult] = []
        self._custom_checks: list[BaseCheck] = []
        self._config: Any | None = None  # set when created via from_config()

    # ----- Factory methods -----

    @classmethod
    def from_config(cls, config: Any) -> SmokeTest:
        """Create a ``SmokeTest`` from a ``PreflightConfig`` object.

        Registers all checks defined in the config and configures auth
        settings.  Call ``run_all()`` to execute them.

        Args:
            config: A ``PreflightConfig`` instance.

        Returns:
            A fully configured ``SmokeTest`` instance.
        """
        from venomqa.preflight.config import PreflightConfig

        if not isinstance(config, PreflightConfig):
            raise TypeError(
                f"Expected PreflightConfig, got {type(config).__name__}"
            )

        token = config.resolve_token()
        instance = cls(
            base_url=config.base_url,
            token=token,
            timeout=config.timeout,
            auth_header=config.auth_header,
            auth_prefix=config.auth_prefix,
        )
        instance._config = config

        # Register health checks
        for hc in config.health_checks:
            check = HealthCheck(
                base_url=config.base_url,
                token=token,
                timeout=hc.timeout or config.timeout,
                path=hc.path,
                auth_header=config.auth_header,
                auth_prefix=config.auth_prefix,
            )
            # Store expected_status and expected_json for config-aware validation
            check._expected_status = hc.expected_status
            check._expected_json = hc.expected_json
            instance._custom_checks.append(check)

        # Register auth checks
        for ac in config.auth_checks:
            check = AuthCheck(
                base_url=config.base_url,
                token=token,
                timeout=config.timeout,
                path=ac.path,
                auth_header=config.auth_header,
                auth_prefix=config.auth_prefix,
            )
            instance._custom_checks.append(check)

        # Register CRUD checks
        for cc in config.crud_checks:
            check = CRUDCheck(
                base_url=config.base_url,
                token=token,
                timeout=config.timeout,
                path=cc.path,
                payload=cc.payload,
                auth_header=config.auth_header,
                auth_prefix=config.auth_prefix,
            )
            if cc.name:
                check.name = cc.name
            instance._custom_checks.append(check)

        # Register list checks
        for lc in config.list_checks:
            check = ListCheck(
                base_url=config.base_url,
                token=token,
                timeout=config.timeout,
                path=lc.path,
                auth_header=config.auth_header,
                auth_prefix=config.auth_prefix,
            )
            instance._custom_checks.append(check)

        # Register custom checks
        for xc in config.custom_checks:
            check = CustomHTTPCheck(
                base_url=config.base_url,
                token=token,
                timeout=config.timeout,
                auth_header=config.auth_header,
                auth_prefix=config.auth_prefix,
                check_name=xc.name,
                method=xc.method,
                path=xc.path,
                payload=xc.payload,
                extra_headers=xc.headers,
                expected_status=xc.expected_status,
                expected_json=xc.expected_json,
            )
            instance._custom_checks.append(check)

        return instance

    @classmethod
    def from_yaml(cls, path: str) -> SmokeTest:
        """Create a ``SmokeTest`` from a YAML configuration file.

        Args:
            path: Path to the YAML config file.

        Returns:
            A fully configured ``SmokeTest`` instance.
        """
        from venomqa.preflight.config import PreflightConfig

        config = PreflightConfig.from_yaml(path)
        return cls.from_config(config)

    # ----- Individual checks -----

    def check_health(self, path: str = "/health") -> SmokeTestResult:
        """Verify the health endpoint returns 2xx.

        Args:
            path: Health endpoint path (default "/health").

        Returns:
            SmokeTestResult with the check outcome.
        """
        check = HealthCheck(
            base_url=self.base_url,
            token=self.token,
            timeout=self.timeout,
            path=path,
        )
        result = check.run()
        self.results.append(result)
        return result

    def check_auth(self, path: str = "/api/v1/workspaces") -> SmokeTestResult:
        """Verify an authenticated request works (not 401/403/500).

        Args:
            path: An auth-protected endpoint to test (default "/api/v1/workspaces").

        Returns:
            SmokeTestResult with the check outcome.
        """
        check = AuthCheck(
            base_url=self.base_url,
            token=self.token,
            timeout=self.timeout,
            path=path,
        )
        result = check.run()
        self.results.append(result)
        return result

    def check_create(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> SmokeTestResult:
        """Verify that a resource creation endpoint works.

        Args:
            path: The POST endpoint path.
            payload: JSON body to send.

        Returns:
            SmokeTestResult with the check outcome.
        """
        check = CRUDCheck(
            base_url=self.base_url,
            token=self.token,
            timeout=self.timeout,
            path=path,
            payload=payload,
        )
        result = check.run()
        self.results.append(result)
        return result

    def check_list(self, path: str) -> SmokeTestResult:
        """Verify a list endpoint returns an array or paginated response.

        Args:
            path: The GET endpoint path.

        Returns:
            SmokeTestResult with the check outcome.
        """
        check = ListCheck(
            base_url=self.base_url,
            token=self.token,
            timeout=self.timeout,
            path=path,
        )
        result = check.run()
        self.results.append(result)
        return result

    def add_check(self, check: BaseCheck) -> None:
        """Register a custom check to be included in run_all().

        Args:
            check: A BaseCheck subclass instance.
        """
        self._custom_checks.append(check)

    # ----- Batch execution -----

    def run_all(
        self,
        health_path: str = "/health",
        auth_path: str = "/api/v1/workspaces",
        create_path: str | None = None,
        create_payload: dict[str, Any] | None = None,
        list_path: str | None = None,
    ) -> SmokeTestReport:
        """Run all standard smoke checks and return a report.

        When created via ``from_config()`` or ``from_yaml()``, runs only the
        checks defined in the configuration (the positional arguments are
        ignored).

        When created directly, runs health + auth checks by default. If
        ``create_path`` or ``list_path`` are provided, those checks are
        included too.

        Args:
            health_path: Path for the health check.
            auth_path: Path for the auth check.
            create_path: Path for the create check (optional).
            create_payload: Payload for the create check (optional).
            list_path: Path for the list check (optional).

        Returns:
            SmokeTestReport with all results.
        """
        self.results = []
        start = time.perf_counter()

        if self._config is not None:
            # Config-driven mode: all checks are pre-registered
            for custom in self._custom_checks:
                result = custom.run()
                self.results.append(result)
        else:
            # Legacy mode: run default checks + any manually added custom checks
            # Always run health check
            self.check_health(path=health_path)

            # Run auth check if token is available
            if self.token:
                self.check_auth(path=auth_path)

            # Run create check if configured
            if create_path:
                self.check_create(path=create_path, payload=create_payload)

            # Run list check if configured
            if list_path:
                self.check_list(path=list_path)

            # Run any custom checks
            for custom in self._custom_checks:
                result = custom.run()
                self.results.append(result)

        total_duration = (time.perf_counter() - start) * 1000

        return SmokeTestReport(
            results=list(self.results),
            total_duration_ms=total_duration,
        )

    def assert_ready(
        self,
        health_path: str = "/health",
        auth_path: str = "/api/v1/workspaces",
        create_path: str | None = None,
        create_payload: dict[str, Any] | None = None,
        list_path: str | None = None,
    ) -> SmokeTestReport:
        """Run smoke tests and raise APINotReadyError if any fail.

        This is the recommended way to gate a test suite behind a
        smoke test. Call it at the top of your test session or in a
        pytest conftest.py fixture.

        Args:
            health_path: Path for the health check.
            auth_path: Path for the auth check.
            create_path: Path for the create check (optional).
            create_payload: Payload for the create check (optional).
            list_path: Path for the list check (optional).

        Returns:
            SmokeTestReport if all checks pass.

        Raises:
            APINotReadyError: If one or more checks fail.
        """
        report = self.run_all(
            health_path=health_path,
            auth_path=auth_path,
            create_path=create_path,
            create_payload=create_payload,
            list_path=list_path,
        )
        if not report.passed:
            raise APINotReadyError(report)
        return report
