"""Medusa Store API - Cart Actions.

Handles shopping cart management including creation, line items, and updates.

Medusa API v2 Endpoints:
    - POST /store/carts - Create cart
    - GET /store/carts/:id - Get cart
    - POST /store/carts/:id/line-items - Add line item
    - POST /store/carts/:id/line-items/:line_id - Update line item
    - DELETE /store/carts/:id/line-items/:line_id - Remove line item
    - POST /store/carts/:id/shipping-methods - Add shipping method
    - POST /store/carts/:id/promotions - Apply promotion code

Example:
    >>> from venomqa import Client
    >>> from examples.medusa_integration.qa.actions.cart import create_cart, add_line_item
    >>>
    >>> client = Client("http://localhost:9000")
    >>> ctx = {"region_id": "reg_123", "first_variant_id": "variant_123"}
    >>> create_cart(client, ctx)
    >>> add_line_item(client, ctx, quantity=2)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from venomqa.client import Client
    from venomqa.core.context import ExecutionContext

logger = logging.getLogger(__name__)


def create_cart(
    client: Client,
    context: ExecutionContext,
    region_id: str | None = None,
    sales_channel_id: str | None = None,
    customer_id: str | None = None,
    email: str | None = None,
) -> Any:
    """Create a new shopping cart.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        region_id: Region ID for pricing (default: from context).
        sales_channel_id: Sales channel ID (default: from context).
        customer_id: Customer ID to associate (default: from context).
        email: Email for guest checkout.

    Returns:
        HTTP response with cart data.

    Context Updates:
        - cart_id: Created cart ID
        - cart: Full cart object
    """
    region_id = region_id or context.get("region_id")
    sales_channel_id = sales_channel_id or context.get("sales_channel_id")
    customer_id = customer_id or context.get("customer_id")
    email = email or context.get("customer_email")

    if not region_id:
        raise ValueError("region_id is required for cart creation")

    payload: dict[str, Any] = {
        "region_id": region_id,
    }

    if sales_channel_id:
        payload["sales_channel_id"] = sales_channel_id
    if email:
        payload["email"] = email

    headers = _get_cart_headers(context)

    response = client.post("/store/carts", json=payload, headers=headers)

    if response.status_code in [200, 201]:
        data = response.json()
        cart = data.get("cart", {})
        context["cart_id"] = cart.get("id")
        context["cart"] = cart
        logger.info(f"Created cart: {cart.get('id')}")

    return response


def get_cart(
    client: Client,
    context: ExecutionContext,
    cart_id: str | None = None,
) -> Any:
    """Get cart by ID.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        cart_id: Cart ID (default: from context).

    Returns:
        HTTP response with cart data.

    Context Updates:
        - cart: Full cart object
        - cart_total: Cart total amount
        - cart_items: List of line items
    """
    cart_id = cart_id or context.get("cart_id")
    if not cart_id:
        raise ValueError("No cart_id provided or found in context")

    headers = _get_cart_headers(context)

    response = client.get(f"/store/carts/{cart_id}", headers=headers)

    if response.status_code == 200:
        data = response.json()
        cart = data.get("cart", {})
        context["cart"] = cart
        context["cart_total"] = cart.get("total", 0)
        context["cart_items"] = cart.get("items", [])
        context["cart_item_count"] = len(cart.get("items", []))
        logger.info(f"Retrieved cart: {cart_id}, items: {len(cart.get('items', []))}")

    return response


def add_line_item(
    client: Client,
    context: ExecutionContext,
    variant_id: str | None = None,
    quantity: int = 1,
    cart_id: str | None = None,
) -> Any:
    """Add a line item to the cart.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        variant_id: Product variant ID (default: from context).
        quantity: Quantity to add (default: 1).
        cart_id: Cart ID (default: from context).

    Returns:
        HTTP response with updated cart.

    Context Updates:
        - cart: Updated cart object
        - last_line_item_id: ID of the added line item
    """
    cart_id = cart_id or context.get("cart_id")
    variant_id = variant_id or context.get("product_variant_id") or context.get("first_variant_id")

    if not cart_id:
        raise ValueError("No cart_id provided or found in context")
    if not variant_id:
        raise ValueError("No variant_id provided or found in context")

    payload = {
        "variant_id": variant_id,
        "quantity": quantity,
    }

    headers = _get_cart_headers(context)

    response = client.post(f"/store/carts/{cart_id}/line-items", json=payload, headers=headers)

    if response.status_code in [200, 201]:
        data = response.json()
        cart = data.get("cart", {})
        context["cart"] = cart
        context["cart_items"] = cart.get("items", [])

        # Store the last added item ID
        items = cart.get("items", [])
        if items:
            # Find the item with matching variant_id
            for item in items:
                if item.get("variant_id") == variant_id:
                    context["last_line_item_id"] = item.get("id")
                    break

        logger.info(f"Added line item to cart: {variant_id} x {quantity}")

    return response


def update_line_item(
    client: Client,
    context: ExecutionContext,
    line_item_id: str | None = None,
    quantity: int | None = None,
    cart_id: str | None = None,
) -> Any:
    """Update a line item quantity.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        line_item_id: Line item ID (default: from context).
        quantity: New quantity.
        cart_id: Cart ID (default: from context).

    Returns:
        HTTP response with updated cart.

    Context Updates:
        - cart: Updated cart object
    """
    cart_id = cart_id or context.get("cart_id")
    line_item_id = line_item_id or context.get("last_line_item_id")

    if not cart_id:
        raise ValueError("No cart_id provided or found in context")
    if not line_item_id:
        raise ValueError("No line_item_id provided or found in context")

    payload: dict[str, Any] = {}
    if quantity is not None:
        payload["quantity"] = quantity

    headers = _get_cart_headers(context)

    response = client.post(
        f"/store/carts/{cart_id}/line-items/{line_item_id}",
        json=payload,
        headers=headers,
    )

    if response.status_code == 200:
        data = response.json()
        cart = data.get("cart", {})
        context["cart"] = cart
        context["cart_items"] = cart.get("items", [])
        logger.info(f"Updated line item: {line_item_id}, quantity: {quantity}")

    return response


def remove_line_item(
    client: Client,
    context: ExecutionContext,
    line_item_id: str | None = None,
    cart_id: str | None = None,
) -> Any:
    """Remove a line item from the cart.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        line_item_id: Line item ID (default: from context).
        cart_id: Cart ID (default: from context).

    Returns:
        HTTP response with updated cart.

    Context Updates:
        - cart: Updated cart object
    """
    cart_id = cart_id or context.get("cart_id")
    line_item_id = line_item_id or context.get("last_line_item_id")

    if not cart_id:
        raise ValueError("No cart_id provided or found in context")
    if not line_item_id:
        raise ValueError("No line_item_id provided or found in context")

    headers = _get_cart_headers(context)

    response = client.delete(
        f"/store/carts/{cart_id}/line-items/{line_item_id}",
        headers=headers,
    )

    if response.status_code in [200, 204]:
        # Refresh cart to get updated state
        get_cart(client, context, cart_id=cart_id)
        logger.info(f"Removed line item: {line_item_id}")

    return response


def update_cart(
    client: Client,
    context: ExecutionContext,
    cart_id: str | None = None,
    email: str | None = None,
    billing_address: dict[str, Any] | None = None,
    shipping_address: dict[str, Any] | None = None,
    sales_channel_id: str | None = None,
    promo_codes: list[str] | None = None,
) -> Any:
    """Update cart details.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        cart_id: Cart ID (default: from context).
        email: Customer email for checkout.
        billing_address: Billing address object.
        shipping_address: Shipping address object.
        sales_channel_id: Sales channel ID.
        promo_codes: List of promotion codes.

    Returns:
        HTTP response with updated cart.

    Context Updates:
        - cart: Updated cart object
    """
    cart_id = cart_id or context.get("cart_id")
    if not cart_id:
        raise ValueError("No cart_id provided or found in context")

    payload: dict[str, Any] = {}

    if email:
        payload["email"] = email
    if billing_address:
        payload["billing_address"] = billing_address
    if shipping_address:
        payload["shipping_address"] = shipping_address
    if sales_channel_id:
        payload["sales_channel_id"] = sales_channel_id
    if promo_codes:
        payload["promo_codes"] = promo_codes

    headers = _get_cart_headers(context)

    response = client.post(f"/store/carts/{cart_id}", json=payload, headers=headers)

    if response.status_code == 200:
        data = response.json()
        cart = data.get("cart", {})
        context["cart"] = cart
        logger.info(f"Updated cart: {cart_id}")

    return response


def add_shipping_method(
    client: Client,
    context: ExecutionContext,
    shipping_option_id: str | None = None,
    cart_id: str | None = None,
) -> Any:
    """Add a shipping method to the cart.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        shipping_option_id: Shipping option ID (default: from context).
        cart_id: Cart ID (default: from context).

    Returns:
        HTTP response with updated cart.

    Context Updates:
        - cart: Updated cart object
    """
    cart_id = cart_id or context.get("cart_id")
    shipping_option_id = shipping_option_id or context.get("shipping_option_id")

    if not cart_id:
        raise ValueError("No cart_id provided or found in context")
    if not shipping_option_id:
        raise ValueError("No shipping_option_id provided or found in context")

    payload = {
        "option_id": shipping_option_id,
    }

    headers = _get_cart_headers(context)

    response = client.post(
        f"/store/carts/{cart_id}/shipping-methods",
        json=payload,
        headers=headers,
    )

    if response.status_code in [200, 201]:
        data = response.json()
        cart = data.get("cart", {})
        context["cart"] = cart
        logger.info(f"Added shipping method to cart: {shipping_option_id}")

    return response


def apply_promotion_code(
    client: Client,
    context: ExecutionContext,
    code: str,
    cart_id: str | None = None,
) -> Any:
    """Apply a promotion code to the cart.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        code: Promotion code string.
        cart_id: Cart ID (default: from context).

    Returns:
        HTTP response with updated cart.

    Context Updates:
        - cart: Updated cart object
        - applied_promotion_code: The applied code
    """
    cart_id = cart_id or context.get("cart_id")
    if not cart_id:
        raise ValueError("No cart_id provided or found in context")

    payload = {
        "code": code,
    }

    headers = _get_cart_headers(context)

    response = client.post(f"/store/carts/{cart_id}/promotions", json=payload, headers=headers)

    if response.status_code in [200, 201]:
        data = response.json()
        cart = data.get("cart", {})
        context["cart"] = cart
        context["applied_promotion_code"] = code
        logger.info(f"Applied promotion code: {code}")

    return response


def _get_cart_headers(context: ExecutionContext) -> dict[str, str]:
    """Get headers for cart API requests.

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
def step_create_cart(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for create_cart action."""
    return create_cart(client, context, **kwargs)


def step_get_cart(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for get_cart action."""
    return get_cart(client, context, **kwargs)


def step_add_line_item(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for add_line_item action."""
    return add_line_item(client, context, **kwargs)


def step_update_line_item(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for update_line_item action."""
    return update_line_item(client, context, **kwargs)


def step_remove_line_item(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for remove_line_item action."""
    return remove_line_item(client, context, **kwargs)


def step_update_cart(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for update_cart action."""
    return update_cart(client, context, **kwargs)


def step_add_shipping_method(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for add_shipping_method action."""
    return add_shipping_method(client, context, **kwargs)


def step_apply_promotion_code(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for apply_promotion_code action."""
    return apply_promotion_code(client, context, **kwargs)
