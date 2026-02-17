"""Tests for VenomQA Mocking Module.

Comprehensive tests for HTTP mocking, service mocks, and verification.
"""

from __future__ import annotations

import json
import time
from datetime import datetime

import httpx
import pytest

from venomqa.mocking import (
    AWSS3Mock,
    CallRecord,
    DelayedResponse,
    ErrorResponse,
    # HTTP Mocking
    HTTPMock,
    MockConfig,
    MockedResponse,
    MockManager,
    # Verification
    MockVerifier,
    RequestMatcher,
    ResponseSequence,
    SendGridMock,
    # Service Mocks
    ServiceMock,
    StripeMock,
    TimeoutResponse,
    TwilioMock,
    VerificationError,
    load_mock_config,
    verify_call_count,
    verify_call_params,
    verify_called,
    verify_not_called,
)
from venomqa.mocking.http import MockNotFoundError, MockTimeoutError


class TestMockedResponse:
    """Tests for MockedResponse dataclass."""

    def test_default_response(self) -> None:
        response = MockedResponse()
        assert response.status == 200
        assert response.headers == {}
        assert response.body is None
        assert response.json_body is None
        assert response.delay_ms == 0
        assert response.timeout is False

    def test_json_response(self) -> None:
        response = MockedResponse(
            status=201,
            json_body={"id": 1, "name": "Test"},
        )
        assert response.status == 201
        assert response.json_body == {"id": 1, "name": "Test"}
        assert "Content-Type" in response.headers
        assert response.headers["Content-Type"] == "application/json"

    def test_text_response(self) -> None:
        response = MockedResponse(
            text_body="Hello, World!",
        )
        assert response.headers["Content-Type"] == "text/plain"

    def test_get_body_json(self) -> None:
        response = MockedResponse(json_body={"key": "value"})
        body = response.get_body()
        assert body == b'{"key": "value"}'

    def test_get_body_text(self) -> None:
        response = MockedResponse(text_body="Hello")
        body = response.get_body()
        assert body == b"Hello"

    def test_get_body_raw(self) -> None:
        response = MockedResponse(body=b"\x00\x01\x02")
        body = response.get_body()
        assert body == b"\x00\x01\x02"

    def test_to_httpx_response(self) -> None:
        response = MockedResponse(status=200, json_body={"ok": True})
        request = httpx.Request("GET", "http://test.local/api")
        httpx_response = response.to_httpx_response(request)
        assert httpx_response.status_code == 200
        assert httpx_response.json() == {"ok": True}


class TestDelayedResponse:
    """Tests for DelayedResponse."""

    def test_delayed_response(self) -> None:
        response = DelayedResponse(delay_ms=500, status=200, json_body={"delayed": True})
        assert response.delay_ms == 500
        assert response.status == 200


class TestErrorResponse:
    """Tests for ErrorResponse."""

    def test_error_response_default(self) -> None:
        response = ErrorResponse()
        assert response.status == 500
        body = json.loads(response.get_body().decode())
        assert body["error"]["message"] == "Internal Server Error"

    def test_error_response_custom(self) -> None:
        response = ErrorResponse(
            status=400,
            error_message="Invalid request",
            error_code="INVALID_REQUEST",
        )
        assert response.status == 400
        body = json.loads(response.get_body().decode())
        assert body["error"]["message"] == "Invalid request"
        assert body["error"]["code"] == "INVALID_REQUEST"


class TestTimeoutResponse:
    """Tests for TimeoutResponse."""

    def test_timeout_response(self) -> None:
        response = TimeoutResponse(timeout_after_ms=5000)
        assert response.timeout is True
        assert response.delay_ms == 5000


