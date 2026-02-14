# Testing Payment Flows

In this tutorial, you'll use checkpoints and branching to test multiple payment methods from a single setup.

**Time:** 20 minutes

**What you'll learn:**

- Creating checkpoints to save state
- Using branches to test multiple scenarios
- Testing success and failure paths
- Organizing complex journeys

## The Challenge

Testing payment flows typically requires:

1. User authentication
2. Adding items to cart
3. Creating an order
4. **Testing multiple payment methods** (card, wallet, PayPal, etc.)

Without checkpoints, you'd need to repeat steps 1-3 for each payment method. With VenomQA, you run setup once and branch to test all methods.

## Prerequisites

- Completed [Your First Journey](first-journey.md) tutorial
- VenomQA installed with `pip install venomqa`

## Step 1: Set Up Project Structure

```bash
mkdir payment-tests
cd payment-tests
mkdir journeys
```

Create `venomqa.yaml`:

```yaml
base_url: "http://localhost:8000"
timeout: 30
verbose: false
```

## Step 2: Create the Payment Journey

Create `journeys/checkout.py`:

```python
"""
Checkout Flow Journey

Tests the complete checkout flow with multiple payment methods:
1. Login
2. Add items to cart
3. Create order
4. [CHECKPOINT] - Save state here
5. [BRANCH] - Test each payment method from saved state
   - Credit card (success)
   - Digital wallet (success)
   - Credit card declined (expected failure)
   - Insufficient wallet balance (expected failure)
"""
from venomqa import Journey, Step, Checkpoint, Branch, Path


# ====================
# Setup Actions
# ====================

def login(client, context):
    """Authenticate user."""
    response = client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "secret123",
    })

    if response.status_code == 200:
        data = response.json()
        context["token"] = data["token"]
        context["user_id"] = data["user"].get("id")
        client.set_auth_token(data["token"])

    return response


def add_to_cart(client, context):
    """Add items to shopping cart."""
    response = client.post("/api/cart/items", json={
        "product_id": 1,
        "quantity": 2,
    })

    if response.status_code in [200, 201]:
        data = response.json()
        context["cart_id"] = data.get("cart_id")
        context["cart_total"] = data.get("total", 59.98)

    return response


def create_order(client, context):
    """Create order from cart."""
    response = client.post("/api/orders", json={
        "cart_id": context.get("cart_id"),
        "shipping_address": {
            "street": "123 Test St",
            "city": "Test City",
            "zip": "12345",
        },
    })

    if response.status_code in [200, 201]:
        data = response.json()
        context["order_id"] = data.get("id")
        context["order_total"] = data.get("total", context.get("cart_total"))

    return response


# ====================
# Payment Actions
# ====================

def pay_with_card_success(client, context):
    """Pay with valid credit card."""
    return client.post("/api/payments", json={
        "order_id": context.get("order_id"),
        "method": "credit_card",
        "card_token": "tok_visa_success",
        "amount": context.get("order_total"),
    })


def pay_with_card_declined(client, context):
    """Pay with card that gets declined."""
    return client.post("/api/payments", json={
        "order_id": context.get("order_id"),
        "method": "credit_card",
        "card_token": "tok_visa_declined",
        "amount": context.get("order_total"),
    })


def pay_with_wallet_success(client, context):
    """Pay with digital wallet (sufficient balance)."""
    return client.post("/api/payments", json={
        "order_id": context.get("order_id"),
        "method": "digital_wallet",
        "wallet_id": "wallet_sufficient",
        "amount": context.get("order_total"),
    })


def pay_with_wallet_insufficient(client, context):
    """Pay with wallet (insufficient balance)."""
    return client.post("/api/payments", json={
        "order_id": context.get("order_id"),
        "method": "digital_wallet",
        "wallet_id": "wallet_empty",
        "amount": context.get("order_total"),
    })


def verify_payment_success(client, context):
    """Verify order status after successful payment."""
    order_id = context.get("order_id")
    return client.get(f"/api/orders/{order_id}")


# ====================
# Journey Definition
# ====================

journey = Journey(
    name="checkout_payment_methods",
    description="Test checkout with multiple payment methods using branching",
    tags=["checkout", "payment", "critical"],
    steps=[
        # ===== Setup Phase =====
        Step(
            name="login",
            action=login,
            description="Authenticate user",
        ),
        Step(
            name="add_to_cart",
            action=add_to_cart,
            description="Add items to cart",
        ),
        Step(
            name="create_order",
            action=create_order,
            description="Create order from cart",
        ),

        # ===== Save State =====
        Checkpoint(name="order_ready"),

        # ===== Test Multiple Payment Methods =====
        Branch(
            checkpoint_name="order_ready",
            paths=[
                # Happy path: Credit card
                Path(
                    name="credit_card_success",
                    description="Pay with valid credit card",
                    steps=[
                        Step(name="pay_card", action=pay_with_card_success),
                        Step(name="verify_order", action=verify_payment_success),
                    ],
                ),

                # Happy path: Digital wallet
                Path(
                    name="wallet_success",
                    description="Pay with digital wallet",
                    steps=[
                        Step(name="pay_wallet", action=pay_with_wallet_success),
                        Step(name="verify_order", action=verify_payment_success),
                    ],
                ),

                # Error path: Declined card
                Path(
                    name="card_declined",
                    description="Test declined credit card handling",
                    steps=[
                        Step(
                            name="pay_card_declined",
                            action=pay_with_card_declined,
                            expect_failure=True,
                        ),
                    ],
                ),

                # Error path: Insufficient wallet balance
                Path(
                    name="wallet_insufficient",
                    description="Test insufficient wallet balance handling",
                    steps=[
                        Step(
                            name="pay_wallet_empty",
                            action=pay_with_wallet_insufficient,
                            expect_failure=True,
                        ),
                    ],
                ),
            ],
        ),
    ],
)
```

