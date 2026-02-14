# Authentication Flows

Examples of testing authentication and authorization.

## Basic Login/Logout

```python
from venomqa import Journey, Step


def login(client, context):
    """Login with valid credentials."""
    response = client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "secret123",
    })

    if response.status_code == 200:
        data = response.json()
        context["token"] = data["token"]
        context["user_id"] = data["user"]["id"]
        client.set_auth_token(data["token"])

    return response


def get_profile(client, context):
    """Get authenticated user's profile."""
    return client.get("/api/users/me")


def logout(client, context):
    """Logout and invalidate token."""
    return client.post("/api/auth/logout")


def access_after_logout(client, context):
    """Try to access protected endpoint after logout."""
    return client.get("/api/users/me")


journey = Journey(
    name="login_logout",
    description="Test login and logout flow",
    tags=["auth", "login"],
    steps=[
        Step(name="login", action=login),
        Step(name="get_profile", action=get_profile),
        Step(name="logout", action=logout),
        Step(
            name="access_after_logout",
            action=access_after_logout,
            expect_failure=True,
        ),
    ],
)
```

## User Registration

```python
from venomqa import Journey, Step, Checkpoint, Branch, Path
import uuid


def register_user(client, context):
    """Register a new user."""
    email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    context["email"] = email
    context["password"] = "SecurePass123!"

    response = client.post("/api/auth/register", json={
        "email": email,
        "password": context["password"],
        "name": "Test User",
    })

    if response.status_code in [200, 201]:
        context["user_id"] = response.json().get("user_id")

    return response


def verify_email(client, context):
    """Verify email (mock token)."""
    return client.post("/api/auth/verify-email", json={
        "token": "mock-verification-token",
    })


def login_verified(client, context):
    """Login with verified account."""
    response = client.post("/api/auth/login", json={
        "email": context["email"],
        "password": context["password"],
    })

    if response.status_code == 200:
        client.set_auth_token(response.json()["token"])

    return response


def login_unverified(client, context):
    """Try login without verification."""
    return client.post("/api/auth/login", json={
        "email": context["email"],
        "password": context["password"],
    })


journey = Journey(
    name="user_registration",
    description="Test user registration flow",
    tags=["auth", "registration"],
    steps=[
        Step(name="register", action=register_user),
        Checkpoint(name="registered"),

        Branch(
            checkpoint_name="registered",
            paths=[
                Path(name="verified_login", steps=[
                    Step(name="verify", action=verify_email),
                    Step(name="login", action=login_verified),
                ]),
                Path(name="unverified_login", steps=[
                    Step(
                        name="login",
                        action=login_unverified,
                        expect_failure=True,
                    ),
                ]),
            ],
        ),
    ],
)
```

## Password Reset

```python
from venomqa import Journey, Step


def request_password_reset(client, context):
    """Request password reset email."""
    return client.post("/api/auth/forgot-password", json={
        "email": "test@example.com",
    })


def reset_password(client, context):
    """Reset password with token."""
    return client.post("/api/auth/reset-password", json={
        "token": "mock-reset-token",
        "password": "NewSecurePass456!",
    })


def login_with_new_password(client, context):
    """Login with new password."""
    response = client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "NewSecurePass456!",
    })

    if response.status_code == 200:
        client.set_auth_token(response.json()["token"])

    return response


def login_with_old_password(client, context):
    """Try login with old password."""
    return client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "secret123",
    })


journey = Journey(
    name="password_reset",
    description="Test password reset flow",
    tags=["auth", "password"],
    steps=[
        Step(name="request_reset", action=request_password_reset),
        Step(name="reset_password", action=reset_password),
        Step(name="login_new", action=login_with_new_password),
        Step(
            name="login_old",
            action=login_with_old_password,
            expect_failure=True,
        ),
    ],
)
```

## Token Refresh

```python
from venomqa import Journey, Step
import time


def login_get_tokens(client, context):
    """Login and get access + refresh tokens."""
    response = client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "secret123",
    })

    if response.status_code == 200:
        data = response.json()
        context["access_token"] = data["access_token"]
        context["refresh_token"] = data["refresh_token"]
        client.set_auth_token(data["access_token"])

    return response


def access_protected(client, context):
    """Access protected resource."""
    return client.get("/api/protected")


def refresh_token(client, context):
    """Refresh access token."""
    response = client.post("/api/auth/refresh", json={
        "refresh_token": context["refresh_token"],
    })

    if response.status_code == 200:
        data = response.json()
        context["access_token"] = data["access_token"]
        client.set_auth_token(data["access_token"])

    return response


def use_old_token(client, context):
    """Try using old access token after refresh."""
    old_token = context.get("old_access_token", context["access_token"])
    client.set_auth_token(old_token)
    return client.get("/api/protected")


journey = Journey(
    name="token_refresh",
    description="Test token refresh flow",
    tags=["auth", "tokens"],
    steps=[
        Step(name="login", action=login_get_tokens),
        Step(name="access", action=access_protected),
        Step(name="refresh", action=refresh_token),
        Step(name="access_new_token", action=access_protected),
    ],
)
```

