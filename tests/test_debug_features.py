"""Tests for debug features and enhanced error handling."""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from venomqa.errors.debug import (
    DebugContext,
    DebugLevel,
    DebugLogger,
    ErrorFormatter,
    StackTraceFilter,
    StepThroughController,
    TroubleshootingEngine,
    create_debug_context,
    format_error,
    ERROR_SUGGESTIONS,
)


class TestTroubleshootingEngine:
    """Tests for TroubleshootingEngine."""

    def test_get_suggestions_connection_refused(self):
        """Test suggestions for connection refused error."""
        result = TroubleshootingEngine.get_suggestions("connection refused")
        assert "cause" in result
        assert "suggestion" in result
        assert "actions" in result
        assert "service" in result["suggestion"].lower() or "running" in result["suggestion"].lower()

    def test_get_suggestions_401_status(self):
        """Test suggestions for 401 Unauthorized."""
        result = TroubleshootingEngine.get_suggestions("error", http_status=401)
        assert "authentication" in result["cause"].lower() or "unauthorized" in result["cause"].lower()
        assert len(result["actions"]) > 0

    def test_get_suggestions_404_status(self):
        """Test suggestions for 404 Not Found."""
        result = TroubleshootingEngine.get_suggestions("error", http_status=404)
        assert "not found" in result["cause"].lower()
        assert any("path" in action.lower() or "url" in action.lower() for action in result["actions"])

    def test_get_suggestions_500_status(self):
        """Test suggestions for 500 Internal Server Error."""
        result = TroubleshootingEngine.get_suggestions("error", http_status=500)
        assert "server error" in result["cause"].lower()
        assert any("log" in action.lower() for action in result["actions"])

    def test_get_suggestions_timeout(self):
        """Test suggestions for timeout error."""
        result = TroubleshootingEngine.get_suggestions("request timeout")
        assert "timeout" in result["cause"].lower() or "time" in result["cause"].lower()

    def test_get_suggestions_unknown_error(self):
        """Test suggestions for unknown error."""
        result = TroubleshootingEngine.get_suggestions("some weird error xyz123")
        # Should return a generic suggestion
        assert "cause" in result
        assert "suggestion" in result

    def test_extract_response_hint(self):
        """Test extraction of hints from response body."""
        response_body = {"detail": "User not found", "code": 404}
        hint = TroubleshootingEngine._extract_response_hint(response_body)
        assert "User not found" in hint

        # Test with nested errors
        response_body = {"errors": ["Email required", "Password too short"]}
        hint = TroubleshootingEngine._extract_response_hint(response_body)
        assert "Email required" in hint


class TestDebugContext:
    """Tests for DebugContext."""

    def test_create_debug_context(self):
        """Test creating a debug context."""
        ctx = DebugContext(
            step_name="test_step",
            journey_name="test_journey",
            path_name="main",
            error_message="Test error",
            error_type="ValueError",
        )
        assert ctx.step_name == "test_step"
        assert ctx.journey_name == "test_journey"
        assert ctx.path_name == "main"
        assert ctx.error_message == "Test error"

    def test_debug_context_to_dict(self):
        """Test serializing debug context to dictionary."""
        ctx = DebugContext(
            step_name="test_step",
            journey_name="test_journey",
            request={"method": "GET", "url": "/api/test"},
            response={"status_code": 200, "body": {}},
        )
        result = ctx.to_dict()
        assert isinstance(result, dict)
        assert result["step_name"] == "test_step"
        assert result["request"]["method"] == "GET"

    def test_create_debug_context_helper(self):
        """Test the create_debug_context helper function."""
        error = ValueError("Test error")
        ctx = create_debug_context(
            step_name="test_step",
            journey_name="test_journey",
            error=error,
            request={"method": "POST", "url": "/api/test"},
            response={"status_code": 400, "body": {"detail": "Bad request"}},
        )
        assert ctx.step_name == "test_step"
        assert ctx.error_message == "Test error"
        assert ctx.error_type == "ValueError"
        assert ctx.http_status == 400


class TestErrorFormatter:
    """Tests for ErrorFormatter."""

    def test_format_basic_error(self):
        """Test formatting a basic error."""
        ctx = DebugContext(
            step_name="login",
            journey_name="auth_flow",
            error_message="Invalid credentials",
            error_type="AuthError",
        )
        formatter = ErrorFormatter(ctx, use_color=False)
        output = formatter.format()

        assert "login" in output
        assert "auth_flow" in output
        assert "Invalid credentials" in output

    def test_format_with_request_response(self):
        """Test formatting with request/response data."""
        ctx = DebugContext(
            step_name="create_user",
            journey_name="user_flow",
            error_message="Validation failed",
            error_type="ValidationError",
            request={"method": "POST", "url": "/api/users", "body": {"name": "test"}},
            response={"status_code": 422, "body": {"detail": "Invalid email"}},
            http_status=422,
        )
        formatter = ErrorFormatter(ctx, use_color=False, verbose=True)
        output = formatter.format()

        assert "POST" in output
        assert "/api/users" in output
        assert "422" in output

    def test_format_to_json(self):
        """Test formatting as JSON."""
        ctx = DebugContext(
            step_name="test",
            journey_name="test_journey",
            error_message="Test error",
        )
        formatter = ErrorFormatter(ctx)
        json_output = formatter.to_json()

        import json
        parsed = json.loads(json_output)
        assert parsed["step_name"] == "test"


