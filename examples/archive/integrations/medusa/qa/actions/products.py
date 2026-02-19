"""Medusa Store API - Product Actions.

Handles product catalog browsing including listing and retrieving products.

Medusa API v2 Endpoints:
    - GET /store/products - List products with filters
    - GET /store/products/:id - Get single product
    - GET /store/product-categories - List categories
    - GET /store/collections - List collections

Example:
    >>> from venomqa import Client
    >>> from examples.medusa_integration.qa.actions.products import list_products, get_product
    >>>
    >>> client = Client("http://localhost:9000")
    >>> ctx = {"region_id": "reg_123"}
    >>> list_products(client, ctx, limit=10)
    >>> get_product(client, ctx, product_id="prod_123")
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from venomqa.client import Client
    from venomqa.core.context import ExecutionContext

logger = logging.getLogger(__name__)


def list_products(
    client: Client,
    context: ExecutionContext,
    limit: int = 20,
    offset: int = 0,
    category_id: str | None = None,
    collection_id: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    order: str | None = None,
) -> Any:
    """List products from the Medusa store.

    Fetches products with optional filters. Requires a region_id for pricing.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        limit: Maximum number of products to return (default: 20).
        offset: Number of products to skip (default: 0).
        category_id: Filter by category ID.
        collection_id: Filter by collection ID.
        tag: Filter by tag.
        q: Search query string.
        order: Sort order (e.g., "created_at", "-created_at").

    Returns:
        HTTP response with products list.

    Context Updates:
        - products: List of product objects
        - products_count: Total count of products
    """
    headers = _get_store_headers(context)

    params: dict[str, Any] = {
        "limit": limit,
        "offset": offset,
    }

    # Add region_id for pricing (required in Medusa v2)
    region_id = context.get("region_id")
    if region_id:
        params["region_id"] = region_id

    # Add optional filters
    if category_id:
        params["category_id"] = category_id
    if collection_id:
        params["collection_id"] = collection_id
    if tag:
        params["tag"] = tag
    if q:
        params["q"] = q
    if order:
        params["order"] = order

    response = client.get("/store/products", headers=headers, params=params)

    if response.status_code == 200:
        data = response.json()
        products = data.get("products", [])
        context["products"] = products
        context["products_count"] = data.get("count", len(products))
        logger.info(f"Retrieved {len(products)} products")

        # Store first product ID for easy access in tests
        if products:
            context["first_product_id"] = products[0].get("id")
            # Also store first variant ID if available
            variants = products[0].get("variants", [])
            if variants:
                context["first_variant_id"] = variants[0].get("id")

    return response


def get_product(
    client: Client,
    context: ExecutionContext,
    product_id: str | None = None,
) -> Any:
    """Get a single product by ID.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        product_id: Product ID (default: from context).

    Returns:
        HTTP response with product data.

    Context Updates:
        - product: Product object
        - product_variants: List of variant objects
    """
    product_id = product_id or context.get("product_id") or context.get("first_product_id")
    if not product_id:
        raise ValueError("No product_id provided or found in context")

    headers = _get_store_headers(context)

    params: dict[str, Any] = {}

    # Add region_id for pricing
    region_id = context.get("region_id")
    if region_id:
        params["region_id"] = region_id

    response = client.get(f"/store/products/{product_id}", headers=headers, params=params)

    if response.status_code == 200:
        data = response.json()
        product = data.get("product", {})
        context["product"] = product
        context["product_variants"] = product.get("variants", [])
        logger.info(f"Retrieved product: {product.get('title')}")

        # Store first variant for cart operations
        variants = product.get("variants", [])
        if variants:
            context["product_variant_id"] = variants[0].get("id")

    return response


def list_categories(
    client: Client,
    context: ExecutionContext,
    limit: int = 50,
    offset: int = 0,
    parent_category_id: str | None = None,
) -> Any:
    """List product categories.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        limit: Maximum categories to return.
        offset: Number to skip.
        parent_category_id: Filter by parent category.

    Returns:
        HTTP response with categories.

    Context Updates:
        - categories: List of category objects
    """
    headers = _get_store_headers(context)

    params: dict[str, Any] = {
        "limit": limit,
        "offset": offset,
    }

    if parent_category_id:
        params["parent_category_id"] = parent_category_id

    response = client.get("/store/product-categories", headers=headers, params=params)

    if response.status_code == 200:
        data = response.json()
        categories = data.get("product_categories", [])
        context["categories"] = categories
        logger.info(f"Retrieved {len(categories)} categories")

    return response


def list_collections(
    client: Client,
    context: ExecutionContext,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """List product collections.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        limit: Maximum collections to return.
        offset: Number to skip.

    Returns:
        HTTP response with collections.

    Context Updates:
        - collections: List of collection objects
    """
    headers = _get_store_headers(context)

    params: dict[str, Any] = {
        "limit": limit,
        "offset": offset,
    }

    response = client.get("/store/collections", headers=headers, params=params)

    if response.status_code == 200:
        data = response.json()
        collections = data.get("collections", [])
        context["collections"] = collections
        logger.info(f"Retrieved {len(collections)} collections")

    return response


def get_shipping_options(
    client: Client,
    context: ExecutionContext,
    cart_id: str | None = None,
) -> Any:
    """Get available shipping options for a cart.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.
        cart_id: Cart ID (default: from context).

    Returns:
        HTTP response with shipping options.

    Context Updates:
        - shipping_options: List of shipping option objects
    """
    cart_id = cart_id or context.get("cart_id")
    if not cart_id:
        raise ValueError("No cart_id provided or found in context")

    headers = _get_store_headers(context)

    params = {"cart_id": cart_id}

    response = client.get("/store/shipping-options", headers=headers, params=params)

    if response.status_code == 200:
        data = response.json()
        options = data.get("shipping_options", [])
        context["shipping_options"] = options
        logger.info(f"Retrieved {len(options)} shipping options")

        # Store first option for easy selection
        if options:
            context["shipping_option_id"] = options[0].get("id")

    return response


def _get_store_headers(context: ExecutionContext) -> dict[str, str]:
    """Get headers for store API requests.

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
def step_list_products(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for list_products action."""
    return list_products(client, context, **kwargs)


def step_get_product(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for get_product action."""
    return get_product(client, context, **kwargs)


def step_list_categories(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for list_categories action."""
    return list_categories(client, context, **kwargs)


def step_get_shipping_options(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for get_shipping_options action."""
    return get_shipping_options(client, context, **kwargs)