## Step 3: Run the Journey

```bash
venomqa run checkout_payment_methods
```

Expected output:

```
Running journey: checkout_payment_methods
  [PASS] login (92ms)
  [PASS] add_to_cart (45ms)
  [PASS] create_order (67ms)
  [CHECKPOINT] order_ready

  Branch: order_ready
    Path: credit_card_success
      [PASS] pay_card (156ms)
      [PASS] verify_order (23ms)
    Path: wallet_success
      [PASS] pay_wallet (134ms)
      [PASS] verify_order (21ms)
    Path: card_declined
      [PASS] pay_card_declined (expected failure) (89ms)
    Path: wallet_insufficient
      [PASS] pay_wallet_empty (expected failure) (76ms)

Journey completed: 4/4 paths passed
```

## Step 4: Understanding Checkpoints

The key insight is what happens at the checkpoint:

```
Timeline:
─────────────────────────────────────────────────────────────────
1. login          → context["token"] = "abc123"
2. add_to_cart    → context["cart_id"] = 1
3. create_order   → context["order_id"] = 42
4. CHECKPOINT     → [State Saved: context + database]
5. BRANCH
   ├─ Path 1: Starts from checkpoint state
   ├─ Path 2: Starts from checkpoint state (rollback first)
   ├─ Path 3: Starts from checkpoint state (rollback first)
   └─ Path 4: Starts from checkpoint state (rollback first)
```

Each path gets:

- Fresh context restored to checkpoint values
- Database rolled back to checkpoint state
- Same `order_id`, `cart_id`, etc.

## Step 5: Add Nested Checkpoints

For more complex flows, add checkpoints inside paths:

```python
Path(
    name="credit_card_with_retry",
    description="Test card payment with retry on soft decline",
    steps=[
        Step(name="first_attempt", action=pay_with_card_soft_decline),
        Checkpoint(name="after_soft_decline"),  # Nested checkpoint
        Step(name="retry_with_3ds", action=pay_with_card_3ds),
        Step(name="verify_order", action=verify_payment_success),
    ],
),
```

## Step 6: Add More Payment Methods

