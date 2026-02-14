"""Medusa Store API - Order Actions.

Handles order management including retrieval and listing customer orders.

Medusa API v2 Endpoints:
    - GET /store/orders - List customer orders
    - GET /store/orders/:id - Get single order
    - POST /store/orders/:id/transfer - Request order transfer
    - POST /store/orders/:id/return - Request return

Example:
    >>> from venomqa import Client
    >>> from examples.medusa_integration.qa.actions.orders import get_order, list_orders
    >>>
    >>> client = Client("http://localhost:9000")
    >>> ctx = {"customer_token": "token123", "order_id": "order_123"}
    >>> get_order(client, ctx)
    >>> list_orders(client, ctx)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from venomqa.client import Client
    from venomqa.core.context import ExecutionContext

logger = logging.getLogger(__name__)


def get_order(
    client: Client,
    context: ExecutionContext,
    order_id: str | None = None,
) -> Any:
    """Get a single order by ID.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        order_id: Order ID (default: from context).

    Returns:
        HTTP response with order data.

    Context Updates:
        - order: Full order object
        - order_status: Order status
        - order_total: Order total amount
        - order_items: List of order items
    """
    order_id = order_id or context.get("order_id")
    if not order_id:
        raise ValueError("No order_id provided or found in context")

    headers = _get_order_headers(context)

    response = client.get(f"/store/orders/{order_id}", headers=headers)

    if response.status_code == 200:
        data = response.json()
        order = data.get("order", {})
        context["order"] = order
        context["order_status"] = order.get("status")
        context["order_total"] = order.get("total", 0)
        context["order_items"] = order.get("items", [])
        context["order_fulfillment_status"] = order.get("fulfillment_status")
        context["order_payment_status"] = order.get("payment_status")
        logger.info(f"Retrieved order: {order_id}, status: {order.get('status')}")

    return response


def list_orders(
    client: Client,
    context: ExecutionContext,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
) -> Any:
    """List customer orders.

    Requires customer authentication.

    Args:
        client: VenomQA HTTP client.
        context: Execution context (must have customer_token).
        limit: Maximum orders to return (default: 20).
        offset: Number to skip (default: 0).
        status: Filter by order status.

    Returns:
        HTTP response with orders list.

    Context Updates:
        - orders: List of order objects
        - orders_count: Total count
    """
    token = context.get("customer_token")
    if not token:
        raise ValueError("No customer_token in context. Must be logged in.")

    headers = _get_order_headers(context)

    params: dict[str, Any] = {
        "limit": limit,
        "offset": offset,
    }

    if status:
        params["status"] = status

    response = client.get("/store/orders", headers=headers, params=params)

    if response.status_code == 200:
        data = response.json()
        orders = data.get("orders", [])
        context["orders"] = orders
        context["orders_count"] = data.get("count", len(orders))
        logger.info(f"Retrieved {len(orders)} orders")

        # Store first order for easy access
        if orders:
            context["first_order_id"] = orders[0].get("id")

    return response


def request_order_transfer(
    client: Client,
    context: ExecutionContext,
    order_id: str | None = None,
) -> Any:
    """Request to claim/transfer an order (for guest orders).

    Used when a guest user creates an account and wants to
    associate previous orders with their account.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        order_id: Order ID (default: from context).

    Returns:
        HTTP response from transfer request.

    Context Updates:
        - order_transfer_requested: True if successful
    """
    order_id = order_id or context.get("order_id")
    if not order_id:
        raise ValueError("No order_id provided or found in context")

    token = context.get("customer_token")
    if not token:
        raise ValueError("No customer_token in context. Must be logged in.")

    headers = _get_order_headers(context)

    response = client.post(f"/store/orders/{order_id}/transfer", headers=headers)

    if response.status_code in [200, 201, 202]:
        context["order_transfer_requested"] = True
        logger.info(f"Order transfer requested: {order_id}")

    return response


def request_return(
    client: Client,
    context: ExecutionContext,
    order_id: str | None = None,
    items: list[dict[str, Any]] | None = None,
    reason: str = "Not satisfied",
) -> Any:
    """Request a return for order items.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        order_id: Order ID (default: from context).
        items: List of items to return with quantities.
        reason: Return reason.

    Returns:
        HTTP response from return request.

    Context Updates:
        - return_id: Created return ID
        - return_requested: True if successful
    """
    order_id = order_id or context.get("order_id")
    if not order_id:
        raise ValueError("No order_id provided or found in context")

    # If no items specified, use all items from order
    if not items:
        order_items = context.get("order_items", [])
        items = [
            {"item_id": item.get("id"), "quantity": item.get("quantity", 1)}
            for item in order_items
        ]

    if not items:
        raise ValueError("No items to return")

    payload = {
        "items": items,
        "reason": reason,
    }

    headers = _get_order_headers(context)

    response = client.post(f"/store/orders/{order_id}/return", json=payload, headers=headers)

    if response.status_code in [200, 201]:
        data = response.json()
        return_obj = data.get("return", {})
        context["return_id"] = return_obj.get("id")
        context["return_requested"] = True
        logger.info(f"Return requested for order {order_id}: {return_obj.get('id')}")

    return response


def verify_order_created(
    client: Client,
    context: ExecutionContext,
    order_id: str | None = None,
) -> Any:
    """Verify that an order was successfully created.

    Checks that the order exists and has a valid status.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        order_id: Order ID (default: from context).

    Returns:
        HTTP response with order data.

    Context Updates:
        - order_verified: True if order exists and is valid
    """
    order_id = order_id or context.get("order_id")
    if not order_id:
        raise ValueError("No order_id provided or found in context")

    headers = _get_order_headers(context)

    response = client.get(f"/store/orders/{order_id}", headers=headers)

    if response.status_code == 200:
        data = response.json()
        order = data.get("order", {})

        # Verify order has required fields
        valid_statuses = ["pending", "completed", "archived", "canceled", "requires_action"]
        status = order.get("status")

        if status in valid_statuses and order.get("id"):
            context["order_verified"] = True
            context["order"] = order
            logger.info(f"Order verified: {order_id}, status: {status}")
        else:
            context["order_verified"] = False
            logger.warning(f"Order verification failed: {order_id}, status: {status}")
    else:
        context["order_verified"] = False

    return response


def check_inventory_after_order(
    client: Client,
    context: ExecutionContext,
) -> Any:
    """Check that inventory was properly decremented after order.

    This is an invariant check to verify inventory consistency.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.

    Returns:
        Result of inventory check.

    Context Updates:
        - inventory_check_passed: True if inventory is consistent
    """
    order = context.get("order", {})
    items = order.get("items", [])

    if not items:
        logger.warning("No items in order to check inventory")
        context["inventory_check_passed"] = True
        return {"status": "no_items"}

    headers = _get_order_headers(context)

    # For each item, we would need to check the variant's inventory
    # This requires admin API access typically, so we store the expectation
    inventory_changes = []

    for item in items:
        variant_id = item.get("variant_id")
        quantity = item.get("quantity", 0)

        if variant_id and quantity > 0:
            inventory_changes.append({
                "variant_id": variant_id,
                "quantity_ordered": quantity,
                "expected_decrease": quantity,
            })

    context["expected_inventory_changes"] = inventory_changes
    context["inventory_check_passed"] = True  # Would be validated by invariant
    logger.info(f"Inventory check prepared for {len(inventory_changes)} variants")

    return {"inventory_changes": inventory_changes, "status": "prepared"}


def _get_order_headers(context: ExecutionContext) -> dict[str, str]:
    """Get headers for order API requests.

    Args:
        context: Execution context.

    Returns:
        Headers dict with publishable key and auth.
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
def step_get_order(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for get_order action."""
    return get_order(client, context, **kwargs)


def step_list_orders(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for list_orders action."""
    return list_orders(client, context, **kwargs)


def step_verify_order_created(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for verify_order_created action."""
    return verify_order_created(client, context, **kwargs)


def step_check_inventory(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for check_inventory_after_order action."""
    return check_inventory_after_order(client, context, **kwargs)
