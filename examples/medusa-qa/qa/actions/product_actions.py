"""Product management actions for Medusa API."""


def list_products(client, context):
    """List all products in the store."""
    response = client.get("/store/products")

    if response.status_code == 200:
        products = response.json().get("products", [])
        if products:
            # Store first product ID for later use
            context["product_id"] = products[0].get("id")
            context["product_title"] = products[0].get("title")

    return response


def get_product(client, context):
    """Get a specific product by ID."""
    product_id = context.get("product_id")
    if not product_id:
        raise ValueError("product_id not found in context")

    response = client.get(f"/store/products/{product_id}")

    if response.status_code == 200:
        product = response.json().get("product", {})
        # Store variant info if available
        variants = product.get("variants", [])
        if variants:
            context["variant_id"] = variants[0].get("id")
            context["variant_price"] = variants[0].get("prices", [{}])[0].get("amount")

    return response


def create_product(client, context):
    """Create a new product (admin only)."""
    response = client.post(
        "/admin/products",
        json={
            "title": "Test Product",
            "description": "A test product for QA",
            "is_giftcard": False,
            "discountable": True,
            "options": [
                {
                    "title": "Size"
                }
            ],
            "variants": [
                {
                    "title": "Small",
                    "prices": [
                        {
                            "amount": 1000,
                            "currency_code": "usd"
                        }
                    ],
                    "options": [
                        {
                            "value": "S"
                        }
                    ]
                }
            ]
        }
    )

    if response.status_code in [200, 201]:
        product = response.json().get("product", {})
        context["created_product_id"] = product.get("id")
        context["created_product_title"] = product.get("title")

        # Store variant info
        variants = product.get("variants", [])
        if variants:
            context["created_variant_id"] = variants[0].get("id")

    return response


def update_product(client, context):
    """Update an existing product (admin only)."""
    product_id = context.get("created_product_id") or context.get("product_id")
    if not product_id:
        raise ValueError("product_id not found in context")

    response = client.post(
        f"/admin/products/{product_id}",
        json={
            "title": "Updated Test Product",
            "description": "Updated description"
        }
    )

    return response


def delete_product(client, context):
    """Delete a product (admin only)."""
    product_id = context.get("created_product_id")
    if not product_id:
        raise ValueError("created_product_id not found in context")

    response = client.delete(f"/admin/products/{product_id}")

    # Clear product from context after deletion
    context.pop("created_product_id", None)

    return response


def search_products(client, context):
    """Search for products."""
    response = client.post(
        "/store/products/search",
        json={
            "q": "test"
        }
    )

    if response.status_code == 200:
        hits = response.json().get("hits", [])
        if hits:
            context["search_result_count"] = len(hits)

    return response
