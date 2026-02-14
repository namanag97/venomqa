# E-commerce Checkout

Complete examples of testing e-commerce checkout flows.

## Complete Checkout Journey

```python
from venomqa import Journey, Step, Checkpoint, Branch, Path


# ====================
# Setup Actions
# ====================

def login(client, context):
    """Authenticate user."""
    response = client.post("/api/auth/login", json={
        "email": "shopper@example.com",
        "password": "shopperpass",
    })

    if response.status_code == 200:
        data = response.json()
        context["token"] = data["token"]
        context["user_id"] = data["user"]["id"]
        client.set_auth_token(data["token"])

    return response


def browse_products(client, context):
    """Browse available products."""
    response = client.get("/api/products", params={"category": "electronics"})

    if response.status_code == 200:
        products = response.json()["products"]
        if products:
            context["product_id"] = products[0]["id"]
            context["product_price"] = products[0]["price"]

    return response


def add_to_cart(client, context):
    """Add product to cart."""
    response = client.post("/api/cart/items", json={
        "product_id": context["product_id"],
        "quantity": 2,
    })

    if response.status_code in [200, 201]:
        data = response.json()
        context["cart_id"] = data["cart_id"]
        context["cart_total"] = data["total"]

    return response


def apply_coupon(client, context):
    """Apply discount coupon."""
    response = client.post(f"/api/cart/{context['cart_id']}/coupon", json={
        "code": "SAVE10",
    })

    if response.status_code == 200:
        context["discount"] = response.json()["discount"]
        context["cart_total"] = response.json()["total"]

    return response


def set_shipping_address(client, context):
    """Set shipping address."""
    return client.post(f"/api/cart/{context['cart_id']}/shipping", json={
        "address": {
            "name": "John Doe",
            "street": "123 Main St",
            "city": "New York",
            "state": "NY",
            "zip": "10001",
            "country": "US",
        },
    })


def create_order(client, context):
    """Create order from cart."""
    response = client.post("/api/orders", json={
        "cart_id": context["cart_id"],
    })

    if response.status_code in [200, 201]:
        data = response.json()
        context["order_id"] = data["id"]
        context["order_total"] = data["total"]

    return response


# ====================
# Payment Actions
# ====================

def pay_with_card_success(client, context):
    """Pay with valid credit card."""
    return client.post("/api/payments", json={
        "order_id": context["order_id"],
        "method": "credit_card",
        "card": {
            "number": "4242424242424242",
            "exp_month": 12,
            "exp_year": 2025,
            "cvv": "123",
        },
    })


def pay_with_card_declined(client, context):
    """Pay with card that will be declined."""
    return client.post("/api/payments", json={
        "order_id": context["order_id"],
        "method": "credit_card",
        "card": {
            "number": "4000000000000002",  # Decline test card
            "exp_month": 12,
            "exp_year": 2025,
            "cvv": "123",
        },
    })


def pay_with_paypal(client, context):
    """Pay with PayPal."""
    response = client.post("/api/payments", json={
        "order_id": context["order_id"],
        "method": "paypal",
        "return_url": "https://example.com/success",
        "cancel_url": "https://example.com/cancel",
    })

    if response.status_code == 200:
        context["paypal_redirect"] = response.json()["redirect_url"]

    return response


def pay_with_wallet(client, context):
    """Pay with digital wallet."""
    return client.post("/api/payments", json={
        "order_id": context["order_id"],
        "method": "wallet",
        "wallet_id": context.get("wallet_id", "default"),
    })


def pay_with_installments(client, context):
    """Pay in installments."""
    return client.post("/api/payments", json={
        "order_id": context["order_id"],
        "method": "installments",
        "installment_plan": {
            "count": 3,
            "interval": "monthly",
        },
    })


# ====================
# Verification Actions
# ====================

def verify_order_completed(client, context):
    """Verify order status is completed."""
    response = client.get(f"/api/orders/{context['order_id']}")

    if response.status_code == 200:
        status = response.json()["status"]
        if status not in ["completed", "processing"]:
            raise AssertionError(f"Expected completed, got {status}")

    return response


def get_order_receipt(client, context):
    """Get order receipt."""
    return client.get(f"/api/orders/{context['order_id']}/receipt")


# ====================
# Journey Definition
# ====================

journey = Journey(
    name="checkout_complete",
    description="Complete checkout flow with multiple payment options",
    tags=["checkout", "payment", "e-commerce", "critical"],
    steps=[
        # Setup
        Step(name="login", action=login),
        Step(name="browse", action=browse_products),
        Step(name="add_to_cart", action=add_to_cart),
        Step(name="apply_coupon", action=apply_coupon),
        Step(name="set_shipping", action=set_shipping_address),
        Step(name="create_order", action=create_order),

        # Save state before payment
        Checkpoint(name="ready_to_pay"),

        # Test all payment methods
        Branch(
            checkpoint_name="ready_to_pay",
            paths=[
                # Credit card success
                Path(name="card_success", steps=[
                    Step(name="pay", action=pay_with_card_success),
                    Step(name="verify", action=verify_order_completed),
                    Step(name="receipt", action=get_order_receipt),
                ]),

                # Credit card declined
                Path(name="card_declined", steps=[
                    Step(
                        name="pay",
                        action=pay_with_card_declined,
                        expect_failure=True,
                    ),
                ]),

                # PayPal
                Path(name="paypal", steps=[
                    Step(name="pay", action=pay_with_paypal),
                ]),

                # Digital wallet
                Path(name="wallet", steps=[
                    Step(name="pay", action=pay_with_wallet),
                    Step(name="verify", action=verify_order_completed),
                ]),

                # Installments
                Path(name="installments", steps=[
                    Step(name="pay", action=pay_with_installments),
                    Step(name="verify", action=verify_order_completed),
                ]),
            ],
        ),
    ],
)
```

