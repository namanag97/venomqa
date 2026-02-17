"""Login actions for authentication journeys.

Reusable login and session management actions.
"""

from venomqa.http import Client


class LoginActions:
    def __init__(self, base_url: str):
        self.client = Client(base_url=base_url)

    def login(self, email: str, password: str):
        return self.client.post("/api/auth/login", json={"email": email, "password": password})

    def logout(self, token: str):
        return self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})

    def refresh_token(self, refresh_token: str):
        return self.client.post("/api/auth/refresh", json={"refresh_token": refresh_token})

    def get_profile(self, token: str):
        return self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    def validate_token(self, token: str):
        return self.client.get("/api/auth/validate", headers={"Authorization": f"Bearer {token}"})

    def revoke_all_sessions(self, token: str):
        return self.client.post(
            "/api/auth/revoke-all", headers={"Authorization": f"Bearer {token}"}
        )


def login(client, context):
    actions = LoginActions(base_url=context.get("base_url", "http://localhost:8000"))
    response = actions.login(
        email=context.get("email", "test@example.com"),
        password=context.get("password", "password123"),
    )
    if response.status_code == 200:
        data = response.json()
        context["token"] = data.get("access_token")
        context["refresh_token"] = data.get("refresh_token")
        context["user_id"] = data.get("user", {}).get("id")
    return response


def logout(client, context):
    actions = LoginActions(base_url=context.get("base_url", "http://localhost:8000"))
    return actions.logout(token=context["token"])


def refresh_token(client, context):
    actions = LoginActions(base_url=context.get("base_url", "http://localhost:8000"))
    response = actions.refresh_token(refresh_token=context["refresh_token"])
    if response.status_code == 200:
        context["token"] = response.json().get("access_token")
    return response


def get_profile(client, context):
    actions = LoginActions(base_url=context.get("base_url", "http://localhost:8000"))
    response = actions.get_profile(token=context["token"])
    if response.status_code == 200:
        data = response.json()
        assert data.get("email") == context.get("email"), "Email should match"
    return response


def validate_token(client, context):
    actions = LoginActions(base_url=context.get("base_url", "http://localhost:8000"))
    response = actions.validate_token(token=context["token"])
    if response.status_code == 200:
        assert response.json().get("valid") is True, "Token should be valid"
    return response


def revoke_all_sessions(client, context):
    actions = LoginActions(base_url=context.get("base_url", "http://localhost:8000"))
    return actions.revoke_all_sessions(token=context["token"])
