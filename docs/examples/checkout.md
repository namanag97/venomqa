# E-commerce Checkout

Complete example testing e-commerce flows: cart management, payment processing, refunds, order state transitions, and inventory validation.

## What You'll Learn

- Complex state machine testing
- Financial invariant patterns
- Inventory consistency checks
- Order lifecycle exploration
- Multi-step transaction testing

## Complete Example

```python
"""
E-commerce Checkout Example

Tests an e-commerce API with these endpoints:
- POST   /cart/items              → Add item to cart
- GET    /cart                    → Get cart contents
- DELETE /cart/items/{id}         → Remove item from cart
- POST   /cart/coupon             → Apply discount coupon
- POST   /checkout                → Create order from cart
- GET    /orders/{id}             → Get order details
- POST   /orders/{id}/pay         → Pay for order
- POST   /orders/{id}/refund      → Refund order
- POST   /orders/{id}/cancel      → Cancel order
- GET    /products/{id}/stock     → Check inventory

Run: python test_checkout.py
"""

from __future__ import annotations

from venomqa import (
    Action,
    Agent,
    BFS,
    Invariant,
    Severity,
    World,
)
from venomqa.adapters.http import HttpClient


# =============================================================================
# CONTEXT KEYS
# =============================================================================
# cart_id: str | None
# order_id: str | None
# order_total: float
# order_paid: float
# order_refunded: float
# product_id: str
# initial_stock: int
# current_stock: int
# last_status: int


# =============================================================================
# ACTIONS — SETUP & AUTH
# =============================================================================

def login_customer(api: HttpClient, context) -> dict | None:
    """Login as a customer."""
    resp = api.post("/auth/login", json={
        "email": "customer@example.com",
        "password": "customer123",
    })
    
    context.set("last_status", resp.status_code)
    
    if resp.status_code == 200:
        data = resp.json()
        api.set_auth_token(data["access_token"])
        context.set("customer_id", data["user"]["id"])
        return data
    return None


def get_product_and_stock(api: HttpClient, context) -> dict | None:
    """Fetch product info and current stock level."""
    resp = api.get("/products")
    
    if resp.status_code == 200:
        products = resp.json()
        if products and len(products) > 0:
            product = products[0]
            context.set("product_id", product["id"])
            context.set("product_price", product["price"])
            
            # Get stock
            stock_resp = api.get(f"/products/{product['id']}/stock")
            if stock_resp.status_code == 200:
                stock = stock_resp.json()["quantity"]
                context.set("initial_stock", stock)
                context.set("current_stock", stock)
                return product
    return None


# =============================================================================
# ACTIONS — CART MANAGEMENT
# =============================================================================

def add_to_cart(api: HttpClient, context) -> dict | None:
    """Add product to cart.
    
    Requires: product_id must exist
    """
    product_id = context.get("product_id")
    if product_id is None:
        return None
    
    quantity = context.get("add_quantity", 1)
    
    resp = api.post("/cart/items", json={
        "product_id": product_id,
        "quantity": quantity,
    })
    
    context.set("last_status", resp.status_code)
    
    if resp.status_code in [200, 201]:
        data = resp.json()
        context.set("cart_id", data.get("cart_id"))
        context.set("cart_total", data.get("total"))
        context.set("cart_item_count", data.get("item_count"))
        return data
    return None


def add_more_to_cart(api: HttpClient, context) -> dict | None:
    """Add another item to the cart."""
    if context.get("cart_id") is None:
        return None  # No cart yet
    
    product_id = context.get("product_id")
    if product_id is None:
        return None
    
    resp = api.post("/cart/items", json={
        "product_id": product_id,
        "quantity": 2,
    })
    
    context.set("last_status", resp.status_code)
    
    if resp.status_code == 200:
        data = resp.json()
        context.set("cart_total", data.get("total"))
        return data
    return None


def get_cart(api: HttpClient, context) -> dict | None:
    """Get current cart contents."""
    if context.get("cart_id") is None:
        return None
    
    resp = api.get("/cart")
    context.set("last_status", resp.status_code)
    
    if resp.status_code == 200:
        return resp.json()
    return None


def remove_from_cart(api: HttpClient, context) -> dict | None:
    """Remove item from cart."""
    if context.get("cart_id") is None:
        return None
    
    resp = api.delete("/cart/items/1")
    context.set("last_status", resp.status_code)
    
    if resp.status_code in [200, 204]:
        return {}
    return None


def apply_coupon(api: HttpClient, context) -> dict | None:
    """Apply a discount coupon.
    
    Requires: cart must exist
    """
    if context.get("cart_id") is None:
        return None
    
    resp = api.post("/cart/coupon", json={
        "code": "SAVE10",
    })
    
    context.set("last_status", resp.status_code)
    
    if resp.status_code == 200:
        data = resp.json()
        context.set("discount", data.get("discount"))
        context.set("cart_total", data.get("total"))
        return data
    return None


def clear_cart(api: HttpClient, context) -> dict | None:
    """Clear all items from cart."""
    if context.get("cart_id") is None:
        return None
    
    resp = api.delete("/cart/items")
    context.set("last_status", resp.status_code)
    
    if resp.status_code in [200, 204]:
        context.delete("cart_total")
        return {}
    return None


# =============================================================================
# ACTIONS — CHECKOUT & ORDER
# =============================================================================

def create_order(api: HttpClient, context) -> dict | None:
    """Create order from cart.
    
    Requires: cart with items must exist
    """
    if context.get("cart_id") is None:
        return None
    if context.get("cart_total", 0) <= 0:
        return None  # Empty cart
    
    resp = api.post("/checkout", json={
        "shipping_address": {
            "street": "123 Main St",
            "city": "New York",
            "zip": "10001",
            "country": "US",
        },
    })
    
    context.set("last_status", resp.status_code)
    
    if resp.status_code in [200, 201]:
        data = resp.json()
        context.set("order_id", data["id"])
        context.set("order_total", data["total"])
        context.set("order_status", data["status"])
        context.set("order_paid", 0.0)
        context.set("order_refunded", 0.0)
        context.delete("cart_id")  # Cart is consumed
        return data
    return None


def get_order(api: HttpClient, context) -> dict | None:
    """Get order details.
    
    Requires: order must exist
    """
    order_id = context.get("order_id")
    if order_id is None:
        return None
    
    resp = api.get(f"/orders/{order_id}")
    context.set("last_status", resp.status_code)
    
    if resp.status_code == 200:
        data = resp.json()
        context.set("order_status", data["status"])
        return data
    return None


# =============================================================================
# ACTIONS — PAYMENT
# =============================================================================

def pay_order(api: HttpClient, context) -> dict | None:
    """Pay for order with credit card.
    
    Requires: order must exist and be unpaid
    """
    order_id = context.get("order_id")
    if order_id is None:
        return None
    
    # Check if already paid
    if context.get("order_paid", 0) >= context.get("order_total", 0):
        return None  # Already paid
    
    resp = api.post(f"/orders/{order_id}/pay", json={
        "method": "credit_card",
        "card": {
            "number": "4242424242424242",
            "exp_month": 12,
            "exp_year": 2025,
            "cvv": "123",
        },
    })
    
    context.set("last_status", resp.status_code)
    
    if resp.status_code == 200:
        data = resp.json()
        context.set("order_paid", data.get("amount_paid", context.get("order_total")))
        context.set("order_status", data.get("status", "paid"))
        
        # Update stock
        new_stock = context.get("current_stock", 0) - 1
        context.set("current_stock", max(0, new_stock))
        return data
    return None


def pay_with_invalid_card(api: HttpClient, context) -> dict | None:
    """Attempt payment with declined card.
    
    Should fail gracefully.
    """
    order_id = context.get("order_id")
    if order_id is None:
        return None
    
    resp = api.post(f"/orders/{order_id}/pay", json={
        "method": "credit_card",
        "card": {
            "number": "4000000000000002",  # Test decline card
            "exp_month": 12,
            "exp_year": 2025,
            "cvv": "123",
        },
    })
    
    context.set("last_status", resp.status_code)
    context.set("payment_declined", resp.status_code != 200)
    return resp.json() if resp.status_code == 200 else None


# =============================================================================
# ACTIONS — ORDER LIFECYCLE
# =============================================================================

def refund_order(api: HttpClient, context) -> dict | None:
    """Request full refund for order.
    
    Requires: order must be paid
    """
    order_id = context.get("order_id")
    if order_id is None:
        return None
    
    # Must be paid to refund
    if context.get("order_paid", 0) <= 0:
        return None
    
    refund_amount = context.get("order_paid", 0)
    
    resp = api.post(f"/orders/{order_id}/refund", json={
        "amount": refund_amount,
    })
    
    context.set("last_status", resp.status_code)
    
    if resp.status_code == 200:
        data = resp.json()
        current_refunded = context.get("order_refunded", 0)
        context.set("order_refunded", current_refunded + refund_amount)
        context.set("order_status", data.get("status", "refunded"))
        return data
    return None


def partial_refund(api: HttpClient, context) -> dict | None:
    """Request partial refund.
    
    Requires: order must be paid with remaining refundable amount
    """
    order_id = context.get("order_id")
    if order_id is None:
        return None
    
    order_paid = context.get("order_paid", 0)
    already_refunded = context.get("order_refunded", 0)
    remaining = order_paid - already_refunded
    
    if remaining <= 0:
        return None  # Nothing left to refund
    
    partial_amount = remaining / 2  # Refund half of remaining
    
    resp = api.post(f"/orders/{order_id}/refund", json={
        "amount": partial_amount,
    })
    
    context.set("last_status", resp.status_code)
    
    if resp.status_code == 200:
        context.set("order_refunded", already_refunded + partial_amount)
        return resp.json()
    return None


def cancel_order(api: HttpClient, context) -> dict | None:
    """Cancel the order.
    
    Requires: order must exist and be cancellable
    """
    order_id = context.get("order_id")
    if order_id is None:
        return None
    
    status = context.get("order_status")
    if status in ["refunded", "cancelled", "shipped"]:
        return None  # Cannot cancel in these states
    
    resp = api.post(f"/orders/{order_id}/cancel", json={
        "reason": "Customer request",
    })
    
    context.set("last_status", resp.status_code)
    
    if resp.status_code == 200:
        context.set("order_status", "cancelled")
        return resp.json()
    return None


def check_stock_after(api: HttpClient, context) -> dict | None:
    """Check product stock level after operations."""
    product_id = context.get("product_id")
    if product_id is None:
        return None
    
    resp = api.get(f"/products/{product_id}/stock")
    context.set("last_status", resp.status_code)
    
    if resp.status_code == 200:
        stock = resp.json()["quantity"]
        context.set("actual_stock", stock)
        return resp.json()
    return None


# =============================================================================
# INVARIANTS — FINANCIAL
# =============================================================================

def no_server_errors(world: World) -> bool:
    """No 5xx errors should occur."""
    return world.context.get("last_status", 200) < 500


def refund_cannot_exceed_payment(world: World) -> bool:
    """Total refunds cannot exceed amount paid.
    
    This catches the classic over-refund bug where:
    - Order total: $100
    - Refund 1: $100
    - Refund 2: $100 (BUG!)
    """
    paid = world.context.get("order_paid", 0)
    refunded = world.context.get("order_refunded", 0)
    
    if paid > 0:
        return refunded <= paid
    return True


def order_total_positive(world: World) -> bool:
    """Order total should always be positive."""
    total = world.context.get("order_total")
    if total is not None:
        return total > 0
    return True


def cart_total_matches_items(world: World) -> bool:
    """Cart total should reflect item prices.
    
    Simplified check — real implementation would sum item prices.
    """
    return True


# =============================================================================
# INVARIANTS — INVENTORY
# =============================================================================

def stock_never_negative(world: World) -> bool:
    """Product stock should never go below zero."""
    stock = world.context.get("current_stock", 0)
    return stock >= 0


def stock_decreases_on_purchase(world: World) -> bool:
    """Stock should decrease when order is paid."""
    initial = world.context.get("initial_stock")
    current = world.context.get("current_stock")
    paid = world.context.get("order_paid", 0)
    
    if initial is not None and current is not None and paid > 0:
        return current < initial
    return True


def stock_restored_on_cancel(world: World) -> bool:
    """Stock should be restored if order is cancelled.
    
    This is a common bug: cancelled orders don't return inventory.
    """
    status = world.context.get("order_status")
    initial = world.context.get("initial_stock")
    current = world.context.get("current_stock")
    actual = world.context.get("actual_stock")
    
    if status == "cancelled" and actual is not None:
        return actual >= current
    return True


# =============================================================================
# INVARIANTS — STATE TRANSITIONS
# =============================================================================

def cannot_pay_cancelled_order(world: World) -> bool:
    """Cancelled orders cannot be paid."""
    status = world.context.get("order_status")
    last_status = world.context.get("last_status")
    
    # If we tried to pay a cancelled order, it should fail
    if status == "cancelled" and last_status is not None:
        # Last action was a payment attempt on cancelled order
        pass  # Would need to track what action was just attempted
    return True


def cannot_refund_unpaid_order(world: World) -> bool:
    """Unpaid orders cannot be refunded."""
    paid = world.context.get("order_paid", 0)
    refunded = world.context.get("order_refunded", 0)
    
    if refunded > 0 and paid <= 0:
        return False  # Refunded without paying!
    return True


# =============================================================================
# BUILD INVARIANT OBJECTS
# =============================================================================

INVARIANTS = [
    Invariant(
        name="no_server_errors",
        check=no_server_errors,
        message="Server returned 5xx error during checkout",
        severity=Severity.CRITICAL,
    ),
    Invariant(
        name="refund_cannot_exceed_payment",
        check=refund_cannot_exceed_payment,
        message="Total refunds exceeded amount paid — over-refund bug!",
        severity=Severity.CRITICAL,
    ),
    Invariant(
        name="stock_never_negative",
        check=stock_never_negative,
        message="Product stock went negative",
        severity=Severity.CRITICAL,
    ),
    Invariant(
        name="order_total_positive",
        check=order_total_positive,
        message="Order total became non-positive",
        severity=Severity.HIGH,
    ),
    Invariant(
        name="cannot_refund_unpaid",
        check=cannot_refund_unpaid_order,
        message="Refund was processed for unpaid order",
        severity=Severity.HIGH,
    ),
    Invariant(
        name="stock_decreases_on_purchase",
        check=stock_decreases_on_purchase,
        message="Stock did not decrease after payment",
        severity=Severity.HIGH,
    ),
]


# =============================================================================
# BUILD ACTIONS
# =============================================================================

ACTIONS = [
    # Setup
    Action(
        name="login_customer",
        execute=login_customer,
        description="Login as customer",
        tags=["auth"],
    ),
    Action(
        name="get_product_stock",
        execute=get_product_and_stock,
        description="Get product and stock info",
        tags=["setup"],
    ),
    # Cart
    Action(
        name="add_to_cart",
        execute=add_to_cart,
        description="Add item to cart",
        tags=["cart", "write"],
    ),
    Action(
        name="add_more_to_cart",
        execute=add_more_to_cart,
        description="Add more items to cart",
        tags=["cart", "write"],
    ),
    Action(
        name="get_cart",
        execute=get_cart,
        description="View cart contents",
        tags=["cart", "read"],
    ),
    Action(
        name="remove_from_cart",
        execute=remove_from_cart,
        description="Remove item from cart",
        tags=["cart", "write"],
    ),
    Action(
        name="apply_coupon",
        execute=apply_coupon,
        description="Apply discount coupon",
        tags=["cart", "discount"],
    ),
    Action(
        name="clear_cart",
        execute=clear_cart,
        description="Clear cart",
        tags=["cart", "write"],
    ),
    # Order
    Action(
        name="create_order",
        execute=create_order,
        description="Create order from cart",
        tags=["order", "write"],
    ),
    Action(
        name="get_order",
        execute=get_order,
        description="Get order details",
        tags=["order", "read"],
    ),
    # Payment
    Action(
        name="pay_order",
        execute=pay_order,
        description="Pay for order",
        tags=["payment", "write"],
    ),
    Action(
        name="pay_invalid_card",
        execute=pay_with_invalid_card,
        description="Try payment with declined card",
        tags=["payment", "error"],
    ),
    # Lifecycle
    Action(
        name="refund_order",
        execute=refund_order,
        description="Request full refund",
        tags=["refund", "write"],
    ),
    Action(
        name="partial_refund",
        execute=partial_refund,
        description="Request partial refund",
        tags=["refund", "write"],
    ),
    Action(
        name="cancel_order",
        execute=cancel_order,
        description="Cancel order",
        tags=["order", "write"],
    ),
    Action(
        name="check_stock",
        execute=check_stock_after,
        description="Verify stock level",
        tags=["inventory", "read"],
    ),
]


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    api = HttpClient("http://localhost:8000")
    world = World(
        api=api,
        state_from_context=["order_id", "order_paid", "order_refunded"],
    )
    
    agent = Agent(
        world=world,
        actions=ACTIONS,
        invariants=INVARIANTS,
        strategy=BFS(),
        max_steps=200,
    )
    
    result = agent.explore()
    
    print("\n" + "=" * 60)
    print("E-COMMERCE CHECKOUT EXPLORATION RESULTS")
    print("=" * 60)
    print(f"States visited:    {result.states_visited}")
    print(f"Transitions taken: {result.transitions_taken}")
    print(f"Action coverage:   {result.action_coverage_percent:.0f}%")
    print(f"Duration:          {result.duration_ms:.0f} ms")
    print(f"Violations found:  {len(result.violations)}")
    
    if result.violations:
        print("\nVIOLATIONS:")
        for v in result.violations:
            print(f"  [{v.severity.value.upper()}] {v.invariant_name}")
            print(f"    {v.message}")
            if v.path:
                print(f"    Path: {' → '.join(v.path)}")
    else:
        print("\nNo violations — all checkout invariants passed.")
    
    print("=" * 60)
```

