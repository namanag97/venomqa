"""HTTP-specific assertions for VenomQA.

Provides assertion functions for validating HTTP responses including
status codes, headers, response times, and JSON content.

Example:
    >>> from venomqa.assertions import assert_status_code, assert_header
    >>> assert_status_code(response, 200)
    >>> assert_header(response, "content-type", "application/json")
"""

from __future__ import annotations

from typing import Any

from venomqa.assertions.expect import AssertionFailed


class HTTPAssertionError(AssertionFailed):
    """Raised when an HTTP assertion fails."""

    pass


def assert_status_code(response: Any, expected: int | list[int]) -> None:
    """Assert response has expected status code.

    Args:
        response: HTTP response object with status_code attribute.
        expected: Expected status code or list of acceptable codes.

    Raises:
        HTTPAssertionError: If status code doesn't match.

    Example:
        >>> assert_status_code(response, 200)
        >>> assert_status_code(response, [200, 201])
    """
    actual = getattr(response, "status_code", None)
    if isinstance(expected, list):
        if actual not in expected:
            raise HTTPAssertionError(
                f"Expected status code in {expected}, got {actual}",
                actual=actual,
                expected=expected,
            )
    else:
        if actual != expected:
            raise HTTPAssertionError(
                f"Expected status code {expected}, got {actual}",
                actual=actual,
                expected=expected,
            )


def assert_response_time(response: Any, max_ms: float) -> None:
    """Assert response time is under threshold.

    Args:
        response: HTTP response object with elapsed attribute.
        max_ms: Maximum allowed response time in milliseconds.

    Raises:
        HTTPAssertionError: If response time exceeds threshold.

    Example:
        >>> assert_response_time(response, 500)
    """
    elapsed = getattr(response, "elapsed", None)
    if elapsed is None:
        return

    actual_ms = elapsed.total_seconds() * 1000
    if actual_ms > max_ms:
        raise HTTPAssertionError(
            f"Response time {actual_ms:.2f}ms exceeded maximum {max_ms}ms",
            actual=f"{actual_ms:.2f}ms",
            expected=f"<= {max_ms}ms",
        )


def assert_header(response: Any, name: str, value: str | None = None) -> None:
    """Assert response has header (optionally with specific value).

    Args:
        response: HTTP response object with headers attribute.
        name: Header name to check.
        value: Expected header value (optional, just checks existence if None).

    Raises:
        HTTPAssertionError: If header check fails.

    Example:
        >>> assert_header(response, "content-type")
        >>> assert_header(response, "content-type", "application/json")
    """
    headers = getattr(response, "headers", {})
    actual = headers.get(name)

    if actual is None:
        raise HTTPAssertionError(
            f"Header {name!r} not found in response",
            actual=list(headers.keys()),
            expected=name,
        )

    if value is not None and actual != value:
        raise HTTPAssertionError(
            f"Header {name!r} has value {actual!r}, expected {value!r}",
            actual=actual,
            expected=value,
        )


def assert_header_contains(response: Any, name: str, substring: str) -> None:
    """Assert response header contains substring.

    Args:
        response: HTTP response object with headers attribute.
        name: Header name to check.
        substring: Substring that should be present in header value.

    Raises:
        HTTPAssertionError: If header doesn't contain substring.

    Example:
        >>> assert_header_contains(response, "content-type", "json")
    """
    headers = getattr(response, "headers", {})
    actual = headers.get(name)

    if actual is None:
        raise HTTPAssertionError(
            f"Header {name!r} not found in response",
            actual=list(headers.keys()),
            expected=name,
        )

    if substring not in actual:
        raise HTTPAssertionError(
            f"Header {name!r} value {actual!r} does not contain {substring!r}",
            actual=actual,
            expected=f"contains {substring!r}",
        )


def assert_json_contains(response: Any, key: str, value: Any = None) -> None:
    """Assert response JSON contains key (optionally with specific value).

    Args:
        response: HTTP response object with json() method.
        key: JSON key to check (supports dot notation for nested keys).
        value: Expected value (optional, just checks existence if None).

    Raises:
        HTTPAssertionError: If JSON assertion fails.

    Example:
        >>> assert_json_contains(response, "id")
        >>> assert_json_contains(response, "user.name", "John")
    """
    try:
        body = response.json() if callable(getattr(response, "json", None)) else {}
    except Exception as e:
        raise HTTPAssertionError(
            f"Failed to parse response as JSON: {e}",
            actual="non-JSON response",
            expected="valid JSON",
        ) from e

    keys = key.split(".")
    current = body
    path_so_far = []

    for k in keys:
        path_so_far.append(k)
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            raise HTTPAssertionError(
                f"JSON path {'.'.join(path_so_far)} not found in response",
                actual=body,
                expected=key,
            )

    if value is not None and current != value:
        raise HTTPAssertionError(
            f"JSON key {key!r} has value {current!r}, expected {value!r}",
            actual=current,
            expected=value,
        )


