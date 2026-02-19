"""Example: Using VenomQA Mocking in Journey Tests.

This example demonstrates how to use external service mocking
capabilities in VenomQA journey tests.
"""

from venomqa import (
    Journey,
    Step,
    Client,
    ExecutionContext,
    # Mocking
    MockManager,
    HTTPMock,
    MockedResponse,
    verify_called,
    verify_call_count,
    verify_call_params,
)
from venomqa.mocking import ResponseSequence


# Example 1: Basic HTTP Mocking
# -----------------------------

def example_http_mocking():
    """Demonstrate basic HTTP endpoint mocking."""
    mock = HTTPMock()

    # Mock a GET endpoint
    mock.get("/api/users").returns(
        status=200,
        json={"users": [{"id": 1, "name": "John"}]}
    )

    # Mock a POST endpoint
    mock.post("/api/users").returns(
        status=201,
        json={"id": 2, "name": "Jane"}
    )

    # Mock with delay (simulate slow response)
    mock.get("/api/slow").returns(
        status=200,
        json={"data": "slow response"},
        delay_ms=2000
    )

    # Mock error response
    mock.get("/api/error").returns_error(
        status=500,
        message="Internal server error",
        code="SERVER_ERROR"
    )

    # Mock with header requirement
    mock.get("/api/protected").with_header(
        "Authorization", "Bearer valid-token"
    ).returns(
        status=200,
        json={"secret": "data"}
    )

    # Use with httpx client
    import httpx
    client = httpx.Client(transport=mock.transport())

    response = client.get("http://test.local/api/users")
    print(f"Users: {response.json()}")

    # Verify calls
    mock.assert_called("GET", "/api/users")
    print("HTTP mocking example completed!")


# Example 2: Service Mocks (Stripe, SendGrid, etc.)
# -------------------------------------------------

def example_service_mocks():
    """Demonstrate pre-built service mocks."""
    mocks = MockManager()

    # Configure Stripe mock
    mocks.stripe.set_response("payment_intents.create", {
        "id": "pi_test_123",
        "status": "succeeded",
        "amount": 5000,
        "currency": "usd"
    })

    # Simulate payment creation
    response = mocks.stripe.create_payment_intent(amount=5000, currency="usd")
    print(f"Payment intent: {response}")

    # Verify Stripe was called
    assert mocks.stripe.was_called("payment_intents.create")
    assert mocks.stripe.call_count("payment_intents.create") == 1

    # Configure SendGrid mock
    mocks.sendgrid.capture_email(
        to="user@example.com",
        subject="Welcome!",
        body="Welcome to our service!"
    )

    # Check captured emails
    emails = mocks.sendgrid.get_captured_emails(to="user@example.com")
    print(f"Captured emails: {len(emails)}")

    # Configure Twilio mock for SMS
    mocks.twilio.capture_sms(
        to="+1234567890",
        body="Your verification code is 123456"
    )

    # Check captured SMS
    messages = mocks.twilio.get_captured_messages()
    print(f"Captured SMS: {len(messages)}")

    # Configure S3 mock
    mocks.s3.put_object("my-bucket", "file.txt", b"Hello, World!")
    obj = mocks.s3.get_object("my-bucket", "file.txt")
    print(f"S3 object content: {obj['Body'].decode()}")

    print("Service mocks example completed!")


# Example 3: Simulating Errors
# ----------------------------

def example_error_simulation():
    """Demonstrate error simulation for resilience testing."""
    mocks = MockManager()

    # Simulate Stripe card declined
    mocks.stripe.simulate_card_declined()
    response = mocks.stripe.get_response("payment_intents.confirm")
    print(f"Card declined error: {response}")

    # Simulate SendGrid rate limit
    mocks.sendgrid.simulate_rate_limit()
    response = mocks.sendgrid.get_response("send")
    print(f"Rate limit error: {response}")

    # Simulate S3 access denied
    mocks.s3.simulate_access_denied()
    response = mocks.s3.get_object("bucket", "file.txt")
    print(f"S3 access denied: {response}")

    # Reset mocks
    mocks.reset_all()
    print("Error simulation example completed!")


# Example 4: Response Sequences (Retry Testing)
# ---------------------------------------------

def example_response_sequences():
    """Demonstrate response sequences for testing retry logic."""
    mock = HTTPMock()

    # Create a sequence that fails twice then succeeds
    # Useful for testing retry logic
    mock.get("/api/flaky").returns_sequence([
        MockedResponse(status=500, json_body={"error": "Temporary failure"}),
        MockedResponse(status=503, json_body={"error": "Service unavailable"}),
        MockedResponse(status=200, json_body={"success": True, "data": "finally worked"}),
    ])

    import httpx
    client = httpx.Client(transport=mock.transport())

    # First call - 500
    resp1 = client.get("http://test.local/api/flaky")
    print(f"Call 1: {resp1.status_code}")

    # Second call - 503
    resp2 = client.get("http://test.local/api/flaky")
    print(f"Call 2: {resp2.status_code}")

    # Third call - 200
    resp3 = client.get("http://test.local/api/flaky")
    print(f"Call 3: {resp3.status_code} - {resp3.json()}")

    print("Response sequences example completed!")


# Example 5: Using Mocks in Journey Steps
# ---------------------------------------

def action_with_payment(client: Client, ctx: ExecutionContext, mocks: MockManager):
    """A journey action that uses mocked payment service."""
    # Configure the mock for this specific test case
    mocks.stripe.set_response("payment_intents.create", {
        "id": "pi_journey_test",
        "status": "succeeded",
        "amount": ctx.get("order_total", 0),
    })

    # Simulate the payment (in real code, this would call Stripe)
    payment = mocks.stripe.create_payment_intent(
        amount=ctx.get("order_total", 0),
        currency="usd"
    )

    ctx["payment_id"] = payment["id"]
    return payment


