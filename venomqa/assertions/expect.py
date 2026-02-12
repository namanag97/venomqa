"""Fluent assertion API for VenomQA.

Provides a chainable, readable assertion interface inspired by Chai.js
and other BDD-style assertion libraries.

Example:
    >>> expect(42).to_equal(42)
    >>> expect([1, 2, 3]).to_contain(2)
    >>> expect(response).to_have_status(200)
    >>> expect({"a": 1}).to_have_key("a")
"""

from __future__ import annotations

import re
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class AssertionFailedError(Exception):
    """Raised when an assertion fails."""

    def __init__(self, message: str, actual: Any = None, expected: Any = None):
        self.message = message
        self.actual = actual
        self.expected = expected
        super().__init__(message)


AssertionFailed = AssertionFailedError


class Expectation(Generic[T]):
    """Fluent assertion wrapper for values."""

    def __init__(self, value: T, description: str = "value"):
        self._value = value
        self._description = description
        self._negated = False

    @property
    def not_(self) -> Expectation[T]:
        """Negate the following assertion."""
        self._negated = not self._negated
        return self

    def _assert(
        self, condition: bool, message: str, actual: Any = None, expected: Any = None
    ) -> Expectation[T]:
        """Execute assertion with negation support."""
        if self._negated:
            condition = not condition
            message = f"NOT {message}"
            self._negated = False

        if not condition:
            raise AssertionFailedError(
                f"Assertion failed: {self._description} {message}",
                actual=actual,
                expected=expected,
            )
        return self

    def to_equal(self, expected: Any) -> Expectation[T]:
        """Assert value equals expected."""
        return self._assert(
            self._value == expected,
            f"to equal {expected!r}",
            actual=self._value,
            expected=expected,
        )

    def to_be(self, expected: Any) -> Expectation[T]:
        """Assert value is (identity) expected."""
        return self._assert(
            self._value is expected,
            f"to be {expected!r}",
            actual=self._value,
            expected=expected,
        )

    def to_be_none(self) -> Expectation[T]:
        """Assert value is None."""
        return self._assert(
            self._value is None,
            "to be None",
            actual=self._value,
            expected=None,
        )

    def to_be_truthy(self) -> Expectation[T]:
        """Assert value is truthy."""
        return self._assert(
            bool(self._value),
            "to be truthy",
            actual=self._value,
            expected="truthy value",
        )

    def to_be_falsy(self) -> Expectation[T]:
        """Assert value is falsy."""
        return self._assert(
            not bool(self._value),
            "to be falsy",
            actual=self._value,
            expected="falsy value",
        )

    def to_be_type(self, expected_type: type) -> Expectation[T]:
        """Assert value is of expected type."""
        return self._assert(
            isinstance(self._value, expected_type),
            f"to be of type {expected_type.__name__}",
            actual=type(self._value).__name__,
            expected=expected_type.__name__,
        )

    def to_contain(self, item: Any) -> Expectation[T]:
        """Assert collection contains item."""
        try:
            contains = item in self._value
        except TypeError:
            contains = False
        return self._assert(
            contains,
            f"to contain {item!r}",
            actual=self._value,
            expected=item,
        )

    def to_contain_all(self, items: list[Any]) -> Expectation[T]:
        """Assert collection contains all items."""
        try:
            contains_all = all(item in self._value for item in items)
        except TypeError:
            contains_all = False
        return self._assert(
            contains_all,
            f"to contain all of {items!r}",
            actual=self._value,
            expected=items,
        )

    def to_be_empty(self) -> Expectation[T]:
        """Assert collection/string is empty."""
        return self._assert(
            len(self._value) == 0,
            "to be empty",
            actual=self._value,
            expected="empty",
        )

    def to_have_length(self, expected: int) -> Expectation[T]:
        """Assert collection/string has expected length."""
        actual_len = len(self._value)
        return self._assert(
            actual_len == expected,
            f"to have length {expected}",
            actual=actual_len,
            expected=expected,
        )

    def to_be_greater_than(self, expected: int | float) -> Expectation[T]:
        """Assert value is greater than expected."""
        return self._assert(
            self._value > expected,
            f"to be greater than {expected}",
            actual=self._value,
            expected=f"> {expected}",
        )

    def to_be_greater_than_or_equal(self, expected: int | float) -> Expectation[T]:
        """Assert value is greater than or equal to expected."""
        return self._assert(
            self._value >= expected,
            f"to be greater than or equal to {expected}",
            actual=self._value,
            expected=f">= {expected}",
        )

    def to_be_less_than(self, expected: int | float) -> Expectation[T]:
        """Assert value is less than expected."""
        return self._assert(
            self._value < expected,
            f"to be less than {expected}",
            actual=self._value,
            expected=f"< {expected}",
        )

    def to_be_less_than_or_equal(self, expected: int | float) -> Expectation[T]:
        """Assert value is less than or equal to expected."""
        return self._assert(
            self._value <= expected,
            f"to be less than or equal to {expected}",
            actual=self._value,
            expected=f"<= {expected}",
        )

    def to_be_between(self, min_val: int | float, max_val: int | float) -> Expectation[T]:
        """Assert value is between min and max (inclusive)."""
        return self._assert(
            min_val <= self._value <= max_val,
            f"to be between {min_val} and {max_val}",
            actual=self._value,
            expected=f"[{min_val}, {max_val}]",
        )

    def to_start_with(self, prefix: str) -> Expectation[T]:
        """Assert string starts with prefix."""
        return self._assert(
            str(self._value).startswith(prefix),
            f"to start with {prefix!r}",
            actual=self._value,
            expected=prefix,
        )

    def to_end_with(self, suffix: str) -> Expectation[T]:
        """Assert string ends with suffix."""
        return self._assert(
            str(self._value).endswith(suffix),
            f"to end with {suffix!r}",
            actual=self._value,
            expected=suffix,
        )

    def to_match(self, pattern: str | re.Pattern) -> Expectation[T]:
        """Assert string matches regex pattern."""
        if isinstance(pattern, str):
            pattern = re.compile(pattern)
        return self._assert(
            pattern.search(str(self._value)) is not None,
            f"to match pattern {pattern.pattern!r}",
            actual=self._value,
            expected=pattern.pattern,
        )

    def to_have_key(self, key: str) -> Expectation[T]:
        """Assert dict has key."""
        return self._assert(
            key in self._value,
            f"to have key {key!r}",
            actual=list(self._value.keys()) if isinstance(self._value, dict) else self._value,
            expected=key,
        )

    def to_have_keys(self, keys: list[str]) -> Expectation[T]:
        """Assert dict has all keys."""
        missing = [k for k in keys if k not in self._value]
        return self._assert(
            len(missing) == 0,
            f"to have keys {keys!r}",
            actual=f"missing keys: {missing}" if missing else list(self._value.keys()),
            expected=keys,
        )

    def to_have_property(self, name: str) -> Expectation[T]:
        """Assert object has property."""
        return self._assert(
            hasattr(self._value, name),
            f"to have property {name!r}",
            actual=dir(self._value),
            expected=name,
        )

    def to_be_instance_of(self, cls: type) -> Expectation[T]:
        """Assert value is instance of class."""
        return self._assert(
            isinstance(self._value, cls),
            f"to be instance of {cls.__name__}",
            actual=type(self._value).__name__,
            expected=cls.__name__,
        )


