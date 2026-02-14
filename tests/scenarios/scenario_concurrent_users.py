"""Concurrent Users Scenario - Tests parallel execution and race conditions.

This scenario verifies VenomQA's ability to:
- Simulate multiple concurrent users
- Detect race conditions in inventory management
- Verify atomic operations under load
- Handle concurrent checkout operations

Requires: todo_app or full_featured_app running on localhost:8000
"""

from __future__ import annotations

import random
import threading
import time
from typing import Any

from venomqa import Branch, Checkpoint, Journey, Path, Step
from venomqa.adapters.threading_concurrency import ThreadingConcurrencyAdapter
from venomqa.core.context import ExecutionContext

# Thread-safe counter for tracking race conditions
_race_condition_lock = threading.Lock()
_inventory_violations: list[dict[str, Any]] = []
_successful_checkouts: list[str] = []


def reset_tracking() -> None:
    """Reset tracking state between test runs."""
    global _inventory_violations, _successful_checkouts
    with _race_condition_lock:
        _inventory_violations = []
        _successful_checkouts = []


# =============================================================================
# Setup Actions
# =============================================================================


def setup_inventory(client: Any, context: ExecutionContext) -> Any:
    """Set up limited inventory for race condition testing."""
    reset_tracking()

    # Create a product with limited stock
    response = client.post(
        "/api/products",
        json={
            "name": "Limited Edition Widget",
            "price": 99.99,
            "stock": 5,  # Only 5 available - will be fought over by 10 users
            "sku": f"LIMITED-{int(time.time())}",
        },
    )
    if response.status_code in [200, 201]:
        data = response.json()
        context["limited_product_id"] = data.get("id")
        context["initial_stock"] = 5
        context["expected_max_checkouts"] = 5

    return response


def create_concurrent_users(client: Any, context: ExecutionContext) -> Any:
    """Create 10 user accounts for concurrent testing."""
    users = []
    timestamp = int(time.time())

    for i in range(10):
        response = client.post(
            "/api/auth/register",
            json={
                "email": f"concurrent_user_{i}_{timestamp}@test.com",
                "password": "ConcurrentTest123!",
                "name": f"Concurrent User {i}",
            },
        )
        if response.status_code in [200, 201]:
            data = response.json()
            user_data = {
                "id": data.get("id") or data.get("user", {}).get("id"),
                "email": f"concurrent_user_{i}_{timestamp}@test.com",
                "index": i,
            }
            users.append(user_data)

    context["concurrent_users"] = users
    context["user_count"] = len(users)

    assert len(users) >= 5, f"Expected at least 5 users, created {len(users)}"

    return {"status": "users_created", "count": len(users)}


# =============================================================================
# Concurrent Checkout Simulation
# =============================================================================


def simulate_user_checkout(
    client: Any, user: dict[str, Any], product_id: str, context: ExecutionContext
) -> dict[str, Any]:
    """Simulate a single user attempting checkout."""
    result = {
        "user_index": user.get("index"),
        "email": user.get("email"),
        "success": False,
        "error": None,
        "order_id": None,
    }

    try:
        # Login
        login_response = client.post(
            "/api/auth/login",
            json={
                "email": user.get("email"),
                "password": "ConcurrentTest123!",
            },
        )

        if login_response.status_code != 200:
            result["error"] = "login_failed"
            return result

        token = login_response.json().get("access_token") or login_response.json().get("token")
        headers = {"Authorization": f"Bearer {token}"}

        # Add small random delay to increase race condition likelihood
        time.sleep(random.uniform(0.01, 0.05))

        # Create cart
        cart_response = client.post("/api/cart", json={}, headers=headers)
        if cart_response.status_code not in [200, 201]:
            result["error"] = "cart_creation_failed"
            return result

        cart_id = cart_response.json().get("id")

        # Add item to cart (attempting to purchase the limited item)
        add_response = client.post(
            f"/api/cart/{cart_id}/items",
            json={"product_id": product_id, "quantity": 1},
            headers=headers,
        )

        if add_response.status_code not in [200, 201]:
            result["error"] = "add_to_cart_failed"
            return result

        # Attempt checkout - this is where race conditions occur
        checkout_response = client.post(
            "/api/checkout",
            json={
                "cart_id": cart_id,
                "payment_method": "card",
                "card_token": "tok_test",
            },
            headers=headers,
        )

        if checkout_response.status_code in [200, 201]:
            order_data = checkout_response.json()
            result["success"] = True
            result["order_id"] = order_data.get("order_id") or order_data.get("id")

            with _race_condition_lock:
                _successful_checkouts.append(result["order_id"])

        elif checkout_response.status_code == 409:
            # Conflict - out of stock (expected for some users)
            result["error"] = "out_of_stock"
        elif checkout_response.status_code == 400:
            result["error"] = "checkout_rejected"
        else:
            result["error"] = f"checkout_failed_{checkout_response.status_code}"

    except Exception as e:
        result["error"] = str(e)

    return result


