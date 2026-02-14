"""Pre-built Service Mocks for VenomQA.

This module provides ready-to-use mocks for common external services:
- Stripe (payments)
- SendGrid (email)
- Twilio (SMS)
- AWS S3 (storage)

Each service mock provides:
- Default successful responses
- Error simulation
- Request capture and verification
- Configurable responses

Example:
    >>> from venomqa.mocking import MockManager
    >>>
    >>> mocks = MockManager()
    >>>
    >>> # Configure Stripe mock
    >>> mocks.stripe.set_response("payment_intents.create", {
    ...     "id": "pi_test_123",
    ...     "status": "succeeded"
    ... })
    >>>
    >>> # Verify Stripe was called
    >>> assert mocks.stripe.was_called("payment_intents.create")
"""

from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

import yaml

from venomqa.mocking.http import HTTPMock, MockedResponse


@dataclass
class CallRecord:
    """Record of a call to a service mock."""

    operation: str
    timestamp: datetime
    params: dict[str, Any]
    response: dict[str, Any]
    success: bool = True
    error: str | None = None


@dataclass
class MockConfig:
    """Configuration for a service mock.

    Attributes:
        enabled: Whether the mock is active
        base_url: Override base URL for the service
        responses: Predefined responses for operations
        capture: Whether to capture all requests
        default_delay_ms: Default response delay
        error_rate: Probability of returning an error (0.0-1.0)
    """

    enabled: bool = True
    base_url: str | None = None
    responses: dict[str, dict[str, Any]] = field(default_factory=dict)
    capture: bool = True
    default_delay_ms: float = 0
    error_rate: float = 0.0


class ServiceMock(ABC):
    """Base class for service mocks.

    Provides common functionality for all service mocks including:
    - Response configuration
    - Call recording
    - Error simulation
    - Verification
    """

    def __init__(self, config: MockConfig | None = None) -> None:
        """Initialize service mock.

        Args:
            config: Optional configuration
        """
        self._config = config or MockConfig()
        self._responses: dict[str, dict[str, Any] | list[dict[str, Any]]] = {}
        self._call_records: list[CallRecord] = []
        self._lock = Lock()
        self._http_mock = HTTPMock()

        # Load default responses
        self._setup_default_responses()

    @property
    @abstractmethod
    def service_name(self) -> str:
        """Return the service name."""
        ...

    @abstractmethod
    def _setup_default_responses(self) -> None:
        """Setup default mock responses."""
        ...

    def set_response(
        self,
        operation: str,
        response: dict[str, Any] | list[dict[str, Any]],
    ) -> None:
        """Set response for an operation.

        Args:
            operation: Operation name (e.g., 'payment_intents.create')
            response: Response data to return
        """
        with self._lock:
            self._responses[operation] = response

    def set_error(
        self,
        operation: str,
        error_code: str,
        error_message: str,
        status: int = 400,
    ) -> None:
        """Set an error response for an operation.

        Args:
            operation: Operation name
            error_code: Error code to return
            error_message: Error message
            status: HTTP status code
        """
        self.set_response(
            operation,
            {
                "__error__": True,
                "__status__": status,
                "error": {
                    "code": error_code,
                    "message": error_message,
                },
            },
        )

    def clear_response(self, operation: str) -> None:
        """Clear custom response for an operation."""
        with self._lock:
            self._responses.pop(operation, None)

    def clear_all_responses(self) -> None:
        """Clear all custom responses."""
        with self._lock:
            self._responses.clear()

    def get_response(self, operation: str) -> dict[str, Any]:
        """Get the response for an operation."""
        with self._lock:
            response = self._responses.get(operation)
            if isinstance(response, list):
                # Return first and rotate
                if response:
                    result = response.pop(0)
                    response.append(result)
                    return result
                return {}
            return response or self._get_default_response(operation)

    def _get_default_response(self, operation: str) -> dict[str, Any]:
        """Get default response for an operation."""
        return {"success": True}

    def record_call(
        self,
        operation: str,
        params: dict[str, Any],
        response: dict[str, Any],
        success: bool = True,
        error: str | None = None,
    ) -> None:
        """Record a call to this mock."""
        if self._config.capture:
            with self._lock:
                self._call_records.append(
                    CallRecord(
                        operation=operation,
                        timestamp=datetime.now(),
                        params=params,
                        response=response,
                        success=success,
                        error=error,
                    )
                )

    def was_called(self, operation: str | None = None) -> bool:
        """Check if the mock was called.

        Args:
            operation: Optional specific operation to check

        Returns:
            True if called
        """
        with self._lock:
            if operation is None:
                return len(self._call_records) > 0
            return any(r.operation == operation for r in self._call_records)

    def call_count(self, operation: str | None = None) -> int:
        """Get number of calls.

        Args:
            operation: Optional specific operation to count

        Returns:
            Number of calls
        """
        with self._lock:
            if operation is None:
                return len(self._call_records)
            return sum(1 for r in self._call_records if r.operation == operation)

    def get_calls(self, operation: str | None = None) -> list[CallRecord]:
        """Get call records.

        Args:
            operation: Optional filter by operation

        Returns:
            List of call records
        """
        with self._lock:
            if operation is None:
                return self._call_records.copy()
            return [r for r in self._call_records if r.operation == operation]

    def get_last_call(self, operation: str | None = None) -> CallRecord | None:
        """Get the most recent call.

        Args:
            operation: Optional filter by operation

        Returns:
            Last call record or None
        """
        calls = self.get_calls(operation)
        return calls[-1] if calls else None

    def clear_calls(self) -> None:
        """Clear all recorded calls."""
        with self._lock:
            self._call_records.clear()

    def reset(self) -> None:
        """Reset mock to initial state."""
        self.clear_all_responses()
        self.clear_calls()

    def verify(
        self,
        operation: str,
        times: int | None = None,
        at_least: int | None = None,
        at_most: int | None = None,
    ) -> bool:
        """Verify operation was called expected number of times."""
        count = self.call_count(operation)

        if times is not None and count != times:
            return False
        if at_least is not None and count < at_least:
            return False
        if at_most is not None and count > at_most:
            return False

        return True

    def verify_called_with(
        self,
        operation: str,
        params: dict[str, Any],
    ) -> bool:
        """Verify operation was called with specific parameters."""
        calls = self.get_calls(operation)
        for call in calls:
            if all(call.params.get(k) == v for k, v in params.items()):
                return True
        return False

    @property
    def http_mock(self) -> HTTPMock:
        """Get the underlying HTTP mock."""
        return self._http_mock