class TestResponseSequence:
    """Tests for ResponseSequence."""

    def test_sequence_returns_in_order(self) -> None:
        sequence = ResponseSequence([
            MockedResponse(status=200, json_body={"count": 1}),
            MockedResponse(status=200, json_body={"count": 2}),
            MockedResponse(status=200, json_body={"count": 3}),
        ])

        resp1 = sequence.next()
        assert resp1.json_body == {"count": 1}

        resp2 = sequence.next()
        assert resp2.json_body == {"count": 2}

        resp3 = sequence.next()
        assert resp3.json_body == {"count": 3}

    def test_sequence_repeats_last(self) -> None:
        sequence = ResponseSequence([
            MockedResponse(status=500),
            MockedResponse(status=200),
        ], repeat_last=True)

        sequence.next()  # 500
        sequence.next()  # 200
        resp = sequence.next()  # Should repeat 200
        assert resp.status == 200

    def test_sequence_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            ResponseSequence([])

    def test_sequence_reset(self) -> None:
        sequence = ResponseSequence([
            MockedResponse(status=200, json_body={"first": True}),
            MockedResponse(status=200, json_body={"second": True}),
        ])

        sequence.next()
        sequence.next()
        sequence.reset()

        resp = sequence.next()
        assert resp.json_body == {"first": True}

    def test_sequence_remaining(self) -> None:
        sequence = ResponseSequence([
            MockedResponse(),
            MockedResponse(),
            MockedResponse(),
        ])

        assert sequence.remaining == 3
        sequence.next()
        assert sequence.remaining == 2


class TestRequestMatcher:
    """Tests for RequestMatcher."""

    def test_matches_method_and_path(self) -> None:
        matcher = RequestMatcher(method="GET", path="/api/users")
        request = httpx.Request("GET", "http://test.local/api/users")
        assert matcher.matches(request) is True

    def test_does_not_match_different_method(self) -> None:
        matcher = RequestMatcher(method="GET", path="/api/users")
        request = httpx.Request("POST", "http://test.local/api/users")
        assert matcher.matches(request) is False

    def test_does_not_match_different_path(self) -> None:
        matcher = RequestMatcher(method="GET", path="/api/users")
        request = httpx.Request("GET", "http://test.local/api/orders")
        assert matcher.matches(request) is False

    def test_matches_headers(self) -> None:
        matcher = RequestMatcher(
            method="GET",
            path="/api/users",
            headers={"Authorization": "Bearer token123"},
        )
        request = httpx.Request(
            "GET",
            "http://test.local/api/users",
            headers={"Authorization": "Bearer token123"},
        )
        assert matcher.matches(request) is True

    def test_matches_query_params(self) -> None:
        matcher = RequestMatcher(
            method="GET",
            path="/api/users",
            query_params={"page": "1"},
        )
        request = httpx.Request("GET", "http://test.local/api/users?page=1")
        assert matcher.matches(request) is True

    def test_matches_body_contains(self) -> None:
        matcher = RequestMatcher(
            method="POST",
            path="/api/users",
            body_contains="John",
        )
        request = httpx.Request(
            "POST",
            "http://test.local/api/users",
            content=b'{"name": "John Doe"}',
        )
        assert matcher.matches(request) is True

    def test_matches_body_json(self) -> None:
        matcher = RequestMatcher(
            method="POST",
            path="/api/users",
            body_json={"name": "John"},
        )
        request = httpx.Request(
            "POST",
            "http://test.local/api/users",
            content=b'{"name": "John", "age": 30}',
        )
        assert matcher.matches(request) is True


