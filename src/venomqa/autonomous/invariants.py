"""Default invariants for autonomous testing."""

from __future__ import annotations

from venomqa import Invariant, Severity, World


def create_default_invariants() -> list[Invariant]:
    """Create sensible default invariants for any API.

    These invariants catch common bugs without requiring
    any configuration from the user.
    """

    def no_server_errors(world: World) -> bool:
        """API should never return 5xx errors."""
        result = world.last_action_result
        if result is None or result.response is None:
            return True
        return result.response.status_code < 500

    def no_empty_error_responses(world: World) -> bool:
        """Error responses should have a message."""
        result = world.last_action_result
        if result is None or result.response is None:
            return True

        status = result.response.status_code
        if status >= 400:
            # Error responses should have content
            try:
                body = result.response.json()
                # Check for common error message fields
                has_message = any(
                    k in body for k in ["error", "message", "detail", "errors"]
                )
                return has_message or len(body) > 0
            except Exception:
                # Non-JSON error is fine
                return len(result.response.text) > 0
        return True

    def reasonable_response_time(world: World) -> bool:
        """Responses should complete within 10 seconds."""
        result = world.last_action_result
        if result is None:
            return True
        # duration_ms might not exist on all ActionResults
        duration = getattr(result, "duration_ms", None)
        if duration is None:
            return True
        return duration < 10000

    def consistent_content_type(world: World) -> bool:
        """JSON endpoints should return application/json."""
        result = world.last_action_result
        if result is None or result.response is None:
            return True

        content_type = result.response.headers.get("content-type", "")

        # If response is JSON parseable, content-type should indicate JSON
        try:
            result.response.json()
            return "json" in content_type.lower()
        except Exception:
            return True

    return [
        Invariant(
            name="no_server_errors",
            check=no_server_errors,
            message="Server returned 5xx error - this indicates a bug",
            severity=Severity.CRITICAL,
        ),
        Invariant(
            name="error_responses_have_message",
            check=no_empty_error_responses,
            message="Error response missing error message",
            severity=Severity.LOW,
        ),
        Invariant(
            name="reasonable_response_time",
            check=reasonable_response_time,
            message="Response took over 10 seconds",
            severity=Severity.LOW,
        ),
        Invariant(
            name="consistent_content_type",
            check=consistent_content_type,
            message="JSON response missing application/json content-type",
            severity=Severity.LOW,
        ),
    ]
