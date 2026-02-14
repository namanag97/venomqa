"""Custom assertions plugin for VenomQA.

This plugin provides additional assertion helpers that can be used
in test steps for common validation patterns.

Configuration:
    ```yaml
    plugins:
      - name: venomqa.plugins.examples.custom_assertions
        config:
          strict_mode: false
    ```

Example:
    >>> from venomqa.plugins.examples import CustomAssertionsPlugin
    >>>
    >>> plugin = CustomAssertionsPlugin()
    >>> assertions = plugin.get_assertions()
    >>>
    >>> # Use in a step
    >>> def my_step(client, ctx):
    ...     response = client.get("/api/users")
    ...     assertions["assert_json_schema"](response, user_schema)
    ...     assertions["assert_response_time"](response, max_ms=500)
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from venomqa.plugins.base import VenomQAPlugin
from venomqa.plugins.types import HookPriority, PluginType

if TYPE_CHECKING:
    pass


class AssertionError(Exception):
    """Raised when a custom assertion fails."""

    def __init__(self, message: str, expected: Any = None, actual: Any = None) -> None:
        self.message = message
        self.expected = expected
        self.actual = actual
        super().__init__(message)


class CustomAssertionsPlugin(VenomQAPlugin):
    """Provide custom assertion helpers for test steps.

    This plugin adds additional assertions beyond the standard
    assertions provided by VenomQA.

    Available Assertions:
        assert_json_schema: Validate response against JSON schema
        assert_response_time: Check response time is within limit
        assert_header_present: Check header exists
        assert_header_value: Check header has expected value
        assert_json_path: Validate value at JSON path
        assert_list_length: Check list has expected length
        assert_contains_all: Check all items are present
        assert_matches_pattern: Check value matches regex
        assert_in_range: Check number is in range
        assert_sorted: Check list is sorted

    Configuration Options:
        strict_mode: If True, assertion failures raise exceptions
    """

    name = "custom-assertions"
    version = "1.0.0"
    plugin_type = PluginType.ASSERTION
    description = "Custom assertion helpers"
    author = "VenomQA Team"
    priority = HookPriority.NORMAL

    def __init__(self) -> None:
        super().__init__()
        self.strict_mode: bool = False
        self._assertions: dict[str, Any] = {}
        self._register_assertions()

    def on_load(self, config: dict[str, Any]) -> None:
        """Load plugin configuration.

        Args:
            config: Plugin configuration
        """
        super().on_load(config)
        self.strict_mode = config.get("strict_mode", False)

    def _register_assertions(self) -> None:
        """Register all available assertions."""
        self._assertions = {
            "assert_json_schema": self.assert_json_schema,
            "assert_response_time": self.assert_response_time,
            "assert_header_present": self.assert_header_present,
            "assert_header_value": self.assert_header_value,
            "assert_json_path": self.assert_json_path,
            "assert_list_length": self.assert_list_length,
            "assert_contains_all": self.assert_contains_all,
            "assert_matches_pattern": self.assert_matches_pattern,
            "assert_in_range": self.assert_in_range,
            "assert_sorted": self.assert_sorted,
            "assert_not_empty": self.assert_not_empty,
            "assert_unique": self.assert_unique,
            "assert_type": self.assert_type,
            "assert_keys_present": self.assert_keys_present,
        }

    def get_assertions(self) -> dict[str, Any]:
        """Get all registered assertions.

        Returns:
            Dictionary mapping assertion names to callables
        """
        return dict(self._assertions)

    def assert_json_schema(
        self,
        response: Any,
        schema: dict[str, Any],
        *,
        message: str = "",
    ) -> bool:
        """Validate response body against a JSON schema.

        Args:
            response: HTTP response object
            schema: JSON schema dictionary
            message: Optional custom error message

        Returns:
            True if validation passes

        Raises:
            AssertionError: If validation fails (in strict mode)
        """
        try:
            import jsonschema

            body = self._get_json_body(response)
            jsonschema.validate(body, schema)
            return True
        except ImportError:
            self._logger.warning("jsonschema not installed, skipping schema validation")
            return True
        except jsonschema.ValidationError as e:
            return self._handle_failure(
                message or f"JSON schema validation failed: {e.message}",
                expected=schema,
                actual=self._get_json_body(response),
            )

    def assert_response_time(
        self,
        response: Any,
        max_ms: float,
        *,
        message: str = "",
    ) -> bool:
        """Assert response time is within limit.

        Args:
            response: HTTP response object
            max_ms: Maximum response time in milliseconds
            message: Optional custom error message

        Returns:
            True if response time is within limit
        """
        elapsed_ms = getattr(response, "elapsed", None)
        if elapsed_ms is None:
            # Try to get from response metadata
            elapsed_ms = 0

        if hasattr(elapsed_ms, "total_seconds"):
            elapsed_ms = elapsed_ms.total_seconds() * 1000

        if elapsed_ms > max_ms:
            return self._handle_failure(
                message or f"Response time {elapsed_ms:.0f}ms exceeds limit {max_ms}ms",
                expected=f"<= {max_ms}ms",
                actual=f"{elapsed_ms:.0f}ms",
            )
        return True

    def assert_header_present(
        self,
        response: Any,
        header_name: str,
        *,
        message: str = "",
    ) -> bool:
        """Assert a header is present in the response.

        Args:
            response: HTTP response object
            header_name: Header name (case-insensitive)
            message: Optional custom error message

        Returns:
            True if header is present
        """
        headers = getattr(response, "headers", {})
        header_lower = header_name.lower()

        for key in headers:
            if key.lower() == header_lower:
                return True

        return self._handle_failure(
            message or f"Header '{header_name}' not found",
            expected=header_name,
            actual=list(headers.keys()),
        )

    def assert_header_value(
        self,
        response: Any,
        header_name: str,
        expected_value: str,
        *,
        message: str = "",
    ) -> bool:
        """Assert a header has the expected value.

        Args:
            response: HTTP response object
            header_name: Header name (case-insensitive)
            expected_value: Expected header value
            message: Optional custom error message

        Returns:
            True if header value matches
        """
        headers = getattr(response, "headers", {})
        header_lower = header_name.lower()
        actual_value = None

        for key, value in headers.items():
            if key.lower() == header_lower:
                actual_value = value
                break

        if actual_value is None:
            return self._handle_failure(
                message or f"Header '{header_name}' not found",
                expected=expected_value,
                actual=None,
            )

        if actual_value != expected_value:
            return self._handle_failure(
                message or f"Header '{header_name}' has wrong value",
                expected=expected_value,
                actual=actual_value,
            )

        return True

    def assert_json_path(
        self,
        response: Any,
        path: str,
        expected_value: Any,
        *,
        message: str = "",
    ) -> bool:
        """Assert value at JSON path equals expected.

        Args:
            response: HTTP response object
            path: Dot-separated path (e.g., "data.user.name")
            expected_value: Expected value at path
            message: Optional custom error message

        Returns:
            True if value matches
        """
        body = self._get_json_body(response)
        actual_value = self._get_value_at_path(body, path)

        if actual_value != expected_value:
            return self._handle_failure(
                message or f"Value at '{path}' does not match",
                expected=expected_value,
                actual=actual_value,
            )

        return True

    def assert_list_length(
        self,
        data: list[Any] | Any,
        expected_length: int,
        *,
        min_length: int | None = None,
        max_length: int | None = None,
        message: str = "",
    ) -> bool:
        """Assert list has expected length or is within range.

        Args:
            data: List or response with JSON list body
            expected_length: Exact expected length (or -1 to skip)
            min_length: Minimum length (optional)
            max_length: Maximum length (optional)
            message: Optional custom error message

        Returns:
            True if length is as expected
        """
        if hasattr(data, "json"):
            data = data.json()

        if not isinstance(data, list):
            return self._handle_failure(
                message or "Expected a list",
                expected="list",
                actual=type(data).__name__,
            )

        actual_length = len(data)

        if expected_length >= 0 and actual_length != expected_length:
            return self._handle_failure(
                message or f"List length mismatch",
                expected=expected_length,
                actual=actual_length,
            )

        if min_length is not None and actual_length < min_length:
            return self._handle_failure(
                message or f"List too short",
                expected=f">= {min_length}",
                actual=actual_length,
            )

        if max_length is not None and actual_length > max_length:
            return self._handle_failure(
                message or f"List too long",
                expected=f"<= {max_length}",
                actual=actual_length,
            )

        return True

    def assert_contains_all(
        self,
        data: list[Any] | dict[str, Any],
        items: list[Any],
        *,
        message: str = "",
    ) -> bool:
        """Assert all items are present in data.

        Args:
            data: List or dictionary to check
            items: Items that must be present
            message: Optional custom error message

        Returns:
            True if all items are present
        """
        if isinstance(data, dict):
            missing = [item for item in items if item not in data]
        else:
            missing = [item for item in items if item not in data]

        if missing:
            return self._handle_failure(
                message or f"Missing items: {missing}",
                expected=items,
                actual=list(data) if isinstance(data, dict) else data,
            )

        return True

    def assert_matches_pattern(
        self,
        value: str,
        pattern: str,
        *,
        message: str = "",
    ) -> bool:
        """Assert string matches regex pattern.

        Args:
            value: String to check
            pattern: Regex pattern
            message: Optional custom error message

        Returns:
            True if pattern matches
        """
        if not re.search(pattern, value):
            return self._handle_failure(
                message or f"Value does not match pattern",
                expected=pattern,
                actual=value,
            )

        return True

    def assert_in_range(
        self,
        value: float | int,
        min_value: float | int,
        max_value: float | int,
        *,
        message: str = "",
    ) -> bool:
        """Assert number is within range.

        Args:
            value: Number to check
            min_value: Minimum value (inclusive)
            max_value: Maximum value (inclusive)
            message: Optional custom error message

        Returns:
            True if value is in range
        """
        if not (min_value <= value <= max_value):
            return self._handle_failure(
                message or f"Value out of range",
                expected=f"{min_value} <= x <= {max_value}",
                actual=value,
            )

        return True

    def assert_sorted(
        self,
        data: list[Any],
        *,
        reverse: bool = False,
        key: str | None = None,
        message: str = "",
    ) -> bool:
        """Assert list is sorted.

        Args:
            data: List to check
            reverse: If True, check for descending order
            key: Optional key for sorting objects
            message: Optional custom error message

        Returns:
            True if list is sorted
        """
        if key:
            values = [item.get(key) if isinstance(item, dict) else getattr(item, key) for item in data]
        else:
            values = list(data)

        expected = sorted(values, reverse=reverse)
        if values != expected:
            return self._handle_failure(
                message or f"List is not sorted",
                expected=expected,
                actual=values,
            )

        return True

    def assert_not_empty(
        self,
        data: Any,
        *,
        message: str = "",
    ) -> bool:
        """Assert data is not empty.

        Args:
            data: Data to check (string, list, dict)
            message: Optional custom error message

        Returns:
            True if data is not empty
        """
        if hasattr(data, "json"):
            data = data.json()

        if not data:
            return self._handle_failure(
                message or "Data is empty",
                expected="non-empty",
                actual=data,
            )

        return True

    def assert_unique(
        self,
        data: list[Any],
        *,
        key: str | None = None,
        message: str = "",
    ) -> bool:
        """Assert all items in list are unique.

        Args:
            data: List to check
            key: Optional key for uniqueness check
            message: Optional custom error message

        Returns:
            True if all items are unique
        """
        if key:
            values = [item.get(key) if isinstance(item, dict) else getattr(item, key) for item in data]
        else:
            values = data

        # Convert to strings for hashability
        str_values = [json.dumps(v, sort_keys=True) if isinstance(v, dict) else str(v) for v in values]

        if len(str_values) != len(set(str_values)):
            return self._handle_failure(
                message or "List contains duplicates",
                expected="all unique",
                actual=values,
            )

        return True

    def assert_type(
        self,
        value: Any,
        expected_type: type | tuple[type, ...],
        *,
        message: str = "",
    ) -> bool:
        """Assert value is of expected type.

        Args:
            value: Value to check
            expected_type: Expected type or tuple of types
            message: Optional custom error message

        Returns:
            True if type matches
        """
        if not isinstance(value, expected_type):
            return self._handle_failure(
                message or f"Type mismatch",
                expected=expected_type,
                actual=type(value),
            )

        return True

    def assert_keys_present(
        self,
        data: dict[str, Any] | Any,
        keys: list[str],
        *,
        message: str = "",
    ) -> bool:
        """Assert all keys are present in dictionary.

        Args:
            data: Dictionary or response with JSON body
            keys: Keys that must be present
            message: Optional custom error message

        Returns:
            True if all keys are present
        """
        if hasattr(data, "json"):
            data = data.json()

        if not isinstance(data, dict):
            return self._handle_failure(
                message or "Expected a dictionary",
                expected="dict",
                actual=type(data).__name__,
            )

        missing = [key for key in keys if key not in data]

        if missing:
            return self._handle_failure(
                message or f"Missing keys: {missing}",
                expected=keys,
                actual=list(data.keys()),
            )

        return True

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _get_json_body(self, response: Any) -> Any:
        """Extract JSON body from response.

        Args:
            response: HTTP response object

        Returns:
            Parsed JSON body
        """
        if hasattr(response, "json"):
            return response.json()
        if isinstance(response, dict):
            return response
        return json.loads(str(response))

    def _get_value_at_path(self, data: Any, path: str) -> Any:
        """Get value at dot-separated path.

        Args:
            data: Data structure to traverse
            path: Dot-separated path

        Returns:
            Value at path or None
        """
        parts = path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    current = current[int(part)]
                except (ValueError, IndexError):
                    return None
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return None

        return current

    def _handle_failure(
        self,
        message: str,
        expected: Any = None,
        actual: Any = None,
    ) -> bool:
        """Handle assertion failure.

        Args:
            message: Error message
            expected: Expected value
            actual: Actual value

        Returns:
            False (or raises in strict mode)
        """
        self._logger.warning(f"Assertion failed: {message}")

        if self.strict_mode:
            raise AssertionError(message, expected, actual)

        return False


# Allow direct import as plugin
Plugin = CustomAssertionsPlugin
plugin = CustomAssertionsPlugin()
