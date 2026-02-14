"""OAuth authentication journeys.

Demonstrates:
- Third-party OAuth flows
- Account linking
- Multi-provider authentication
"""

from venomqa import Branch, Checkpoint, Journey, Path, Step
from venomqa.client import Client


class OAuthActions:
    def __init__(self, base_url: str, auth_url: str | None = None):
        self.client = Client(base_url=base_url)
        self.auth_client = Client(base_url=auth_url or base_url)

    def initiate_oauth(self, provider: str, redirect_uri: str):
        return self.auth_client.get(
            f"/api/auth/oauth/{provider}",
            params={"redirect_uri": redirect_uri},
            allow_redirects=False,
        )

    def callback_oauth(self, provider: str, code: str, state: str):
        return self.auth_client.post(
            f"/api/auth/oauth/{provider}/callback",
            json={"code": code, "state": state},
        )

    def link_provider(self, provider: str, token: str):
        return self.auth_client.post(
            f"/api/auth/oauth/{provider}/link",
            headers={"Authorization": f"Bearer {token}"},
        )

    def unlink_provider(self, provider: str, token: str):
        return self.auth_client.delete(
            f"/api/auth/oauth/{provider}/unlink",
            headers={"Authorization": f"Bearer {token}"},
        )

    def get_linked_providers(self, token: str):
        return self.auth_client.get(
            "/api/auth/oauth/providers",
            headers={"Authorization": f"Bearer {token}"},
        )

    def get_profile(self, token: str):
        return self.auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})


def login_with_google(client, context):
    actions = OAuthActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    response = actions.callback_oauth(
        provider="google",
        code=context.get("google_code", "test_google_code"),
        state=context.get("oauth_state", "test_state"),
    )
    if response.status_code == 200:
        data = response.json()
        context["token"] = data.get("access_token")
        context["user_id"] = data.get("user", {}).get("id")
        assert data.get("provider") == "google", "Provider should be google"
    return response


def login_with_github(client, context):
    actions = OAuthActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    response = actions.callback_oauth(
        provider="github",
        code=context.get("github_code", "test_github_code"),
        state=context.get("oauth_state", "test_state"),
    )
    if response.status_code == 200:
        data = response.json()
        context["token"] = data.get("access_token")
        context["user_id"] = data.get("user", {}).get("id")
        assert data.get("provider") == "github", "Provider should be github"
    return response


def get_profile(client, context):
    actions = OAuthActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    response = actions.get_profile(token=context["token"])
    if response.status_code == 200:
        data = response.json()
        assert data.get("id") == context.get("user_id"), "User ID should match"
    return response


def initiate_google_oauth(client, context):
    actions = OAuthActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    response = actions.initiate_oauth(
        provider="google",
        redirect_uri=context.get("redirect_uri", "http://localhost:3000/callback"),
    )
    if response.status_code in [200, 302]:
        context["oauth_state"] = "test_state"
    return response


def initiate_github_oauth(client, context):
    actions = OAuthActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    response = actions.initiate_oauth(
        provider="github",
        redirect_uri=context.get("redirect_uri", "http://localhost:3000/callback"),
    )
    if response.status_code in [200, 302]:
        context["oauth_state"] = "test_state"
    return response


def link_google(client, context):
    actions = OAuthActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    response = actions.link_provider(provider="google", token=context["token"])
    if response.status_code == 200:
        context["google_linked"] = True
    return response


def link_github(client, context):
    actions = OAuthActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    response = actions.link_provider(provider="github", token=context["token"])
    if response.status_code == 200:
        context["github_linked"] = True
    return response


def get_linked_providers(client, context):
    actions = OAuthActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    response = actions.get_linked_providers(token=context["token"])
    if response.status_code == 200:
        providers = response.json().get("providers", [])
        context["linked_providers"] = providers
    return response


def unlink_google(client, context):
    actions = OAuthActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        auth_url=context.get("auth_url"),
    )
    return actions.unlink_provider(provider="google", token=context["token"])


oauth_google_flow = Journey(
    name="auth_oauth_google",
    description="Google OAuth login flow",
    steps=[
        Step(name="initiate_google", action=initiate_google_oauth),
        Checkpoint(name="oauth_initiated"),
        Step(name="google_callback", action=login_with_google),
        Checkpoint(name="authenticated"),
        Step(name="get_profile", action=get_profile),
    ],
)

oauth_github_flow = Journey(
    name="auth_oauth_github",
    description="GitHub OAuth login flow",
    steps=[
        Step(name="initiate_github", action=initiate_github_oauth),
        Checkpoint(name="oauth_initiated"),
        Step(name="github_callback", action=login_with_github),
        Checkpoint(name="authenticated"),
        Step(name="get_profile", action=get_profile),
    ],
)

oauth_linking_flow = Journey(
    name="auth_oauth_linking",
    description="Link multiple OAuth providers to account",
    steps=[
        Step(name="google_login", action=login_with_google),
        Checkpoint(name="authenticated"),
        Step(name="check_providers", action=get_linked_providers),
        Checkpoint(name="providers_checked"),
        Branch(
            checkpoint_name="providers_checked",
            paths=[
                Path(
                    name="link_github",
                    steps=[
                        Step(name="link_github_provider", action=link_github),
                        Step(name="verify_linked", action=get_linked_providers),
                    ],
                ),
                Path(
                    name="no_linking",
                    steps=[Step(name="skip_linking", action=get_profile)],
                ),
            ],
        ),
    ],
)
