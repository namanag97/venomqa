"""Issue formatting and creation for journey execution failures."""

from __future__ import annotations

import json
import logging
from typing import Any

from venomqa.core.models import Issue, Severity

logger = logging.getLogger(__name__)


class IssueFormatter:
    """Formats step failures and creates Issue objects with helpful suggestions.

    This class is responsible for:
    - Creating Issue objects from step failures
    - Formatting request/response data for display
    - Generating helpful suggestions based on error patterns
    """

    def __init__(self) -> None:
        self._issues: list[Issue] = []

    def clear(self) -> None:
        """Clear all captured issues."""
        self._issues = []

    def add_issue(
        self,
        journey: str,
        path: str,
        step: str,
        error: str,
        severity: Severity = Severity.HIGH,
        request: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
        logs: list[str] | None = None,
    ) -> Issue:
        """Create and store an issue from a step failure.

        Args:
            journey: Name of the journey.
            path: Name of the path within the journey.
            step: Name of the failed step.
            error: Error message describing the failure.
            severity: Issue severity level.
            request: Request data (method, URL, headers, body).
            response: Response data (status_code, headers, body).
            logs: Relevant log entries.

        Returns:
            The created Issue object.
        """
        issue = Issue(
            journey=journey,
            path=path,
            step=step,
            error=error,
            severity=severity,
            request=request,
            response=response,
            logs=logs or [],
        )
        self._issues.append(issue)
        logger.warning(f"Issue captured: {journey}/{path}/{step} - {error}")
        return issue

    def get_issues(self) -> list[Issue]:
        """Get a copy of all captured issues."""
        return self._issues.copy()

    def format_step_failure(
        self,
        step_name: str,
        error: str,
        request: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
    ) -> str:
        """Format step failure with full request/response details.

        Always shows request and response information when a step fails,
        regardless of debug mode setting (TD-004).

        Args:
            step_name: Name of the failed step.
            error: Error message.
            request: Request data (method, URL, headers, body).
            response: Response data (status_code, headers, body).

        Returns:
            Formatted error string with request/response details.
        """
        lines: list[str] = []
        lines.append("")
        lines.append(f"Step '{step_name}' failed: {error}")
        lines.append("")

        # Format request details
        if request:
            lines.append("Request:")
            method = request.get("method", "?")
            url = request.get("url", "?")
            lines.append(f"  {method} {url}")

            # Show relevant headers (Content-Type is most important)
            headers = request.get("headers", {})
            if headers:
                content_type = headers.get("Content-Type") or headers.get("content-type")
                if content_type:
                    lines.append(f"  Content-Type: {content_type}")

            # Show request body
            body = request.get("body")
            if body:
                body_str = self.format_body_for_display(body)
                lines.append(f"  {body_str}")
            lines.append("")

        # Format response details
        if response:
            status_code = response.get("status_code", "?")
            lines.append(f"Response ({status_code}):")

            # Show response body
            body = response.get("body")
            if body:
                body_str = self.format_body_for_display(body)
                lines.append(f"  {body_str}")
            lines.append("")

        # Add suggestion based on error type
        suggestion = self.get_error_suggestion(error, response)
        if suggestion:
            lines.append(f"Suggestion: {suggestion}")
            lines.append("")

        return "\n".join(lines)

    def format_body_for_display(self, body: Any) -> str:
        """Format request/response body for display.

        Args:
            body: Body data (string, dict, or other).

        Returns:
            Formatted body string.
        """
        if body is None:
            return "(empty)"

        if isinstance(body, str):
            # Try to parse as JSON for pretty formatting
            try:
                parsed = json.loads(body)
                return json.dumps(parsed, indent=2)
            except (json.JSONDecodeError, TypeError):
                # Truncate long strings
                if len(body) > 500:
                    return body[:500] + "... [truncated]"
                return body

        if isinstance(body, (dict, list)):
            try:
                formatted = json.dumps(body, indent=2, default=str)
                if len(formatted) > 500:
                    return formatted[:500] + "... [truncated]"
                return formatted
            except (TypeError, ValueError):
                return str(body)

        return str(body)

    def get_error_suggestion(
        self,
        error: str,
        response: dict[str, Any] | None = None,
    ) -> str:
        """Get a helpful suggestion based on the error.

        Args:
            error: Error message.
            response: Response data if available.

        Returns:
            Suggestion string or empty string.
        """
        error_lower = error.lower()
        status_code = response.get("status_code") if response else None

        # Status code based suggestions
        if status_code:
            status_suggestions = {
                400: "Check request body format and required fields",
                401: "Check authentication token or credentials",
                403: "Check user permissions for this action",
                404: "Check endpoint path and resource ID",
                405: "Check HTTP method (GET/POST/PUT/DELETE)",
                409: "Check for duplicate entries or state conflicts",
                422: "Check request body validation rules",
                429: "Rate limit exceeded - add delays between requests",
                500: "Check backend logs for exception details",
                502: "Check if upstream services are running",
                503: "Service unavailable - check if service is healthy",
                504: "Gateway timeout - check service performance",
            }
            if status_code in status_suggestions:
                return status_suggestions[status_code]

        # Error pattern based suggestions
        if "connection refused" in error_lower:
            return "Is the service running? Check with `docker ps` or service status"
        if "timeout" in error_lower:
            return "Service may be slow - try increasing timeout"
        if "validation" in error_lower:
            return "Check input data matches expected format"
        if "not found" in error_lower:
            return "Resource may not exist - check if it was created first"

        return ""
