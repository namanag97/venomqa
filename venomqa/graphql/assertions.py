"""GraphQL-specific assertions for VenomQA.

Provides fluent and functional assertions for GraphQL responses, including
error checking, data path validation, and type assertions.

Example:
    >>> from venomqa.graphql import expect_graphql
    >>>
    >>> response = client.query("{ users { id name } }")
    >>> expect_graphql(response).to_have_no_errors()
    >>> expect_graphql(response).to_have_data_at("users[0].id")
    >>> expect_graphql(response).to_have_data_equal("users[0].name", "Alice")
"""

from __future__ import annotations

import re
from typing import Any, TypeVar

from venomqa.http.graphql import GraphQLError, GraphQLResponse

T = TypeVar("T")


class GraphQLAssertionError(Exception):
    """Raised when a GraphQL assertion fails.

    Attributes:
        message: The error message.
        actual: The actual value.
        expected: The expected value.
        path: The data path if applicable.
    """

    def __init__(
        self,
        message: str,
        actual: Any = None,
        expected: Any = None,
        path: str | None = None,
    ):
        self.message = message
        self.actual = actual
        self.expected = expected
        self.path = path
        super().__init__(message)


class GraphQLExpectation:
    """Fluent assertion wrapper for GraphQL responses.

    Provides chainable assertions for validating GraphQL response
    structure, data, and errors.

    Example:
        >>> expect_graphql(response) \\
        ...     .to_have_no_errors() \\
        ...     .to_have_data_at("products.edges") \\
        ...     .to_have_data_length("products.edges", 10)
    """

    def __init__(self, response: GraphQLResponse, description: str = "GraphQL response"):
        """Initialize GraphQL expectation.

        Args:
            response: The GraphQL response to assert on.
            description: Description for error messages.
        """
        self._response = response
        self._description = description
        self._negated = False

    @property
    def not_(self) -> GraphQLExpectation:
        """Negate the following assertion.

        Returns:
            Self for chaining.
        """
        self._negated = not self._negated
        return self

    def _assert(
        self,
        condition: bool,
        message: str,
        actual: Any = None,
        expected: Any = None,
        path: str | None = None,
    ) -> GraphQLExpectation:
        """Execute assertion with negation support.

        Args:
            condition: The condition to check.
            message: Error message if assertion fails.
            actual: The actual value.
            expected: The expected value.
            path: The data path if applicable.

        Returns:
            Self for chaining.

        Raises:
            GraphQLAssertionError: If assertion fails.
        """
        if self._negated:
            condition = not condition
            message = f"NOT {message}"
            self._negated = False

        if not condition:
            raise GraphQLAssertionError(
                f"Assertion failed: {self._description} {message}",
                actual=actual,
                expected=expected,
                path=path,
            )
        return self

    def to_have_no_errors(self) -> GraphQLExpectation:
        """Assert that the response has no GraphQL errors.

        Returns:
            Self for chaining.

        Raises:
            GraphQLAssertionError: If response has errors.
        """
        errors = self._response.errors
        error_messages = [str(e) for e in errors] if errors else []

        return self._assert(
            len(errors) == 0,
            "to have no errors",
            actual=error_messages if errors else "no errors",
            expected="no errors",
        )

    def to_have_errors(self) -> GraphQLExpectation:
        """Assert that the response has GraphQL errors.

        Returns:
            Self for chaining.

        Raises:
            GraphQLAssertionError: If response has no errors.
        """
        return self._assert(
            len(self._response.errors) > 0,
            "to have errors",
            actual="no errors" if not self._response.errors else self._response.errors,
            expected="errors",
        )

    def to_have_error_count(self, count: int) -> GraphQLExpectation:
        """Assert that the response has a specific number of errors.

        Args:
            count: Expected error count.

        Returns:
            Self for chaining.
        """
        actual_count = len(self._response.errors)
        return self._assert(
            actual_count == count,
            f"to have {count} error(s)",
            actual=actual_count,
            expected=count,
        )

    def to_have_error_containing(self, substring: str) -> GraphQLExpectation:
        """Assert that at least one error contains the given substring.

        Args:
            substring: Substring to search for in error messages.

        Returns:
            Self for chaining.
        """
        error_messages = [str(e) for e in self._response.errors]
        has_match = any(substring in msg for msg in error_messages)

        return self._assert(
            has_match,
            f"to have error containing '{substring}'",
            actual=error_messages,
            expected=substring,
        )

    def to_have_error_matching(self, pattern: str) -> GraphQLExpectation:
        """Assert that at least one error matches the given regex pattern.

        Args:
            pattern: Regex pattern to match against error messages.

        Returns:
            Self for chaining.
        """
        regex = re.compile(pattern)
        error_messages = [str(e) for e in self._response.errors]
        has_match = any(regex.search(msg) for msg in error_messages)

        return self._assert(
            has_match,
            f"to have error matching pattern '{pattern}'",
            actual=error_messages,
            expected=pattern,
        )

    def to_have_error_code(self, code: str) -> GraphQLExpectation:
        """Assert that at least one error has the given error code.

        Args:
            code: Error code to search for in error extensions.

        Returns:
            Self for chaining.
        """
        codes = []
        for error in self._response.errors:
            if error.extensions and "code" in error.extensions:
                codes.append(error.extensions["code"])

        has_code = code in codes

        return self._assert(
            has_code,
            f"to have error with code '{code}'",
            actual=codes,
            expected=code,
        )

    def to_have_data(self) -> GraphQLExpectation:
        """Assert that the response has data (not None).

        Returns:
            Self for chaining.
        """
        return self._assert(
            self._response.data is not None,
            "to have data",
            actual=self._response.data,
            expected="data",
        )

    def to_have_data_at(self, path: str) -> GraphQLExpectation:
        """Assert that data exists at the given path.

        Supports dot notation and array index notation:
        - "users.name" - nested object access
        - "users[0].name" - array access
        - "products.edges[0].node.id" - mixed access

        Args:
            path: Dot/bracket notation path to the data.

        Returns:
            Self for chaining.
        """
        value = self._resolve_path(self._response.data, path)
        return self._assert(
            value is not None,
            f"to have data at path '{path}'",
            actual=self._response.data,
            expected=f"value at {path}",
            path=path,
        )

    def to_have_data_equal(self, path: str, expected: Any) -> GraphQLExpectation:
        """Assert that data at the given path equals the expected value.

        Args:
            path: Dot/bracket notation path to the data.
            expected: Expected value at the path.

        Returns:
            Self for chaining.
        """
        value = self._resolve_path(self._response.data, path)
        return self._assert(
            value == expected,
            f"to have data at '{path}' equal to {expected!r}",
            actual=value,
            expected=expected,
            path=path,
        )

    def to_have_data_containing(self, path: str, item: Any) -> GraphQLExpectation:
        """Assert that data at the given path contains the item.

        Args:
            path: Dot/bracket notation path to the data (should be a list or string).
            item: Item to search for.

        Returns:
            Self for chaining.
        """
        value = self._resolve_path(self._response.data, path)
        try:
            contains = item in value if value is not None else False
        except TypeError:
            contains = False

        return self._assert(
            contains,
            f"to have data at '{path}' containing {item!r}",
            actual=value,
            expected=item,
            path=path,
        )

    def to_have_data_length(self, path: str, length: int) -> GraphQLExpectation:
        """Assert that data at the given path has the specified length.

        Args:
            path: Dot/bracket notation path to the data.
            length: Expected length.

        Returns:
            Self for chaining.
        """
        value = self._resolve_path(self._response.data, path)
        try:
            actual_length = len(value) if value is not None else 0
        except TypeError:
            actual_length = 0

        return self._assert(
            actual_length == length,
            f"to have data at '{path}' with length {length}",
            actual=actual_length,
            expected=length,
            path=path,
        )

    def to_have_data_type(self, path: str, expected_type: type) -> GraphQLExpectation:
        """Assert that data at the given path is of the expected type.

        Args:
            path: Dot/bracket notation path to the data.
            expected_type: Expected type.

        Returns:
            Self for chaining.
        """
        value = self._resolve_path(self._response.data, path)
        is_type = isinstance(value, expected_type)

        return self._assert(
            is_type,
            f"to have data at '{path}' of type {expected_type.__name__}",
            actual=type(value).__name__ if value is not None else "None",
            expected=expected_type.__name__,
            path=path,
        )

    def to_have_data_matching(self, path: str, pattern: str) -> GraphQLExpectation:
        """Assert that string data at the given path matches the regex pattern.

        Args:
            path: Dot/bracket notation path to the data.
            pattern: Regex pattern to match.

        Returns:
            Self for chaining.
        """
        value = self._resolve_path(self._response.data, path)
        if not isinstance(value, str):
            return self._assert(
                False,
                f"to have string data at '{path}' matching pattern '{pattern}'",
                actual=type(value).__name__ if value is not None else "None",
                expected=f"string matching {pattern}",
                path=path,
            )

        matches = re.search(pattern, value) is not None
        return self._assert(
            matches,
            f"to have data at '{path}' matching pattern '{pattern}'",
            actual=value,
            expected=pattern,
            path=path,
        )

    def to_have_status_code(self, status_code: int) -> GraphQLExpectation:
        """Assert that the response has the expected HTTP status code.

        Args:
            status_code: Expected status code.

        Returns:
            Self for chaining.
        """
        return self._assert(
            self._response.status_code == status_code,
            f"to have status code {status_code}",
            actual=self._response.status_code,
            expected=status_code,
        )

    def to_be_successful(self) -> GraphQLExpectation:
        """Assert that the response is successful (no errors and has data).

        Returns:
            Self for chaining.
        """
        is_successful = self._response.successful
        return self._assert(
            is_successful,
            "to be successful (no errors and has data)",
            actual={
                "has_errors": self._response.has_errors,
                "has_data": self._response.data is not None,
            },
            expected="successful response",
        )

    def to_have_response_time_under(self, max_ms: float) -> GraphQLExpectation:
        """Assert that the response time is under the threshold.

        Args:
            max_ms: Maximum response time in milliseconds.

        Returns:
            Self for chaining.
        """
        return self._assert(
            self._response.duration_ms < max_ms,
            f"to have response time under {max_ms}ms",
            actual=f"{self._response.duration_ms:.2f}ms",
            expected=f"< {max_ms}ms",
        )

    def to_have_extension(self, key: str) -> GraphQLExpectation:
        """Assert that the response has the given extension key.

        Args:
            key: Extension key to check for.

        Returns:
            Self for chaining.
        """
        extensions = self._response.extensions or {}
        has_key = key in extensions

        return self._assert(
            has_key,
            f"to have extension '{key}'",
            actual=list(extensions.keys()),
            expected=key,
        )

    def to_have_extension_value(self, key: str, value: Any) -> GraphQLExpectation:
        """Assert that the response has the given extension key with the value.

        Args:
            key: Extension key.
            value: Expected value.

        Returns:
            Self for chaining.
        """
        extensions = self._response.extensions or {}
        actual_value = extensions.get(key)

        return self._assert(
            actual_value == value,
            f"to have extension '{key}' with value {value!r}",
            actual=actual_value,
            expected=value,
        )

    def _resolve_path(self, data: Any, path: str) -> Any:
        """Resolve a dot/bracket notation path to a value.

        Args:
            data: The data to traverse.
            path: The path string (e.g., "users[0].name").

        Returns:
            The value at the path, or None if not found.
        """
        if data is None:
            return None

        # Parse path into segments
        segments = self._parse_path(path)
        current = data

        for segment in segments:
            if current is None:
                return None

            if isinstance(segment, int):
                # Array index access
                if isinstance(current, list) and 0 <= segment < len(current):
                    current = current[segment]
                else:
                    return None
            elif isinstance(current, dict):
                current = current.get(segment)
            else:
                return None

        return current

    def _parse_path(self, path: str) -> list[str | int]:
        """Parse a path string into segments.

        Args:
            path: The path string (e.g., "users[0].name").

        Returns:
            List of path segments (strings for keys, ints for indices).
        """
        segments: list[str | int] = []
        current = ""
        i = 0

        while i < len(path):
            char = path[i]

            if char == ".":
                if current:
                    segments.append(current)
                    current = ""
                i += 1
            elif char == "[":
                if current:
                    segments.append(current)
                    current = ""
                # Find closing bracket
                end = path.index("]", i)
                index_str = path[i + 1 : end]
                segments.append(int(index_str))
                i = end + 1
            else:
                current += char
                i += 1

        if current:
            segments.append(current)

        return segments