## Cart Operations

```python
from venomqa import Journey, Step, Checkpoint


def login(client, context):
    response = client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "secret123",
    })
    if response.status_code == 200:
        client.set_auth_token(response.json()["token"])
    return response


def create_cart(client, context):
    """Create a new cart."""
    response = client.post("/api/cart")
    if response.status_code in [200, 201]:
        context["cart_id"] = response.json()["id"]
    return response


def add_item_1(client, context):
    """Add first item to cart."""
    return client.post(f"/api/cart/{context['cart_id']}/items", json={
        "product_id": 1,
        "quantity": 2,
    })


def add_item_2(client, context):
    """Add second item to cart."""
    return client.post(f"/api/cart/{context['cart_id']}/items", json={
        "product_id": 2,
        "quantity": 1,
    })


def update_quantity(client, context):
    """Update item quantity."""
    return client.patch(f"/api/cart/{context['cart_id']}/items/1", json={
        "quantity": 5,
    })


def remove_item(client, context):
    """Remove item from cart."""
    return client.delete(f"/api/cart/{context['cart_id']}/items/2")


def get_cart(client, context):
    """Get cart contents."""
    return client.get(f"/api/cart/{context['cart_id']}")


def clear_cart(client, context):
    """Clear all items from cart."""
    return client.delete(f"/api/cart/{context['cart_id']}/items")


journey = Journey(
    name="cart_operations",
    description="Test shopping cart operations",
    tags=["cart", "e-commerce"],
    steps=[
        Step(name="login", action=login),
        Step(name="create_cart", action=create_cart),
        Checkpoint(name="cart_created"),
        Step(name="add_item_1", action=add_item_1),
        Step(name="add_item_2", action=add_item_2),
        Step(name="view_cart", action=get_cart),
        Step(name="update_quantity", action=update_quantity),
        Step(name="remove_item", action=remove_item),
        Step(name="view_updated", action=get_cart),
        Step(name="clear_cart", action=clear_cart),
    ],
)
```

## Order Management

```python
from venomqa import Journey, Step, Checkpoint, Branch, Path


def setup_and_create_order(client, context):
    """Setup and create an order."""
    # Login
    response = client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "secret123",
    })
    client.set_auth_token(response.json()["token"])

    # Create order
    response = client.post("/api/orders", json={
        "items": [{"product_id": 1, "quantity": 2}],
        "shipping_address": {"street": "123 Main St", "city": "NYC"},
    })
    context["order_id"] = response.json()["id"]

    return response


def pay_order(client, context):
    """Pay for the order."""
    return client.post(f"/api/orders/{context['order_id']}/pay", json={
        "method": "credit_card",
        "card_token": "tok_visa",
    })


def cancel_order(client, context):
    """Cancel the order."""
    return client.post(f"/api/orders/{context['order_id']}/cancel", json={
        "reason": "Changed my mind",
    })


def request_refund(client, context):
    """Request a refund."""
    return client.post(f"/api/orders/{context['order_id']}/refund", json={
        "reason": "Product not as described",
    })


def get_order_status(client, context):
    """Get order status."""
    return client.get(f"/api/orders/{context['order_id']}")


def get_order_tracking(client, context):
    """Get shipping tracking info."""
    return client.get(f"/api/orders/{context['order_id']}/tracking")


journey = Journey(
    name="order_lifecycle",
    description="Test order lifecycle",
    tags=["orders", "e-commerce"],
    steps=[
        Step(name="create_order", action=setup_and_create_order),
        Checkpoint(name="order_created"),

        Branch(
            checkpoint_name="order_created",
            paths=[
                # Normal flow: pay and track
                Path(name="complete_flow", steps=[
                    Step(name="pay", action=pay_order),
                    Step(name="status", action=get_order_status),
                    Step(name="tracking", action=get_order_tracking),
                ]),

                # Cancel before payment
                Path(name="cancel_unpaid", steps=[
                    Step(name="cancel", action=cancel_order),
                    Step(name="verify_cancelled", action=get_order_status),
                ]),

                # Pay then refund
                Path(name="refund_flow", steps=[
                    Step(name="pay", action=pay_order),
                    Step(name="refund", action=request_refund),
                    Step(name="verify_refunded", action=get_order_status),
                ]),
            ],
        ),
    ],
)
```