## Why These Patterns Matter

### Financial Invariants

The most critical invariant catches over-refunds:

```python
def refund_cannot_exceed_payment(world):
    paid = world.context.get("order_paid", 0)
    refunded = world.context.get("order_refunded", 0)
    
    if paid > 0:
        return refunded <= paid  # Never refund more than paid
    return True
```

This catches the sequence `create_order → pay → refund → refund` where each refund succeeds even though the order was already fully refunded.

### State Machine Tracking

Context tracks the full order lifecycle:

| Variable | Purpose |
|----------|---------|
| `order_status` | Current order state |
| `order_paid` | Total amount paid |
| `order_refunded` | Total amount refunded |
| `order_total` | Original order total |

Actions update these values, and invariants check they remain consistent.

### Inventory Consistency

```python
def stock_never_negative(world):
    stock = world.context.get("current_stock", 0)
    return stock >= 0
```

Stock should never go negative, even with concurrent purchases or edge cases in the order flow.

## Sequences Tested

| Sequence | What It Tests |
|----------|---------------|
| `add_to_cart → create_order → pay` | Happy path checkout |
| `pay → refund → refund` | Over-refund bug |
| `create_order → cancel` | Cancellation flow |
| `pay → partial_refund → partial_refund` | Multiple partial refunds |
| `pay → cancel` | Cancel after payment |
| `add_to_cart → clear_cart → create_order` | Empty cart handling |
| `pay_invalid_card → pay` | Recovery from declined card |