def expect_graphql(
    response: GraphQLResponse,
    description: str = "GraphQL response",
) -> GraphQLExpectation:
    """Create a fluent assertion for a GraphQL response.

    Args:
        response: The GraphQL response to assert on.
        description: Optional description for error messages.

    Returns:
        GraphQLExpectation wrapper for chainable assertions.

    Example:
        >>> expect_graphql(response).to_have_no_errors()
        >>> expect_graphql(response).to_have_data_at("users[0].id")
    """
    return GraphQLExpectation(response, description)


# Functional assertion API


def assert_graphql_no_errors(
    response: GraphQLResponse,
    message: str | None = None,
) -> None:
    """Assert that a GraphQL response has no errors.

    Args:
        response: The GraphQL response to check.
        message: Optional custom error message.

    Raises:
        GraphQLAssertionError: If response has errors.
    """
    if response.has_errors:
        error_details = [str(e) for e in response.errors]
        raise GraphQLAssertionError(
            message or f"Expected no errors, but got: {error_details}",
            actual=error_details,
            expected="no errors",
        )


def assert_graphql_data_at(
    response: GraphQLResponse,
    path: str,
    message: str | None = None,
) -> Any:
    """Assert that data exists at the given path and return it.

    Args:
        response: The GraphQL response.
        path: Dot/bracket notation path to the data.
        message: Optional custom error message.

    Returns:
        The value at the path.

    Raises:
        GraphQLAssertionError: If path doesn't exist.
    """
    expectation = GraphQLExpectation(response)
    value = expectation._resolve_path(response.data, path)

    if value is None:
        raise GraphQLAssertionError(
            message or f"Expected data at path '{path}', but got None",
            actual=response.data,
            expected=f"value at {path}",
            path=path,
        )

    return value


def assert_graphql_error_contains(
    response: GraphQLResponse,
    substring: str,
    message: str | None = None,
) -> None:
    """Assert that at least one error contains the given substring.

    Args:
        response: The GraphQL response.
        substring: Substring to search for in error messages.
        message: Optional custom error message.

    Raises:
        GraphQLAssertionError: If no error contains the substring.
    """
    error_messages = [str(e) for e in response.errors]
    has_match = any(substring in msg for msg in error_messages)

    if not has_match:
        raise GraphQLAssertionError(
            message or f"Expected error containing '{substring}', but got: {error_messages}",
            actual=error_messages,
            expected=substring,
        )