class TestHTTPMock:
    """Tests for HTTPMock."""

    def test_mock_get_endpoint(self) -> None:
        mock = HTTPMock()
        mock.get("/api/users").returns(
            status=200,
            json={"users": [{"id": 1, "name": "John"}]},
        )

        request = httpx.Request("GET", "http://test.local/api/users")
        response = mock.handle_request(request)

        assert response.status_code == 200
        assert response.json() == {"users": [{"id": 1, "name": "John"}]}

    def test_mock_post_endpoint(self) -> None:
        mock = HTTPMock()
        mock.post("/api/users").returns(
            status=201,
            json={"id": 1, "name": "John"},
        )

        request = httpx.Request("POST", "http://test.local/api/users")
        response = mock.handle_request(request)

        assert response.status_code == 201

    def test_mock_with_delay(self) -> None:
        mock = HTTPMock()
        mock.get("/api/slow").returns(
            status=200,
            json={"ok": True},
            delay_ms=100,
        )

        request = httpx.Request("GET", "http://test.local/api/slow")
        start = time.time()
        mock.handle_request(request)
        elapsed = time.time() - start

        assert elapsed >= 0.1

    def test_mock_error_response(self) -> None:
        mock = HTTPMock()
        mock.get("/api/error").returns_error(
            status=500,
            message="Server error",
            code="INTERNAL_ERROR",
        )

        request = httpx.Request("GET", "http://test.local/api/error")
        response = mock.handle_request(request)

        assert response.status_code == 500
        data = response.json()
        assert data["error"]["message"] == "Server error"

    def test_mock_timeout(self) -> None:
        mock = HTTPMock()
        mock.get("/api/timeout").times_out(after_ms=100)

        request = httpx.Request("GET", "http://test.local/api/timeout")
        with pytest.raises(MockTimeoutError):
            mock.handle_request(request)

    def test_mock_raises_exception(self) -> None:
        mock = HTTPMock()
        mock.get("/api/fail").raises(ValueError("Test error"))

        request = httpx.Request("GET", "http://test.local/api/fail")
        with pytest.raises(ValueError, match="Test error"):
            mock.handle_request(request)

    def test_mock_not_found(self) -> None:
        mock = HTTPMock()
        request = httpx.Request("GET", "http://test.local/api/unknown")
        with pytest.raises(MockNotFoundError):
            mock.handle_request(request)

    def test_mock_records_calls(self) -> None:
        mock = HTTPMock()
        mock.get("/api/users").returns(status=200, json={"users": []})

        request = httpx.Request("GET", "http://test.local/api/users")
        mock.handle_request(request)
        mock.handle_request(request)

        assert mock.call_count("GET", "/api/users") == 2
        assert mock.was_called("GET", "/api/users") is True

    def test_mock_verify(self) -> None:
        mock = HTTPMock()
        mock.get("/api/users").returns(status=200, json={})

        request = httpx.Request("GET", "http://test.local/api/users")
        mock.handle_request(request)
        mock.handle_request(request)

        assert mock.verify("GET", "/api/users", times=2) is True
        assert mock.verify("GET", "/api/users", at_least=1) is True
        assert mock.verify("GET", "/api/users", at_most=3) is True

    def test_mock_response_sequence(self) -> None:
        mock = HTTPMock()
        mock.get("/api/retry").returns_sequence([
            MockedResponse(status=500, json_body={"error": "Temporary"}),
            MockedResponse(status=500, json_body={"error": "Still failing"}),
            MockedResponse(status=200, json_body={"success": True}),
        ])

        request = httpx.Request("GET", "http://test.local/api/retry")

        resp1 = mock.handle_request(request)
        assert resp1.status_code == 500

        resp2 = mock.handle_request(request)
        assert resp2.status_code == 500

        resp3 = mock.handle_request(request)
        assert resp3.status_code == 200

    def test_mock_with_header_requirement(self) -> None:
        mock = HTTPMock()
        mock.get("/api/protected").with_header("Authorization", "Bearer secret").returns(
            status=200,
            json={"data": "protected"},
        )

        # Without header - should not match
        request_no_auth = httpx.Request("GET", "http://test.local/api/protected")
        with pytest.raises(MockNotFoundError):
            mock.handle_request(request_no_auth)

        # With header - should match
        request_with_auth = httpx.Request(
            "GET",
            "http://test.local/api/protected",
            headers={"Authorization": "Bearer secret"},
        )
        response = mock.handle_request(request_with_auth)
        assert response.status_code == 200

    def test_mock_with_body_matching(self) -> None:
        mock = HTTPMock()
        mock.post("/api/users").with_body_json({"name": "John"}).returns(
            status=201,
            json={"id": 1},
        )

        # Matching body
        request = httpx.Request(
            "POST",
            "http://test.local/api/users",
            content=b'{"name": "John", "email": "john@example.com"}',
        )
        response = mock.handle_request(request)
        assert response.status_code == 201

    def test_mock_transport(self) -> None:
        mock = HTTPMock()
        mock.get("/api/test").returns(status=200, json={"ok": True})

        client = httpx.Client(transport=mock.transport())
        response = client.get("http://test.local/api/test")

        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_mock_clear(self) -> None:
        mock = HTTPMock()
        mock.get("/api/users").returns(status=200, json={})

        request = httpx.Request("GET", "http://test.local/api/users")
        mock.handle_request(request)

        mock.clear()

        assert len(mock.endpoints) == 0
        with pytest.raises(MockNotFoundError):
            mock.handle_request(request)

    def test_mock_context_manager(self) -> None:
        with HTTPMock() as mock:
            mock.get("/api/test").returns(status=200, json={"ok": True})
            request = httpx.Request("GET", "http://test.local/api/test")
            mock.handle_request(request)

        # After context, mock should be cleared
        assert len(mock.endpoints) == 0


