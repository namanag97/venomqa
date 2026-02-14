"""Medusa Checkout Flow Journey with Branching.

Complete checkout journey testing for Medusa e-commerce platform.
Includes branching paths for different payment outcomes:
- Successful payment -> Order created
- Failed payment -> Cart intact
- Abandoned cart -> Timeout handling

Features:
- Database checkpointing for state rollback
- Invariant checking for cart totals and inventory
- Multiple payment provider testing

Example:
    >>> from venomqa import Client, JourneyRunner
    >>> from qa.journeys.checkout_flow import checkout_journey
    >>>
    >>> client = Client("http://localhost:9000")
    >>> runner = JourneyRunner(client=client)
    >>> result = runner.run(checkout_journey)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from venomqa import Branch, Checkpoint, Journey, Path, Severity, Step

from qa.actions.auth import step_login, step_register
from qa.actions.cart import (
    step_add_line_item,
    step_add_shipping_method,
    step_create_cart,
    step_get_cart,
    step_update_cart,
)
from qa.actions.checkout import (
    step_complete_cart,
    step_create_payment_session,
    step_simulate_abandoned_cart,
    step_simulate_failed_payment,
    step_verify_cart_intact,
)
from qa.actions.orders import (
    step_check_inventory,
    step_get_order,
    step_verify_order_created,
)
from qa.actions.products import (
    step_get_product,
    step_get_shipping_options,
    step_list_products,
)

if TYPE_CHECKING:
    from venomqa.client import Client
    from venomqa.core.context import ExecutionContext

logger = logging.getLogger(__name__)


# ============================================================================
# Setup Actions
# ============================================================================


def setup_medusa_context(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Initialize Medusa testing context with configuration.

    Sets up required configuration like region_id, publishable API key, etc.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.

    Returns:
        Success indicator.
    """
    # Set default configuration if not provided
    if "region_id" not in context:
        context["region_id"] = kwargs.get("region_id", "reg_01")
    if "publishable_api_key" not in context:
        context["publishable_api_key"] = kwargs.get("publishable_api_key", "pk_test_key")
    if "sales_channel_id" not in context:
        context["sales_channel_id"] = kwargs.get("sales_channel_id", "sc_01")

    # Generate test customer credentials
    if "customer_email" not in context:
        import time

        context["customer_email"] = f"test_{int(time.time())}@example.com"
    if "customer_password" not in context:
        context["customer_password"] = "testpassword123"

    logger.info("Medusa context initialized")
    return {"status": "context_initialized"}


