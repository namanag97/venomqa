"""Medusa Store API - Authentication Actions.

Handles customer authentication including registration, login, and profile retrieval.

Medusa API v2 Endpoints:
    - POST /auth/customer/emailpass - Register/login with email and password
    - POST /auth/session - Create session
    - GET /store/customers/me - Get current customer
    - POST /auth/token/refresh - Refresh JWT token
    - DELETE /auth/session - Logout

Example:
    >>> from venomqa import Client
    >>> from examples.medusa_integration.qa.actions.auth import register, login, get_customer
    >>>
    >>> client = Client("http://localhost:9000")
    >>> ctx = {}
    >>> register(client, ctx, email="test@example.com", password="password123")
    >>> login(client, ctx, email="test@example.com", password="password123")
    >>> get_customer(client, ctx)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from venomqa.client import Client
    from venomqa.core.context import ExecutionContext

logger = logging.getLogger(__name__)


def register(
    client: Client,
    context: ExecutionContext,
    email: str | None = None,
    password: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> Any:
    """Register a new customer account in Medusa.

    Uses the Medusa v2 authentication API to create a new customer.
    After successful registration, stores the token in context.

    Args:
        client: VenomQA HTTP client.
        context: Execution context for storing state.
        email: Customer email address (default: from context or generated).
        password: Customer password (default: from context or 'testpassword123').
        first_name: Customer first name (optional).
        last_name: Customer last name (optional).

    Returns:
        HTTP response from registration endpoint.

    Context Updates:
        - customer_token: JWT access token
        - customer_email: Registered email
        - customer_id: Customer ID (if available)
    """
    email = email or context.get("customer_email", "test@example.com")
    password = password or context.get("customer_password", "testpassword123")
    first_name = first_name or context.get("first_name", "Test")
    last_name = last_name or context.get("last_name", "Customer")

    # Medusa v2 uses /auth/customer/emailpass for registration
    payload = {
        "email": email,
        "password": password,
    }

    headers = _get_publishable_headers(context)

    response = client.post(
        "/auth/customer/emailpass",
        json=payload,
        headers=headers,
    )

    if response.status_code in [200, 201]:
        data = response.json()
        token = data.get("token")
        if token:
            context["customer_token"] = token
            context["customer_email"] = email
            logger.info(f"Customer registered successfully: {email}")

            # Now create the customer profile
            profile_response = client.post(
                "/store/customers",
                json={
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                },
                headers={
                    **headers,
                    "Authorization": f"Bearer {token}",
                },
            )
            if profile_response.status_code in [200, 201]:
                profile_data = profile_response.json()
                customer = profile_data.get("customer", {})
                context["customer_id"] = customer.get("id")
                logger.info(f"Customer profile created: {customer.get('id')}")

    return response


def login(
    client: Client,
    context: ExecutionContext,
    email: str | None = None,
    password: str | None = None,
) -> Any:
    """Login an existing customer to Medusa.

    Authenticates against the Medusa v2 authentication API.

    Args:
        client: VenomQA HTTP client.
        context: Execution context for storing state.
        email: Customer email (default: from context).
        password: Customer password (default: from context).

    Returns:
        HTTP response from login endpoint.

    Context Updates:
        - customer_token: JWT access token
        - customer_email: Logged in email
    """
    email = email or context.get("customer_email", "test@example.com")
    password = password or context.get("customer_password", "testpassword123")

    payload = {
        "email": email,
        "password": password,
    }

    headers = _get_publishable_headers(context)

    response = client.post(
        "/auth/customer/emailpass",
        json=payload,
        headers=headers,
    )

    if response.status_code == 200:
        data = response.json()
        token = data.get("token")
        if token:
            context["customer_token"] = token
            context["customer_email"] = email
            logger.info(f"Customer logged in successfully: {email}")

    return response


def get_customer(
    client: Client,
    context: ExecutionContext,
) -> Any:
    """Get the currently authenticated customer's profile.

    Requires a valid customer token in the context.

    Args:
        client: VenomQA HTTP client.
        context: Execution context (must contain customer_token).

    Returns:
        HTTP response with customer data.

    Context Updates:
        - customer_id: Customer ID
        - customer_data: Full customer object
    """
    token = context.get("customer_token")
    if not token:
        raise ValueError("No customer token in context. Must login first.")

    headers = _get_auth_headers(context)

    response = client.get("/store/customers/me", headers=headers)

    if response.status_code == 200:
        data = response.json()
        customer = data.get("customer", {})
        context["customer_id"] = customer.get("id")
        context["customer_data"] = customer
        logger.info(f"Retrieved customer profile: {customer.get('id')}")

    return response


def refresh_token(
    client: Client,
    context: ExecutionContext,
) -> Any:
    """Refresh the customer's JWT token.

    Args:
        client: VenomQA HTTP client.
        context: Execution context (must contain customer_token).

    Returns:
        HTTP response with new token.

    Context Updates:
        - customer_token: New JWT access token
    """
    headers = _get_auth_headers(context)

    response = client.post("/auth/token/refresh", headers=headers)

    if response.status_code == 200:
        data = response.json()
        token = data.get("token")
        if token:
            context["customer_token"] = token
            logger.info("Token refreshed successfully")

    return response


def logout(
    client: Client,
    context: ExecutionContext,
) -> Any:
    """Logout the current customer session.

    Args:
        client: VenomQA HTTP client.
        context: Execution context.

    Returns:
        HTTP response from logout endpoint.

    Context Updates:
        - Removes customer_token
    """
    headers = _get_auth_headers(context)

    response = client.delete("/auth/session", headers=headers)

    if response.status_code in [200, 204]:
        context.pop("customer_token", None)
        logger.info("Customer logged out successfully")

    return response


def _get_publishable_headers(context: ExecutionContext) -> dict[str, str]:
    """Get headers with publishable API key.

    Args:
        context: Execution context.

    Returns:
        Headers dict with publishable key.
    """
    headers = {
        "Content-Type": "application/json",
    }

    publishable_key = context.get("publishable_api_key")
    if publishable_key:
        headers["x-publishable-api-key"] = publishable_key

    return headers


def _get_auth_headers(context: ExecutionContext) -> dict[str, str]:
    """Get headers with customer authentication.

    Args:
        context: Execution context.

    Returns:
        Headers dict with auth token and publishable key.
    """
    headers = _get_publishable_headers(context)

    token = context.get("customer_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    return headers


# Step action wrappers for journey definition
def step_register(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for register action."""
    return register(client, context, **kwargs)


def step_login(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for login action."""
    return login(client, context, **kwargs)


def step_get_customer(client: Client, context: ExecutionContext, **kwargs: Any) -> Any:
    """Step wrapper for get_customer action."""
    return get_customer(client, context, **kwargs)
