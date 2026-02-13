"""Shopping cart actions for Medusa API."""


def create_cart(client, context):
    """Create a new shopping cart."""
    response = client.post("/store/carts")

    if response.status_code in [200, 201]:
        cart = response.json().get("cart", {})
        context["cart_id"] = cart.get("id")
        context["cart_region_id"] = cart.get("region_id")

    return response


def get_cart(client, context):
    """Get current cart."""
    cart_id = context.get("cart_id")
    if not cart_id:
        raise ValueError("cart_id not found in context")

    response = client.get(f"/store/carts/{cart_id}")

    if response.status_code == 200:
        cart = response.json().get("cart", {})
        items = cart.get("items", [])
        context["cart_item_count"] = len(items)
        context["cart_total"] = cart.get("total")

    return response


def add_to_cart(client, context):
    """Add a product variant to cart."""
    cart_id = context.get("cart_id")
    variant_id = context.get("variant_id") or context.get("created_variant_id")

    if not cart_id:
        raise ValueError("cart_id not found in context")
    if not variant_id:
        raise ValueError("variant_id not found in context")

    response = client.post(
        f"/store/carts/{cart_id}/line-items",
        json={
            "variant_id": variant_id,
            "quantity": 1
        }
    )

    if response.status_code == 200:
        cart = response.json().get("cart", {})
        items = cart.get("items", [])
        if items:
            context["line_item_id"] = items[0].get("id")
            context["cart_item_count"] = len(items)

    return response


def update_cart_item(client, context):
    """Update quantity of a cart item."""
    cart_id = context.get("cart_id")
    line_item_id = context.get("line_item_id")

    if not cart_id or not line_item_id:
        raise ValueError("cart_id or line_item_id not found in context")

    response = client.post(
        f"/store/carts/{cart_id}/line-items/{line_item_id}",
        json={
            "quantity": 2
        }
    )

    return response


def remove_from_cart(client, context):
    """Remove item from cart."""
    cart_id = context.get("cart_id")
    line_item_id = context.get("line_item_id")

    if not cart_id or not line_item_id:
        raise ValueError("cart_id or line_item_id not found in context")

    response = client.delete(
        f"/store/carts/{cart_id}/line-items/{line_item_id}"
    )

    # Clear line item from context
    context.pop("line_item_id", None)

    return response


def add_shipping_address(client, context):
    """Add shipping address to cart."""
    cart_id = context.get("cart_id")
    if not cart_id:
        raise ValueError("cart_id not found in context")

    response = client.post(
        f"/store/carts/{cart_id}",
        json={
            "shipping_address": {
                "first_name": "Test",
                "last_name": "Customer",
                "address_1": "123 Test St",
                "city": "TestCity",
                "country_code": "us",
                "postal_code": "12345"
            }
        }
    )

    return response


def select_shipping_option(client, context):
    """Select shipping option for cart."""
    cart_id = context.get("cart_id")
    if not cart_id:
        raise ValueError("cart_id not found in context")

    # First get available shipping options
    options_response = client.get(f"/store/shipping-options/{cart_id}")

    if options_response.status_code == 200:
        options = options_response.json().get("shipping_options", [])
        if options:
            shipping_option_id = options[0].get("id")
            context["shipping_option_id"] = shipping_option_id

            # Now add the shipping method
            response = client.post(
                f"/store/carts/{cart_id}/shipping-methods",
                json={
                    "option_id": shipping_option_id
                }
            )
            return response

    return options_response
