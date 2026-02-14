"""Mock Verification for VenomQA.

This module provides utilities for verifying mock interactions:
- Assert mock was called
- Assert call count
- Assert call parameters
- Assert mock was not called

Example:
    >>> from venomqa.mocking import MockManager, verify_called, verify_call_count
    >>>
    >>> mocks = MockManager()
    >>> # ... run test ...
    >>>
    >>> # Verify interactions
    >>> verify_called(mocks.stripe, "payment_intents.create")
    >>> verify_call_count(mocks.stripe, "payment_intents.create", times=2)
    >>> verify_call_params(mocks.stripe, "payment_intents.create", {"amount": 2000})
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from venomqa.mocking.http import HTTPMock
    from venomqa.mocking.services import ServiceMock


class VerificationError(AssertionError):
    """Raised when mock verification fails."""

    def __init__(
        self,
        message: str,
        expected: Any = None,
        actual: Any = None,
        calls: list[Any] | None = None,
    ) -> None:
        self.expected = expected
        self.actual = actual
        self.calls = calls or []
        super().__init__(message)


@dataclass
class CallRecord:
    """Record of a mock call for verification.

    Attributes:
        operation: Operation or endpoint that was called
        timestamp: When the call was made
        params: Parameters passed to the call
        response: Response returned
        success: Whether the call succeeded
        error: Error message if call failed
    """

    operation: str
    timestamp: datetime = field(default_factory=datetime.now)
    params: dict[str, Any] = field(default_factory=dict)
    response: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str | None = None


class MockVerifier:
    """Verifier for mock interactions.

    Provides fluent API for verifying mock calls.

    Example:
        >>> verifier = MockVerifier(mocks.stripe)
        >>> verifier.operation("payment_intents.create").was_called().with_params(amount=2000)
        >>> verifier.operation("refunds.create").was_not_called()
    """

    def __init__(self, mock: ServiceMock | HTTPMock) -> None:
        """Initialize verifier.

        Args:
            mock: Mock to verify
        """
        self._mock = mock
        self._operation: str | None = None
        self._method: str | None = None
        self._path: str | None = None

    def operation(self, operation: str) -> MockVerifier:
        """Set operation to verify (for ServiceMock).

        Args:
            operation: Operation name

        Returns:
            Self for chaining
        """
        self._operation = operation
        return self

    def endpoint(self, method: str, path: str) -> MockVerifier:
        """Set endpoint to verify (for HTTPMock).

        Args:
            method: HTTP method
            path: URL path

        Returns:
            Self for chaining
        """
        self._method = method
        self._path = path
        return self

    def was_called(self, times: int | None = None) -> MockVerifier:
        """Verify the mock was called.

        Args:
            times: Optional exact number of expected calls

        Returns:
            Self for chaining

        Raises:
            VerificationError: If verification fails
        """
        if self._operation:
            count = self._mock.call_count(self._operation)
            if times is not None:
                if count != times:
                    raise VerificationError(
                        f"Expected {self._operation} to be called {times} times, "
                        f"but was called {count} times",
                        expected=times,
                        actual=count,
                    )
            elif count == 0:
                raise VerificationError(
                    f"Expected {self._operation} to be called, but was not called"
                )
        elif self._method and self._path:
            count = self._mock.call_count(self._method, self._path)
            if times is not None:
                if count != times:
                    raise VerificationError(
                        f"Expected {self._method} {self._path} to be called {times} times, "
                        f"but was called {count} times",
                        expected=times,
                        actual=count,
                    )
            elif count == 0:
                raise VerificationError(
                    f"Expected {self._method} {self._path} to be called, but was not called"
                )
        else:
            raise VerificationError("No operation or endpoint specified for verification")

        return self

    def was_not_called(self) -> MockVerifier:
        """Verify the mock was not called.

        Returns:
            Self for chaining

        Raises:
            VerificationError: If mock was called
        """
        if self._operation:
            count = self._mock.call_count(self._operation)
            if count > 0:
                calls = self._mock.get_calls(self._operation)
                raise VerificationError(
                    f"Expected {self._operation} to not be called, "
                    f"but was called {count} times",
                    expected=0,
                    actual=count,
                    calls=calls,
                )
        elif self._method and self._path:
            count = self._mock.call_count(self._method, self._path)
            if count > 0:
                raise VerificationError(
                    f"Expected {self._method} {self._path} to not be called, "
                    f"but was called {count} times",
                    expected=0,
                    actual=count,
                )
        else:
            raise VerificationError("No operation or endpoint specified for verification")

        return self

    def at_least(self, times: int) -> MockVerifier:
        """Verify minimum number of calls.

        Args:
            times: Minimum expected calls

        Returns:
            Self for chaining

        Raises:
            VerificationError: If too few calls
        """
        if self._operation:
            count = self._mock.call_count(self._operation)
            if count < times:
                raise VerificationError(
                    f"Expected {self._operation} to be called at least {times} times, "
                    f"but was called {count} times",
                    expected=f">= {times}",
                    actual=count,
                )
        elif self._method and self._path:
            count = self._mock.call_count(self._method, self._path)
            if count < times:
                raise VerificationError(
                    f"Expected {self._method} {self._path} to be called at least {times} times, "
                    f"but was called {count} times",
                    expected=f">= {times}",
                    actual=count,
                )
        return self

    def at_most(self, times: int) -> MockVerifier:
        """Verify maximum number of calls.

        Args:
            times: Maximum expected calls

        Returns:
            Self for chaining

        Raises:
            VerificationError: If too many calls
        """
        if self._operation:
            count = self._mock.call_count(self._operation)
            if count > times:
                raise VerificationError(
                    f"Expected {self._operation} to be called at most {times} times, "
                    f"but was called {count} times",
                    expected=f"<= {times}",
                    actual=count,
                )
        elif self._method and self._path:
            count = self._mock.call_count(self._method, self._path)
            if count > times:
                raise VerificationError(
                    f"Expected {self._method} {self._path} to be called at most {times} times, "
                    f"but was called {count} times",
                    expected=f"<= {times}",
                    actual=count,
                )
        return self

    def with_params(self, **params: Any) -> MockVerifier:
        """Verify call was made with specific parameters.

        Args:
            **params: Expected parameters

        Returns:
            Self for chaining

        Raises:
            VerificationError: If parameters don't match
        """
        if self._operation:
            calls = self._mock.get_calls(self._operation)
            if not calls:
                raise VerificationError(
                    f"Expected {self._operation} to be called with {params}, "
                    "but was not called"
                )

            # Check if any call matches
            for call in calls:
                call_params = call.params if hasattr(call, "params") else call.get("params", {})
                if all(call_params.get(k) == v for k, v in params.items()):
                    return self

            last_call = calls[-1]
            last_params = last_call.params if hasattr(last_call, "params") else last_call.get("params", {})
            raise VerificationError(
                f"Expected {self._operation} to be called with {params}, "
                f"but last call had params: {last_params}",
                expected=params,
                actual=last_params,
                calls=calls,
            )

        elif self._method and self._path:
            calls = self._mock.get_calls(self._method, self._path)
            if not calls:
                raise VerificationError(
                    f"Expected {self._method} {self._path} to be called with {params}, "
                    "but was not called"
                )

            # Check last call body
            last_call = calls[-1]
            import json

            try:
                body = json.loads(last_call.get("body", "{}"))
            except (json.JSONDecodeError, AttributeError):
                body = {}

            for key, value in params.items():
                if body.get(key) != value:
                    raise VerificationError(
                        f"Expected {self._method} {self._path} to be called with {params}, "
                        f"but body was: {body}",
                        expected=params,
                        actual=body,
                    )

        return self

    def with_header(self, key: str, value: str) -> MockVerifier:
        """Verify call was made with specific header (HTTPMock only).

        Args:
            key: Header name
            value: Expected header value

        Returns:
            Self for chaining

        Raises:
            VerificationError: If header doesn't match
        """
        if not (self._method and self._path):
            raise VerificationError("with_header only works with endpoint verification")

        calls = self._mock.get_calls(self._method, self._path)
        if not calls:
            raise VerificationError(
                f"Expected {self._method} {self._path} to be called with header {key}: {value}, "
                "but was not called"
            )

        last_call = calls[-1]
        headers = last_call.get("headers", {})
        actual_value = headers.get(key.lower()) or headers.get(key)

        if actual_value != value:
            raise VerificationError(
                f"Expected header {key}: {value}, but got: {actual_value}",
                expected={key: value},
                actual=headers,
            )

        return self


def verify_called(
    mock: ServiceMock | HTTPMock,
    operation_or_method: str,
    path: str | None = None,
) -> None:
    """Verify a mock was called.

    Args:
        mock: Mock to verify
        operation_or_method: Operation name or HTTP method
        path: URL path (for HTTPMock)

    Raises:
        VerificationError: If mock was not called
    """
    verifier = MockVerifier(mock)
    if path:
        verifier.endpoint(operation_or_method, path).was_called()
    else:
        verifier.operation(operation_or_method).was_called()


def verify_not_called(
    mock: ServiceMock | HTTPMock,
    operation_or_method: str,
    path: str | None = None,
) -> None:
    """Verify a mock was not called.

    Args:
        mock: Mock to verify
        operation_or_method: Operation name or HTTP method
        path: URL path (for HTTPMock)

    Raises:
        VerificationError: If mock was called
    """
    verifier = MockVerifier(mock)
    if path:
        verifier.endpoint(operation_or_method, path).was_not_called()
    else:
        verifier.operation(operation_or_method).was_not_called()


def verify_call_count(
    mock: ServiceMock | HTTPMock,
    operation_or_method: str,
    path: str | None = None,
    *,
    times: int | None = None,
    at_least: int | None = None,
    at_most: int | None = None,
) -> None:
    """Verify mock call count.

    Args:
        mock: Mock to verify
        operation_or_method: Operation name or HTTP method
        path: URL path (for HTTPMock)
        times: Exact expected count
        at_least: Minimum expected count
        at_most: Maximum expected count

    Raises:
        VerificationError: If count doesn't match
    """
    verifier = MockVerifier(mock)
    if path:
        verifier.endpoint(operation_or_method, path)
    else:
        verifier.operation(operation_or_method)

    if times is not None:
        verifier.was_called(times=times)
    if at_least is not None:
        verifier.at_least(at_least)
    if at_most is not None:
        verifier.at_most(at_most)


def verify_call_params(
    mock: ServiceMock | HTTPMock,
    operation_or_method: str,
    params: dict[str, Any],
    path: str | None = None,
) -> None:
    """Verify mock was called with specific parameters.

    Args:
        mock: Mock to verify
        operation_or_method: Operation name or HTTP method
        params: Expected parameters
        path: URL path (for HTTPMock)

    Raises:
        VerificationError: If parameters don't match
    """
    verifier = MockVerifier(mock)
    if path:
        verifier.endpoint(operation_or_method, path).with_params(**params)
    else:
        verifier.operation(operation_or_method).with_params(**params)


class InOrderVerifier:
    """Verify mocks were called in specific order.

    Example:
        >>> verifier = InOrderVerifier()
        >>> verifier.add(mocks.stripe, "customers.create")
        >>> verifier.add(mocks.stripe, "payment_intents.create")
        >>> verifier.verify()  # Passes if called in this order
    """

    def __init__(self) -> None:
        """Initialize in-order verifier."""
        self._expected: list[tuple[ServiceMock | HTTPMock, str, str | None]] = []

    def add(
        self,
        mock: ServiceMock | HTTPMock,
        operation_or_method: str,
        path: str | None = None,
    ) -> InOrderVerifier:
        """Add expected call to sequence.

        Args:
            mock: Mock that should be called
            operation_or_method: Operation name or HTTP method
            path: URL path (for HTTPMock)

        Returns:
            Self for chaining
        """
        self._expected.append((mock, operation_or_method, path))
        return self

    def verify(self) -> None:
        """Verify calls happened in expected order.

        Raises:
            VerificationError: If order doesn't match
        """
        all_calls: list[tuple[datetime, str, ServiceMock | HTTPMock]] = []

        for mock, operation, path in self._expected:
            if path:
                calls = mock.get_calls(operation, path)
                for call in calls:
                    timestamp = datetime.fromisoformat(call["timestamp"]) if isinstance(call.get("timestamp"), str) else call.get("timestamp", datetime.now())
                    all_calls.append((timestamp, f"{operation} {path}", mock))
            else:
                calls = mock.get_calls(operation)
                for call in calls:
                    timestamp = call.timestamp if hasattr(call, "timestamp") else datetime.now()
                    all_calls.append((timestamp, operation, mock))

        # Sort by timestamp
        all_calls.sort(key=lambda x: x[0])

        # Verify order matches expected
        expected_index = 0
        for _, operation, mock in all_calls:
            if expected_index >= len(self._expected):
                break

            exp_mock, exp_operation, exp_path = self._expected[expected_index]
            exp_name = f"{exp_operation} {exp_path}" if exp_path else exp_operation

            if mock is exp_mock and operation == exp_name:
                expected_index += 1

        if expected_index < len(self._expected):
            remaining = [
                f"{op} {p}" if p else op
                for _, op, p in self._expected[expected_index:]
            ]
            raise VerificationError(
                f"Expected calls not found in order: {remaining}"
            )


def in_order() -> InOrderVerifier:
    """Create an in-order verifier.

    Example:
        >>> in_order().add(mock1, "op1").add(mock2, "op2").verify()
    """
    return InOrderVerifier()