class TestStackTraceFilter:
    """Tests for StackTraceFilter."""

    def test_filter_traceback_basic(self):
        """Test basic traceback filtering."""
        # Create a fake traceback string
        tb = """Traceback (most recent call last):
  File "/path/to/site-packages/venomqa/runner/__init__.py", line 100, in run
    result = step.execute()
  File "/path/to/journeys/test_auth.py", line 25, in login_step
    response = client.post("/api/login", json=data)
  File "/path/to/site-packages/httpx/_client.py", line 200, in post
    return self.request("POST", url, **kwargs)
ValueError: Invalid credentials"""

        filtered = StackTraceFilter.filter_traceback(tb, show_framework=False)

        # Should contain the user code
        assert "journeys/test_auth.py" in filtered or "login_step" in filtered

    def test_get_user_frame(self):
        """Test getting user frame from stack."""
        # This will return None in tests since we're not in user code
        frame = StackTraceFilter.get_user_frame()
        # Just ensure it doesn't crash
        assert frame is None or isinstance(frame, tuple)


class TestDebugLogger:
    """Tests for DebugLogger."""

    def test_debug_logger_singleton(self):
        """Test debug logger singleton pattern."""
        logger1 = DebugLogger.get_instance()
        logger2 = DebugLogger.get_instance()
        assert logger1 is logger2

    def test_debug_logger_disabled_by_default(self):
        """Test that debug logger is disabled by default."""
        logger = DebugLogger()
        assert not logger.enabled

    def test_debug_logger_configure(self):
        """Test configuring debug logger."""
        logger = DebugLogger.configure(
            enabled=True,
            log_file=None,  # Console only
            level=DebugLevel.BASIC,
        )
        assert logger.enabled
        assert logger.level == DebugLevel.BASIC

    def test_log_request(self):
        """Test logging HTTP request."""
        logger = DebugLogger(enabled=True, level=DebugLevel.VERBOSE)
        req_id = logger.log_request("GET", "http://example.com/api/test")
        assert req_id == 1

        req_id2 = logger.log_request("POST", "http://example.com/api/users")
        assert req_id2 == 2

    def test_log_sql(self):
        """Test logging SQL query."""
        logger = DebugLogger(enabled=True, level=DebugLevel.VERBOSE)
        logger.log_sql("SELECT * FROM users WHERE id = ?", (1,))
        # Just ensure it doesn't crash


class TestStepThroughController:
    """Tests for StepThroughController."""

    def test_controller_disabled_by_default(self):
        """Test step controller is disabled by default."""
        controller = StepThroughController()
        assert not controller.enabled
        assert not controller.should_pause("any_step")

    def test_controller_enabled(self):
        """Test enabled step controller."""
        controller = StepThroughController(enabled=True)
        assert controller.enabled
        assert controller.should_pause("any_step")

    def test_breakpoints(self):
        """Test breakpoint management."""
        controller = StepThroughController(enabled=True)

        # Add breakpoints
        controller.add_breakpoint("step1")
        controller.add_breakpoint("step2")

        # With breakpoints, should only pause at those steps
        assert controller.should_pause("step1")
        assert controller.should_pause("step2")
        # Note: when breakpoints are set, it should still pause at them

        # Remove breakpoint
        controller.remove_breakpoint("step1")
        assert not controller.should_pause("step1")

        # Clear all
        controller.clear_breakpoints()
        # With no breakpoints, should pause at all steps
        assert controller.should_pause("any_step")

    def test_skip_to_end(self):
        """Test skip to end functionality."""
        controller = StepThroughController(enabled=True)
        controller._skip_to_end = True

        assert not controller.should_pause("any_step")


class TestFormatError:
    """Tests for format_error convenience function."""

    def test_format_error_basic(self):
        """Test basic error formatting."""
        error = ValueError("Something went wrong")
        output = format_error(
            step_name="test_step",
            journey_name="test_journey",
            error=error,
        )

        assert "test_step" in output
        assert "test_journey" in output
        assert "Something went wrong" in output

    def test_format_error_with_http_context(self):
        """Test error formatting with HTTP context."""
        error = Exception("HTTP 401 Unauthorized")
        output = format_error(
            step_name="login",
            journey_name="auth",
            error=error,
            request={"method": "POST", "url": "/api/login"},
            response={"status_code": 401, "body": {"detail": "Invalid token"}},
            verbose=True,
        )

        assert "login" in output
        assert "POST" in output


class TestErrorSuggestionsCompleteness:
    """Test that error suggestions cover common scenarios."""

    def test_all_common_http_codes_have_suggestions(self):
        """Test that common HTTP status codes have suggestions."""
        common_codes = [400, 401, 403, 404, 405, 409, 422, 429, 500, 502, 503, 504]

        for code in common_codes:
            suggestions = TroubleshootingEngine.get_suggestions("error", http_status=code)
            assert suggestions["cause"] != "Unknown error occurred.", f"No suggestion for HTTP {code}"

    def test_connection_errors_have_suggestions(self):
        """Test that connection errors have suggestions."""
        connection_errors = [
            "connection refused",
            "connection reset",
            "connection timeout",
            "name resolution",
        ]

        for error in connection_errors:
            suggestions = TroubleshootingEngine.get_suggestions(error)
            assert suggestions["cause"] != "Unknown error occurred.", f"No suggestion for: {error}"