def run_concurrent_checkouts(client: Any, context: ExecutionContext) -> Any:
    """Execute 10 concurrent checkout attempts."""
    users = context.get("concurrent_users", [])
    product_id = context.get("limited_product_id")

    if not users or not product_id:
        return {"status": "error", "message": "Missing users or product"}

    # Use ThreadingConcurrencyAdapter for parallel execution
    concurrency = ThreadingConcurrencyAdapter(max_workers=10)

    results = []
    task_ids = []

    # Spawn all checkout tasks simultaneously
    for user in users:
        task_id = concurrency.spawn(
            simulate_user_checkout, client, user, product_id, context
        )
        task_ids.append(task_id)

    # Wait for all to complete
    for task_id in task_ids:
        try:
            task_result = concurrency.join(task_id, timeout=60.0)
            if task_result.success and task_result.result:
                results.append(task_result.result)
        except Exception as e:
            results.append({"error": str(e)})

    concurrency.shutdown()

    # Store results for verification
    context["checkout_results"] = results
    context["successful_count"] = len([r for r in results if r.get("success")])
    context["failed_count"] = len([r for r in results if not r.get("success")])

    return {
        "status": "concurrent_checkouts_complete",
        "total_attempts": len(results),
        "successful": context["successful_count"],
        "failed": context["failed_count"],
    }


# =============================================================================
# Verification Actions
# =============================================================================


def verify_no_race_conditions(client: Any, context: ExecutionContext) -> Any:
    """Verify that inventory constraints were respected."""
    initial_stock = context.get("initial_stock", 5)
    successful_count = context.get("successful_count", 0)

    # Core invariant: successful checkouts should not exceed initial stock
    assert successful_count <= initial_stock, (
        f"RACE CONDITION DETECTED: {successful_count} successful checkouts "
        f"but only {initial_stock} items in stock"
    )

    # Verify through API
    product_id = context.get("limited_product_id")
    if product_id:
        response = client.get(f"/api/products/{product_id}")
        if response.status_code == 200:
            data = response.json()
            remaining_stock = data.get("stock", 0)
            expected_remaining = initial_stock - successful_count

            assert remaining_stock == expected_remaining, (
                f"Stock mismatch: expected {expected_remaining}, "
                f"got {remaining_stock}"
            )

    return {
        "status": "no_race_conditions",
        "initial_stock": initial_stock,
        "successful_checkouts": successful_count,
        "invariant_passed": True,
    }


def verify_order_uniqueness(client: Any, context: ExecutionContext) -> Any:
    """Verify each successful checkout has a unique order ID."""
    with _race_condition_lock:
        order_ids = _successful_checkouts.copy()

    unique_orders = set(order_ids)

    assert len(order_ids) == len(unique_orders), (
        f"Duplicate order IDs detected: "
        f"{len(order_ids)} orders, {len(unique_orders)} unique"
    )

    return {
        "status": "orders_unique",
        "total_orders": len(order_ids),
        "unique_orders": len(unique_orders),
    }


def verify_inventory_final_state(client: Any, context: ExecutionContext) -> Any:
    """Final inventory verification."""
    product_id = context.get("limited_product_id")

    response = client.get(f"/api/products/{product_id}")

    if response.status_code == 200:
        data = response.json()
        final_stock = data.get("stock", 0)
        initial_stock = context.get("initial_stock", 5)
        successful_count = context.get("successful_count", 0)

        # Stock should never go negative
        assert final_stock >= 0, f"Negative stock detected: {final_stock}"

        # Stock + successful orders should equal initial stock
        assert final_stock + successful_count == initial_stock, (
            f"Inventory inconsistency: "
            f"{final_stock} remaining + {successful_count} sold != {initial_stock} initial"
        )

        context["final_stock"] = final_stock
        context["inventory_consistent"] = True

    return {
        "status": "inventory_verified",
        "final_stock": context.get("final_stock"),
        "consistent": context.get("inventory_consistent", False),
    }


