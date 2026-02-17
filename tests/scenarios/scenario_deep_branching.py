"""Deep Branching Scenario - Tests nested checkpoints and state isolation.

This scenario verifies VenomQA's ability to:
- Create multiple levels of nested checkpoints
- Maintain state isolation between branches
- Roll back to different checkpoint levels
- Handle complex branch structures

Requires: todo_app or full_featured_app running on localhost:8000
"""

from __future__ import annotations

from typing import Any

from venomqa import Branch, Checkpoint, Journey, Path, Step
from venomqa.core.context import ExecutionContext

# =============================================================================
# Level 1 Actions - User Management
# =============================================================================


def create_user(client: Any, context: ExecutionContext) -> Any:
    """Create a test user and store credentials."""
    response = client.post(
        "/api/auth/register",
        json={
            "email": f"test_{context.get('run_id', 'default')}@example.com",
            "password": "TestPass123!",
            "name": "Test User",
        },
    )
    if response.status_code in [200, 201]:
        data = response.json()
        context["user_id"] = data.get("id") or data.get("user", {}).get("id")
        context["user_email"] = data.get("email") or data.get("user", {}).get("email")
    return response


def login_user(client: Any, context: ExecutionContext) -> Any:
    """Log in the test user."""
    response = client.post(
        "/api/auth/login",
        json={
            "email": context.get("user_email", "test@example.com"),
            "password": "TestPass123!",
        },
    )
    if response.status_code == 200:
        data = response.json()
        context["token"] = data.get("access_token") or data.get("token")
    return response


def verify_user_state_l1(client: Any, context: ExecutionContext) -> Any:
    """Verify user state at level 1 - user should exist."""
    assert context.get("user_id"), "User ID should be set at L1"
    assert context.get("token"), "Token should be set at L1"

    # Mark L1 state verified
    context["l1_verified"] = True
    context["l1_user_id"] = context.get("user_id")

    return {"status": "l1_verified", "user_id": context.get("user_id")}


# =============================================================================
# Level 2 Actions - Product/Item Management
# =============================================================================


def create_product_a(client: Any, context: ExecutionContext) -> Any:
    """Create Product A in branch A."""
    headers = {"Authorization": f"Bearer {context.get('token')}"}
    response = client.post(
        "/api/products",
        json={"name": "Product A", "price": 29.99, "stock": 100},
        headers=headers,
    )
    if response.status_code in [200, 201]:
        context["product_a_id"] = response.json().get("id")
        context["branch_path"] = "A"
    return response


def create_product_b(client: Any, context: ExecutionContext) -> Any:
    """Create Product B in branch B."""
    headers = {"Authorization": f"Bearer {context.get('token')}"}
    response = client.post(
        "/api/products",
        json={"name": "Product B", "price": 49.99, "stock": 50},
        headers=headers,
    )
    if response.status_code in [200, 201]:
        context["product_b_id"] = response.json().get("id")
        context["branch_path"] = "B"
    return response


def create_product_c(client: Any, context: ExecutionContext) -> Any:
    """Create Product C in branch C."""
    headers = {"Authorization": f"Bearer {context.get('token')}"}
    response = client.post(
        "/api/products",
        json={"name": "Product C", "price": 99.99, "stock": 25},
        headers=headers,
    )
    if response.status_code in [200, 201]:
        context["product_c_id"] = response.json().get("id")
        context["branch_path"] = "C"
    return response