## Inventory Testing

```python
from venomqa import Journey, Step, Checkpoint


def check_stock(client, context):
    """Check product stock."""
    response = client.get("/api/products/1/stock")
    context["initial_stock"] = response.json()["quantity"]
    return response


def add_to_cart_available(client, context):
    """Add available quantity to cart."""
    return client.post("/api/cart/items", json={
        "product_id": 1,
        "quantity": 2,
    })


def add_to_cart_excess(client, context):
    """Try to add more than available."""
    return client.post("/api/cart/items", json={
        "product_id": 1,
        "quantity": 999999,
    })


def complete_purchase(client, context):
    """Complete purchase."""
    return client.post("/api/checkout", json={
        "payment_method": "credit_card",
        "card_token": "tok_visa",
    })


def check_stock_after(client, context):
    """Check stock after purchase."""
    response = client.get("/api/products/1/stock")
    context["final_stock"] = response.json()["quantity"]
    return response


journey = Journey(
    name="inventory_management",
    description="Test inventory during checkout",
    tags=["inventory", "stock", "e-commerce"],
    steps=[
        Step(name="check_initial_stock", action=check_stock),
        Step(name="add_available", action=add_to_cart_available),
        Step(
            name="add_excess",
            action=add_to_cart_excess,
            expect_failure=True,
        ),
        Step(name="purchase", action=complete_purchase),
        Step(name="check_final_stock", action=check_stock_after),
    ],
)
```

## Promotion and Discount Testing

```python
from venomqa import Journey, Step, Checkpoint, Branch, Path


def setup_cart(client, context):
    """Setup cart with items."""
    client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "secret123",
    })

    response = client.post("/api/cart/items", json={
        "product_id": 1,
        "quantity": 3,
    })
    context["cart_id"] = response.json()["cart_id"]
    context["original_total"] = response.json()["total"]

    return response


def apply_percentage_coupon(client, context):
    """Apply percentage discount coupon."""
    return client.post(f"/api/cart/{context['cart_id']}/coupon", json={
        "code": "SAVE20",  # 20% off
    })


def apply_fixed_coupon(client, context):
    """Apply fixed amount coupon."""
    return client.post(f"/api/cart/{context['cart_id']}/coupon", json={
        "code": "FLAT10",  # $10 off
    })


def apply_expired_coupon(client, context):
    """Apply expired coupon."""
    return client.post(f"/api/cart/{context['cart_id']}/coupon", json={
        "code": "EXPIRED2023",
    })


def apply_invalid_coupon(client, context):
    """Apply invalid coupon."""
    return client.post(f"/api/cart/{context['cart_id']}/coupon", json={
        "code": "NOTREAL",
    })


def remove_coupon(client, context):
    """Remove applied coupon."""
    return client.delete(f"/api/cart/{context['cart_id']}/coupon")


journey = Journey(
    name="coupon_testing",
    description="Test coupon and discount functionality",
    tags=["coupons", "discounts", "e-commerce"],
    steps=[
        Step(name="setup", action=setup_cart),
        Checkpoint(name="cart_ready"),

        Branch(
            checkpoint_name="cart_ready",
            paths=[
                Path(name="percentage_discount", steps=[
                    Step(name="apply", action=apply_percentage_coupon),
                    Step(name="remove", action=remove_coupon),
                ]),
                Path(name="fixed_discount", steps=[
                    Step(name="apply", action=apply_fixed_coupon),
                ]),
                Path(name="expired_coupon", steps=[
                    Step(
                        name="apply",
                        action=apply_expired_coupon,
                        expect_failure=True,
                    ),
                ]),
                Path(name="invalid_coupon", steps=[
                    Step(
                        name="apply",
                        action=apply_invalid_coupon,
                        expect_failure=True,
                    ),
                ]),
            ],
        ),
    ],
)
```