def assert_json_path(response: Any, path: str, expected: Any = None) -> None:
    """Assert response JSON has path with optional value check.

    Args:
        response: HTTP response object with json() method.
        path: JSONPath expression (supports $.field.nested syntax).
        expected: Expected value (optional, just checks existence if None).

    Raises:
        HTTPAssertionError: If JSONPath assertion fails.

    Example:
        >>> assert_json_path(response, "$.data.id")
        >>> assert_json_path(response, "$.items[0].name", "first")
    """
    try:
        body = response.json() if callable(getattr(response, "json", None)) else {}
    except Exception as e:
        raise HTTPAssertionError(
            f"Failed to parse response as JSON: {e}",
            actual="non-JSON response",
            expected="valid JSON",
        ) from e

    value = _resolve_json_path(body, path)

    if value is None and expected is not None:
        raise HTTPAssertionError(
            f"JSON path {path!r} not found or is None",
            actual=body,
            expected=path,
        )

    if expected is not None and value != expected:
        raise HTTPAssertionError(
            f"JSON path {path!r} has value {value!r}, expected {expected!r}",
            actual=value,
            expected=expected,
        )


def assert_json_array_length(response: Any, path: str, expected: int) -> None:
    """Assert JSON array at path has expected length.

    Args:
        response: HTTP response object with json() method.
        path: JSONPath to array field.
        expected: Expected array length.

    Raises:
        HTTPAssertionError: If array length doesn't match.

    Example:
        >>> assert_json_array_length(response, "$.items", 3)
    """
    try:
        body = response.json() if callable(getattr(response, "json", None)) else {}
    except Exception as e:
        raise HTTPAssertionError(
            f"Failed to parse response as JSON: {e}",
            actual="non-JSON response",
            expected="valid JSON",
        ) from e

    value = _resolve_json_path(body, path)

    if not isinstance(value, list):
        raise HTTPAssertionError(
            f"JSON path {path!r} is not an array",
            actual=type(value).__name__,
            expected="array",
        )

    actual_len = len(value)
    if actual_len != expected:
        raise HTTPAssertionError(
            f"JSON array at {path!r} has length {actual_len}, expected {expected}",
            actual=actual_len,
            expected=expected,
        )


def assert_content_type(response: Any, content_type: str) -> None:
    """Assert response has specific content-type.

    Args:
        response: HTTP response object with headers attribute.
        content_type: Expected content-type (partial match).

    Raises:
        HTTPAssertionError: If content-type doesn't match.

    Example:
        >>> assert_content_type(response, "application/json")
    """
    headers = getattr(response, "headers", {})
    actual = headers.get("content-type", "")

    if content_type not in actual:
        raise HTTPAssertionError(
            f"Content-Type {actual!r} does not contain {content_type!r}",
            actual=actual,
            expected=content_type,
        )


def assert_ok(response: Any) -> None:
    """Assert response status is 2xx.

    Args:
        response: HTTP response object with status_code attribute.

    Raises:
        HTTPAssertionError: If status is not 2xx.

    Example:
        >>> assert_ok(response)
    """
    actual = getattr(response, "status_code", 0)
    if not (200 <= actual < 300):
        raise HTTPAssertionError(
            f"Expected 2xx status, got {actual}",
            actual=actual,
            expected="2xx",
        )


def assert_created(response: Any) -> None:
    """Assert response status is 201 Created.

    Args:
        response: HTTP response object with status_code attribute.

    Raises:
        HTTPAssertionError: If status is not 201.

    Example:
        >>> assert_created(response)
    """
    actual = getattr(response, "status_code", 0)
    if actual != 201:
        raise HTTPAssertionError(
            f"Expected status 201 Created, got {actual}",
            actual=actual,
            expected=201,
        )


def assert_no_content(response: Any) -> None:
    """Assert response status is 204 No Content.

    Args:
        response: HTTP response object with status_code attribute.

    Raises:
        HTTPAssertionError: If status is not 204.

    Example:
        >>> assert_no_content(response)
    """
    actual = getattr(response, "status_code", 0)
    if actual != 204:
        raise HTTPAssertionError(
            f"Expected status 204 No Content, got {actual}",
            actual=actual,
            expected=204,
        )


def assert_bad_request(response: Any) -> None:
    """Assert response status is 400 Bad Request.

    Args:
        response: HTTP response object with status_code attribute.

    Raises:
        HTTPAssertionError: If status is not 400.

    Example:
        >>> assert_bad_request(response)
    """
    actual = getattr(response, "status_code", 0)
    if actual != 400:
        raise HTTPAssertionError(
            f"Expected status 400 Bad Request, got {actual}",
            actual=actual,
            expected=400,
        )