class StripeMock(ServiceMock):
    """Mock for Stripe payment API.

    Supports common Stripe operations:
    - payment_intents.create
    - payment_intents.confirm
    - payment_intents.capture
    - customers.create
    - customers.retrieve
    - charges.create
    - refunds.create
    - subscriptions.create

    Example:
        >>> stripe = StripeMock()
        >>>
        >>> # Configure payment success
        >>> stripe.set_response("payment_intents.create", {
        ...     "id": "pi_test_123",
        ...     "status": "succeeded",
        ...     "amount": 2000,
        ...     "currency": "usd"
        ... })
        >>>
        >>> # Configure payment failure
        >>> stripe.set_error(
        ...     "payment_intents.create",
        ...     error_code="card_declined",
        ...     error_message="Your card was declined"
        ... )
    """

    @property
    def service_name(self) -> str:
        return "stripe"

    def _setup_default_responses(self) -> None:
        """Setup default Stripe responses."""
        self._default_responses = {
            "payment_intents.create": {
                "id": f"pi_{uuid.uuid4().hex[:24]}",
                "object": "payment_intent",
                "amount": 2000,
                "currency": "usd",
                "status": "requires_confirmation",
                "client_secret": f"pi_{uuid.uuid4().hex[:24]}_secret_{uuid.uuid4().hex[:24]}",
                "created": int(datetime.now().timestamp()),
                "livemode": False,
            },
            "payment_intents.confirm": {
                "id": f"pi_{uuid.uuid4().hex[:24]}",
                "object": "payment_intent",
                "status": "succeeded",
                "amount": 2000,
                "currency": "usd",
            },
            "payment_intents.capture": {
                "id": f"pi_{uuid.uuid4().hex[:24]}",
                "object": "payment_intent",
                "status": "succeeded",
                "amount_capturable": 0,
                "amount_received": 2000,
            },
            "customers.create": {
                "id": f"cus_{uuid.uuid4().hex[:14]}",
                "object": "customer",
                "email": "test@example.com",
                "created": int(datetime.now().timestamp()),
                "livemode": False,
            },
            "customers.retrieve": {
                "id": f"cus_{uuid.uuid4().hex[:14]}",
                "object": "customer",
                "email": "test@example.com",
            },
            "charges.create": {
                "id": f"ch_{uuid.uuid4().hex[:24]}",
                "object": "charge",
                "amount": 2000,
                "currency": "usd",
                "status": "succeeded",
                "paid": True,
            },
            "refunds.create": {
                "id": f"re_{uuid.uuid4().hex[:24]}",
                "object": "refund",
                "amount": 2000,
                "status": "succeeded",
                "charge": f"ch_{uuid.uuid4().hex[:24]}",
            },
            "subscriptions.create": {
                "id": f"sub_{uuid.uuid4().hex[:24]}",
                "object": "subscription",
                "status": "active",
                "current_period_start": int(datetime.now().timestamp()),
                "current_period_end": int(datetime.now().timestamp()) + 2592000,
            },
        }

    def _get_default_response(self, operation: str) -> dict[str, Any]:
        """Get default Stripe response."""
        return self._default_responses.get(operation, {"success": True})

    def create_payment_intent(
        self,
        amount: int = 2000,
        currency: str = "usd",
        status: str = "requires_confirmation",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a mock payment intent response."""
        response = {
            "id": f"pi_{uuid.uuid4().hex[:24]}",
            "object": "payment_intent",
            "amount": amount,
            "currency": currency,
            "status": status,
            "client_secret": f"pi_{uuid.uuid4().hex[:24]}_secret_{uuid.uuid4().hex[:24]}",
            "created": int(datetime.now().timestamp()),
            "livemode": False,
            **kwargs,
        }
        self.record_call("payment_intents.create", {"amount": amount, "currency": currency}, response)
        return response

    def simulate_card_declined(self) -> None:
        """Simulate a card declined error."""
        self.set_error(
            "payment_intents.confirm",
            error_code="card_declined",
            error_message="Your card was declined.",
        )

    def simulate_insufficient_funds(self) -> None:
        """Simulate insufficient funds error."""
        self.set_error(
            "payment_intents.confirm",
            error_code="insufficient_funds",
            error_message="Your card has insufficient funds.",
        )

    def simulate_expired_card(self) -> None:
        """Simulate expired card error."""
        self.set_error(
            "payment_intents.confirm",
            error_code="expired_card",
            error_message="Your card has expired.",
        )

    def simulate_processing_error(self) -> None:
        """Simulate a processing error."""
        self.set_error(
            "payment_intents.confirm",
            error_code="processing_error",
            error_message="An error occurred while processing your card.",
            status=500,
        )


class SendGridMock(ServiceMock):
    """Mock for SendGrid email API.

    Supports:
    - send (single email)
    - send_batch (multiple emails)

    Captures sent emails for verification.

    Example:
        >>> sendgrid = SendGridMock()
        >>>
        >>> # Send will be captured
        >>> # ... application sends email ...
        >>>
        >>> # Verify email was sent
        >>> assert sendgrid.was_called("send")
        >>> call = sendgrid.get_last_call("send")
        >>> assert call.params["to"] == "user@example.com"
    """

    def __init__(self, config: MockConfig | None = None) -> None:
        super().__init__(config)
        self._captured_emails: list[dict[str, Any]] = []

    @property
    def service_name(self) -> str:
        return "sendgrid"

    def _setup_default_responses(self) -> None:
        """Setup default SendGrid responses."""
        self._default_responses = {
            "send": {
                "statusCode": 202,
                "headers": {
                    "x-message-id": f"msg_{uuid.uuid4().hex}",
                },
            },
            "send_batch": {
                "statusCode": 202,
                "headers": {
                    "x-message-id": f"msg_{uuid.uuid4().hex}",
                },
            },
        }

    def _get_default_response(self, operation: str) -> dict[str, Any]:
        """Get default SendGrid response."""
        return self._default_responses.get(operation, {"statusCode": 202})

    def capture_email(
        self,
        to: str | list[str],
        subject: str,
        body: str,
        from_email: str = "noreply@example.com",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Capture a sent email."""
        email = {
            "id": str(uuid.uuid4()),
            "to": to if isinstance(to, list) else [to],
            "subject": subject,
            "body": body,
            "from": from_email,
            "timestamp": datetime.now().isoformat(),
            **kwargs,
        }
        self._captured_emails.append(email)

        response = self.get_response("send")
        self.record_call(
            "send",
            {"to": to, "subject": subject, "from": from_email},
            response,
        )
        return response

    def get_captured_emails(
        self,
        to: str | None = None,
        subject_contains: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get captured emails with optional filtering.

        Args:
            to: Filter by recipient
            subject_contains: Filter by subject substring

        Returns:
            List of captured emails
        """
        result = self._captured_emails.copy()

        if to:
            result = [e for e in result if to in e["to"]]

        if subject_contains:
            result = [e for e in result if subject_contains in e["subject"]]

        return result

    def get_last_email(self, to: str | None = None) -> dict[str, Any] | None:
        """Get the last captured email."""
        emails = self.get_captured_emails(to=to)
        return emails[-1] if emails else None

    def clear_captured_emails(self) -> None:
        """Clear captured emails."""
        self._captured_emails.clear()

    def simulate_rate_limit(self) -> None:
        """Simulate rate limit error."""
        self.set_error(
            "send",
            error_code="rate_limit",
            error_message="Too many requests",
            status=429,
        )

    def simulate_invalid_email(self) -> None:
        """Simulate invalid email address error."""
        self.set_error(
            "send",
            error_code="invalid_email",
            error_message="Invalid email address",
            status=400,
        )


class TwilioMock(ServiceMock):
    """Mock for Twilio SMS/Voice API.

    Supports:
    - messages.create (send SMS)
    - calls.create (make call)
    - verify.create (send verification code)
    - verify.check (check verification code)

    Example:
        >>> twilio = TwilioMock()
        >>>
        >>> # Configure SMS response
        >>> twilio.set_response("messages.create", {
        ...     "sid": "SM123",
        ...     "status": "delivered"
        ... })
        >>>
        >>> # Simulate SMS failure
        >>> twilio.set_error(
        ...     "messages.create",
        ...     error_code="21211",
        ...     error_message="Invalid 'To' Phone Number"
        ... )
    """

    def __init__(self, config: MockConfig | None = None) -> None:
        super().__init__(config)
        self._captured_messages: list[dict[str, Any]] = []
        self._verification_codes: dict[str, str] = {}

    @property
    def service_name(self) -> str:
        return "twilio"

    def _setup_default_responses(self) -> None:
        """Setup default Twilio responses."""
        self._default_responses = {
            "messages.create": {
                "sid": f"SM{uuid.uuid4().hex[:32]}",
                "status": "queued",
                "date_created": datetime.now().isoformat(),
                "direction": "outbound-api",
            },
            "calls.create": {
                "sid": f"CA{uuid.uuid4().hex[:32]}",
                "status": "queued",
                "direction": "outbound-api",
            },
            "verify.create": {
                "sid": f"VE{uuid.uuid4().hex[:32]}",
                "status": "pending",
                "valid": False,
            },
            "verify.check": {
                "sid": f"VE{uuid.uuid4().hex[:32]}",
                "status": "approved",
                "valid": True,
            },
        }

    def _get_default_response(self, operation: str) -> dict[str, Any]:
        """Get default Twilio response."""
        return self._default_responses.get(operation, {"success": True})

    def capture_sms(
        self,
        to: str,
        body: str,
        from_number: str = "+15555555555",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Capture a sent SMS."""
        message = {
            "sid": f"SM{uuid.uuid4().hex[:32]}",
            "to": to,
            "body": body,
            "from": from_number,
            "status": "delivered",
            "timestamp": datetime.now().isoformat(),
            **kwargs,
        }
        self._captured_messages.append(message)

        response = self.get_response("messages.create")
        self.record_call(
            "messages.create",
            {"to": to, "body": body, "from": from_number},
            response,
        )
        return response

    def get_captured_messages(
        self,
        to: str | None = None,
        body_contains: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get captured SMS messages."""
        result = self._captured_messages.copy()

        if to:
            result = [m for m in result if m["to"] == to]

        if body_contains:
            result = [m for m in result if body_contains in m["body"]]

        return result

    def set_verification_code(self, phone: str, code: str) -> None:
        """Set expected verification code for a phone number."""
        self._verification_codes[phone] = code

    def check_verification(self, phone: str, code: str) -> dict[str, Any]:
        """Check a verification code."""
        expected = self._verification_codes.get(phone)

        if expected and code == expected:
            response = {"sid": f"VE{uuid.uuid4().hex[:32]}", "status": "approved", "valid": True}
            self.record_call("verify.check", {"phone": phone, "code": code}, response, success=True)
        else:
            response = {"sid": f"VE{uuid.uuid4().hex[:32]}", "status": "pending", "valid": False}
            self.record_call("verify.check", {"phone": phone, "code": code}, response, success=False)

        return response

    def simulate_invalid_number(self) -> None:
        """Simulate invalid phone number error."""
        self.set_error(
            "messages.create",
            error_code="21211",
            error_message="Invalid 'To' Phone Number",
            status=400,
        )

    def simulate_undeliverable(self) -> None:
        """Simulate message undeliverable."""
        self.set_response(
            "messages.create",
            {
                "sid": f"SM{uuid.uuid4().hex[:32]}",
                "status": "undelivered",
                "error_code": "30003",
                "error_message": "Unreachable destination handset",
            },
        )


class AWSS3Mock(ServiceMock):
    """Mock for AWS S3 storage API.

    Supports:
    - put_object
    - get_object
    - delete_object
    - list_objects
    - head_object
    - copy_object
    - generate_presigned_url

    Example:
        >>> s3 = AWSS3Mock()
        >>>
        >>> # Store object
        >>> s3.put_object("my-bucket", "path/to/file.txt", b"content")
        >>>
        >>> # Retrieve object
        >>> content = s3.get_object("my-bucket", "path/to/file.txt")
        >>>
        >>> # Simulate access denied
        >>> s3.set_error(
        ...     "get_object",
        ...     error_code="AccessDenied",
        ...     error_message="Access Denied"
        ... )
    """

    def __init__(self, config: MockConfig | None = None) -> None:
        super().__init__(config)
        self._objects: dict[str, dict[str, bytes]] = {}
        self._object_metadata: dict[str, dict[str, dict[str, Any]]] = {}

    @property
    def service_name(self) -> str:
        return "aws_s3"

    def _setup_default_responses(self) -> None:
        """Setup default S3 responses."""
        self._default_responses = {
            "put_object": {
                "ETag": f'"{uuid.uuid4().hex}"',
                "VersionId": str(uuid.uuid4()),
            },
            "delete_object": {
                "DeleteMarker": False,
            },
            "copy_object": {
                "CopyObjectResult": {
                    "ETag": f'"{uuid.uuid4().hex}"',
                    "LastModified": datetime.now().isoformat(),
                },
            },
        }

    def _get_default_response(self, operation: str) -> dict[str, Any]:
        """Get default S3 response."""
        return self._default_responses.get(operation, {"success": True})

    def put_object(
        self,
        bucket: str,
        key: str,
        body: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Store an object."""
        if bucket not in self._objects:
            self._objects[bucket] = {}
            self._object_metadata[bucket] = {}

        self._objects[bucket][key] = body
        self._object_metadata[bucket][key] = {
            "ContentType": content_type,
            "ContentLength": len(body),
            "LastModified": datetime.now(),
            "ETag": f'"{uuid.uuid4().hex}"',
            "Metadata": metadata or {},
        }

        response = self.get_response("put_object")
        self.record_call(
            "put_object",
            {"bucket": bucket, "key": key, "size": len(body)},
            response,
        )
        return response

    def get_object(self, bucket: str, key: str) -> dict[str, Any]:
        """Retrieve an object."""
        # Check for error response
        error_response = self._responses.get("get_object")
        if error_response and error_response.get("__error__"):
            self.record_call(
                "get_object",
                {"bucket": bucket, "key": key},
                error_response,
                success=False,
            )
            return error_response

        if bucket not in self._objects or key not in self._objects[bucket]:
            error = {
                "__error__": True,
                "__status__": 404,
                "error": {"code": "NoSuchKey", "message": f"The specified key does not exist: {key}"},
            }
            self.record_call("get_object", {"bucket": bucket, "key": key}, error, success=False)
            return error

        body = self._objects[bucket][key]
        metadata = self._object_metadata[bucket][key]

        response = {
            "Body": body,
            **metadata,
        }
        self.record_call("get_object", {"bucket": bucket, "key": key}, {"size": len(body)})
        return response

    def delete_object(self, bucket: str, key: str) -> dict[str, Any]:
        """Delete an object."""
        if bucket in self._objects:
            self._objects[bucket].pop(key, None)
            if bucket in self._object_metadata:
                self._object_metadata[bucket].pop(key, None)

        response = self.get_response("delete_object")
        self.record_call("delete_object", {"bucket": bucket, "key": key}, response)
        return response

    def list_objects(
        self,
        bucket: str,
        prefix: str = "",
        max_keys: int = 1000,
    ) -> dict[str, Any]:
        """List objects in bucket."""
        if bucket not in self._objects:
            return {"Contents": [], "KeyCount": 0, "IsTruncated": False}

        contents = []
        for key, body in self._objects[bucket].items():
            if key.startswith(prefix):
                metadata = self._object_metadata[bucket].get(key, {})
                contents.append(
                    {
                        "Key": key,
                        "Size": len(body),
                        "LastModified": metadata.get("LastModified", datetime.now()),
                        "ETag": metadata.get("ETag", f'"{uuid.uuid4().hex}"'),
                    }
                )

        contents = contents[:max_keys]

        response = {
            "Contents": contents,
            "KeyCount": len(contents),
            "IsTruncated": len(self._objects[bucket]) > max_keys,
            "Prefix": prefix,
        }
        self.record_call(
            "list_objects",
            {"bucket": bucket, "prefix": prefix},
            {"count": len(contents)},
        )
        return response

    def head_object(self, bucket: str, key: str) -> dict[str, Any]:
        """Get object metadata."""
        if bucket not in self._objects or key not in self._objects[bucket]:
            error = {
                "__error__": True,
                "__status__": 404,
                "error": {"code": "NotFound", "message": "Not Found"},
            }
            return error

        metadata = self._object_metadata[bucket][key]
        self.record_call("head_object", {"bucket": bucket, "key": key}, metadata)
        return metadata

    def generate_presigned_url(
        self,
        bucket: str,
        key: str,
        operation: str = "get_object",
        expires_in: int = 3600,
    ) -> str:
        """Generate a presigned URL."""
        url = f"https://{bucket}.s3.amazonaws.com/{key}?AWSAccessKeyId=MOCK&Signature=mock&Expires={int(datetime.now().timestamp()) + expires_in}"
        self.record_call(
            "generate_presigned_url",
            {"bucket": bucket, "key": key, "operation": operation},
            {"url": url},
        )
        return url

    def clear_bucket(self, bucket: str) -> None:
        """Clear all objects from a bucket."""
        self._objects.pop(bucket, None)
        self._object_metadata.pop(bucket, None)

    def clear_all(self) -> None:
        """Clear all buckets."""
        self._objects.clear()
        self._object_metadata.clear()

    def simulate_access_denied(self, operation: str = "get_object") -> None:
        """Simulate access denied error."""
        self.set_error(
            operation,
            error_code="AccessDenied",
            error_message="Access Denied",
            status=403,
        )

    def simulate_bucket_not_found(self) -> None:
        """Simulate bucket not found error."""
        self.set_error(
            "get_object",
            error_code="NoSuchBucket",
            error_message="The specified bucket does not exist",
            status=404,
        )


class MockManager:
    """Manager for all service mocks.

    Provides a central point for configuring and accessing service mocks
    in tests. Can be configured via YAML or programmatically.

    Example:
        >>> mocks = MockManager()
        >>>
        >>> # Access service mocks
        >>> mocks.stripe.set_response("payment_intents.create", {...})
        >>> mocks.sendgrid.capture_email(to="user@example.com", ...)
        >>>
        >>> # Load from config
        >>> mocks = MockManager.from_config("venomqa.yaml")
        >>>
        >>> # Reset all mocks
        >>> mocks.reset_all()
    """

    def __init__(self, config: dict[str, MockConfig] | None = None) -> None:
        """Initialize mock manager.

        Args:
            config: Optional configuration dict by service name
        """
        self._config = config or {}
        self._stripe = StripeMock(self._config.get("stripe"))
        self._sendgrid = SendGridMock(self._config.get("sendgrid"))
        self._twilio = TwilioMock(self._config.get("twilio"))
        self._s3 = AWSS3Mock(self._config.get("aws_s3"))
        self._custom_mocks: dict[str, ServiceMock] = {}
        self._http_mock = HTTPMock()

    @classmethod
    def from_config(cls, config_path: str | Path) -> MockManager:
        """Create MockManager from YAML config file.

        Args:
            config_path: Path to YAML config file

        Returns:
            Configured MockManager
        """
        config = load_mock_config(config_path)
        return cls(config)

    @property
    def stripe(self) -> StripeMock:
        """Get Stripe mock."""
        return self._stripe

    @property
    def sendgrid(self) -> SendGridMock:
        """Get SendGrid mock."""
        return self._sendgrid

    @property
    def twilio(self) -> TwilioMock:
        """Get Twilio mock."""
        return self._twilio

    @property
    def s3(self) -> AWSS3Mock:
        """Get AWS S3 mock."""
        return self._s3

    @property
    def http(self) -> HTTPMock:
        """Get HTTP mock for custom endpoints."""
        return self._http_mock

    def register_mock(self, name: str, mock: ServiceMock) -> None:
        """Register a custom service mock.

        Args:
            name: Name for the mock
            mock: ServiceMock instance
        """
        self._custom_mocks[name] = mock

    def get_mock(self, name: str) -> ServiceMock | None:
        """Get a registered mock by name.

        Args:
            name: Mock name

        Returns:
            ServiceMock or None
        """
        builtin = {
            "stripe": self._stripe,
            "sendgrid": self._sendgrid,
            "twilio": self._twilio,
            "aws_s3": self._s3,
            "s3": self._s3,
        }
        return builtin.get(name) or self._custom_mocks.get(name)

    def reset_all(self) -> None:
        """Reset all mocks to initial state."""
        self._stripe.reset()
        self._sendgrid.reset()
        self._twilio.reset()
        self._s3.reset()
        self._http_mock.clear()

        for mock in self._custom_mocks.values():
            mock.reset()

    def clear_all_calls(self) -> None:
        """Clear call records from all mocks."""
        self._stripe.clear_calls()
        self._sendgrid.clear_calls()
        self._twilio.clear_calls()
        self._s3.clear_calls()
        self._http_mock.reset_calls()

        for mock in self._custom_mocks.values():
            mock.clear_calls()

    def get_all_calls(self) -> dict[str, list[CallRecord]]:
        """Get all call records grouped by service."""
        return {
            "stripe": self._stripe.get_calls(),
            "sendgrid": self._sendgrid.get_calls(),
            "twilio": self._twilio.get_calls(),
            "aws_s3": self._s3.get_calls(),
            **{name: mock.get_calls() for name, mock in self._custom_mocks.items()},
        }

    def configure_from_dict(self, config: dict[str, Any]) -> None:
        """Configure mocks from a dictionary.

        Expected format:
        {
            "stripe": {
                "enabled": true,
                "responses": {
                    "payment_intents.create": {"status": "succeeded"}
                }
            },
            ...
        }
        """
        for service_name, service_config in config.items():
            mock = self.get_mock(service_name)
            if mock and isinstance(service_config, dict):
                responses = service_config.get("responses", {})
                for operation, response in responses.items():
                    mock.set_response(operation, response)

    def __enter__(self) -> MockManager:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - reset all mocks."""
        self.reset_all()


def load_mock_config(config_path: str | Path) -> dict[str, MockConfig]:
    """Load mock configuration from YAML file.

    Expected format:
    ```yaml
    mocks:
      stripe:
        enabled: true
        responses:
          payment_intents.create:
            status: succeeded
            id: pi_test_123
      sendgrid:
        enabled: true
        capture: true
    ```

    Args:
        config_path: Path to YAML config file

    Returns:
        Dict of service name to MockConfig
    """
    path = Path(config_path)
    if not path.exists():
        return {}

    with open(path) as f:
        raw_config = yaml.safe_load(f)

    if not raw_config or "mocks" not in raw_config:
        return {}

    mocks_config = raw_config["mocks"]
    result: dict[str, MockConfig] = {}

    for service_name, service_config in mocks_config.items():
        if not isinstance(service_config, dict):
            continue

        result[service_name] = MockConfig(
            enabled=service_config.get("enabled", True),
            base_url=service_config.get("base_url"),
            responses=service_config.get("responses", {}),
            capture=service_config.get("capture", True),
            default_delay_ms=service_config.get("default_delay_ms", 0),
            error_rate=service_config.get("error_rate", 0.0),
        )

    return result
