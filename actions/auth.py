def login(client, context):
    return client.post(
        "/api/auth/login",
        json={
            "email": context.get("email", "test@example.com"),
            "password": context.get("password", "testpassword123"),
        },
    )


def logout(client, context):
    return client.post("/api/auth/logout")


def register(client, context):
    return client.post(
        "/api/auth/register",
        json={
            "email": context.get("email", "test@example.com"),
            "password": context.get("password", "testpassword123"),
            "name": context.get("name", "Test User"),
        },
    )


def refresh_token(client, context):
    return client.post(
        "/api/auth/refresh",
        json={"refresh_token": context.get("refresh_token")},
    )


def get_current_user(client, context):
    return client.get("/api/auth/me")