class TestStripeMock:
    """Tests for StripeMock."""

    def test_default_responses(self) -> None:
        stripe = StripeMock()
        response = stripe.get_response("payment_intents.create")
        assert "id" in response
        assert response["object"] == "payment_intent"

    def test_set_custom_response(self) -> None:
        stripe = StripeMock()
        stripe.set_response("payment_intents.create", {
            "id": "pi_custom_123",
            "status": "succeeded",
        })

        response = stripe.get_response("payment_intents.create")
        assert response["id"] == "pi_custom_123"
        assert response["status"] == "succeeded"

    def test_set_error(self) -> None:
        stripe = StripeMock()
        stripe.set_error(
            "payment_intents.create",
            error_code="card_declined",
            error_message="Your card was declined",
        )

        response = stripe.get_response("payment_intents.create")
        assert response["__error__"] is True
        assert response["error"]["code"] == "card_declined"

    def test_simulate_card_declined(self) -> None:
        stripe = StripeMock()
        stripe.simulate_card_declined()

        response = stripe.get_response("payment_intents.confirm")
        assert response["__error__"] is True
        assert response["error"]["code"] == "card_declined"

    def test_record_calls(self) -> None:
        stripe = StripeMock()
        stripe.create_payment_intent(amount=5000, currency="usd")

        assert stripe.was_called("payment_intents.create")
        assert stripe.call_count("payment_intents.create") == 1

        call = stripe.get_last_call("payment_intents.create")
        assert call is not None
        assert call.params["amount"] == 5000

    def test_verify(self) -> None:
        stripe = StripeMock()
        stripe.create_payment_intent(amount=2000)
        stripe.create_payment_intent(amount=3000)

        assert stripe.verify("payment_intents.create", times=2)
        assert stripe.verify("payment_intents.create", at_least=1)
        assert stripe.verify("payment_intents.create", at_most=5)

    def test_reset(self) -> None:
        stripe = StripeMock()
        stripe.set_response("payment_intents.create", {"custom": True})
        stripe.create_payment_intent(amount=1000)

        stripe.reset()

        assert stripe.call_count() == 0
        response = stripe.get_response("payment_intents.create")
        assert "custom" not in response


class TestSendGridMock:
    """Tests for SendGridMock."""

    def test_capture_email(self) -> None:
        sendgrid = SendGridMock()
        sendgrid.capture_email(
            to="user@example.com",
            subject="Test Subject",
            body="Test body",
        )

        assert sendgrid.was_called("send")
        emails = sendgrid.get_captured_emails()
        assert len(emails) == 1
        assert emails[0]["to"] == ["user@example.com"]
        assert emails[0]["subject"] == "Test Subject"

    def test_filter_captured_emails(self) -> None:
        sendgrid = SendGridMock()
        sendgrid.capture_email(to="user1@example.com", subject="Hello", body="Body 1")
        sendgrid.capture_email(to="user2@example.com", subject="World", body="Body 2")

        filtered = sendgrid.get_captured_emails(to="user1@example.com")
        assert len(filtered) == 1
        assert "user1@example.com" in filtered[0]["to"]

    def test_filter_by_subject(self) -> None:
        sendgrid = SendGridMock()
        sendgrid.capture_email(to="user@example.com", subject="Welcome to our service", body="Body")
        sendgrid.capture_email(to="user@example.com", subject="Password reset", body="Body")

        filtered = sendgrid.get_captured_emails(subject_contains="Welcome")
        assert len(filtered) == 1

    def test_simulate_rate_limit(self) -> None:
        sendgrid = SendGridMock()
        sendgrid.simulate_rate_limit()

        response = sendgrid.get_response("send")
        assert response["__error__"] is True
        assert response["__status__"] == 429