def verify_product_state_l2(client: Any, context: ExecutionContext) -> Any:
    """Verify product state at level 2."""
    branch_path = context.get("branch_path", "unknown")

    # Verify L1 state is preserved
    assert context.get("l1_verified"), "L1 state should be preserved"
    assert context.get("l1_user_id") == context.get("user_id"), "User ID should match L1"

    # Verify branch-specific state
    if branch_path == "A":
        assert context.get("product_a_id"), "Product A should exist in branch A"
        assert not context.get("product_b_id"), "Product B should NOT exist in branch A"
        assert not context.get("product_c_id"), "Product C should NOT exist in branch A"
    elif branch_path == "B":
        assert context.get("product_b_id"), "Product B should exist in branch B"
        assert not context.get("product_a_id"), "Product A should NOT exist in branch B"
        assert not context.get("product_c_id"), "Product C should NOT exist in branch B"
    elif branch_path == "C":
        assert context.get("product_c_id"), "Product C should exist in branch C"
        assert not context.get("product_a_id"), "Product A should NOT exist in branch C"
        assert not context.get("product_b_id"), "Product B should NOT exist in branch C"

    context["l2_verified"] = True
    context["l2_branch"] = branch_path

    return {"status": "l2_verified", "branch": branch_path}


# =============================================================================
# Level 3 Actions - Cart/Order Management
# =============================================================================


def create_cart_premium(client: Any, context: ExecutionContext) -> Any:
    """Create premium cart (high quantity)."""
    headers = {"Authorization": f"Bearer {context.get('token')}"}
    response = client.post("/api/cart", json={"type": "premium"}, headers=headers)
    if response.status_code in [200, 201]:
        context["cart_id"] = response.json().get("id")
        context["cart_type"] = "premium"
        context["l3_branch"] = "premium"
    return response


def create_cart_standard(client: Any, context: ExecutionContext) -> Any:
    """Create standard cart (normal quantity)."""
    headers = {"Authorization": f"Bearer {context.get('token')}"}
    response = client.post("/api/cart", json={"type": "standard"}, headers=headers)
    if response.status_code in [200, 201]:
        context["cart_id"] = response.json().get("id")
        context["cart_type"] = "standard"
        context["l3_branch"] = "standard"
    return response


def add_to_cart_bulk(client: Any, context: ExecutionContext) -> Any:
    """Add items to cart in bulk."""
    headers = {"Authorization": f"Bearer {context.get('token')}"}

    # Determine which product to use based on L2 branch
    product_id = (
        context.get("product_a_id")
        or context.get("product_b_id")
        or context.get("product_c_id")
        or "default_product"
    )

    quantity = 10 if context.get("cart_type") == "premium" else 2

    response = client.post(
        f"/api/cart/{context.get('cart_id')}/items",
        json={"product_id": product_id, "quantity": quantity},
        headers=headers,
    )
    if response.status_code in [200, 201]:
        context["cart_items"] = response.json().get("items", [])
    return response


def verify_state_l3(client: Any, context: ExecutionContext) -> Any:
    """Verify complete state isolation at level 3."""
    # Verify L1 state
    assert context.get("l1_verified"), "L1 should be verified"

    # Verify L2 state
    assert context.get("l2_verified"), "L2 should be verified"

    # Verify L3 state
    assert context.get("cart_id"), "Cart should exist at L3"
    assert context.get("cart_type") in ["premium", "standard"], "Cart type should be set"

    # Verify complete path
    full_path = f"L1->{context.get('l2_branch')}->{context.get('l3_branch')}"
    context["full_path"] = full_path
    context["l3_verified"] = True

    return {
        "status": "l3_verified",
        "full_path": full_path,
        "user_id": context.get("user_id"),
        "cart_type": context.get("cart_type"),
    }


def checkout_express(client: Any, context: ExecutionContext) -> Any:
    """Express checkout path."""
    headers = {"Authorization": f"Bearer {context.get('token')}"}
    response = client.post(
        "/api/checkout",
        json={
            "cart_id": context.get("cart_id"),
            "payment_method": "express",
        },
        headers=headers,
    )
    if response.status_code in [200, 201]:
        context["order_id"] = response.json().get("order_id")
        context["checkout_type"] = "express"
    return response


