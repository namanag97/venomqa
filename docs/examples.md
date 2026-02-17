# Real-World Examples

This page provides practical, real-world examples of using VenomQA.

> **Looking for basics?** See the [Getting Started Guide](getting-started/index.md) for introductory examples.

## Table of Contents

- [E-Commerce Checkout Flow](#e-commerce-checkout-flow)
- [User Registration with Email Verification](#user-registration-with-email-verification)
- [API Rate Limiting Tests](#api-rate-limiting-tests)
- [Multi-Tenant Application Testing](#multi-tenant-application-testing)
- [Payment Gateway Integration](#payment-gateway-integration)
- [File Upload and Processing](#file-upload-and-processing)
- [WebSocket and Real-Time Features](#websocket-and-real-time-features)
- [Third-Party API Mocking](#third-party-api-mocking)

## Related Documentation

| Topic | Document |
|-------|----------|
| Journey DSL | [journeys.md](concepts/journeys.md) |
| Adapters | [adapters.md](reference/adapters.md) |
| Ports | [ports.md](reference/adapters.md) |
| Advanced Patterns | [advanced.md](advanced.md) |

---

## E-Commerce Checkout Flow

Complete checkout journey testing multiple payment methods.

### Actions File

```python
# actions/shop.py

def add_to_cart(client, context, product_id=None, quantity=1):
    """Add product to shopping cart."""
    product_id = product_id or context.get("product_id")
    response = client.post("/api/cart/items", json={
        "product_id": product_id,
        "quantity": quantity,
    })
    if response.status_code == 200:
        context["cart_id"] = response.json()["cart_id"]
    return response

def get_cart(client, context):
    """Get current cart contents."""
    cart_id = context.get("cart_id")
    if cart_id:
        return client.get(f"/api/cart/{cart_id}")
    return client.get("/api/cart")

def apply_coupon(client, context, code="DISCOUNT10"):
    """Apply discount coupon to cart."""
    cart_id = context.get_required("cart_id")
    return client.post(f"/api/cart/{cart_id}/coupon", json={"code": code})

def start_checkout(client, context):
    """Begin checkout process."""
    cart_id = context.get_required("cart_id")
    response = client.post(f"/api/cart/{cart_id}/checkout")
    if response.status_code == 200:
        context["order_id"] = response.json()["order_id"]
    return response

def add_shipping_address(client, context):
    """Add shipping address to order."""
    order_id = context.get_required("order_id")
    return client.post(f"/api/orders/{order_id}/shipping", json={
        "name": "John Doe",
        "address": "123 Main St",
        "city": "New York",
        "state": "NY",
        "zip": "10001",
        "country": "USA",
    })

def pay_with_credit_card(client, context):
    """Process credit card payment."""
    order_id = context.get_required("order_id")
    return client.post(f"/api/orders/{order_id}/payment", json={
        "method": "credit_card",
        "card_number": "4242424242424242",
        "exp_month": 12,
        "exp_year": 2025,
        "cvv": "123",
    })

def pay_with_paypal(client, context):
    """Process PayPal payment."""
    order_id = context.get_required("order_id")
    return client.post(f"/api/orders/{order_id}/payment", json={
        "method": "paypal",
        "return_url": "https://example.com/return",
    })

def pay_with_crypto(client, context):
    """Process cryptocurrency payment."""
    order_id = context.get_required("order_id")
    return client.post(f"/api/orders/{order_id}/payment", json={
        "method": "crypto",
        "currency": "BTC",
    })

def confirm_order(client, context):
    """Confirm and finalize order."""
    order_id = context.get_required("order_id")
    response = client.post(f"/api/orders/{order_id}/confirm")
    if response.status_code == 200:
        context["confirmation_number"] = response.json()["confirmation_number"]
    return response
```

### Journey Definition

```python
# journeys/ecommerce_checkout.py
from venomqa import Journey, Step, Checkpoint, Branch, Path
from actions.auth import login
from actions.shop import (
    add_to_cart, get_cart, apply_coupon, start_checkout,
    add_shipping_address, pay_with_credit_card, pay_with_paypal,
    pay_with_crypto, confirm_order,
)

checkout_journey = Journey(
    name="ecommerce_checkout",
    description="Complete e-commerce checkout flow with multiple payment methods",
    tags=["e-commerce", "checkout", "payment"],
    steps=[
        Step(name="login", action=login),
        Step(name="add_item", action=lambda c, ctx: add_to_cart(c, ctx, product_id=123)),
        Step(name="verify_cart", action=get_cart),
        Step(name="apply_discount", action=apply_coupon),
        Checkpoint(name="cart_ready"),
        Step(name="start_checkout", action=start_checkout),
        Step(name="add_shipping", action=add_shipping_address),
        Checkpoint(name="ready_for_payment"),
        Branch(
            checkpoint_name="ready_for_payment",
            paths=[
                Path(name="credit_card", steps=[
                    Step(name="pay_card", action=pay_with_credit_card),
                    Step(name="confirm_card", action=confirm_order),
                ]),
                Path(name="paypal", steps=[
                    Step(name="pay_paypal", action=pay_with_paypal),
                    Step(name="confirm_paypal", action=confirm_order),
                ]),
                Path(name="crypto", steps=[
                    Step(name="pay_crypto", action=pay_with_crypto),
                    Step(name="confirm_crypto", action=confirm_order),
                ]),
            ],
        ),
    ],
)
```

---

## User Registration with Email Verification

Test complete registration flow including email verification.

### Actions

```python
# actions/user_registration.py
import time

def register_user(client, context, email=None, password=None):
    """Register a new user account."""
    email = email or context.get("email", f"test_{int(time.time())}@example.com")
    password = password or context.get("password", "SecurePass123!")
    
    response = client.post("/api/auth/register", json={
        "email": email,
        "password": password,
        "name": "Test User",
    })
    
    if response.status_code == 201:
        context["user_email"] = email
        context["user_password"] = password
        context["user_id"] = response.json()["user"]["id"]
    
    return response

def get_verification_token(client, context):
    """Get email verification token (simulating email retrieval)."""
    # In real tests, this might query a test email service
    user_id = context.get_required("user_id")
    response = client.get(f"/api/test/verification-token/{user_id}")
    
    if response.status_code == 200:
        context["verification_token"] = response.json()["token"]
    
    return response

def verify_email(client, context):
    """Verify email with token."""
    token = context.get_required("verification_token")
    return client.post("/api/auth/verify-email", json={"token": token})

def login_and_verify(client, context):
    """Login and verify account is active."""
    email = context.get_required("user_email")
    password = context.get_required("user_password")
    
    response = client.post("/api/auth/login", json={
        "email": email,
        "password": password,
    })
    
    if response.status_code == 200:
        context["auth_token"] = response.json()["token"]
        client.set_auth_token(context["auth_token"])
    
    return response

def check_account_status(client, context):
    """Verify account is verified and active."""
    return client.get("/api/auth/me")
```

### Journey

```python
# journeys/user_registration.py
from venomqa import Journey, Step, Checkpoint, Branch, Path
from actions.user_registration import (
    register_user, get_verification_token, verify_email,
    login_and_verify, check_account_status,
)

registration_journey = Journey(
    name="user_registration",
    description="Complete user registration with email verification",
    tags=["auth", "registration", "email"],
    steps=[
        Step(name="register", action=register_user),
        Checkpoint(name="user_created"),
        Step(name="get_token", action=get_verification_token),
        Checkpoint(name="token_retrieved"),
        Branch(
            checkpoint_name="token_retrieved",
            paths=[
                Path(name="valid_verification", steps=[
                    Step(name="verify_email", action=verify_email),
                    Step(name="login", action=login_and_verify),
                    Step(name="check_status", action=check_account_status),
                ]),
                Path(name="invalid_token", steps=[
                    Step(
                        name="verify_with_invalid",
                        action=lambda c, ctx: c.post("/api/auth/verify-email", json={"token": "invalid"}),
                        expect_failure=True,
                    ),
                ]),
                Path(name="expired_token", steps=[
                    Step(
                        name="verify_with_expired",
                        action=lambda c, ctx: c.post("/api/auth/verify-email", json={"token": "expired_token_123"}),
                        expect_failure=True,
                    ),
                ]),
            ],
        ),
    ],
)
```

---

## API Rate Limiting Tests

Test rate limiting behavior and error handling.

### Actions

```python
# actions/rate_limit.py
import time
from concurrent.futures import ThreadPoolExecutor

def make_request(client, context, endpoint="/api/data"):
    """Make a single API request."""
    return client.get(endpoint)

def burst_requests(client, context, count=10, endpoint="/api/data"):
    """Make multiple rapid requests."""
    results = []
    for _ in range(count):
        results.append(client.get(endpoint))
    context["burst_results"] = results
    return results[-1]

def parallel_requests(client, context, count=10, endpoint="/api/data"):
    """Make parallel requests to trigger rate limiting."""
    def make_request():
        return client.get(endpoint)
    
    with ThreadPoolExecutor(max_workers=count) as executor:
        futures = [executor.submit(make_request) for _ in range(count)]
        results = [f.result() for f in futures]
    
    context["parallel_results"] = results
    return results[-1]

def wait_and_retry(client, context):
    """Wait for rate limit to reset and retry."""
    time.sleep(60)  # Wait for rate limit window
    return client.get("/api/data")

def check_rate_limit_headers(client, context):
    """Check rate limit headers in response."""
    response = client.get("/api/data")
    
    headers = response.headers
    context["rate_limit"] = {
        "limit": headers.get("X-RateLimit-Limit"),
        "remaining": headers.get("X-RateLimit-Remaining"),
        "reset": headers.get("X-RateLimit-Reset"),
    }
    
    return response
```

### Journey

```python
# journeys/rate_limiting.py
from venomqa import Journey, Step, Checkpoint, Branch, Path
from actions.auth import login
from actions.rate_limit import (
    make_request, burst_requests, parallel_requests,
    wait_and_retry, check_rate_limit_headers,
)

rate_limit_journey = Journey(
    name="rate_limiting",
    description="Test API rate limiting behavior",
    tags=["rate-limit", "api", "reliability"],
    steps=[
        Step(name="login", action=login),
        Step(name="check_headers", action=check_rate_limit_headers),
        Checkpoint(name="initial_state"),
        Branch(
            checkpoint_name="initial_state",
            paths=[
                Path(name="sequential_burst", steps=[
                    Step(name="burst_10", action=lambda c, ctx: burst_requests(c, ctx, count=10)),
                    Step(
                        name="expect_rate_limited",
                        action=lambda c, ctx: make_request(c, ctx),
                        expect_failure=True,
                    ),
                ]),
                Path(name="parallel_burst", steps=[
                    Step(name="parallel_20", action=lambda c, ctx: parallel_requests(c, ctx, count=20)),
                    Step(
                        name="expect_blocked",
                        action=lambda c, ctx: make_request(c, ctx),
                        expect_failure=True,
                    ),
                ]),
            ],
        ),
    ],
)
```

---

## Multi-Tenant Application Testing

Test behavior across different tenants with data isolation.

### Actions

```python
# actions/multi_tenant.py

def switch_tenant(client, context, tenant_id=None):
    """Switch to a specific tenant context."""
    tenant_id = tenant_id or context.get("tenant_id")
    client.clear_auth()
    
    # Get tenant-specific auth
    response = client.post("/api/auth/tenant-login", json={
        "tenant_id": tenant_id,
        "api_key": f"key_{tenant_id}",
    })
    
    if response.status_code == 200:
        client.set_auth_token(response.json()["token"])
        context["current_tenant"] = tenant_id
    
    return response

def create_tenant_resource(client, context, name=None):
    """Create a resource in current tenant."""
    tenant = context.get("current_tenant")
    name = name or f"Resource for {tenant}"
    
    response = client.post("/api/resources", json={
        "name": name,
        "tenant_id": tenant,
    })
    
    if response.status_code == 201:
        context[f"resource_{tenant}"] = response.json()["id"]
    
    return response

def list_tenant_resources(client, context):
    """List resources for current tenant."""
    return client.get("/api/resources")

def try_cross_tenant_access(client, context, target_tenant=None, resource_id=None):
    """Attempt to access another tenant's resource."""
    target = target_tenant or context.get("other_tenant")
    resource = resource_id or context.get(f"resource_{target}")
    
    return client.get(f"/api/resources/{resource}")
```

### Journey

```python
# journeys/multi_tenant.py
from venomqa import Journey, Step, Checkpoint, Branch, Path
from actions.multi_tenant import (
    switch_tenant, create_tenant_resource, list_tenant_resources,
    try_cross_tenant_access,
)

multi_tenant_journey = Journey(
    name="multi_tenant_isolation",
    description="Test multi-tenant data isolation",
    tags=["multi-tenant", "security", "isolation"],
    steps=[
        # Setup tenant A
        Step(name="switch_tenant_a", action=lambda c, ctx: switch_tenant(c, ctx, tenant_id="tenant_a")),
        Step(name="create_resource_a", action=create_tenant_resource),
        Checkpoint(name="tenant_a_setup"),
        
        # Setup tenant B
        Step(name="switch_tenant_b", action=lambda c, ctx: switch_tenant(c, ctx, tenant_id="tenant_b")),
        Step(name="create_resource_b", action=create_tenant_resource),
        context["other_tenant"] = "tenant_a",
        Checkpoint(name="tenant_b_setup"),
        
        # Test isolation
        Branch(
            checkpoint_name="tenant_b_setup",
            paths=[
                Path(name="isolation_test", steps=[
                    # Tenant B tries to access Tenant A's resource
                    Step(
                        name="cross_tenant_access",
                        action=try_cross_tenant_access,
                        expect_failure=True,  # Should fail
                    ),
                ]),
                Path(name="list_own_resources", steps=[
                    Step(name="list_b_resources", action=list_tenant_resources),
                ]),
            ],
        ),
        
        # Switch back to A and verify
        Step(name="back_to_tenant_a", action=lambda c, ctx: switch_tenant(c, ctx, tenant_id="tenant_a")),
        Step(name="verify_a_resources", action=list_tenant_resources),
    ],
)
```

---

## Payment Gateway Integration

Test payment processing with various scenarios.

### Actions

```python
# actions/payment.py

def create_payment_intent(client, context, amount=1000, currency="usd"):
    """Create a payment intent."""
    response = client.post("/api/payments/intents", json={
        "amount": amount,
        "currency": currency,
    })
    
    if response.status_code == 201:
        context["payment_intent_id"] = response.json()["id"]
        context["payment_amount"] = amount
    
    return response

def confirm_payment(client, context, payment_method="card_success"):
    """Confirm a payment with specified method."""
    intent_id = context.get_required("payment_intent_id")
    
    response = client.post(f"/api/payments/intents/{intent_id}/confirm", json={
        "payment_method": payment_method,
    })
    
    if response.status_code == 200:
        context["payment_status"] = response.json()["status"]
    
    return response

def refund_payment(client, context, amount=None):
    """Refund a payment."""
    intent_id = context.get_required("payment_intent_id")
    amount = amount or context.get("payment_amount")
    
    return client.post(f"/api/payments/intents/{intent_id}/refund", json={
        "amount": amount,
    })

def get_payment_status(client, context):
    """Get current payment status."""
    intent_id = context.get_required("payment_intent_id")
    return client.get(f"/api/payments/intents/{intent_id}")
```

### Journey

```python
# journeys/payment_gateway.py
from venomqa import Journey, Step, Checkpoint, Branch, Path
from actions.auth import login
from actions.payment import (
    create_payment_intent, confirm_payment, refund_payment, get_payment_status,
)

payment_journey = Journey(
    name="payment_gateway",
    description="Test payment gateway integration",
    tags=["payment", "integration", "critical"],
    steps=[
        Step(name="login", action=login),
        Step(name="create_intent", action=create_payment_intent),
        Checkpoint(name="intent_created"),
        Branch(
            checkpoint_name="intent_created",
            paths=[
                Path(name="successful_payment", steps=[
                    Step(name="confirm_success", action=lambda c, ctx: confirm_payment(c, ctx, "card_success")),
                    Step(name="verify_success", action=get_payment_status),
                ]),
                Path(name="declined_payment", steps=[
                    Step(
                        name="confirm_declined",
                        action=lambda c, ctx: confirm_payment(c, ctx, "card_declined"),
                        expect_failure=True,
                    ),
                ]),
                Path(name="insufficient_funds", steps=[
                    Step(
                        name="confirm_insufficient",
                        action=lambda c, ctx: confirm_payment(c, ctx, "card_insufficient"),
                        expect_failure=True,
                    ),
                ]),
                Path(name="payment_then_refund", steps=[
                    Step(name="confirm_for_refund", action=lambda c, ctx: confirm_payment(c, ctx, "card_success")),
                    Step(name="refund_full", action=refund_payment),
                    Step(name="verify_refunded", action=get_payment_status),
                ]),
            ],
        ),
    ],
)
```

---

## File Upload and Processing

Test file upload and async processing.

### Actions

```python
# actions/file_upload.py
import io
import time

def upload_file(client, context, filename="test.csv", content=None):
    """Upload a file for processing."""
    content = content or b"id,name\n1,Test\n2,Example"
    
    files = {
        "file": (filename, io.BytesIO(content), "text/csv"),
    }
    
    response = client.post("/api/uploads", files=files)
    
    if response.status_code == 201:
        context["upload_id"] = response.json()["upload_id"]
    
    return response

def get_upload_status(client, context):
    """Get upload processing status."""
    upload_id = context.get_required("upload_id")
    return client.get(f"/api/uploads/{upload_id}")

def wait_for_processing(client, context, timeout=60):
    """Wait for upload to finish processing."""
    upload_id = context.get_required("upload_id")
    start = time.time()
    
    while time.time() - start < timeout:
        response = client.get(f"/api/uploads/{upload_id}")
        status = response.json()["status"]
        
        if status in ["completed", "failed"]:
            context["processing_status"] = status
            return response
        
        time.sleep(1)
    
    raise TimeoutError("Processing timed out")

def get_upload_results(client, context):
    """Get results of processed upload."""
    upload_id = context.get_required("upload_id")
    return client.get(f"/api/uploads/{upload_id}/results")

def upload_large_file(client, context, size_mb=10):
    """Upload a large file."""
    content = b"x" * (size_mb * 1024 * 1024)
    return upload_file(client, context, filename="large.bin", content=content)
```

### Journey

```python
# journeys/file_upload.py
from venomqa import Journey, Step, Checkpoint, Branch, Path
from actions.auth import login
from actions.file_upload import (
    upload_file, get_upload_status, wait_for_processing,
    get_upload_results, upload_large_file,
)

file_upload_journey = Journey(
    name="file_upload",
    description="Test file upload and processing",
    tags=["upload", "async", "processing"],
    timeout=120.0,
    steps=[
        Step(name="login", action=login),
        Checkpoint(name="authenticated"),
        Branch(
            checkpoint_name="authenticated",
            paths=[
                Path(name="small_csv", steps=[
                    Step(name="upload_csv", action=upload_file),
                    Step(name="wait_process", action=wait_for_processing),
                    Step(name="get_results", action=get_upload_results),
                ]),
                Path(name="invalid_format", steps=[
                    Step(
                        name="upload_invalid",
                        action=lambda c, ctx: upload_file(c, ctx, filename="test.exe", content=b"invalid"),
                        expect_failure=True,
                    ),
                ]),
                Path(name="large_file", steps=[
                    Step(name="upload_large", action=lambda c, ctx: upload_large_file(c, ctx, size_mb=50)),
                    Step(name="wait_large", action=wait_for_processing),
                ], description="Test large file handling"),
            ],
        ),
    ],
)
```

---

## WebSocket and Real-Time Features

Test WebSocket connections and real-time updates.

### Actions

```python
# actions/websocket.py
import json
import time

def subscribe_to_channel(client, context, channel="updates"):
    """Subscribe to a real-time channel via REST."""
    response = client.post("/api/realtime/subscribe", json={
        "channel": channel,
    })
    
    if response.status_code == 200:
        context["channel"] = channel
        context["subscription_id"] = response.json()["subscription_id"]
    
    return response

def trigger_event(client, context, event_type="test_event", data=None):
    """Trigger a real-time event."""
    channel = context.get("channel", "updates")
    
    return client.post("/api/realtime/events", json={
        "channel": channel,
        "event": event_type,
        "data": data or {"message": "test"},
    })

def poll_for_events(client, context, timeout=10):
    """Poll for events (simulating WebSocket)."""
    subscription_id = context.get_required("subscription_id")
    events = []
    start = time.time()
    
    while time.time() - start < timeout:
        response = client.get(f"/api/realtime/events/{subscription_id}")
        if response.status_code == 200:
            new_events = response.json().get("events", [])
            events.extend(new_events)
            
            if events:
                context["received_events"] = events
                return response
        
        time.sleep(0.5)
    
    context["received_events"] = events
    return response

def unsubscribe(client, context):
    """Unsubscribe from channel."""
    subscription_id = context.get_required("subscription_id")
    return client.delete(f"/api/realtime/subscriptions/{subscription_id}")
```

### Journey

```python
# journeys/realtime.py
from venomqa import Journey, Step, Checkpoint, Branch, Path
from actions.auth import login
from actions.websocket import (
    subscribe_to_channel, trigger_event, poll_for_events, unsubscribe,
)

realtime_journey = Journey(
    name="realtime_features",
    description="Test real-time WebSocket features",
    tags=["websocket", "realtime", "events"],
    steps=[
        Step(name="login", action=login),
        Step(name="subscribe", action=subscribe_to_channel),
        Checkpoint(name="subscribed"),
        Branch(
            checkpoint_name="subscribed",
            paths=[
                Path(name="single_event", steps=[
                    Step(name="trigger", action=trigger_event),
                    Step(name="poll", action=poll_for_events),
                ]),
                Path(name="multiple_events", steps=[
                    Step(name="trigger_1", action=lambda c, ctx: trigger_event(c, ctx, "event_1")),
                    Step(name="trigger_2", action=lambda c, ctx: trigger_event(c, ctx, "event_2")),
                    Step(name="trigger_3", action=lambda c, ctx: trigger_event(c, ctx, "event_3")),
                    Step(name="poll_multiple", action=lambda c, ctx: poll_for_events(c, ctx, timeout=15)),
                ]),
            ],
        ),
        Step(name="unsubscribe", action=unsubscribe),
    ],
)
```

---

## Third-Party API Mocking

Test with mocked third-party services.

### Actions

```python
# actions/integrations.py

def configure_stripe_mock(client, context, scenario="success"):
    """Configure Stripe mock for testing."""
    return client.post("/api/test/mock/stripe", json={
        "scenario": scenario,
    })

def configure_sendgrid_mock(client, context, scenario="success"):
    """Configure SendGrid mock for testing."""
    return client.post("/api/test/mock/sendgrid", json={
        "scenario": scenario,
    })

def verify_email_sent(client, context):
    """Verify email was sent via mock."""
    response = client.get("/api/test/mock/sendgrid/emails")
    
    if response.status_code == 200:
        emails = response.json().get("emails", [])
        if emails:
            context["last_email"] = emails[-1]
    
    return response

def verify_stripe_charge(client, context):
    """Verify Stripe charge was created."""
    response = client.get("/api/test/mock/stripe/charges")
    
    if response.status_code == 200:
        charges = response.json().get("charges", [])
        if charges:
            context["last_charge"] = charges[-1]
    
    return response
```

### Journey

```python
# journeys/third_party_mocks.py
from venomqa import Journey, Step, Checkpoint, Branch, Path
from actions.auth import login
from actions.integrations import (
    configure_stripe_mock, configure_sendgrid_mock,
    verify_email_sent, verify_stripe_charge,
)
from actions.payment import create_payment_intent, confirm_payment
from actions.user_registration import register_user

mocked_integration_journey = Journey(
    name="third_party_mocks",
    description="Test with mocked third-party services",
    tags=["mocking", "integration", "testing"],
    steps=[
        Step(name="login", action=login),
        Checkpoint(name="authenticated"),
        
        Branch(
            checkpoint_name="authenticated",
            paths=[
                Path(name="stripe_success", steps=[
                    Step(name="mock_stripe_ok", action=lambda c, ctx: configure_stripe_mock(c, ctx, "success")),
                    Step(name="create_payment", action=create_payment_intent),
                    Step(name="confirm_payment", action=lambda c, ctx: confirm_payment(c, ctx, "card_success")),
                    Step(name="verify_charge", action=verify_stripe_charge),
                ]),
                Path(name="stripe_failure", steps=[
                    Step(name="mock_stripe_fail", action=lambda c, ctx: configure_stripe_mock(c, ctx, "card_declined")),
                    Step(name="create_payment_fail", action=create_payment_intent),
                    Step(
                        name="confirm_fail",
                        action=lambda c, ctx: confirm_payment(c, ctx, "card_declined"),
                        expect_failure=True,
                    ),
                ]),
                Path(name="email_success", steps=[
                    Step(name="mock_sendgrid_ok", action=lambda c, ctx: configure_sendgrid_mock(c, ctx, "success")),
                    Step(name="register_user", action=register_user),
                    Step(name="verify_email", action=verify_email_sent),
                ]),
            ],
        ),
    ],
)
```