def assert_unauthorized(response: Any) -> None:
    """Assert response status is 401 Unauthorized.

    Args:
        response: HTTP response object with status_code attribute.

    Raises:
        HTTPAssertionError: If status is not 401.

    Example:
        >>> assert_unauthorized(response)
    """
    actual = getattr(response, "status_code", 0)
    if actual != 401:
        raise HTTPAssertionError(
            f"Expected status 401 Unauthorized, got {actual}",
            actual=actual,
            expected=401,
        )


def assert_forbidden(response: Any) -> None:
    """Assert response status is 403 Forbidden.

    Args:
        response: HTTP response object with status_code attribute.

    Raises:
        HTTPAssertionError: If status is not 403.

    Example:
        >>> assert_forbidden(response)
    """
    actual = getattr(response, "status_code", 0)
    if actual != 403:
        raise HTTPAssertionError(
            f"Expected status 403 Forbidden, got {actual}",
            actual=actual,
            expected=403,
        )


def assert_not_found(response: Any) -> None:
    """Assert response status is 404 Not Found.

    Args:
        response: HTTP response object with status_code attribute.

    Raises:
        HTTPAssertionError: If status is not 404.

    Example:
        >>> assert_not_found(response)
    """
    actual = getattr(response, "status_code", 0)
    if actual != 404:
        raise HTTPAssertionError(
            f"Expected status 404 Not Found, got {actual}",
            actual=actual,
            expected=404,
        )


def assert_client_error(response: Any) -> None:
    """Assert response status is 4xx.

    Args:
        response: HTTP response object with status_code attribute.

    Raises:
        HTTPAssertionError: If status is not 4xx.

    Example:
        >>> assert_client_error(response)
    """
    actual = getattr(response, "status_code", 0)
    if not (400 <= actual < 500):
        raise HTTPAssertionError(
            f"Expected 4xx status, got {actual}",
            actual=actual,
            expected="4xx",
        )


def assert_server_error(response: Any) -> None:
    """Assert response status is 5xx.

    Args:
        response: HTTP response object with status_code attribute.

    Raises:
        HTTPAssertionError: If status is not 5xx.

    Example:
        >>> assert_server_error(response)
    """
    actual = getattr(response, "status_code", 0)
    if not (500 <= actual < 600):
        raise HTTPAssertionError(
            f"Expected 5xx status, got {actual}",
            actual=actual,
            expected="5xx",
        )


def assert_cookie_set(response: Any, name: str, value: str | None = None) -> None:
    """Assert response sets a cookie.

    Args:
        response: HTTP response object with cookies attribute.
        name: Cookie name to check.
        value: Expected cookie value (optional).

    Raises:
        HTTPAssertionError: If cookie not found or value doesn't match.

    Example:
        >>> assert_cookie_set(response, "session_id")
        >>> assert_cookie_set(response, "session_id", "abc123")
    """
    cookies = getattr(response, "cookies", {})
    actual = cookies.get(name)

    if actual is None:
        raise HTTPAssertionError(
            f"Cookie {name!r} not found in response",
            actual=list(cookies.keys()),
            expected=name,
        )

    if value is not None and actual != value:
        raise HTTPAssertionError(
            f"Cookie {name!r} has value {actual!r}, expected {value!r}",
            actual=actual,
            expected=value,
        )


def assert_redirect(response: Any, expected_location: str | None = None) -> None:
    """Assert response is a redirect.

    Args:
        response: HTTP response object with status_code and headers.
        expected_location: Expected redirect location (optional).

    Raises:
        HTTPAssertionError: If not a redirect or location doesn't match.

    Example:
        >>> assert_redirect(response)
        >>> assert_redirect(response, "/login")
    """
    actual = getattr(response, "status_code", 0)
    if not (300 <= actual < 400):
        raise HTTPAssertionError(
            f"Expected 3xx redirect status, got {actual}",
            actual=actual,
            expected="3xx",
        )

    if expected_location is not None:
        headers = getattr(response, "headers", {})
        location = headers.get("location", "")
        if expected_location not in location:
            raise HTTPAssertionError(
                f"Redirect location {location!r} does not match {expected_location!r}",
                actual=location,
                expected=expected_location,
            )


def _resolve_json_path(data: Any, path: str) -> Any:
    """Simple JSONPath resolution (supports $.field.nested syntax)."""
    if not path.startswith("$"):
        return None

    parts = path[1:].split(".")
    if parts[0] == "":
        parts = parts[1:]

    current = data
    for part in parts:
        if not part:
            continue
        if "[" in part and part.endswith("]"):
            field = part[: part.index("[")]
            idx = int(part[part.index("[") + 1 : -1])
            if field:
                if isinstance(current, dict) and field in current:
                    current = current[field]
                else:
                    return None
            if isinstance(current, list) and 0 <= idx < len(current):
                current = current[idx]
            else:
                return None
        elif isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            if 0 <= idx < len(current):
                current = current[idx]
            else:
                return None
        else:
            return None
    return current