class TestTwilioMock:
    """Tests for TwilioMock."""

    def test_capture_sms(self) -> None:
        twilio = TwilioMock()
        twilio.capture_sms(
            to="+1234567890",
            body="Your code is 123456",
        )

        assert twilio.was_called("messages.create")
        messages = twilio.get_captured_messages()
        assert len(messages) == 1
        assert messages[0]["to"] == "+1234567890"

    def test_verification_code(self) -> None:
        twilio = TwilioMock()
        twilio.set_verification_code("+1234567890", "123456")

        # Correct code
        result = twilio.check_verification("+1234567890", "123456")
        assert result["valid"] is True

        # Wrong code
        result = twilio.check_verification("+1234567890", "000000")
        assert result["valid"] is False

    def test_simulate_invalid_number(self) -> None:
        twilio = TwilioMock()
        twilio.simulate_invalid_number()

        response = twilio.get_response("messages.create")
        assert response["__error__"] is True
        assert response["error"]["code"] == "21211"


class TestAWSS3Mock:
    """Tests for AWSS3Mock."""

    def test_put_and_get_object(self) -> None:
        s3 = AWSS3Mock()
        s3.put_object(
            bucket="my-bucket",
            key="test/file.txt",
            body=b"Hello, World!",
        )

        result = s3.get_object("my-bucket", "test/file.txt")
        assert result["Body"] == b"Hello, World!"

    def test_list_objects(self) -> None:
        s3 = AWSS3Mock()
        s3.put_object("bucket", "docs/file1.txt", b"Content 1")
        s3.put_object("bucket", "docs/file2.txt", b"Content 2")
        s3.put_object("bucket", "images/img.png", b"Image data")

        result = s3.list_objects("bucket", prefix="docs/")
        assert result["KeyCount"] == 2
        assert all(obj["Key"].startswith("docs/") for obj in result["Contents"])

    def test_delete_object(self) -> None:
        s3 = AWSS3Mock()
        s3.put_object("bucket", "file.txt", b"Content")
        s3.delete_object("bucket", "file.txt")

        result = s3.get_object("bucket", "file.txt")
        assert result["__error__"] is True

    def test_head_object(self) -> None:
        s3 = AWSS3Mock()
        s3.put_object(
            "bucket",
            "file.txt",
            b"Content",
            content_type="text/plain",
        )

        result = s3.head_object("bucket", "file.txt")
        assert result["ContentType"] == "text/plain"
        assert result["ContentLength"] == 7

    def test_presigned_url(self) -> None:
        s3 = AWSS3Mock()
        url = s3.generate_presigned_url("bucket", "file.txt")
        assert "bucket.s3.amazonaws.com" in url
        assert "file.txt" in url

    def test_simulate_access_denied(self) -> None:
        s3 = AWSS3Mock()
        s3.simulate_access_denied()

        result = s3.get_object("bucket", "file.txt")
        assert result["__error__"] is True
        assert result["error"]["code"] == "AccessDenied"


class TestMockManager:
    """Tests for MockManager."""

    def test_access_service_mocks(self) -> None:
        mocks = MockManager()
        assert isinstance(mocks.stripe, StripeMock)
        assert isinstance(mocks.sendgrid, SendGridMock)
        assert isinstance(mocks.twilio, TwilioMock)
        assert isinstance(mocks.s3, AWSS3Mock)

    def test_http_mock(self) -> None:
        mocks = MockManager()
        mocks.http.get("/api/test").returns(status=200, json={"ok": True})
        assert len(mocks.http.endpoints) == 1

    def test_reset_all(self) -> None:
        mocks = MockManager()
        mocks.stripe.create_payment_intent(amount=1000)
        mocks.sendgrid.capture_email(to="test@test.com", subject="Test", body="Body")

        mocks.reset_all()

        assert mocks.stripe.call_count() == 0
        assert mocks.sendgrid.call_count() == 0

    def test_get_all_calls(self) -> None:
        mocks = MockManager()
        mocks.stripe.create_payment_intent(amount=1000)
        mocks.stripe.create_payment_intent(amount=2000)

        all_calls = mocks.get_all_calls()
        assert "stripe" in all_calls
        assert len(all_calls["stripe"]) == 2

    def test_register_custom_mock(self) -> None:
        mocks = MockManager()

        class CustomMock(ServiceMock):
            @property
            def service_name(self) -> str:
                return "custom"

            def _setup_default_responses(self) -> None:
                pass

        custom = CustomMock()
        mocks.register_mock("custom", custom)

        assert mocks.get_mock("custom") is custom

    def test_context_manager(self) -> None:
        with MockManager() as mocks:
            mocks.stripe.create_payment_intent(amount=1000)
            assert mocks.stripe.call_count() == 1

        # After context, should be reset
        assert mocks.stripe.call_count() == 0

    def test_configure_from_dict(self) -> None:
        mocks = MockManager()
        mocks.configure_from_dict({
            "stripe": {
                "responses": {
                    "payment_intents.create": {
                        "id": "pi_configured",
                        "status": "succeeded",
                    }
                }
            }
        })

        response = mocks.stripe.get_response("payment_intents.create")
        assert response["id"] == "pi_configured"