Extend the journey with additional payment methods:

```python
# Add more payment actions
def pay_with_paypal(client, context):
    """Pay with PayPal."""
    return client.post("/api/payments", json={
        "order_id": context.get("order_id"),
        "method": "paypal",
        "return_url": "https://example.com/success",
        "cancel_url": "https://example.com/cancel",
    })

def pay_with_crypto(client, context):
    """Pay with cryptocurrency."""
    return client.post("/api/payments", json={
        "order_id": context.get("order_id"),
        "method": "crypto",
        "currency": "BTC",
    })

def pay_with_installments(client, context):
    """Pay in installments."""
    return client.post("/api/payments", json={
        "order_id": context.get("order_id"),
        "method": "installments",
        "installment_count": 3,
    })

# Add paths to the branch
Branch(
    checkpoint_name="order_ready",
    paths=[
        # ... existing paths ...

        Path(name="paypal", steps=[
            Step(name="pay_paypal", action=pay_with_paypal),
        ]),

        Path(name="crypto", steps=[
            Step(name="pay_crypto", action=pay_with_crypto),
        ]),

        Path(name="installments", steps=[
            Step(name="pay_installments", action=pay_with_installments),
        ]),
    ],
)
```

## Step 7: Test with Database State

For true state isolation, configure a database backend:

```yaml
# venomqa.yaml
base_url: "http://localhost:8000"
db_url: "postgresql://qa:secret@localhost:5432/qa_test"
db_backend: "postgresql"
```

Now checkpoints will:

1. Create SQL SAVEPOINTs
2. Roll back database state between paths
3. Ensure each path sees the same data

## Best Practices

### 1. Name Paths Clearly

```python
# Good
Path(name="credit_card_success", ...)
Path(name="credit_card_declined", ...)

# Bad
Path(name="test1", ...)
Path(name="path_a", ...)
```

### 2. Group Related Paths

```python
Branch(
    checkpoint_name="order_ready",
    paths=[
        # Credit card paths
        Path(name="card_success", ...),
        Path(name="card_declined", ...),
        Path(name="card_expired", ...),

        # Wallet paths
        Path(name="wallet_success", ...),
        Path(name="wallet_insufficient", ...),

        # Alternative methods
        Path(name="paypal_success", ...),
        Path(name="bank_transfer", ...),
    ],
)
```

### 3. Test Both Success and Failure

Always test error handling:

```python
# Success path
Path(name="card_success", steps=[
    Step(name="pay", action=pay_valid_card),
]),

# Failure paths
Path(name="card_declined", steps=[
    Step(name="pay", action=pay_declined_card, expect_failure=True),
]),
Path(name="card_expired", steps=[
    Step(name="pay", action=pay_expired_card, expect_failure=True),
]),
```

### 4. Verify State After Actions

Always verify the expected outcome:

```python
Path(name="success", steps=[
    Step(name="pay", action=pay),
    Step(name="verify", action=verify_payment_completed),  # Verify!
]),
```

## Troubleshooting

### "Checkpoint not found"

Ensure checkpoint is created before the branch:

```python
# Correct
Checkpoint(name="order_ready"),
Branch(checkpoint_name="order_ready", ...)

# Wrong - checkpoint after branch reference
Branch(checkpoint_name="order_ready", ...)
Checkpoint(name="order_ready"),
```

### Paths interfering with each other

Use `parallel_paths=1` for sequential execution:

```yaml
# venomqa.yaml
parallel_paths: 1
```

### Context values missing in paths

Remember: context is restored at each path start:

```python
# Setup
context["order_id"] = 42  # Set before checkpoint

# At checkpoint: context["order_id"] = 42

# Path 1: context["order_id"] = 42 (restored)
# Path 2: context["order_id"] = 42 (restored, not 43!)
```

## Next Steps

- [CI/CD Integration](ci-cd.md) - Run payment tests in your pipeline
- [State Management](../concepts/state.md) - Deep dive into state handling
- [Examples](../examples/checkout.md) - More checkout examples