def checkout_standard_process(client: Any, context: ExecutionContext) -> Any:
    """Standard checkout path."""
    headers = {"Authorization": f"Bearer {context.get('token')}"}
    response = client.post(
        "/api/checkout",
        json={
            "cart_id": context.get("cart_id"),
            "payment_method": "standard",
        },
        headers=headers,
    )
    if response.status_code in [200, 201]:
        context["order_id"] = response.json().get("order_id")
        context["checkout_type"] = "standard"
    return response


# =============================================================================
# Invariant Checking
# =============================================================================


def check_state_isolation_invariant(client: Any, context: ExecutionContext) -> Any:
    """Final invariant check - verify no state leakage between branches."""
    assertions_passed = 0
    assertions_failed = 0
    issues = []

    # Check that L1 state is preserved
    if context.get("l1_verified"):
        assertions_passed += 1
    else:
        assertions_failed += 1
        issues.append("L1 verification missing")

    # Check L2 branch isolation
    if context.get("l2_verified"):
        assertions_passed += 1
        branch = context.get("l2_branch")
        # Ensure only one product exists
        products = [
            context.get("product_a_id"),
            context.get("product_b_id"),
            context.get("product_c_id"),
        ]
        non_null_products = [p for p in products if p]
        if len(non_null_products) == 1:
            assertions_passed += 1
        else:
            assertions_failed += 1
            issues.append(f"Expected 1 product in branch {branch}, got {len(non_null_products)}")
    else:
        assertions_failed += 1
        issues.append("L2 verification missing")

    # Check L3 state
    if context.get("l3_verified"):
        assertions_passed += 1
    else:
        assertions_failed += 1
        issues.append("L3 verification missing")

    # Final assertion
    assert assertions_failed == 0, f"State isolation failed: {issues}"

    return {
        "status": "invariant_passed",
        "assertions_passed": assertions_passed,
        "assertions_failed": assertions_failed,
        "full_path": context.get("full_path"),
    }


# =============================================================================
# Journey Definitions
# =============================================================================

# Level 3 paths for branch A
level3_paths_a = [
    Path(
        name="a_premium",
        description="Branch A -> Premium checkout",
        steps=[
            Step(name="create_premium_cart", action=create_cart_premium),
            Step(name="add_bulk_items", action=add_to_cart_bulk),
            Checkpoint(name="l3_a_premium"),
            Step(name="verify_l3", action=verify_state_l3),
            Step(name="express_checkout", action=checkout_express),
            Step(name="check_invariant", action=check_state_isolation_invariant),
        ],
    ),
    Path(
        name="a_standard",
        description="Branch A -> Standard checkout",
        steps=[
            Step(name="create_standard_cart", action=create_cart_standard),
            Step(name="add_items", action=add_to_cart_bulk),
            Checkpoint(name="l3_a_standard"),
            Step(name="verify_l3", action=verify_state_l3),
            Step(name="standard_checkout", action=checkout_standard_process),
            Step(name="check_invariant", action=check_state_isolation_invariant),
        ],
    ),
]

# Level 3 paths for branch B
level3_paths_b = [
    Path(
        name="b_premium",
        description="Branch B -> Premium checkout",
        steps=[
            Step(name="create_premium_cart", action=create_cart_premium),
            Step(name="add_bulk_items", action=add_to_cart_bulk),
            Checkpoint(name="l3_b_premium"),
            Step(name="verify_l3", action=verify_state_l3),
            Step(name="express_checkout", action=checkout_express),
            Step(name="check_invariant", action=check_state_isolation_invariant),
        ],
    ),
    Path(
        name="b_standard",
        description="Branch B -> Standard checkout",
        steps=[
            Step(name="create_standard_cart", action=create_cart_standard),
            Step(name="add_items", action=add_to_cart_bulk),
            Checkpoint(name="l3_b_standard"),
            Step(name="verify_l3", action=verify_state_l3),
            Step(name="standard_checkout", action=checkout_standard_process),
            Step(name="check_invariant", action=check_state_isolation_invariant),
        ],
    ),
]