class TestMockVerifier:
    """Tests for MockVerifier."""

    def test_verify_was_called(self) -> None:
        stripe = StripeMock()
        stripe.create_payment_intent(amount=1000)

        verifier = MockVerifier(stripe)
        verifier.operation("payment_intents.create").was_called()

    def test_verify_was_called_times(self) -> None:
        stripe = StripeMock()
        stripe.create_payment_intent(amount=1000)
        stripe.create_payment_intent(amount=2000)

        verifier = MockVerifier(stripe)
        verifier.operation("payment_intents.create").was_called(times=2)

    def test_verify_was_not_called(self) -> None:
        stripe = StripeMock()

        verifier = MockVerifier(stripe)
        verifier.operation("refunds.create").was_not_called()

    def test_verify_at_least(self) -> None:
        stripe = StripeMock()
        stripe.create_payment_intent(amount=1000)
        stripe.create_payment_intent(amount=2000)
        stripe.create_payment_intent(amount=3000)

        verifier = MockVerifier(stripe)
        verifier.operation("payment_intents.create").at_least(2)

    def test_verify_at_most(self) -> None:
        stripe = StripeMock()
        stripe.create_payment_intent(amount=1000)

        verifier = MockVerifier(stripe)
        verifier.operation("payment_intents.create").at_most(5)

    def test_verify_with_params(self) -> None:
        stripe = StripeMock()
        stripe.create_payment_intent(amount=5000, currency="usd")

        verifier = MockVerifier(stripe)
        verifier.operation("payment_intents.create").with_params(amount=5000)

    def test_verify_fails_when_not_called(self) -> None:
        stripe = StripeMock()

        verifier = MockVerifier(stripe)
        with pytest.raises(VerificationError):
            verifier.operation("payment_intents.create").was_called()

    def test_verify_fails_wrong_count(self) -> None:
        stripe = StripeMock()
        stripe.create_payment_intent(amount=1000)

        verifier = MockVerifier(stripe)
        with pytest.raises(VerificationError):
            verifier.operation("payment_intents.create").was_called(times=5)


class TestVerificationFunctions:
    """Tests for verification helper functions."""

    def test_verify_called(self) -> None:
        stripe = StripeMock()
        stripe.create_payment_intent(amount=1000)
        verify_called(stripe, "payment_intents.create")

    def test_verify_not_called(self) -> None:
        stripe = StripeMock()
        verify_not_called(stripe, "refunds.create")

    def test_verify_call_count(self) -> None:
        stripe = StripeMock()
        stripe.create_payment_intent(amount=1000)
        stripe.create_payment_intent(amount=2000)

        verify_call_count(stripe, "payment_intents.create", times=2)
        verify_call_count(stripe, "payment_intents.create", at_least=1)
        verify_call_count(stripe, "payment_intents.create", at_most=5)

    def test_verify_call_params(self) -> None:
        stripe = StripeMock()
        stripe.create_payment_intent(amount=5000, currency="eur")

        verify_call_params(stripe, "payment_intents.create", {"amount": 5000})


class TestMockConfig:
    """Tests for MockConfig."""

    def test_default_config(self) -> None:
        config = MockConfig()
        assert config.enabled is True
        assert config.capture is True
        assert config.default_delay_ms == 0
        assert config.error_rate == 0.0

    def test_custom_config(self) -> None:
        config = MockConfig(
            enabled=True,
            base_url="http://custom.api",
            responses={"operation": {"result": "custom"}},
            capture=True,
            default_delay_ms=100,
            error_rate=0.1,
        )

        assert config.base_url == "http://custom.api"
        assert config.responses["operation"]["result"] == "custom"