class ResponseExpectation(Expectation):
    """Fluent assertion wrapper for HTTP responses."""

    def to_have_status(self, expected: int) -> ResponseExpectation:
        """Assert response has expected status code."""
        actual = getattr(self._value, "status_code", None)
        return self._assert(
            actual == expected,
            f"to have status code {expected}",
            actual=actual,
            expected=expected,
        )

    def to_have_status_in(self, codes: list[int]) -> ResponseExpectation:
        """Assert response status is in list of codes."""
        actual = getattr(self._value, "status_code", None)
        return self._assert(
            actual in codes,
            f"to have status code in {codes}",
            actual=actual,
            expected=codes,
        )

    def to_be_ok(self) -> ResponseExpectation:
        """Assert response status is 2xx."""
        actual = getattr(self._value, "status_code", 0)
        return self._assert(
            200 <= actual < 300,
            "to be OK (2xx status)",
            actual=actual,
            expected="2xx",
        )

    def to_be_client_error(self) -> ResponseExpectation:
        """Assert response status is 4xx."""
        actual = getattr(self._value, "status_code", 0)
        return self._assert(
            400 <= actual < 500,
            "to be client error (4xx status)",
            actual=actual,
            expected="4xx",
        )

    def to_be_server_error(self) -> ResponseExpectation:
        """Assert response status is 5xx."""
        actual = getattr(self._value, "status_code", 0)
        return self._assert(
            500 <= actual < 600,
            "to be server error (5xx status)",
            actual=actual,
            expected="5xx",
        )

    def to_have_header(self, name: str) -> ResponseExpectation:
        """Assert response has header."""
        headers = getattr(self._value, "headers", {})
        return self._assert(
            name in headers,
            f"to have header {name!r}",
            actual=list(headers.keys()),
            expected=name,
        )

    def to_have_header_value(self, name: str, value: str) -> ResponseExpectation:
        """Assert response header has specific value."""
        headers = getattr(self._value, "headers", {})
        actual = headers.get(name)
        return self._assert(
            actual == value,
            f"to have header {name!r} with value {value!r}",
            actual=actual,
            expected=value,
        )

    def to_have_content_type(self, content_type: str) -> ResponseExpectation:
        """Assert response has content-type header."""
        headers = getattr(self._value, "headers", {})
        actual = headers.get("content-type", "")
        return self._assert(
            content_type in actual,
            f"to have content-type {content_type!r}",
            actual=actual,
            expected=content_type,
        )

    def to_be_json(self) -> ResponseExpectation:
        """Assert response is JSON."""
        headers = getattr(self._value, "headers", {})
        content_type = headers.get("content-type", "")
        return self._assert(
            "application/json" in content_type,
            "to be JSON",
            actual=content_type,
            expected="application/json",
        )

    def to_have_json_path(self, path: str) -> ResponseExpectation:
        """Assert response body has JSONPath."""
        try:
            body = self._value.json() if callable(getattr(self._value, "json", None)) else {}
            value = self._resolve_json_path(body, path)
            return self._assert(
                value is not None,
                f"to have JSON path {path!r}",
                actual=body,
                expected=path,
            )
        except Exception:
            return self._assert(
                False,
                f"to have JSON path {path!r}",
                actual="failed to parse JSON",
                expected=path,
            )

    def to_have_json_value(self, path: str, expected: Any) -> ResponseExpectation:
        """Assert JSONPath has expected value."""
        try:
            body = self._value.json() if callable(getattr(self._value, "json", None)) else {}
            value = self._resolve_json_path(body, path)
            return self._assert(
                value == expected,
                f"to have JSON path {path!r} equal to {expected!r}",
                actual=value,
                expected=expected,
            )
        except Exception:
            return self._assert(
                False,
                f"to have JSON path {path!r} equal to {expected!r}",
                actual="failed to parse JSON",
                expected=expected,
            )

    def to_have_response_time_under(self, max_ms: float) -> ResponseExpectation:
        """Assert response time is under threshold."""
        elapsed = getattr(self._value, "elapsed", None)
        if elapsed is not None:
            actual_ms = elapsed.total_seconds() * 1000
        else:
            actual_ms = 0
        return self._assert(
            actual_ms < max_ms,
            f"to have response time under {max_ms}ms",
            actual=f"{actual_ms:.2f}ms",
            expected=f"< {max_ms}ms",
        )

    def _resolve_json_path(self, data: Any, path: str) -> Any:
        """Simple JSONPath resolution (supports $.field.nested syntax)."""
        if not path.startswith("$"):
            return None

        parts = path[1:].split(".")
        if parts[0] == "":
            parts = parts[1:]

        current = data
        for part in parts:
            if isinstance(current, dict) and part in current:
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


def expect(value: T, description: str = "value") -> Expectation[T]:
    """Create a fluent assertion for a value.

    Args:
        value: The value to assert on.
        description: Optional description for error messages.

    Returns:
        Expectation wrapper for chainable assertions.

    Example:
        >>> expect(42).to_equal(42)
        >>> expect("hello").to_contain("ell")
        >>> expect([1, 2, 3]).to_have_length(3)
    """
    if hasattr(value, "status_code"):
        return ResponseExpectation(value, description)
    return Expectation(value, description)


def expect_response(response: Any, description: str = "response") -> ResponseExpectation:
    """Create a fluent assertion for an HTTP response.

    Args:
        response: HTTP response object.
        description: Optional description for error messages.

    Returns:
        ResponseExpectation wrapper for HTTP-specific assertions.

    Example:
        >>> expect_response(response).to_have_status(200)
        >>> expect_response(response).to_be_json()
    """
    return ResponseExpectation(response, description)