def action_verify_notifications(client: Client, ctx: ExecutionContext, mocks: MockManager):
    """Verify that notifications were sent."""
    # Check that email was sent
    emails = mocks.sendgrid.get_captured_emails(subject_contains="Order Confirmation")
    assert len(emails) == 1, "Expected order confirmation email"

    # Check that SMS was sent
    messages = mocks.twilio.get_captured_messages(body_contains="Order #")
    assert len(messages) == 1, "Expected order SMS notification"

    return {"emails": len(emails), "sms": len(messages)}


def example_journey_with_mocks():
    """Demonstrate using mocks in a journey."""
    mocks = MockManager()

    # Define steps that use mocks
    def setup_order(client, ctx):
        ctx["order_total"] = 9999
        ctx["customer_email"] = "test@example.com"
        ctx["customer_phone"] = "+1234567890"
        return {"status": "order_created"}

    def process_payment(client, ctx):
        return action_with_payment(client, ctx, mocks)

    def send_confirmation_email(client, ctx):
        mocks.sendgrid.capture_email(
            to=ctx["customer_email"],
            subject="Order Confirmation #12345",
            body=f"Your order total: ${ctx['order_total'] / 100}"
        )
        return {"email_sent": True}

    def send_confirmation_sms(client, ctx):
        mocks.twilio.capture_sms(
            to=ctx["customer_phone"],
            body=f"Order #12345 confirmed! Total: ${ctx['order_total'] / 100}"
        )
        return {"sms_sent": True}

    def verify_notifications(client, ctx):
        return action_verify_notifications(client, ctx, mocks)

    # Create journey
    journey = Journey(
        name="checkout_with_notifications",
        description="Test checkout flow with mocked external services",
        steps=[
            Step(name="setup_order", action=setup_order),
            Step(name="process_payment", action=process_payment),
            Step(name="send_email", action=send_confirmation_email),
            Step(name="send_sms", action=send_confirmation_sms),
            Step(name="verify_notifications", action=verify_notifications),
        ]
    )

    print("Journey with mocks example completed!")
    return journey, mocks


# Example 6: Configuration from YAML
# ----------------------------------

def example_yaml_configuration():
    """Demonstrate loading mock configuration from YAML."""
    import tempfile
    import os

    # Create a temporary YAML config
    yaml_content = """
mocks:
  stripe:
    enabled: true
    responses:
      payment_intents.create:
        id: pi_from_config
        status: succeeded
        amount: 1000
      charges.create:
        id: ch_from_config
        paid: true
  sendgrid:
    enabled: true
    capture: true
  twilio:
    enabled: true
    capture: true
  aws_s3:
    enabled: true
"""

    # Write to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        config_path = f.name

    try:
        # Load mocks from config
        from venomqa.mocking import load_mock_config
        config = load_mock_config(config_path)
        print(f"Loaded config for services: {list(config.keys())}")

        # Create manager with config
        mocks = MockManager(config)

        # The responses are automatically configured
        mocks.configure_from_dict({
            "stripe": config["stripe"].__dict__
        })

        print("YAML configuration example completed!")
    finally:
        os.unlink(config_path)


# Example 7: Mock Verification
# ----------------------------

def example_verification():
    """Demonstrate mock verification capabilities."""
    from venomqa.mocking import MockVerifier, in_order

    mocks = MockManager()

    # Perform some operations
    mocks.stripe.create_payment_intent(amount=1000, currency="usd")
    mocks.stripe.create_payment_intent(amount=2000, currency="eur")
    mocks.sendgrid.capture_email(to="test@test.com", subject="Test", body="Body")

    # Use helper functions
    verify_called(mocks.stripe, "payment_intents.create")
    verify_call_count(mocks.stripe, "payment_intents.create", times=2)
    verify_call_params(mocks.stripe, "payment_intents.create", {"currency": "eur"})

    # Use fluent verifier
    verifier = MockVerifier(mocks.stripe)
    verifier.operation("payment_intents.create").was_called(times=2)
    verifier.operation("payment_intents.create").at_least(1)
    verifier.operation("payment_intents.create").with_params(amount=2000)

    # Verify something was NOT called
    verifier.operation("refunds.create").was_not_called()

    # Verify order of operations
    verifier = in_order()
    verifier.add(mocks.stripe, "payment_intents.create")
    verifier.add(mocks.sendgrid, "send")
    # verifier.verify()  # Would verify operations happened in this order

    print("Verification example completed!")


if __name__ == "__main__":
    print("=" * 60)
    print("VenomQA Mocking Examples")
    print("=" * 60)

    print("\n1. HTTP Mocking")
    print("-" * 40)
    example_http_mocking()

    print("\n2. Service Mocks")
    print("-" * 40)
    example_service_mocks()

    print("\n3. Error Simulation")
    print("-" * 40)
    example_error_simulation()

    print("\n4. Response Sequences")
    print("-" * 40)
    example_response_sequences()

    print("\n5. Journey with Mocks")
    print("-" * 40)
    example_journey_with_mocks()

    print("\n6. YAML Configuration")
    print("-" * 40)
    example_yaml_configuration()

    print("\n7. Verification")
    print("-" * 40)
    example_verification()

    print("\n" + "=" * 60)
    print("All examples completed successfully!")
    print("=" * 60)
