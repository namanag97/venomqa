"""Password management journeys.

Demonstrates:
- Password reset flow
- Password change with validation
- Password strength enforcement
"""


from venomqa import Checkpoint, Journey, Step
from venomqa.clients import HTTPClient


class PasswordActions:
    def __init__(self, base_url: str, auth_url: str | None = None):
        self.client = HTTPClient(base_url=base_url)
        self.auth_client = HTTPClient(base_url=auth_url or base_url)

    def request_reset(self, email: str):
        return self.auth_client.post("/api/auth/forgot-password", json={"email": email})

    def reset_password(self, token: str, new_password: str):
        return self.auth_client.post(
            "/api/auth/reset-password", json={"token": token, "new_password": new_password}
        )

    def change_password(self, token: str, old_password: str, new_password: str):
        return self.auth_client.post(
            "/api/auth/change-password",
            json={"old_password": old_password, "new_password": new_password},
            headers={"Authorization": f"Bearer {token}"},
        )

    def login(self, email: str, password: str):
        return self.auth_client.post("/api/auth/login", json={"email": email, "password": password})

    def logout(self, token: str):
        return self.auth_client.post(
            "/api/auth/logout", headers={"Authorization": f"Bearer {token}"}
        )


def request_password_reset(client, context):
    actions = PasswordActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    response = actions.request_reset(email=context["email"])
    if response.status_code == 200:
        data = response.json()
        context["reset_token"] = data.get("token", "test_reset_token")
    return response


def reset_password(client, context):
    actions = PasswordActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    new_password = context.get("new_password", "NewSecurePass456!")
    response = actions.reset_password(
        token=context.get("reset_token", "test_reset_token"),
        new_password=new_password,
    )
    if response.status_code == 200:
        context["password"] = new_password
        assert response.json().get("success") is True, "Password reset should succeed"
    return response


def login_with_old_password(client, context):
    actions = PasswordActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    return actions.login(
        email=context["email"], password=context.get("old_password", "OldPass123!")
    )


def login_with_new_password(client, context):
    actions = PasswordActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    response = actions.login(email=context["email"], password=context["password"])
    if response.status_code == 200:
        context["token"] = response.json().get("access_token")
    return response


def change_password(client, context):
    actions = PasswordActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    new_password = context.get("new_password", "NewSecurePass456!")
    response = actions.change_password(
        token=context["token"],
        old_password=context.get("password", "SecurePass123!"),
        new_password=new_password,
    )
    if response.status_code == 200:
        context["password"] = new_password
    return response


def change_password_weak(client, context):
    actions = PasswordActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    return actions.change_password(
        token=context["token"],
        old_password=context.get("password", "SecurePass123!"),
        new_password="weak",
    )


def logout(client, context):
    actions = PasswordActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    return actions.logout(token=context["token"])


def login_user(client, context):
    actions = PasswordActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    response = actions.login(
        email=context["email"],
        password=context.get("password", "SecurePass123!"),
    )
    if response.status_code == 200:
        context["token"] = response.json().get("access_token")
    return response


password_reset_flow = Journey(
    name="password_reset",
    description="Complete password reset flow",
    steps=[
        Step(name="request_reset", action=request_password_reset),
        Checkpoint(name="reset_requested"),
        Step(name="reset_password", action=reset_password),
        Checkpoint(name="password_reset"),
        Step(name="login_old_fail", action=login_with_old_password, expect_failure=True),
        Step(name="login_new_success", action=login_with_new_password),
        Checkpoint(name="authenticated"),
    ],
)

password_change_flow = Journey(
    name="password_change",
    description="Change password while logged in",
    steps=[
        Step(name="login", action=login_user),
        Checkpoint(name="authenticated"),
        Step(name="change_password", action=change_password),
        Step(name="logout", action=logout),
        Step(name="login_with_new", action=login_with_new_password),
        Checkpoint(name="password_changed"),
    ],
)

password_strength_flow = Journey(
    name="password_strength",
    description="Test password strength enforcement",
    steps=[
        Step(name="login", action=login_user),
        Checkpoint(name="authenticated"),
        Step(name="weak_password_rejected", action=change_password_weak, expect_failure=True),
        Step(name="strong_password_accepted", action=change_password),
        Checkpoint(name="password_updated"),
    ],
)
