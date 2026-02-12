from venomqa import Journey, Step, Checkpoint
from venomqa.clients import HTTPClient


class AuthActions:
    def __init__(self, base_url: str):
        self.client = HTTPClient(base_url=base_url)

    def register(self, email: str, password: str, name: str = "Test User"):
        return self.client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "name": name},
        )

    def login(self, email: str, password: str):
        return self.client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )

    def logout(self, token: str):
        return self.client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )

    def refresh_token(self, refresh_token: str):
        return self.client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token},
        )

    def get_profile(self, token: str):
        return self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    def update_profile(self, token: str, data: dict):
        return self.client.patch(
            "/api/auth/me",
            json=data,
            headers={"Authorization": f"Bearer {token}"},
        )

    def change_password(self, token: str, old_password: str, new_password: str):
        return self.client.post(
            "/api/auth/change-password",
            json={"old_password": old_password, "new_password": new_password},
            headers={"Authorization": f"Bearer {token}"},
        )

    def request_password_reset(self, email: str):
        return self.client.post(
            "/api/auth/forgot-password",
            json={"email": email},
        )

    def reset_password(self, token: str, new_password: str):
        return self.client.post(
            "/api/auth/reset-password",
            json={"token": token, "new_password": new_password},
        )

    def delete_account(self, token: str, password: str):
        return self.client.delete(
            "/api/auth/me",
            json={"password": password},
            headers={"Authorization": f"Bearer {token}"},
        )


def register_user(client, context):
    auth = AuthActions(context.get("base_url", "http://localhost:8000"))
    return auth.register(
        email=context.get("email", "test@example.com"),
        password=context.get("password", "SecurePass123!"),
        name=context.get("name", "Test User"),
    )


def login_user(client, context):
    auth = AuthActions(context.get("base_url", "http://localhost:8000"))
    response = auth.login(
        email=context.get("email", "test@example.com"),
        password=context.get("password", "SecurePass123!"),
    )
    if response.status_code == 200:
        context["access_token"] = response.json().get("access_token")
        context["refresh_token"] = response.json().get("refresh_token")
    return response


def get_user_profile(client, context):
    auth = AuthActions(context.get("base_url", "http://localhost:8000"))
    return auth.get_profile(token=context["access_token"])


def update_user_profile(client, context):
    auth = AuthActions(context.get("base_url", "http://localhost:8000"))
    return auth.update_profile(
        token=context["access_token"],
        data=context.get("profile_data", {"name": "Updated Name"}),
    )


def logout_user(client, context):
    auth = AuthActions(context.get("base_url", "http://localhost:8000"))
    return auth.logout(token=context["access_token"])


def refresh_access_token(client, context):
    auth = AuthActions(context.get("base_url", "http://localhost:8000"))
    response = auth.refresh_token(refresh_token=context["refresh_token"])
    if response.status_code == 200:
        context["access_token"] = response.json().get("access_token")
    return response


def change_password(client, context):
    auth = AuthActions(context.get("base_url", "http://localhost:8000"))
    return auth.change_password(
        token=context["access_token"],
        old_password=context.get("password", "SecurePass123!"),
        new_password=context.get("new_password", "NewSecurePass456!"),
    )


def request_password_reset(client, context):
    auth = AuthActions(context.get("base_url", "http://localhost:8000"))
    return auth.request_password_reset(email=context.get("email", "test@example.com"))


def delete_account(client, context):
    auth = AuthActions(context.get("base_url", "http://localhost:8000"))
    return auth.delete_account(
        token=context["access_token"],
        password=context.get("password", "SecurePass123!"),
    )


auth_registration_flow = Journey(
    name="auth_registration",
    description="User registration and initial login flow",
    steps=[
        Step(
            name="register_new_user",
            action=register_user,
        ),
        Step(
            name="login_with_new_credentials",
            action=login_user,
        ),
        Checkpoint(name="user_authenticated"),
        Step(
            name="fetch_profile",
            action=get_user_profile,
        ),
        Step(
            name="update_profile",
            action=update_user_profile,
        ),
    ],
)


auth_login_flow = Journey(
    name="auth_login",
    description="Standard login and token management flow",
    steps=[
        Step(
            name="login",
            action=login_user,
        ),
        Checkpoint(name="authenticated"),
        Step(
            name="get_profile",
            action=get_user_profile,
        ),
        Step(
            name="refresh_token",
            action=refresh_access_token,
        ),
        Step(
            name="get_profile_after_refresh",
            action=get_user_profile,
        ),
        Step(
            name="logout",
            action=logout_user,
        ),
    ],
)


auth_password_flow = Journey(
    name="auth_password_change",
    description="Password change and reset flow",
    steps=[
        Step(
            name="login",
            action=login_user,
        ),
        Checkpoint(name="authenticated"),
        Step(
            name="change_password",
            action=change_password,
        ),
        Step(
            name="logout_after_change",
            action=logout_user,
        ),
        Step(
            name="login_with_new_password",
            action=login_user,
            context_overrides={"password": "NewSecurePass456!"},
        ),
        Checkpoint(name="password_changed_verified"),
    ],
)


auth_full_flow = Journey(
    name="auth_full_lifecycle",
    description="Complete authentication lifecycle from registration to deletion",
    steps=[
        Step(
            name="register",
            action=register_user,
        ),
        Step(
            name="login",
            action=login_user,
        ),
        Checkpoint(name="authenticated"),
        Step(
            name="get_profile",
            action=get_user_profile,
        ),
        Step(
            name="update_profile",
            action=update_user_profile,
        ),
        Step(
            name="refresh_token",
            action=refresh_access_token,
        ),
        Step(
            name="delete_account",
            action=delete_account,
        ),
        Checkpoint(name="account_deleted"),
    ],
)
