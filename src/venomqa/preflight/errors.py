"""Custom exceptions for preflight smoke testing.

These exceptions provide clear, actionable error messages when smoke tests
detect that an API is not ready for full test execution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from venomqa.preflight.smoke import SmokeTestReport


class PreflightError(Exception):
    """Base class for all preflight errors."""


class APINotReadyError(PreflightError):
    """Raised when smoke tests determine the API is not ready for testing.

    This exception carries the full SmokeTestReport so callers can inspect
    individual check results and display actionable diagnostics.

    Attributes:
        report: The SmokeTestReport containing all check results.

    Example:
        >>> from venomqa.preflight import SmokeTest, APINotReadyError
        >>> smoke = SmokeTest("http://localhost:8000")
        >>> try:
        ...     smoke.assert_ready()
        ... except APINotReadyError as e:
        ...     print(e.report.summary)
        ...     for r in e.report.failed_results:
        ...         print(f"  {r.name}: {r.suggestion}")
    """

    def __init__(self, report: SmokeTestReport) -> None:
        self.report = report
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Build a human-readable error message from the report."""
        lines = [
            "API is not ready for testing.",
            "",
            self.report.summary,
            "",
        ]
        for result in self.report.results:
            if not result.passed:
                lines.append(f"  FAILED: {result.name}")
                if result.error:
                    lines.append(f"    Error: {result.error}")
                if result.suggestion:
                    lines.append(f"    Suggestion: {result.suggestion}")
                lines.append("")
        return "\n".join(lines)


class ConnectionFailedError(PreflightError):
    """Raised when a connection to the API cannot be established."""

    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(
            f"Could not connect to {url}. {reason}\n"
            f"  - Is the server running?\n"
            f"  - Check that the port is correct and not blocked by firewall."
        )


class AuthenticationFailedError(PreflightError):
    """Raised when authentication check fails during preflight."""

    def __init__(self, status_code: int, url: str) -> None:
        self.status_code = status_code
        self.url = url
        super().__init__(
            f"Authentication failed (HTTP {status_code}) at {url}.\n"
            f"  - Verify your token is valid and not expired.\n"
            f"  - Check that the user exists in the database."
        )