class TestLoadMockConfig:
    """Tests for load_mock_config function."""

    def test_load_nonexistent_file(self, tmp_path) -> None:
        config = load_mock_config(tmp_path / "nonexistent.yaml")
        assert config == {}

    def test_load_empty_file(self, tmp_path) -> None:
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")

        config = load_mock_config(config_file)
        assert config == {}

    def test_load_valid_config(self, tmp_path) -> None:
        config_file = tmp_path / "venomqa.yaml"
        config_file.write_text("""
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
""")

        config = load_mock_config(config_file)

        assert "stripe" in config
        assert config["stripe"].enabled is True
        assert "payment_intents.create" in config["stripe"].responses

        assert "sendgrid" in config
        assert config["sendgrid"].capture is True


class TestCallRecord:
    """Tests for CallRecord dataclass."""

    def test_call_record_creation(self) -> None:
        record = CallRecord(
            operation="payment_intents.create",
            params={"amount": 2000},
            response={"id": "pi_123"},
        )

        assert record.operation == "payment_intents.create"
        assert record.params["amount"] == 2000
        assert record.success is True
        assert isinstance(record.timestamp, datetime)

    def test_call_record_with_error(self) -> None:
        record = CallRecord(
            operation="payment_intents.create",
            params={},
            response={},
            success=False,
            error="Card declined",
        )

        assert record.success is False
        assert record.error == "Card declined"


class TestHTTPMockAdvanced:
    """Advanced tests for HTTPMock."""

    def test_priority_matching(self) -> None:
        mock = HTTPMock()

        # Lower priority (default)
        mock.get("/api/users").returns(status=200, json={"default": True})

        # Higher priority - should match first
        mock.get("/api/users").with_priority(10).returns(status=200, json={"priority": True})

        request = httpx.Request("GET", "http://test.local/api/users")
        response = mock.handle_request(request)

        assert response.json()["priority"] is True

    def test_assert_methods(self) -> None:
        mock = HTTPMock()
        mock.get("/api/users").returns(status=200, json={})

        request = httpx.Request("GET", "http://test.local/api/users")
        mock.handle_request(request)
        mock.handle_request(request)

        mock.assert_called("GET", "/api/users", times=2)

        with pytest.raises(AssertionError):
            mock.assert_called("GET", "/api/users", times=5)

    def test_assert_not_called(self) -> None:
        mock = HTTPMock()
        mock.get("/api/users").returns(status=200, json={})

        mock.assert_not_called("GET", "/api/users")

    def test_assert_called_with(self) -> None:
        mock = HTTPMock()
        mock.post("/api/users").returns(status=201, json={"id": 1})

        request = httpx.Request(
            "POST",
            "http://test.local/api/users",
            content=b'{"name": "John", "email": "john@test.com"}',
            headers={"Content-Type": "application/json"},
        )
        mock.handle_request(request)

        mock.assert_called_with(
            "POST",
            "/api/users",
            json_body={"name": "John"},
        )

    def test_get_unmatched_requests(self) -> None:
        mock = HTTPMock()

        try:
            request = httpx.Request("GET", "http://test.local/api/unknown")
            mock.handle_request(request)
        except MockNotFoundError:
            pass

        unmatched = mock.get_unmatched_requests()
        assert len(unmatched) == 1
        assert unmatched[0]["method"] == "GET"

    def test_remove_endpoint(self) -> None:
        mock = HTTPMock()
        endpoint = mock.get("/api/users").returns(status=200, json={})

        assert len(mock.endpoints) == 1

        result = mock.remove_endpoint(endpoint.id)
        assert result is True
        assert len(mock.endpoints) == 0

    def test_reset_calls(self) -> None:
        mock = HTTPMock()
        mock.get("/api/users").returns(status=200, json={})

        request = httpx.Request("GET", "http://test.local/api/users")
        mock.handle_request(request)

        assert mock.call_count("GET", "/api/users") == 1

        mock.reset_calls()

        assert mock.call_count("GET", "/api/users") == 0
        # Endpoints should still exist
        assert len(mock.endpoints) == 1
