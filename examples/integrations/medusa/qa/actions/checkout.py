"""Medusa Store API - Checkout Actions.

Handles payment and checkout including payment sessions and cart completion.

Medusa API v2 Endpoints:
    - POST /store/payment-collections - Initialize payment collection
    - POST /store/payment-collections/:id/payment-sessions - Create payment session
    - POST /store/carts/:id/complete - Complete cart and create order
    - GET /store/payment-providers - List payment providers

Example:
    >>> from venomqa import Client
    >>> from examples.medusa_integration.qa.actions.checkout import (
    ...     create_payment_session, complete_cart
    ... )
    >>>
    >>> client = Client("http://localhost:9000")
    >>> ctx = {"cart_id": "cart_123"}
    >>> create_payment_session(client, ctx)
    >>> complete_cart(client, ctx)
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from venomqa.client import Client
    from venomqa.core.context import ExecutionContext

logger = logging.getLogger(__name__)


def initialize_payment_collection(
    client: Client,
    context: ExecutionContext,
    cart_id: str | None = None,
) -> Any:
    """Initialize a payment collection for the cart.

    This is the first step in the checkout process. Creates a payment
    collection that can hold payment sessions.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        cart_id: Cart ID (default: from context).

    Returns:
        HTTP response with payment collection data.

    Context Updates:
        - payment_collection_id: Created payment collection ID
        - payment_collection: Full payment collection object
    """
    cart_id = cart_id or context.get("cart_id")
    if not cart_id:
        raise ValueError("No cart_id provided or found in context")

    # First, get the cart to get the payment collection ID if it exists
    headers = _get_checkout_headers(context)

    cart_response = client.get(f"/store/carts/{cart_id}", headers=headers)
    if cart_response.status_code == 200:
        cart_data = cart_response.json()
        cart = cart_data.get("cart", {})
        payment_collection = cart.get("payment_collection")

        if payment_collection:
            context["payment_collection_id"] = payment_collection.get("id")
            context["payment_collection"] = payment_collection
            logger.info(f"Found existing payment collection: {payment_collection.get('id')}")
            return cart_response

    # If no payment collection exists, create one via the cart
    payload = {
        "cart_id": cart_id,
    }

    response = client.post("/store/payment-collections", json=payload, headers=headers)

    if response.status_code in [200, 201]:
        data = response.json()
        payment_collection = data.get("payment_collection", {})
        context["payment_collection_id"] = payment_collection.get("id")
        context["payment_collection"] = payment_collection
        logger.info(f"Created payment collection: {payment_collection.get('id')}")

    return response


def create_payment_session(
    client: Client,
    context: ExecutionContext,
    provider_id: str = "pp_system_default",
    payment_collection_id: str | None = None,
) -> Any:
    """Create a payment session for checkout.

    Initializes a payment session with the specified provider.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        provider_id: Payment provider ID (default: system default).
        payment_collection_id: Payment collection ID (default: from context).

    Returns:
        HTTP response with payment session data.

    Context Updates:
        - payment_session_id: Created payment session ID
        - payment_session: Full payment session object
    """
    payment_collection_id = payment_collection_id or context.get("payment_collection_id")

    # If no payment collection, initialize one first
    if not payment_collection_id:
        init_response = initialize_payment_collection(client, context)
        if init_response.status_code not in [200, 201]:
            return init_response
        payment_collection_id = context.get("payment_collection_id")

    if not payment_collection_id:
        raise ValueError("Could not get or create payment_collection_id")

    payload = {
        "provider_id": provider_id,
    }

    headers = _get_checkout_headers(context)

    response = client.post(
        f"/store/payment-collections/{payment_collection_id}/payment-sessions",
        json=payload,
        headers=headers,
    )

    if response.status_code in [200, 201]:
        data = response.json()
        payment_session = data.get("payment_session", {})
        context["payment_session_id"] = payment_session.get("id")
        context["payment_session"] = payment_session
        logger.info(f"Created payment session: {payment_session.get('id')}")

    return response


def complete_cart(
    client: Client,
    context: ExecutionContext,
    cart_id: str | None = None,
) -> Any:
    """Complete the cart and create an order.

    This is the final step in checkout. Converts the cart to an order.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        cart_id: Cart ID (default: from context).

    Returns:
        HTTP response with order data.

    Context Updates:
        - order_id: Created order ID
        - order: Full order object
        - checkout_complete: True if successful
    """
    cart_id = cart_id or context.get("cart_id")
    if not cart_id:
        raise ValueError("No cart_id provided or found in context")

    headers = _get_checkout_headers(context)

    response = client.post(f"/store/carts/{cart_id}/complete", headers=headers)

    if response.status_code in [200, 201]:
        data = response.json()
        order = data.get("order", {})
        context["order_id"] = order.get("id")
        context["order"] = order
        context["checkout_complete"] = True
        logger.info(f"Cart completed, order created: {order.get('id')}")

    return response


def list_payment_providers(
    client: Client,
    context: ExecutionContext,
    region_id: str | None = None,
) -> Any:
    """List available payment providers.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        region_id: Region ID to filter providers.

    Returns:
        HTTP response with payment providers.

    Context Updates:
        - payment_providers: List of available providers
    """
    headers = _get_checkout_headers(context)

    params: dict[str, Any] = {}
    region_id = region_id or context.get("region_id")
    if region_id:
        params["region_id"] = region_id

    response = client.get("/store/payment-providers", headers=headers, params=params)

    if response.status_code == 200:
        data = response.json()
        providers = data.get("payment_providers", [])
        context["payment_providers"] = providers
        logger.info(f"Retrieved {len(providers)} payment providers")

        # Store first provider for easy access
        if providers:
            context["payment_provider_id"] = providers[0].get("id")

    return response


def simulate_failed_payment(
    client: Client,
    context: ExecutionContext,
    cart_id: str | None = None,
) -> Any:
    """Simulate a failed payment attempt.

    This action is for testing payment failure scenarios.
    Uses a special test provider or card token that triggers failure.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        cart_id: Cart ID (default: from context).

    Returns:
        HTTP response (should be an error response).

    Context Updates:
        - payment_failed: True
        - payment_error: Error message
    """
    # First create a payment session with a test failure provider
    create_response = create_payment_session(
        client,
        context,
        provider_id="pp_test_failure",  # Test provider that simulates failure
    )

    if create_response.status_code not in [200, 201]:
        context["payment_failed"] = True
        context["payment_error"] = "Failed to create payment session"
        return create_response

    # Now try to complete - this should fail
    cart_id = cart_id or context.get("cart_id")
    headers = _get_checkout_headers(context)

    response = client.post(f"/store/carts/{cart_id}/complete", headers=headers)

    if response.status_code >= 400:
        context["payment_failed"] = True
        try:
            error_data = response.json()
            context["payment_error"] = error_data.get("message", "Payment failed")
        except Exception:
            context["payment_error"] = "Payment failed"
        logger.info("Payment failure simulated successfully")
    else:
        # If it didn't fail, something unexpected happened
        logger.warning("Expected payment failure but got success")

    return response


def simulate_abandoned_cart(
    client: Client,
    context: ExecutionContext,
    timeout_seconds: int = 5,
) -> Any:
    """Simulate an abandoned cart scenario.

    Waits for a timeout period without completing checkout.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        timeout_seconds: How long to wait (simulated timeout).

    Returns:
        Cart state after timeout.

    Context Updates:
        - cart_abandoned: True
        - abandonment_time: Timestamp
    """
    logger.info(f"Simulating cart abandonment (waiting {timeout_seconds}s)...")

    # In a real scenario, this would involve session timeout
    # Here we simulate by just waiting and then checking cart state
    time.sleep(timeout_seconds)

    cart_id = context.get("cart_id")
    if not cart_id:
        raise ValueError("No cart_id in context")

    # Fetch cart state
    headers = _get_checkout_headers(context)
    response = client.get(f"/store/carts/{cart_id}", headers=headers)

    if response.status_code == 200:
        data = response.json()
        cart = data.get("cart", {})
        context["cart"] = cart
        context["cart_abandoned"] = True
        context["abandonment_time"] = time.time()

        # Verify cart is still in pending state (not completed)
        if cart.get("completed_at") is None:
            logger.info(f"Cart {cart_id} marked as abandoned")
        else:
            logger.warning(f"Cart {cart_id} was already completed")

    return response


def verify_cart_intact(
    client: Client,
    context: ExecutionContext,
    cart_id: str | None = None,
) -> Any:
    """Verify cart is still intact after failed payment.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        cart_id: Cart ID (default: from context).

    Returns:
        HTTP response with cart data.

    Context Updates:
        - cart_intact: True if cart still has items
    """
    cart_id = cart_id or context.get("cart_id")
    if not cart_id:
        raise ValueError("No cart_id provided or found in context")

    headers = _get_checkout_headers(context)

    response = client.get(f"/store/carts/{cart_id}", headers=headers)

    if response.status_code == 200:
        data = response.json()
        cart = data.get("cart", {})
        context["cart"] = cart

        # Verify cart has items and is not completed
        items = cart.get("items", [])
        completed_at = cart.get("completed_at")

        if items and not completed_at:
            context["cart_intact"] = True
            logger.info(f"Cart {cart_id} is intact with {len(items)} items")
        else:
            context["cart_intact"] = False
            logger.warning(f"Cart {cart_id} is not intact")

    return response


def _get_checkout_headers(context: ExecutionContext) -> dict[str, str]:
    """Get headers for checkout API requests.

    Args:
        context: Execution context.

    Returns:
        Headers dict with publishable key and optional auth.
    """
    headers: dict[str, str] = {
        "Content-Type": "application/json",
    }

    # Add publishable API key
    publishable_key = context.get("publishable_api_key")
    if publishable_key:
        headers["x-publishable-api-key"] = publishable_key

    # Add customer auth if available
    token = context.get("customer_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    return headers


# Step action wrappers for journey definition
def step_initialize_payment(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for initialize_payment_collection action."""
    return initialize_payment_collection(client, context, **kwargs)


def step_create_payment_session(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for create_payment_session action."""
    return create_payment_session(client, context, **kwargs)


def step_complete_cart(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for complete_cart action."""
    return complete_cart(client, context, **kwargs)


def step_simulate_failed_payment(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for simulate_failed_payment action."""
    return simulate_failed_payment(client, context, **kwargs)


def step_simulate_abandoned_cart(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for simulate_abandoned_cart action."""
    return simulate_abandoned_cart(client, context, **kwargs)


def step_verify_cart_intact(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for verify_cart_intact action."""
    return verify_cart_intact(client, context, **kwargs)