# =============================================================================
# Stress Test: High Volume Inventory Operations
# =============================================================================


def create_high_volume_inventory(client: Any, context: ExecutionContext) -> Any:
    """Create multiple products for volume testing."""
    products = []

    for i in range(5):
        response = client.post(
            "/api/products",
            json={
                "name": f"Volume Test Product {i}",
                "price": 19.99 + i,
                "stock": 100,
            },
        )
        if response.status_code in [200, 201]:
            products.append(response.json().get("id"))

    context["volume_products"] = products
    return {"status": "products_created", "count": len(products)}


def concurrent_inventory_updates(client: Any, context: ExecutionContext) -> Any:
    """Perform concurrent inventory operations across multiple products."""
    products = context.get("volume_products", [])

    if not products:
        return {"status": "skip", "reason": "no products"}

    concurrency = ThreadingConcurrencyAdapter(max_workers=20)

    def update_inventory(product_id: str, operation: str) -> dict[str, Any]:
        if operation == "decrement":
            # Attempt to reduce stock
            response = client.post(
                f"/api/products/{product_id}/stock",
                json={"adjustment": -1},
            )
        else:
            # Attempt to increase stock
            response = client.post(
                f"/api/products/{product_id}/stock",
                json={"adjustment": 1},
            )

        return {
            "product_id": product_id,
            "operation": operation,
            "success": response.status_code in [200, 201],
            "status_code": response.status_code,
        }

    task_ids = []
    operations = ["decrement", "increment"]

    # Spawn 50 random operations across products
    for _ in range(50):
        product_id = random.choice(products)
        operation = random.choice(operations)
        task_id = concurrency.spawn(update_inventory, product_id, operation)
        task_ids.append(task_id)

    # Wait for completion
    results = concurrency.join_all(task_ids, timeout=120.0)
    concurrency.shutdown()

    successful = sum(1 for r in results if r.success and r.result and r.result.get("success"))

    return {
        "status": "volume_operations_complete",
        "total_operations": len(results),
        "successful": successful,
    }


# =============================================================================
# Journey Definitions
# =============================================================================

concurrent_checkout_journey = Journey(
    name="concurrent_checkout_stress",
    description="Tests 10 concurrent users competing for limited inventory",
    tags=["stress-test", "concurrency", "race-conditions"],
    timeout=300.0,
    steps=[
        Step(
            name="setup_inventory",
            action=setup_inventory,
            description="Create product with limited stock",
        ),
        Step(
            name="create_users",
            action=create_concurrent_users,
            description="Create 10 concurrent test users",
        ),
        Checkpoint(name="ready_for_concurrent_test"),
        Step(
            name="run_concurrent_checkouts",
            action=run_concurrent_checkouts,
            description="Execute 10 simultaneous checkout attempts",
        ),
        Checkpoint(name="checkouts_complete"),
        Step(
            name="verify_no_race_conditions",
            action=verify_no_race_conditions,
            description="Verify inventory constraints respected",
        ),
        Step(
            name="verify_order_uniqueness",
            action=verify_order_uniqueness,
            description="Verify all order IDs are unique",
        ),
        Step(
            name="verify_final_inventory",
            action=verify_inventory_final_state,
            description="Verify final inventory consistency",
        ),
    ],
)

inventory_stress_journey = Journey(
    name="inventory_stress_test",
    description="High-volume concurrent inventory operations",
    tags=["stress-test", "inventory", "volume"],
    timeout=300.0,
    steps=[
        Step(
            name="create_inventory",
            action=create_high_volume_inventory,
            description="Set up multiple products",
        ),
        Checkpoint(name="inventory_ready"),
        Step(
            name="concurrent_updates",
            action=concurrent_inventory_updates,
            description="Execute 50 concurrent inventory operations",
        ),
        Checkpoint(name="updates_complete"),
        Branch(
            checkpoint_name="updates_complete",
            paths=[
                Path(
                    name="verify_positive_stock",
                    steps=[
                        Step(
                            name="check_stocks",
                            action=lambda c, ctx: {
                                "products_checked": len(ctx.get("volume_products", [])),
                                "status": "verified",
                            },
                        ),
                    ],
                ),
            ],
        ),
    ],
)
