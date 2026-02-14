"""Assertion helpers for QA testing.

This module provides reusable assertion functions for:
- HTTP status code assertions
- Response time assertions
- JSON schema validation
- Response content assertions
- Header assertions

Example:
    >>> from venomqa.tools import assert_status_code, assert_response_time, assert_json_schema
    >>>
    >>> response = get(client, context, "/api/users/1")
    >>> assert_status_code(response, 200)
    >>> assert_response_time(response, max_ms=500)
    >>> assert_json_schema(response, {"type": "object", "properties": {"id": {"type": "integer"}}})
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from re import Pattern
from typing import TYPE_CHECKING, Any

import httpx

from venomqa.errors import VenomQAError

if TYPE_CHECKING:
    pass


class AssertionError(VenomQAError):
    """Raised when an assertion fails."""

    pass


def assert_status_code(
    response: httpx.Response,
    expected: int | list[int],
    message: str | None = None,
) -> None:
    """Assert response has expected status code.

    Args:
        response: HTTP response to check.
        expected: Expected status code or list of acceptable codes.
        message: Custom error message.

    Raises:
        AssertionError: If status code doesn't match.

    Example:
        >>> response = get(client, context, "/api/users")
        >>> assert_status_code(response, 200)
        >>>
        >>> # Multiple acceptable codes
        >>> assert_status_code(response, [200, 201])
    """
    if isinstance(expected, int):
        expected_codes = {expected}
    else:
        expected_codes = set(expected)

    if response.status_code not in expected_codes:
        expected_str = ", ".join(map(str, sorted(expected_codes)))
        msg = message or (
            f"Expected status code {expected_str}, got {response.status_code}. "
            f"Response: {response.text[:500]}"
        )
        raise AssertionError(msg)


def assert_status_ok(response: httpx.Response, message: str | None = None) -> None:
    """Assert response status is 200 OK.

    Args:
        response: HTTP response to check.
        message: Custom error message.

    Raises:
        AssertionError: If status is not 200.

    Example:
        >>> response = get(client, context, "/api/users")
        >>> assert_status_ok(response)
    """
    assert_status_code(response, 200, message)


def assert_status_created(response: httpx.Response, message: str | None = None) -> None:
    """Assert response status is 201 Created.

    Args:
        response: HTTP response to check.
        message: Custom error message.

    Raises:
        AssertionError: If status is not 201.

    Example:
        >>> response = post(client, context, "/api/users", json={"name": "John"})
        >>> assert_status_created(response)
    """
    assert_status_code(response, 201, message)


def assert_status_no_content(response: httpx.Response, message: str | None = None) -> None:
    """Assert response status is 204 No Content.

    Args:
        response: HTTP response to check.
        message: Custom error message.

    Raises:
        AssertionError: If status is not 204.

    Example:
        >>> response = delete(client, context, "/api/users/1")
        >>> assert_status_no_content(response)
    """
    assert_status_code(response, 204, message)


def assert_status_bad_request(response: httpx.Response, message: str | None = None) -> None:
    """Assert response status is 400 Bad Request.

    Args:
        response: HTTP response to check.
        message: Custom error message.

    Raises:
        AssertionError: If status is not 400.
    """
    assert_status_code(response, 400, message)


def assert_status_unauthorized(response: httpx.Response, message: str | None = None) -> None:
    """Assert response status is 401 Unauthorized.

    Args:
        response: HTTP response to check.
        message: Custom error message.

    Raises:
        AssertionError: If status is not 401.
    """
    assert_status_code(response, 401, message)


def assert_status_forbidden(response: httpx.Response, message: str | None = None) -> None:
    """Assert response status is 403 Forbidden.

    Args:
        response: HTTP response to check.
        message: Custom error message.

    Raises:
        AssertionError: If status is not 403.
    """
    assert_status_code(response, 403, message)


def assert_status_not_found(response: httpx.Response, message: str | None = None) -> None:
    """Assert response status is 404 Not Found.

    Args:
        response: HTTP response to check.
        message: Custom error message.

    Raises:
        AssertionError: If status is not 404.
    """
    assert_status_code(response, 404, message)


def assert_status_client_error(response: httpx.Response, message: str | None = None) -> None:
    """Assert response status is 4xx client error.

    Args:
        response: HTTP response to check.
        message: Custom error message.

    Raises:
        AssertionError: If status is not 4xx.

    Example:
        >>> response = get(client, context, "/api/invalid")
        >>> assert_status_client_error(response)
    """
    if not (400 <= response.status_code < 500):
        msg = message or f"Expected 4xx client error, got {response.status_code}"
        raise AssertionError(msg)


def assert_status_server_error(response: httpx.Response, message: str | None = None) -> None:
    """Assert response status is 5xx server error.

    Args:
        response: HTTP response to check.
        message: Custom error message.

    Raises:
        AssertionError: If status is not 5xx.

    Example:
        >>> response = get(client, context, "/api/error")
        >>> assert_status_server_error(response)
    """
    if not (500 <= response.status_code < 600):
        msg = message or f"Expected 5xx server error, got {response.status_code}"
        raise AssertionError(msg)


def assert_response_time(
    response: httpx.Response,
    max_ms: float,
    message: str | None = None,
) -> None:
    """Assert response time is within acceptable limit.

    Args:
        response: HTTP response to check.
        max_ms: Maximum acceptable response time in milliseconds.
        message: Custom error message.

    Raises:
        AssertionError: If response time exceeds limit.

    Example:
        >>> response = get(client, context, "/api/users")
        >>> assert_response_time(response, max_ms=500)
    """
    elapsed_ms = response.elapsed.total_seconds() * 1000

    if elapsed_ms > max_ms:
        msg = message or (f"Response time {elapsed_ms:.0f}ms exceeded maximum {max_ms}ms")
        raise AssertionError(msg)


def assert_response_time_range(
    response: httpx.Response,
    min_ms: float = 0,
    max_ms: float = 1000,
    message: str | None = None,
) -> None:
    """Assert response time is within acceptable range.

    Args:
        response: HTTP response to check.
        min_ms: Minimum acceptable response time in milliseconds.
        max_ms: Maximum acceptable response time in milliseconds.
        message: Custom error message.

    Raises:
        AssertionError: If response time is outside range.

    Example:
        >>> response = get(client, context, "/api/users")
        >>> assert_response_time_range(response, min_ms=10, max_ms=500)
    """
    elapsed_ms = response.elapsed.total_seconds() * 1000

    if not (min_ms <= elapsed_ms <= max_ms):
        msg = message or (f"Response time {elapsed_ms:.0f}ms outside range [{min_ms}, {max_ms}]ms")
        raise AssertionError(msg)


def assert_json_schema(
    response: httpx.Response,
    schema: dict[str, Any],
    message: str | None = None,
) -> None:
    """Assert response body matches JSON schema.

    Args:
        response: HTTP response to check.
        schema: JSON Schema to validate against.
        message: Custom error message.

    Raises:
        AssertionError: If schema validation fails.

    Example:
        >>> schema = {
        ...     "type": "object",
        ...     "required": ["id", "name"],
        ...     "properties": {
        ...         "id": {"type": "integer"},
        ...         "name": {"type": "string"}
        ...     }
        ... }
        >>> response = get(client, context, "/api/users/1")
        >>> assert_json_schema(response, schema)
    """
    try:
        import jsonschema
    except ImportError:
        raise AssertionError(
            "jsonschema library not installed. Install with: pip install jsonschema"
        ) from None

    try:
        data = response.json()
    except json.JSONDecodeError as e:
        raise AssertionError(f"Response is not valid JSON: {e}") from e

    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as e:
        msg = message or f"JSON schema validation failed: {e.message}"
        raise AssertionError(msg) from e


def assert_json_path(
    response: httpx.Response,
    path: str,
    expected_value: Any = None,
    message: str | None = None,
) -> Any:
    """Assert JSON response contains expected value at path.

    Args:
        response: HTTP response to check.
        path: Dot-separated path to check (e.g., "data.user.name").
        expected_value: Expected value at path. If None, just checks path exists.
        message: Custom error message.

    Returns:
        Any: The value at the specified path.

    Raises:
        AssertionError: If path doesn't exist or value doesn't match.

    Example:
        >>> response = get(client, context, "/api/users/1")
        >>> assert_json_path(response, "name", "John")
        >>>
        >>> # Check nested path
        >>> assert_json_path(response, "address.city", "New York")
    """
    try:
        data = response.json()
    except json.JSONDecodeError as e:
        raise AssertionError(f"Response is not valid JSON: {e}") from e

    parts = path.split(".")
    current = data
    path_parts = []

    for part in parts:
        path_parts.append(part)
        current_path = ".".join(path_parts)

        if isinstance(current, dict):
            if part not in current:
                msg = message or f"Path '{current_path}' not found in response"
                raise AssertionError(msg)
            current = current[part]
        elif isinstance(current, list):
            try:
                idx = int(part)
                current = current[idx]
            except (ValueError, IndexError) as e:
                msg = message or f"Invalid array index '{part}' at path '{current_path}'"
                raise AssertionError(msg) from e
        else:
            msg = message or f"Cannot access '{part}' on non-dict/list at path '{current_path}'"
            raise AssertionError(msg)

    if expected_value is not None and current != expected_value:
        msg = message or (f"Expected value {expected_value!r} at path '{path}', got {current!r}")
        raise AssertionError(msg)

    return current


def assert_json_contains(
    response: httpx.Response,
    expected: dict[str, Any],
    message: str | None = None,
) -> None:
    """Assert JSON response contains expected key-value pairs.

    Args:
        response: HTTP response to check.
        expected: Key-value pairs that must be present in response.
        message: Custom error message.

    Raises:
        AssertionError: If expected pairs are not all present.

    Example:
        >>> response = get(client, context, "/api/users/1")
        >>> assert_json_contains(response, {"status": "active", "role": "admin"})
    """
    try:
        data = response.json()
    except json.JSONDecodeError as e:
        raise AssertionError(f"Response is not valid JSON: {e}") from e

    def _contains(obj: Any, expected_dict: dict) -> bool:
        if not isinstance(obj, dict):
            return False

        for key, value in expected_dict.items():
            if key not in obj:
                return False
            if isinstance(value, dict):
                if not _contains(obj[key], value):
                    return False
            elif obj[key] != value:
                return False
        return True

    if not _contains(data, expected):
        msg = message or f"Response does not contain expected values: {expected}"
        raise AssertionError(msg)


def assert_json_list_length(
    response: httpx.Response,
    expected_length: int | tuple[int, int],
    list_path: str | None = None,
    message: str | None = None,
) -> None:
    """Assert JSON response list has expected length.

    Args:
        response: HTTP response to check.
        expected_length: Expected list length or (min, max) tuple.
        list_path: Path to list in response. If None, treats response as list.
        message: Custom error message.

    Raises:
        AssertionError: If list length doesn't match.

    Example:
        >>> response = get(client, context, "/api/users")
        >>> assert_json_list_length(response, expected_length=10)
        >>>
        >>> # With range
        >>> assert_json_list_length(response, expected_length=(1, 100))
        >>>
        >>> # Nested list
        >>> assert_json_list_length(response, list_path="data.items", expected_length=5)
    """
    try:
        data = response.json()
    except json.JSONDecodeError as e:
        raise AssertionError(f"Response is not valid JSON: {e}") from e

    if list_path:
        data = assert_json_path(response, list_path)

    if not isinstance(data, list):
        raise AssertionError(f"Value at '{list_path or 'root'}' is not a list")

    length = len(data)

    if isinstance(expected_length, tuple):
        min_len, max_len = expected_length
        if not (min_len <= length <= max_len):
            msg = message or (f"List length {length} not in range [{min_len}, {max_len}]")
            raise AssertionError(msg)
    else:
        if length != expected_length:
            msg = message or (f"Expected list length {expected_length}, got {length}")
            raise AssertionError(msg)


def assert_contains(
    response: httpx.Response,
    expected: str | bytes,
    message: str | None = None,
) -> None:
    """Assert response body contains expected string or bytes.

    Args:
        response: HTTP response to check.
        expected: String or bytes expected to be in response.
        message: Custom error message.

    Raises:
        AssertionError: If expected content is not found.

    Example:
        >>> response = get(client, context, "/api/users")
        >>> assert_contains(response, "John")
    """
    content = response.content if isinstance(expected, bytes) else response.text

    if expected not in content:
        msg = message or f"Response does not contain expected content: {expected!r}"
        raise AssertionError(msg)


def assert_not_contains(
    response: httpx.Response,
    unexpected: str | bytes,
    message: str | None = None,
) -> None:
    """Assert response body does NOT contain unexpected string or bytes.

    Args:
        response: HTTP response to check.
        unexpected: String or bytes that should NOT be in response.
        message: Custom error message.

    Raises:
        AssertionError: If unexpected content is found.

    Example:
        >>> response = get(client, context, "/api/users")
        >>> assert_not_contains(response, "password")
    """
    content = response.content if isinstance(unexpected, bytes) else response.text

    if unexpected in content:
        msg = message or f"Response contains unexpected content: {unexpected!r}"
        raise AssertionError(msg)


def assert_matches_regex(
    response: httpx.Response,
    pattern: str | Pattern[str],
    message: str | None = None,
) -> None:
    """Assert response body matches a regex pattern.

    Args:
        response: HTTP response to check.
        pattern: Regex pattern to match.
        message: Custom error message.

    Raises:
        AssertionError: If pattern doesn't match.

    Example:
        >>> response = get(client, context, "/api/config")
        >>> assert_matches_regex(response, r'"version":\\s*"\\d+\\.\\d+\\.\\d+"')
    """
    if isinstance(pattern, str):
        pattern = re.compile(pattern)

    if not pattern.search(response.text):
        msg = message or f"Response does not match pattern: {pattern.pattern}"
        raise AssertionError(msg)


def assert_header(
    response: httpx.Response,
    header_name: str,
    expected_value: str,
    message: str | None = None,
) -> None:
    """Assert response has expected header value.

    Args:
        response: HTTP response to check.
        header_name: Name of header to check (case-insensitive).
        expected_value: Expected header value.
        message: Custom error message.

    Raises:
        AssertionError: If header value doesn't match.

    Example:
        >>> response = get(client, context, "/api/users")
        >>> assert_header(response, "Content-Type", "application/json")
    """
    actual_value = response.headers.get(header_name)

    if actual_value is None:
        msg = message or f"Header '{header_name}' not found in response"
        raise AssertionError(msg)

    if actual_value != expected_value:
        msg = message or (
            f"Header '{header_name}' expected '{expected_value}', got '{actual_value}'"
        )
        raise AssertionError(msg)


def assert_header_exists(
    response: httpx.Response,
    header_name: str,
    message: str | None = None,
) -> None:
    """Assert response has a specific header.

    Args:
        response: HTTP response to check.
        header_name: Name of header to check (case-insensitive).
        message: Custom error message.

    Raises:
        AssertionError: If header is not present.

    Example:
        >>> response = get(client, context, "/api/users")
        >>> assert_header_exists(response, "X-Request-ID")
    """
    if header_name not in response.headers:
        msg = message or f"Header '{header_name}' not found in response"
        raise AssertionError(msg)


def assert_header_contains(
    response: httpx.Response,
    header_name: str,
    contains: str,
    message: str | None = None,
) -> None:
    """Assert response header contains a specific string.

    Args:
        response: HTTP response to check.
        header_name: Name of header to check.
        contains: String that header value should contain.
        message: Custom error message.

    Raises:
        AssertionError: If header doesn't contain string.

    Example:
        >>> response = get(client, context, "/api/users")
        >>> assert_header_contains(response, "Content-Type", "json")
    """
    actual_value = response.headers.get(header_name)

    if actual_value is None:
        msg = message or f"Header '{header_name}' not found in response"
        raise AssertionError(msg)

    if contains not in actual_value:
        msg = message or (
            f"Header '{header_name}' value '{actual_value}' does not contain '{contains}'"
        )
        raise AssertionError(msg)


def assert_content_type(
    response: httpx.Response,
    expected: str,
    message: str | None = None,
) -> None:
    """Assert response Content-Type header matches expected.

    Args:
        response: HTTP response to check.
        expected: Expected content type (e.g., "application/json").
        message: Custom error message.

    Raises:
        AssertionError: If Content-Type doesn't match.

    Example:
        >>> response = get(client, context, "/api/users")
        >>> assert_content_type(response, "application/json")
    """
    content_type = response.headers.get("Content-Type", "")

    if expected not in content_type:
        msg = message or (f"Content-Type '{content_type}' does not contain '{expected}'")
        raise AssertionError(msg)


def assert_json_type(
    response: httpx.Response,
    expected_type: type | tuple[type, ...],
    path: str | None = None,
    message: str | None = None,
) -> None:
    """Assert JSON value at path is of expected type.

    Args:
        response: HTTP response to check.
        expected_type: Expected type or tuple of types.
        path: Dot-separated path to value. If None, checks root.
        message: Custom error message.

    Raises:
        AssertionError: If type doesn't match.

    Example:
        >>> response = get(client, context, "/api/users/1")
        >>> assert_json_type(response, str, path="name")
        >>> assert_json_type(response, (list, dict), path="data")
    """
    try:
        data = response.json()
    except json.JSONDecodeError as e:
        raise AssertionError(f"Response is not valid JSON: {e}") from e

    if path:
        data = assert_json_path(response, path)

    if not isinstance(data, expected_type):
        type_name = getattr(expected_type, "__name__", str(expected_type))
        actual_type = type(data).__name__
        msg = message or (f"Expected type {type_name} at '{path or 'root'}', got {actual_type}")
        raise AssertionError(msg)


def assert_custom(
    response: httpx.Response,
    condition_fn: Callable[[httpx.Response], bool],
    message: str | None = None,
) -> None:
    """Assert a custom condition on the response.

    Args:
        response: HTTP response to check.
        condition_fn: Function that takes response and returns True if condition passes.
        message: Custom error message.

    Raises:
        AssertionError: If condition returns False.

    Example:
        >>> response = get(client, context, "/api/users")
        >>> assert_custom(
        ...     response,
        ...     condition_fn=lambda r: len(r.json().get("users", [])) > 0,
        ...     message="No users found"
        ... )
    """
    if not condition_fn(response):
        msg = message or "Custom assertion condition failed"
        raise AssertionError(msg)


def assert_redirect(
    response: httpx.Response,
    expected_status: int | list[int] | None = None,
    message: str | None = None,
) -> None:
    """Assert response is a redirect (3xx status code).

    Args:
        response: HTTP response to check.
        expected_status: Expected redirect status code(s). If None, accepts any 3xx.
        message: Custom error message.

    Raises:
        AssertionError: If not a redirect.

    Example:
        >>> response = get(client, context, "/old-path", follow_redirects=False)
        >>> assert_redirect(response)
        >>> assert_redirect(response, expected_status=301)
    """
    is_redirect = 300 <= response.status_code < 400

    if expected_status is not None:
        if isinstance(expected_status, int):
            expected_codes = {expected_status}
        else:
            expected_codes = set(expected_status)
        if response.status_code not in expected_codes:
            msg = message or (
                f"Expected redirect status {expected_codes}, got {response.status_code}"
            )
            raise AssertionError(msg)
    elif not is_redirect:
        msg = message or f"Expected redirect (3xx), got {response.status_code}"
        raise AssertionError(msg)


def assert_redirect_to(
    response: httpx.Response,
    expected_location: str,
    message: str | None = None,
) -> None:
    """Assert response redirects to a specific location.

    Args:
        response: HTTP response to check.
        expected_location: Expected redirect location (full URL or path).
        message: Custom error message.

    Raises:
        AssertionError: If redirect location doesn't match.

    Example:
        >>> response = get(client, context, "/login", follow_redirects=False)
        >>> assert_redirect_to(response, "/dashboard")
    """
    location = response.headers.get("Location") or response.headers.get("location")

    if not location:
        msg = message or "Response has no Location header"
        raise AssertionError(msg)

    if expected_location not in location:
        msg = message or (f"Expected redirect to '{expected_location}', got '{location}'")
        raise AssertionError(msg)


def assert_length(
    response: httpx.Response,
    expected_length: int | tuple[int, int],
    message: str | None = None,
) -> None:
    """Assert response content length.

    Args:
        response: HTTP response to check.
        expected_length: Expected length or (min, max) tuple.
        message: Custom error message.

    Raises:
        AssertionError: If length doesn't match.

    Example:
        >>> response = get(client, context, "/api/data")
        >>> assert_length(response, expected_length=1000)
        >>> assert_length(response, expected_length=(100, 5000))
    """
    content_length = len(response.content)

    if isinstance(expected_length, tuple):
        min_len, max_len = expected_length
        if not (min_len <= content_length <= max_len):
            msg = message or (
                f"Content length {content_length} not in range [{min_len}, {max_len}]"
            )
            raise AssertionError(msg)
    else:
        if content_length != expected_length:
            msg = message or (f"Expected content length {expected_length}, got {content_length}")
            raise AssertionError(msg)


def assert_json_keys(
    response: httpx.Response,
    expected_keys: list[str],
    path: str | None = None,
    exact: bool = False,
    message: str | None = None,
) -> None:
    """Assert JSON response has expected keys.

    Args:
        response: HTTP response to check.
        expected_keys: List of keys that must be present.
        path: Dot-separated path to object. If None, checks root.
        exact: If True, response must have exactly these keys (no more).
        message: Custom error message.

    Raises:
        AssertionError: If keys don't match.

    Example:
        >>> response = get(client, context, "/api/users/1")
        >>> assert_json_keys(response, ["id", "name", "email"])
        >>> assert_json_keys(response, ["id", "name"], exact=True)
    """
    try:
        data = response.json()
    except json.JSONDecodeError as e:
        raise AssertionError(f"Response is not valid JSON: {e}") from e

    if path:
        data = assert_json_path(response, path)

    if not isinstance(data, dict):
        raise AssertionError(f"Value at '{path or 'root'}' is not a dictionary")

    actual_keys = set(data.keys())
    expected_set = set(expected_keys)

    missing = expected_set - actual_keys
    if missing:
        msg = message or f"Missing required keys: {missing}"
        raise AssertionError(msg)

    if exact:
        extra = actual_keys - expected_set
        if extra:
            msg = message or f"Unexpected keys (exact match required): {extra}"
            raise AssertionError(msg)


def assert_json_has_key(
    response: httpx.Response,
    key: str,
    path: str | None = None,
    message: str | None = None,
) -> None:
    """Assert JSON response has a specific key.

    Args:
        response: HTTP response to check.
        key: Key that must be present.
        path: Dot-separated path to object. If None, checks root.
        message: Custom error message.

    Raises:
        AssertionError: If key is not present.

    Example:
        >>> response = get(client, context, "/api/users/1")
        >>> assert_json_has_key(response, "email")
    """
    assert_json_keys(response, [key], path=path, exact=False, message=message)


def assert_is_empty(
    response: httpx.Response,
    path: str | None = None,
    message: str | None = None,
) -> None:
    """Assert JSON value is empty (empty list, dict, string, or None).

    Args:
        response: HTTP response to check.
        path: Dot-separated path to value. If None, checks root.
        message: Custom error message.

    Raises:
        AssertionError: If value is not empty.

    Example:
        >>> response = get(client, context, "/api/users")
        >>> assert_is_empty(response, path="errors")
    """
    try:
        data = response.json()
    except json.JSONDecodeError as e:
        raise AssertionError(f"Response is not valid JSON: {e}") from e

    if path:
        data = assert_json_path(response, path)

    is_empty = data is None or data == [] or data == {} or data == ""

    if not is_empty:
        msg = message or f"Expected empty value at '{path or 'root'}', got: {data!r}"
        raise AssertionError(msg)


def assert_is_not_empty(
    response: httpx.Response,
    path: str | None = None,
    message: str | None = None,
) -> None:
    """Assert JSON value is not empty.

    Args:
        response: HTTP response to check.
        path: Dot-separated path to value. If None, checks root.
        message: Custom error message.

    Raises:
        AssertionError: If value is empty.

    Example:
        >>> response = get(client, context, "/api/users")
        >>> assert_is_not_empty(response, path="data")
    """
    try:
        data = response.json()
    except json.JSONDecodeError as e:
        raise AssertionError(f"Response is not valid JSON: {e}") from e

    if path:
        data = assert_json_path(response, path)

    is_empty = data is None or data == [] or data == {} or data == ""

    if is_empty:
        msg = message or f"Expected non-empty value at '{path or 'root'}'"
        raise AssertionError(msg)


def assert_starts_with(
    response: httpx.Response,
    prefix: str,
    message: str | None = None,
) -> None:
    """Assert response body starts with a specific string.

    Args:
        response: HTTP response to check.
        prefix: String that response should start with.
        message: Custom error message.

    Raises:
        AssertionError: If response doesn't start with prefix.

    Example:
        >>> response = get(client, context, "/api/data")
        >>> assert_starts_with(response, '{"data":')
    """
    if not response.text.startswith(prefix):
        actual = response.text[: len(prefix) + 50]
        msg = message or f"Response does not start with '{prefix}'. Got: '{actual}...'"
        raise AssertionError(msg)


def assert_ends_with(
    response: httpx.Response,
    suffix: str,
    message: str | None = None,
) -> None:
    """Assert response body ends with a specific string.

    Args:
        response: HTTP response to check.
        suffix: String that response should end with.
        message: Custom error message.

    Raises:
        AssertionError: If response doesn't end with suffix.

    Example:
        >>> response = get(client, context, "/api/data")
        >>> assert_ends_with(response, '"success":true}')
    """
    if not response.text.endswith(suffix):
        actual = response.text[-(len(suffix) + 50) :]
        msg = message or f"Response does not end with '{suffix}'. Got: '...{actual}'"
        raise AssertionError(msg)


def assert_cookie_exists(
    response: httpx.Response,
    cookie_name: str,
    message: str | None = None,
) -> None:
    """Assert response sets a specific cookie.

    Args:
        response: HTTP response to check.
        cookie_name: Name of the cookie to check.
        message: Custom error message.

    Raises:
        AssertionError: If cookie is not set.

    Example:
        >>> response = post(client, context, "/login", json={"user": "john"})
        >>> assert_cookie_exists(response, "session_id")
    """
    set_cookie_headers = response.headers.get_list("Set-Cookie")
    cookies = [h.split("=")[0] for h in set_cookie_headers if "=" in h]

    if cookie_name not in cookies:
        msg = message or f"Cookie '{cookie_name}' not found in response"
        raise AssertionError(msg)


def assert_cookie_value(
    response: httpx.Response,
    cookie_name: str,
    expected_value: str,
    message: str | None = None,
) -> None:
    """Assert response sets a cookie with a specific value.

    Args:
        response: HTTP response to check.
        cookie_name: Name of the cookie to check.
        expected_value: Expected cookie value (or part of it).
        message: Custom error message.

    Raises:
        AssertionError: If cookie value doesn't match.

    Example:
        >>> response = post(client, context, "/login", json={"user": "john"})
        >>> assert_cookie_value(response, "session_id", "abc123")
    """
    set_cookie_headers = response.headers.get_list("Set-Cookie")

    for header in set_cookie_headers:
        if header.startswith(f"{cookie_name}="):
            parts = header.split(";", 1)[0]
            value = parts.split("=", 1)[1] if "=" in parts else ""
            if expected_value in value:
                return
            msg = message or (
                f"Cookie '{cookie_name}' value '{value}' does not contain '{expected_value}'"
            )
            raise AssertionError(msg)

    msg = message or f"Cookie '{cookie_name}' not found in response"
    raise AssertionError(msg)


def assert_json_value_greater_than(
    response: httpx.Response,
    path: str,
    minimum: int | float,
    message: str | None = None,
) -> None:
    """Assert JSON value at path is greater than minimum.

    Args:
        response: HTTP response to check.
        path: Dot-separated path to numeric value.
        minimum: Minimum value (exclusive).
        message: Custom error message.

    Raises:
        AssertionError: If value is not greater than minimum.

    Example:
        >>> response = get(client, context, "/api/stats")
        >>> assert_json_value_greater_than(response, "total_users", 100)
    """
    value = assert_json_path(response, path)

    if not isinstance(value, (int, float)):
        raise AssertionError(f"Value at '{path}' is not numeric: {type(value).__name__}")

    if value <= minimum:
        msg = message or f"Value {value} at '{path}' is not greater than {minimum}"
        raise AssertionError(msg)


def assert_json_value_less_than(
    response: httpx.Response,
    path: str,
    maximum: int | float,
    message: str | None = None,
) -> None:
    """Assert JSON value at path is less than maximum.

    Args:
        response: HTTP response to check.
        path: Dot-separated path to numeric value.
        maximum: Maximum value (exclusive).
        message: Custom error message.

    Raises:
        AssertionError: If value is not less than maximum.

    Example:
        >>> response = get(client, context, "/api/stats")
        >>> assert_json_value_less_than(response, "response_time_ms", 1000)
    """
    value = assert_json_path(response, path)

    if not isinstance(value, (int, float)):
        raise AssertionError(f"Value at '{path}' is not numeric: {type(value).__name__}")

    if value >= maximum:
        msg = message or f"Value {value} at '{path}' is not less than {maximum}"
        raise AssertionError(msg)


def assert_json_value_between(
    response: httpx.Response,
    path: str,
    minimum: int | float,
    maximum: int | float,
    message: str | None = None,
) -> None:
    """Assert JSON value at path is within a range.

    Args:
        response: HTTP response to check.
        path: Dot-separated path to numeric value.
        minimum: Minimum value (inclusive).
        maximum: Maximum value (inclusive).
        message: Custom error message.

    Raises:
        AssertionError: If value is outside range.

    Example:
        >>> response = get(client, context, "/api/product/123")
        >>> assert_json_value_between(response, "price", 10, 100)
    """
    value = assert_json_path(response, path)

    if not isinstance(value, (int, float)):
        raise AssertionError(f"Value at '{path}' is not numeric: {type(value).__name__}")

    if not (minimum <= value <= maximum):
        msg = message or f"Value {value} at '{path}' not in range [{minimum}, {maximum}]"
        raise AssertionError(msg)


def assert_json_value_equals(
    response: httpx.Response,
    path: str,
    expected: Any,
    message: str | None = None,
) -> None:
    """Assert JSON value at path equals expected value.

    Args:
        response: HTTP response to check.
        path: Dot-separated path to value.
        expected: Expected value.
        message: Custom error message.

    Raises:
        AssertionError: If value doesn't equal expected.

    Example:
        >>> response = get(client, context, "/api/users/1")
        >>> assert_json_value_equals(response, "status", "active")
    """
    assert_json_path(response, path, expected_value=expected, message=message)


def assert_all(
    response: httpx.Response,
    *assertions: Callable[[httpx.Response], None],
) -> None:
    """Run multiple assertions and collect all failures.

    Args:
        response: HTTP response to check.
        *assertions: Assertion functions to run.

    Raises:
        AssertionError: If any assertions fail, with all errors combined.

    Example:
        >>> assert_all(
        ...     response,
        ...     lambda r: assert_status_ok(r),
        ...     lambda r: assert_content_type(r, "application/json"),
        ...     lambda r: assert_json_has_key(r, "id"),
        ... )
    """
    errors: list[str] = []

    for assertion in assertions:
        try:
            assertion(response)
        except AssertionError as e:
            errors.append(str(e))

    if errors:
        combined = "\n  - ".join(["Multiple assertions failed:"] + errors)
        raise AssertionError(combined)
