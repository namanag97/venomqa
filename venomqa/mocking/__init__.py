"""External Service Mocking for VenomQA.

This module provides comprehensive mocking capabilities for external services
commonly used in web applications, including:

- HTTP endpoint mocking with predefined responses
- Pre-built service mocks (Stripe, SendGrid, Twilio, AWS S3)
- Mock verification and assertions
- WireMock integration for complex scenarios
- YAML configuration support

Example:
    >>> from venomqa.mocking import MockManager, ServiceMocks
    >>>
    >>> # Create mock manager
    >>> mocks = MockManager()
    >>>
    >>> # Use pre-built service mocks
    >>> mocks.stripe.set_response("payment_intents.create", {
    ...     "status": "succeeded",
    ...     "id": "pi_test_123"
    ... })
    >>>
    >>> # Verify mock was called
    >>> assert mocks.stripe.was_called("payment_intents.create")
    >>> assert mocks.stripe.call_count("payment_intents.create") == 1

Configuration (venomqa.yaml):
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
"""

from venomqa.mocking.http import (
    HTTPMock,
    MockedEndpoint,
    MockedResponse,
    RequestMatcher,
    ResponseSequence,
    DelayedResponse,
    ErrorResponse,
    TimeoutResponse,
)
from venomqa.mocking.services import (
    ServiceMock,
    StripeMock,
    SendGridMock,
    TwilioMock,
    AWSS3Mock,
    MockManager,
    MockConfig,
    load_mock_config,
)
from venomqa.mocking.wiremock import (
    WireMockManager,
    WireMockContainer,
    WireMockStub,
)
from venomqa.mocking.verification import (
    MockVerifier,
    CallRecord,
    VerificationError,
    verify_called,
    verify_call_count,
    verify_call_params,
    verify_not_called,
    InOrderVerifier,
    in_order,
)

__all__ = [
    # HTTP Mocking
    "HTTPMock",
    "MockedEndpoint",
    "MockedResponse",
    "RequestMatcher",
    "ResponseSequence",
    "DelayedResponse",
    "ErrorResponse",
    "TimeoutResponse",
    # Service Mocks
    "ServiceMock",
    "StripeMock",
    "SendGridMock",
    "TwilioMock",
    "AWSS3Mock",
    "MockManager",
    "MockConfig",
    "load_mock_config",
    # WireMock
    "WireMockManager",
    "WireMockContainer",
    "WireMockStub",
    # Verification
    "MockVerifier",
    "CallRecord",
    "VerificationError",
    "verify_called",
    "verify_call_count",
    "verify_call_params",
    "verify_not_called",
    "InOrderVerifier",
    "in_order",
]
