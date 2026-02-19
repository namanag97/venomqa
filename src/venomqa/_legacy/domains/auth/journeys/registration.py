"""User registration journeys.

Demonstrates:
- Registration flow with validation
- Email verification
- Profile setup branching
"""

from venomqa import Branch, JourneyCheckpoint as Checkpoint, Journey, Path, Step
from venomqa.http import Client


class RegistrationActions:
    def __init__(self, base_url: str, auth_url: str | None = None):
        self.client = Client(base_url=base_url)
        self.auth_client = Client(base_url=auth_url or base_url)

    def register(self, email: str, password: str, name: str, **extra_fields):
        return self.auth_client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "name": name, **extra_fields},
        )

    def verify_email(self, token: str):
        return self.auth_client.post("/api/auth/verify-email", json={"token": token})

    def resend_verification(self, email: str):
        return self.auth_client.post("/api/auth/resend-verification", json={"email": email})

    def login(self, email: str, password: str):
        return self.auth_client.post("/api/auth/login", json={"email": email, "password": password})

    def get_profile(self, token: str):
        return self.auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    def update_profile(self, token: str, data: dict):
        return self.auth_client.patch(
            "/api/auth/me", json=data, headers={"Authorization": f"Bearer {token}"}
        )


def register_user(client, context):
    actions = RegistrationActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    response = actions.register(
        email=context.get("email", "newuser@example.com"),
        password=context.get("password", "SecurePass123!"),
        name=context.get("name", "New User"),
    )
    if response.status_code in [200, 201]:
        data = response.json()
        context["user_id"] = data.get("user", {}).get("id")
        context["verification_token"] = data.get("verification_token")
    return response


def verify_email(client, context):
    actions = RegistrationActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    response = actions.verify_email(token=context.get("verification_token", "test_token"))
    if response.status_code == 200:
        assert response.json().get("verified") is True, "Email should be verified"
    return response


def resend_verification(client, context):
    actions = RegistrationActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    return actions.resend_verification(email=context["email"])


def login_user(client, context):
    actions = RegistrationActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    response = actions.login(
        email=context["email"],
        password=context.get("password", "SecurePass123!"),
    )
    if response.status_code == 200:
        data = response.json()
        context["token"] = data.get("access_token")
        context["refresh_token"] = data.get("refresh_token")
    return response


def get_profile(client, context):
    actions = RegistrationActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    response = actions.get_profile(token=context["token"])
    if response.status_code == 200:
        data = response.json()
        assert data.get("email") == context["email"], "Profile email should match"
    return response


def update_profile(client, context):
    actions = RegistrationActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    profile_data = context.get("profile_data", {"name": "Updated Name", "bio": "Test bio"})
    return actions.update_profile(token=context["token"], data=profile_data)


def setup_personal_profile(client, context):
    actions = RegistrationActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    return actions.update_profile(
        token=context["token"],
        data={
            "account_type": "personal",
            "timezone": "America/New_York",
            "preferences": {"notifications": True},
        },
    )


def setup_business_profile(client, context):
    actions = RegistrationActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    return actions.update_profile(
        token=context["token"],
        data={
            "account_type": "business",
            "company_name": context.get("company_name", "Test Corp"),
            "timezone": "America/New_York",
            "preferences": {"notifications": True, "marketing": True},
        },
    )


registration_flow = Journey(
    name="auth_registration",
    description="Standard user registration flow",
    steps=[
        Step(name="register", action=register_user),
        Checkpoint(name="registered"),
        Step(name="login", action=login_user),
        Checkpoint(name="authenticated"),
        Step(name="get_profile", action=get_profile),
    ],
)

email_verification_flow = Journey(
    name="auth_email_verification",
    description="Registration with email verification",
    steps=[
        Step(name="register", action=register_user),
        Checkpoint(name="registered"),
        Step(name="verify_email", action=verify_email),
        Checkpoint(name="email_verified"),
        Step(name="login", action=login_user),
        Step(name="get_profile", action=get_profile),
    ],
)

registration_with_profile_flow = Journey(
    name="auth_registration_with_profile",
    description="Registration with profile type branching",
    steps=[
        Step(name="register", action=register_user),
        Checkpoint(name="registered"),
        Step(name="verify_email", action=verify_email),
        Step(name="login", action=login_user),
        Checkpoint(name="authenticated"),
        Branch(
            checkpoint_name="authenticated",
            paths=[
                Path(
                    name="personal_account",
                    steps=[
                        Step(name="setup_personal", action=setup_personal_profile),
                        Step(name="verify_profile", action=get_profile),
                    ],
                ),
                Path(
                    name="business_account",
                    steps=[
                        Step(name="setup_business", action=setup_business_profile),
                        Step(name="verify_profile", action=get_profile),
                    ],
                ),
            ],
        ),
    ],
)