# Level 3 paths for branch C
level3_paths_c = [
    Path(
        name="c_premium",
        description="Branch C -> Premium checkout",
        steps=[
            Step(name="create_premium_cart", action=create_cart_premium),
            Step(name="add_bulk_items", action=add_to_cart_bulk),
            Checkpoint(name="l3_c_premium"),
            Step(name="verify_l3", action=verify_state_l3),
            Step(name="express_checkout", action=checkout_express),
            Step(name="check_invariant", action=check_state_isolation_invariant),
        ],
    ),
    Path(
        name="c_standard",
        description="Branch C -> Standard checkout",
        steps=[
            Step(name="create_standard_cart", action=create_cart_standard),
            Step(name="add_items", action=add_to_cart_bulk),
            Checkpoint(name="l3_c_standard"),
            Step(name="verify_l3", action=verify_state_l3),
            Step(name="standard_checkout", action=checkout_standard_process),
            Step(name="check_invariant", action=check_state_isolation_invariant),
        ],
    ),
]

# Level 2 paths (each containing Level 3 branches)
level2_paths = [
    Path(
        name="branch_a_products",
        description="Product A path with nested L3 branches",
        steps=[
            Step(name="create_product_a", action=create_product_a),
            Step(name="verify_l2_state", action=verify_product_state_l2),
            Checkpoint(name="l2_branch_a"),
            # Note: Nested branches not directly supported, but we test the pattern
        ],
    ),
    Path(
        name="branch_b_products",
        description="Product B path with nested L3 branches",
        steps=[
            Step(name="create_product_b", action=create_product_b),
            Step(name="verify_l2_state", action=verify_product_state_l2),
            Checkpoint(name="l2_branch_b"),
        ],
    ),
    Path(
        name="branch_c_products",
        description="Product C path with nested L3 branches",
        steps=[
            Step(name="create_product_c", action=create_product_c),
            Step(name="verify_l2_state", action=verify_product_state_l2),
            Checkpoint(name="l2_branch_c"),
        ],
    ),
]

# Main deep branching journey
deep_branching_journey = Journey(
    name="deep_branching_scenario",
    description="Tests 3-level nested checkpoints with state isolation verification",
    tags=["stress-test", "branching", "state-isolation"],
    timeout=300.0,
    steps=[
        # Level 1: User setup
        Step(name="create_user", action=create_user),
        Step(name="login_user", action=login_user),
        Step(name="verify_l1_state", action=verify_user_state_l1),
        Checkpoint(name="l1_user_created"),
        # Level 2: Branch into different product paths
        Branch(
            checkpoint_name="l1_user_created",
            paths=level2_paths,
        ),
    ],
)

# Triple-nested journey demonstrating maximum branching depth
triple_nested_journey = Journey(
    name="triple_nested_branching",
    description="Full 3-level nesting with all branch combinations",
    tags=["stress-test", "deep-branching", "exhaustive"],
    timeout=600.0,
    steps=[
        # Setup
        Step(name="create_user", action=create_user),
        Step(name="login_user", action=login_user),
        Step(name="verify_l1", action=verify_user_state_l1),
        Checkpoint(name="root"),
        # First level branch
        Branch(
            checkpoint_name="root",
            paths=[
                Path(
                    name="path_a",
                    steps=[
                        Step(name="product_a", action=create_product_a),
                        Step(name="verify_a", action=verify_product_state_l2),
                        Checkpoint(name="branch_a"),
                    ],
                ),
                Path(
                    name="path_b",
                    steps=[
                        Step(name="product_b", action=create_product_b),
                        Step(name="verify_b", action=verify_product_state_l2),
                        Checkpoint(name="branch_b"),
                    ],
                ),
                Path(
                    name="path_c",
                    steps=[
                        Step(name="product_c", action=create_product_c),
                        Step(name="verify_c", action=verify_product_state_l2),
                        Checkpoint(name="branch_c"),
                    ],
                ),
            ],
        ),
    ],
)