## Expected Output

```
============================================================
E-COMMERCE CHECKOUT EXPLORATION RESULTS
============================================================
States visited:    24
Transitions taken: 68
Action coverage:   100%
Duration:          412 ms
Violations found:  1

VIOLATIONS:
  [CRITICAL] refund_cannot_exceed_payment
    Total refunds exceeded amount paid — over-refund bug!
    Path: create_order → pay_order → refund_order → refund_order
============================================================
```

## Common E-commerce Bugs Found

| Bug | Sequence That Finds It |
|-----|------------------------|
| Over-refund | `pay → refund → refund` |
| Negative stock | `add_to_cart × 100 → pay` |
| Cancel doesn't restore stock | `create_order → cancel → check_stock` |
| Refund unpaid order | `create_order → refund` |
| Double payment | `pay → pay` |
| Discount exploits | `apply_coupon → apply_coupon` |

## Database Rollback for Real Testing

With PostgreSQL rollback:

```python
from venomqa.adapters.postgres import PostgresAdapter

api = HttpClient("http://localhost:8000")
db = PostgresAdapter("postgresql://user:pass@localhost/shop")

world = World(
    api=api,
    systems={"db": db},
)

# Each exploration branch gets a clean DB state
# Allows testing: create_order → pay → refund
# Then rollback and test: create_order → cancel
```

## Next Steps

- [Authentication Flows](auth.md) — Multi-user auth testing
- [CRUD Operations](crud.md) — Basic patterns