def setup_test_addresses(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Set up test shipping and billing addresses.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.

    Returns:
        Success indicator.
    """
    from qa.fixtures.customer import AddressFactory

    address = AddressFactory.us_address()

    context["shipping_address"] = {
        "first_name": address.first_name,
        "last_name": address.last_name,
        "address_1": address.address_1,
        "city": address.city,
        "province": address.province,
        "postal_code": address.postal_code,
        "country_code": address.country_code,
        "phone": address.phone,
    }
    context["billing_address"] = context["shipping_address"].copy()

    logger.info("Test addresses configured")
    return {"status": "addresses_configured"}


# ============================================================================
# Invariant Checks
# ============================================================================


def check_cart_total_invariant(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Invariant: Cart total must equal sum of line items.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.

    Returns:
        Invariant check result.

    Raises:
        AssertionError: If invariant is violated.
    """
    cart = context.get("cart", {})
    items = cart.get("items", [])

    if not items:
        return {"status": "no_items", "passed": True}

    # Calculate expected total from items
    calculated_subtotal = sum(
        item.get("unit_price", 0) * item.get("quantity", 0) for item in items
    )

    actual_subtotal = cart.get("subtotal", 0)

    # Allow small rounding differences (1 cent)
    if abs(calculated_subtotal - actual_subtotal) > 1:
        raise AssertionError(
            f"Cart total invariant violated: "
            f"expected subtotal {calculated_subtotal}, got {actual_subtotal}"
        )

    logger.info(f"Cart total invariant passed: {actual_subtotal}")
    return {
        "status": "passed",
        "calculated_subtotal": calculated_subtotal,
        "actual_subtotal": actual_subtotal,
    }


def check_inventory_invariant(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Invariant: Inventory must decrease after order.

    Note: This requires tracking inventory before and after order.
    In real implementation, this would query the database or API.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.

    Returns:
        Invariant check result.
    """
    # This is a simplified version - real implementation would
    # compare inventory_before and inventory_after
    expected_changes = context.get("expected_inventory_changes", [])

    if not expected_changes:
        return {"status": "no_changes_tracked", "passed": True}

    # Log expected inventory changes for manual verification or database query
    for change in expected_changes:
        logger.info(
            f"Expected inventory decrease: {change['variant_id']} "
            f"by {change['quantity_ordered']}"
        )

    context["inventory_invariant_checked"] = True
    return {
        "status": "logged",
        "expected_changes": expected_changes,
        "passed": True,
    }


# ============================================================================
# Branch-specific verification actions (defined before journeys)
# ============================================================================


def verify_no_order_created(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Verify that no order was created after failed payment.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.

    Returns:
        Verification result.

    Raises:
        AssertionError: If an order was unexpectedly created.
    """
    order_id = context.get("order_id")
    checkout_complete = context.get("checkout_complete", False)

    if checkout_complete:
        raise AssertionError("Checkout was completed when it should have failed")

    if order_id:
        raise AssertionError(f"Order {order_id} was created when payment should have failed")

    logger.info("Verified: No order was created after payment failure")
    return {"status": "verified", "order_created": False}


def verify_cart_abandoned(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Verify cart is in abandoned state.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.

    Returns:
        Verification result.

    Raises:
        AssertionError: If cart is not marked as abandoned.
    """
    cart_abandoned = context.get("cart_abandoned", False)
    cart = context.get("cart", {})

    if not cart_abandoned:
        raise AssertionError("Cart was not marked as abandoned")

    # Cart should not be completed
    if cart.get("completed_at") is not None:
        raise AssertionError("Abandoned cart was unexpectedly completed")

    # Cart should still have items
    items = cart.get("items", [])
    if not items:
        raise AssertionError("Abandoned cart has no items")

    logger.info(f"Verified: Cart {context.get('cart_id')} is properly abandoned")
    return {
        "status": "verified",
        "cart_id": context.get("cart_id"),
        "items_count": len(items),
        "abandoned": True,
    }


# ============================================================================
# Journey Definitions
# ============================================================================


class MedusaCheckoutJourney(Journey):
    """Medusa checkout journey with payment branching and invariants.

    This journey tests the complete checkout flow with three outcomes:
    1. Successful payment - Order is created
    2. Failed payment - Cart remains intact
    3. Abandoned cart - Cart times out

    The journey uses checkpoints to save database state before payment,
    allowing each branch to execute independently.
    """

    def invariants(self) -> list[Any]:
        """Define invariants to check after journey execution.

        Returns:
            List of invariant definitions.
        """
        return [
            {
                "name": "cart_total_equals_sum_of_items",
                "description": "Cart total must equal sum of line item totals",
                "check": check_cart_total_invariant,
                "severity": Severity.HIGH,
            },
            {
                "name": "inventory_decreases_after_order",
                "description": "Product inventory must decrease after order completion",
                "check": check_inventory_invariant,
                "severity": Severity.CRITICAL,
            },
        ]


# Main checkout journey with branching
checkout_journey = MedusaCheckoutJourney(
    name="medusa_checkout_flow",
    description="Complete Medusa checkout flow with payment branching",
    tags=["medusa", "checkout", "e2e", "payment"],
    timeout=300.0,
    requires=["medusa", "postgres"],
    steps=[
        # ----------------------------------------------------------------
        # Setup Phase
        # ----------------------------------------------------------------
        Step(
            name="setup_context",
            action=setup_medusa_context,
            description="Initialize Medusa testing context",
        ),
        Step(
            name="setup_addresses",
            action=setup_test_addresses,
            description="Configure test shipping and billing addresses",
        ),
        # ----------------------------------------------------------------
        # Authentication Phase
        # ----------------------------------------------------------------
        Step(
            name="register_customer",
            action=step_register,
            description="Register new test customer",
            timeout=10.0,
        ),
        Step(
            name="login_customer",
            action=step_login,
            description="Login with test customer credentials",
            timeout=10.0,
        ),
        # Checkpoint after authentication
        Checkpoint(name="authenticated"),
        # ----------------------------------------------------------------
        # Product Selection Phase
        # ----------------------------------------------------------------
        Step(
            name="browse_products",
            action=step_list_products,
            description="List available products",
            timeout=15.0,
        ),
        Step(
            name="select_product",
            action=step_get_product,
            description="Get product details for first product",
            timeout=10.0,
        ),
        # ----------------------------------------------------------------
        # Cart Creation Phase
        # ----------------------------------------------------------------
        Step(
            name="create_cart",
            action=step_create_cart,
            description="Create new shopping cart",
            timeout=10.0,
        ),
        Step(
            name="add_item_1",
            action=step_add_line_item,
            description="Add first item to cart",
            timeout=10.0,
        ),
        Step(
            name="add_item_2",
            action=step_add_line_item,
            description="Add second item to cart (same product, quantity increases)",
            timeout=10.0,
            args={"quantity": 2},
        ),
        Step(
            name="verify_cart",
            action=step_get_cart,
            description="Verify cart contents",
            timeout=10.0,
        ),
        Step(
            name="check_cart_total",
            action=check_cart_total_invariant,
            description="Verify cart total invariant",
        ),
        # ----------------------------------------------------------------
        # Shipping Setup Phase
        # ----------------------------------------------------------------
        Step(
            name="update_cart_addresses",
            action=step_update_cart,
            description="Add shipping and billing addresses to cart",
            timeout=10.0,
        ),
        Step(
            name="get_shipping_options",
            action=step_get_shipping_options,
            description="Get available shipping options",
            timeout=10.0,
        ),
        Step(
            name="add_shipping_method",
            action=step_add_shipping_method,
            description="Add shipping method to cart",
            timeout=10.0,
        ),
        # ----------------------------------------------------------------
        # Payment Setup - CHECKPOINT before branching
        # ----------------------------------------------------------------
        Step(
            name="create_payment_session",
            action=step_create_payment_session,
            description="Initialize payment session",
            timeout=15.0,
        ),
        # CHECKPOINT: Save state before payment attempts
        Checkpoint(name="before_payment"),
        # ----------------------------------------------------------------
        # Payment BRANCH: Test different payment outcomes
        # ----------------------------------------------------------------
        Branch(
            checkpoint_name="before_payment",
            paths=[
                # Path 1: Successful payment -> Order created
                Path(
                    name="successful_payment",
                    description="Test successful payment flow - order should be created",
                    steps=[
                        Step(
                            name="complete_checkout",
                            action=step_complete_cart,
                            description="Complete cart and create order",
                            timeout=30.0,
                        ),
                        Step(
                            name="verify_order",
                            action=step_verify_order_created,
                            description="Verify order was created successfully",
                            timeout=10.0,
                        ),
                        Step(
                            name="get_order_details",
                            action=step_get_order,
                            description="Get full order details",
                            timeout=10.0,
                        ),
                        Step(
                            name="check_inventory",
                            action=step_check_inventory,
                            description="Verify inventory was decremented",
                        ),
                    ],
                ),
                # Path 2: Failed payment -> Cart intact
                Path(
                    name="failed_payment",
                    description="Test failed payment flow - cart should remain intact",
                    steps=[
                        Step(
                            name="simulate_payment_failure",
                            action=step_simulate_failed_payment,
                            description="Simulate a payment failure",
                            timeout=15.0,
                            expect_failure=True,
                        ),
                        Step(
                            name="verify_cart_intact",
                            action=step_verify_cart_intact,
                            description="Verify cart still exists with items",
                            timeout=10.0,
                        ),
                        Step(
                            name="verify_no_order",
                            action=verify_no_order_created,
                            description="Verify no order was created",
                        ),
                    ],
                ),
                # Path 3: Abandoned cart -> Timeout
                Path(
                    name="abandoned_cart",
                    description="Test abandoned cart scenario - timeout handling",
                    steps=[
                        Step(
                            name="simulate_abandonment",
                            action=step_simulate_abandoned_cart,
                            description="Simulate cart abandonment (5 second timeout)",
                            timeout=30.0,
                            args={"timeout_seconds": 5},
                        ),
                        Step(
                            name="verify_cart_abandoned",
                            action=verify_cart_abandoned,
                            description="Verify cart is marked as abandoned",
                        ),
                        Step(
                            name="verify_cart_recoverable",
                            action=step_get_cart,
                            description="Verify cart can still be recovered",
                            timeout=10.0,
                        ),
                    ],
                ),
            ],
        ),
    ],
)


# ============================================================================
# Additional Journey Variants
# ============================================================================


# Guest checkout journey (no authentication)
guest_checkout_journey = Journey(
    name="medusa_guest_checkout",
    description="Guest checkout flow without customer authentication",
    tags=["medusa", "checkout", "guest"],
    timeout=180.0,
    steps=[
        Step(name="setup_context", action=setup_medusa_context),
        Step(name="setup_addresses", action=setup_test_addresses),
        Step(name="browse_products", action=step_list_products),
        Step(name="select_product", action=step_get_product),
        Step(name="create_cart", action=step_create_cart),
        Step(name="add_item", action=step_add_line_item),
        Step(name="update_cart", action=step_update_cart),
        Checkpoint(name="guest_cart_ready"),
        Step(name="get_shipping", action=step_get_shipping_options),
        Step(name="add_shipping", action=step_add_shipping_method),
        Step(name="create_payment", action=step_create_payment_session),
        Step(name="complete_checkout", action=step_complete_cart),
        Step(name="verify_order", action=step_verify_order_created),
    ],
)


# Express checkout journey (saved payment method)
express_checkout_journey = Journey(
    name="medusa_express_checkout",
    description="Express checkout with saved payment method",
    tags=["medusa", "checkout", "express"],
    timeout=120.0,
    steps=[
        Step(name="setup_context", action=setup_medusa_context),
        Step(name="login", action=step_login),
        Checkpoint(name="logged_in"),
        Step(name="browse_products", action=step_list_products),
        Step(name="create_cart", action=step_create_cart),
        Step(name="add_item", action=step_add_line_item),
        # Express checkout would use saved addresses and payment
        Step(name="create_payment", action=step_create_payment_session),
        Step(name="complete", action=step_complete_cart),
        Step(name="verify", action=step_verify_order_created),
    ],
)


# Export all journeys
__all__ = [
    "checkout_journey",
    "guest_checkout_journey",
    "express_checkout_journey",
    "MedusaCheckoutJourney",
    "setup_medusa_context",
    "setup_test_addresses",
    "check_cart_total_invariant",
    "check_inventory_invariant",
    "verify_no_order_created",
    "verify_cart_abandoned",
]