## Authorization Testing

```python
from venomqa import Journey, Step, Checkpoint, Branch, Path


def login_as_user(client, context):
    """Login as regular user."""
    response = client.post("/api/auth/login", json={
        "email": "user@example.com",
        "password": "userpass",
    })

    if response.status_code == 200:
        client.set_auth_token(response.json()["token"])
        context["role"] = "user"

    return response


def login_as_admin(client, context):
    """Login as admin."""
    response = client.post("/api/auth/login", json={
        "email": "admin@example.com",
        "password": "adminpass",
    })

    if response.status_code == 200:
        client.set_auth_token(response.json()["token"])
        context["role"] = "admin"

    return response


def access_user_endpoint(client, context):
    """Access user-level endpoint."""
    return client.get("/api/users/me")


def access_admin_endpoint(client, context):
    """Access admin-only endpoint."""
    return client.get("/api/admin/users")


def access_superadmin_endpoint(client, context):
    """Access superadmin-only endpoint."""
    return client.get("/api/admin/settings")


journey = Journey(
    name="authorization",
    description="Test role-based authorization",
    tags=["auth", "authorization", "rbac"],
    steps=[
        Checkpoint(name="start"),

        Branch(
            checkpoint_name="start",
            paths=[
                Path(name="user_permissions", steps=[
                    Step(name="login", action=login_as_user),
                    Step(name="user_endpoint", action=access_user_endpoint),
                    Step(
                        name="admin_endpoint",
                        action=access_admin_endpoint,
                        expect_failure=True,
                    ),
                ]),
                Path(name="admin_permissions", steps=[
                    Step(name="login", action=login_as_admin),
                    Step(name="user_endpoint", action=access_user_endpoint),
                    Step(name="admin_endpoint", action=access_admin_endpoint),
                    Step(
                        name="superadmin_endpoint",
                        action=access_superadmin_endpoint,
                        expect_failure=True,
                    ),
                ]),
            ],
        ),
    ],
)
```

## OAuth Flow

```python
from venomqa import Journey, Step


def initiate_oauth(client, context):
    """Start OAuth flow."""
    response = client.get("/api/auth/oauth/google/authorize")

    if response.status_code == 200:
        context["oauth_url"] = response.json()["authorize_url"]
        context["state"] = response.json()["state"]

    return response


def oauth_callback(client, context):
    """Handle OAuth callback."""
    # Simulate OAuth provider callback
    response = client.get("/api/auth/oauth/google/callback", params={
        "code": "mock-oauth-code",
        "state": context["state"],
    })

    if response.status_code == 200:
        data = response.json()
        context["token"] = data["token"]
        client.set_auth_token(data["token"])

    return response


def get_oauth_profile(client, context):
    """Get profile after OAuth login."""
    return client.get("/api/users/me")


journey = Journey(
    name="oauth_google",
    description="Test Google OAuth flow",
    tags=["auth", "oauth"],
    steps=[
        Step(name="initiate", action=initiate_oauth),
        Step(name="callback", action=oauth_callback),
        Step(name="profile", action=get_oauth_profile),
    ],
)
```

## Security Testing

```python
from venomqa import Journey, Step


def test_sql_injection(client, context):
    """Test SQL injection prevention."""
    return client.post("/api/auth/login", json={
        "email": "'; DROP TABLE users; --",
        "password": "test",
    })


def test_xss_prevention(client, context):
    """Test XSS prevention."""
    return client.post("/api/users", json={
        "name": "<script>alert('xss')</script>",
    })


def test_rate_limiting(client, context):
    """Test rate limiting (many requests)."""
    for i in range(100):
        response = client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "wrong",
        })
        if response.status_code == 429:  # Rate limited
            return response

    return response


def test_brute_force_protection(client, context):
    """Test brute force protection."""
    for i in range(10):
        client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": f"wrongpassword{i}",
        })

    # Account should be locked
    return client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "correctpassword",
    })


journey = Journey(
    name="security_tests",
    description="Test security measures",
    tags=["auth", "security"],
    steps=[
        Step(
            name="sql_injection",
            action=test_sql_injection,
            expect_failure=True,
        ),
        Step(
            name="xss_prevention",
            action=test_xss_prevention,
            expect_failure=True,
        ),
        Step(
            name="rate_limiting",
            action=test_rate_limiting,
            expect_failure=True,
        ),
        Step(
            name="brute_force",
            action=test_brute_force_protection,
            expect_failure=True,
        ),
    ],
)
```
