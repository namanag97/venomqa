"""Authentication actions for Medusa API."""


def admin_login(client, context):
    """Login as admin user."""
    response = client.post(
        "/admin/auth",
        json={
            "email": "admin@test.com",
            "password": "supersecret"
        }
    )

    if response.status_code == 200:
        user_data = response.json().get("user", {})
        context["admin_token"] = response.cookies.get("connect.sid")
        context["admin_id"] = user_data.get("id")
        context["admin_email"] = user_data.get("email")

        # Set auth header for subsequent requests
        if context.get("admin_token"):
            client.headers["Cookie"] = f"connect.sid={context['admin_token']}"

    return response


def customer_register(client, context):
    """Register a new customer."""
    response = client.post(
        "/store/customers",
        json={
            "email": "customer@test.com",
            "password": "password123",
            "first_name": "Test",
            "last_name": "Customer"
        }
    )

    if response.status_code in [200, 201]:
        customer_data = response.json().get("customer", {})
        context["customer_id"] = customer_data.get("id")
        context["customer_email"] = customer_data.get("email")

    return response


def customer_login(client, context):
    """Login as customer."""
    response = client.post(
        "/store/auth",
        json={
            "email": context.get("customer_email", "customer@test.com"),
            "password": "password123"
        }
    )

    if response.status_code == 200:
        customer_data = response.json().get("customer", {})
        context["customer_token"] = response.cookies.get("connect.sid")
        context["customer_id"] = customer_data.get("id")

        # Set auth header for subsequent requests
        if context.get("customer_token"):
            client.headers["Cookie"] = f"connect.sid={context['customer_token']}"

    return response


def admin_logout(client, context):
    """Logout admin user."""
    response = client.delete("/admin/auth")

    # Clear auth from context
    context.pop("admin_token", None)
    client.headers.pop("Cookie", None)

    return response


def customer_logout(client, context):
    """Logout customer."""
    response = client.delete("/store/auth")

    # Clear auth from context
    context.pop("customer_token", None)
    client.headers.pop("Cookie", None)

    return response
