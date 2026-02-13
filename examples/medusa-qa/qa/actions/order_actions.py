"""Order management actions for Medusa API."""


def complete_cart(client, context):
    """Complete a cart to create an order."""
    cart_id = context.get("cart_id")
    if not cart_id:
        raise ValueError("cart_id not found in context")

    response = client.post(f"/store/carts/{cart_id}/complete")

    if response.status_code == 200:
        order_data = response.json().get("data", {})
        context["order_id"] = order_data.get("id")
        context["order_status"] = order_data.get("status")

    return response


def get_order(client, context):
    """Get order details."""
    order_id = context.get("order_id")
    if not order_id:
        raise ValueError("order_id not found in context")

    response = client.get(f"/store/orders/{order_id}")

    if response.status_code == 200:
        order = response.json().get("order", {})
        context["order_status"] = order.get("status")
        context["order_total"] = order.get("total")

    return response


def list_orders_admin(client, context):
    """List all orders (admin only)."""
    response = client.get("/admin/orders")

    if response.status_code == 200:
        orders = response.json().get("orders", [])
        context["total_orders"] = len(orders)
        if orders:
            context["latest_order_id"] = orders[0].get("id")

    return response


def get_order_admin(client, context):
    """Get order details as admin."""
    order_id = context.get("order_id") or context.get("latest_order_id")
    if not order_id:
        raise ValueError("order_id not found in context")

    response = client.get(f"/admin/orders/{order_id}")

    if response.status_code == 200:
        order = response.json().get("order", {})
        context["order_fulfillment_status"] = order.get("fulfillment_status")
        context["order_payment_status"] = order.get("payment_status")

    return response


def create_fulfillment(client, context):
    """Create a fulfillment for an order (admin only)."""
    order_id = context.get("order_id") or context.get("latest_order_id")
    if not order_id:
        raise ValueError("order_id not found in context")

    # Get order items first
    order_response = client.get(f"/admin/orders/{order_id}")
    if order_response.status_code != 200:
        return order_response

    order = order_response.json().get("order", {})
    items = order.get("items", [])

    if not items:
        raise ValueError("No items in order to fulfill")

    response = client.post(
        f"/admin/orders/{order_id}/fulfillment",
        json={
            "items": [
                {
                    "item_id": item.get("id"),
                    "quantity": item.get("quantity")
                }
                for item in items
            ]
        }
    )

    if response.status_code == 200:
        fulfillment = response.json().get("order", {}).get("fulfillments", [])
        if fulfillment:
            context["fulfillment_id"] = fulfillment[0].get("id")

    return response


def cancel_order(client, context):
    """Cancel an order (admin only)."""
    order_id = context.get("order_id") or context.get("latest_order_id")
    if not order_id:
        raise ValueError("order_id not found in context")

    response = client.post(f"/admin/orders/{order_id}/cancel")

    if response.status_code == 200:
        context["order_status"] = "cancelled"

    return response


def create_payment_session(client, context):
    """Create payment sessions for cart."""
    cart_id = context.get("cart_id")
    if not cart_id:
        raise ValueError("cart_id not found in context")

    response = client.post(f"/store/carts/{cart_id}/payment-sessions")

    if response.status_code == 200:
        cart = response.json().get("cart", {})
        payment_sessions = cart.get("payment_sessions", [])
        if payment_sessions:
            context["payment_session_id"] = payment_sessions[0].get("id")
            context["payment_provider_id"] = payment_sessions[0].get("provider_id")

    return response


def select_payment_session(client, context):
    """Select a payment session."""
    cart_id = context.get("cart_id")
    provider_id = context.get("payment_provider_id", "manual")

    if not cart_id:
        raise ValueError("cart_id not found in context")

    response = client.post(
        f"/store/carts/{cart_id}/payment-session",
        json={
            "provider_id": provider_id
        }
    )

    return response
