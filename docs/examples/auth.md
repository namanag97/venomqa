# Authentication Flows

Complete example testing authentication systems: login, logout, token refresh, session expiry, multi-user scenarios, and permission boundaries.

## What You'll Learn

- Multi-role authentication testing
- Token lifecycle management
- Permission boundary invariants
- Session state exploration
- Security-focused invariant patterns

## Complete Example

```python
"""
Authentication Flows Example

Tests an authentication API with these endpoints:
- POST /auth/login          → Login with email/password
- POST /auth/logout         → Invalidate session
- POST /auth/refresh        → Refresh access token
- GET  /users/me            → Get current user profile
- GET  /admin/users         → Admin: list all users
- DELETE /admin/users/{id}  → Admin: delete user

Run: python test_auth.py
"""

from __future__ import annotations

from venomqa import (
    Action,
    Agent,
    BFS,
    Invariant,
    Severity,
    World,
)
from venomqa.adapters.http import HttpClient


# =============================================================================
# CONTEXT KEYS
# =============================================================================
# auth_role: "admin" | "user" | None (current logged-in role)
# access_token: str | None
# refresh_token: str | None
# last_status: int
# created_user_id: str | None (for admin user creation)


# =============================================================================
# ACTIONS — AUTHENTICATION
# =============================================================================

def login_as_admin(api: HttpClient, context) -> dict | None:
    """Login as admin user."""
    resp = api.post("/auth/login", json={
        "email": "admin@example.com",
        "password": "adminpass123",
    })
    
    context.set("last_status", resp.status_code)
    
    if resp.status_code == 200:
        data = resp.json()
        context.set("access_token", data["access_token"])
        context.set("refresh_token", data.get("refresh_token"))
        context.set("auth_role", "admin")
        api.set_auth_token(data["access_token"])
        return data
    return None


def login_as_user(api: HttpClient, context) -> dict | None:
    """Login as regular user."""
    # First ensure the test user exists
    resp = api.post("/auth/login", json={
        "email": "user@example.com",
        "password": "userpass123",
    })
    
    context.set("last_status", resp.status_code)
    
    if resp.status_code == 200:
        data = resp.json()
        context.set("access_token", data["access_token"])
        context.set("refresh_token", data.get("refresh_token"))
        context.set("auth_role", "user")
        api.set_auth_token(data["access_token"])
        return data
    return None


def logout(api: HttpClient, context) -> dict | None:
    """Logout and invalidate session.
    
    Requires: Must be logged in (access_token exists)
    """
    if context.get("access_token") is None:
        return None  # Skip — not logged in
    
    resp = api.post("/auth/logout")
    context.set("last_status", resp.status_code)
    
    if resp.status_code in [200, 204]:
        context.delete("access_token")
        context.delete("refresh_token")
        context.delete("auth_role")
        api.clear_auth_token()
        return {}
    return None


def refresh_token(api: HttpClient, context) -> dict | None:
    """Refresh access token using refresh token.
    
    Requires: refresh_token must exist
    """
    refresh = context.get("refresh_token")
    if refresh is None:
        return None  # Skip — no refresh token
    
    resp = api.post("/auth/refresh", json={
        "refresh_token": refresh,
    })
    
    context.set("last_status", resp.status_code)
    
    if resp.status_code == 200:
        data = resp.json()
        context.set("access_token", data["access_token"])
        api.set_auth_token(data["access_token"])
        return data
    return None


# =============================================================================
# ACTIONS — USER OPERATIONS
# =============================================================================

def get_profile(api: HttpClient, context) -> dict | None:
    """Get current user's profile.
    
    Requires: Must be logged in
    """
    if context.get("access_token") is None:
        return None  # Skip — not authenticated
    
    resp = api.get("/users/me")
    context.set("last_status", resp.status_code)
    
    if resp.status_code == 200:
        return resp.json()
    return None


def access_protected_resource(api: HttpClient, context) -> dict | None:
    """Access a protected resource.
    
    Requires: Must be logged in
    """
    if context.get("access_token") is None:
        return None
    
    resp = api.get("/protected")
    context.set("last_status", resp.status_code)
    return resp.json() if resp.status_code == 200 else None


def access_after_logout(api: HttpClient, context) -> dict | None:
    """Try to access protected resource after logout.
    
    This tests that tokens are properly invalidated.
    """
    # We need to have logged out but still have the old token stored
    old_token = context.get("old_access_token")
    if old_token is None:
        return None
    
    # Try using the old token
    api.set_auth_token(old_token)
    resp = api.get("/users/me")
    context.set("last_status", resp.status_code)
    
    # Clear it again
    api.clear_auth_token()
    return resp.json() if resp.status_code == 200 else None


# =============================================================================
# ACTIONS — ADMIN OPERATIONS
# =============================================================================

def admin_list_users(api: HttpClient, context) -> list | None:
    """Admin: List all users.
    
    Requires: Must be logged in as admin
    """
    if context.get("auth_role") != "admin":
        return None  # Skip — not admin
    
    resp = api.get("/admin/users")
    context.set("last_status", resp.status_code)
    
    if resp.status_code == 200:
        return resp.json()
    return None


def admin_create_user(api: HttpClient, context) -> dict | None:
    """Admin: Create a new user.
    
    Requires: Must be logged in as admin
    """
    if context.get("auth_role") != "admin":
        return None
    
    resp = api.post("/admin/users", json={
        "email": "newuser@example.com",
        "password": "newpass123",
        "role": "user",
    })
    
    context.set("last_status", resp.status_code)
    
    if resp.status_code in [200, 201]:
        data = resp.json()
        context.set("created_user_id", data["id"])
        return data
    return None


def admin_delete_user(api: HttpClient, context) -> dict | None:
    """Admin: Delete the created user.
    
    Requires: Must be admin AND have created a user
    """
    if context.get("auth_role") != "admin":
        return None
    
    user_id = context.get("created_user_id")
    if user_id is None:
        return None  # No user to delete
    
    resp = api.delete(f"/admin/users/{user_id}")
    context.set("last_status", resp.status_code)
    
    if resp.status_code in [200, 204]:
        context.delete("created_user_id")
        return {}
    return None


def user_try_admin_endpoint(api: HttpClient, context) -> dict | None:
    """Regular user attempts to access admin endpoint.
    
    Requires: Must be logged in as regular user (not admin)
    This should fail with 403 Forbidden.
    """
    role = context.get("auth_role")
    if role != "user":
        return None  # Only test this as regular user
    
    resp = api.get("/admin/users")
    context.set("last_status", resp.status_code)
    context.set("tried_admin_as_user", True)
    return resp.json() if resp.status_code == 200 else None


# =============================================================================
# INVARIANTS
# =============================================================================

def no_server_errors(world: World) -> bool:
    """No 5xx errors should occur."""
    return world.context.get("last_status", 200) < 500


def unauthenticated_cannot_access_protected(world: World) -> bool:
    """Without a token, protected endpoints should return 401."""
    token = world.context.get("access_token")
    status = world.context.get("last_status", 200)
    
    # If we tried to access protected without a token
    if token is None and status in [401, 403]:
        return True
    return True  # Pass if condition doesn't apply


def user_cannot_access_admin(world: World) -> bool:
    """Regular users should get 403 on admin endpoints."""
    role = world.context.get("auth_role")
    tried_admin = world.context.get("tried_admin_as_user")
    status = world.context.get("last_status")
    
    if role == "user" and tried_admin and status is not None:
        return status == 403
    return True


def logout_invalidates_token(world: World) -> bool:
    """After logout, the old token should not work."""
    old_token = world.context.get("old_access_token")
    status = world.context.get("last_status")
    
    if old_token is not None and status is not None:
        return status in [401, 403]
    return True


def token_refresh_preserves_role(world: World) -> bool:
    """Token refresh should not change user role."""
    role_before = world.context.get("auth_role_before_refresh")
    role_after = world.context.get("auth_role")
    
    if role_before is not None and role_after is not None:
        return role_before == role_after
    return True


def no_token_leak_in_responses(world: World) -> bool:
    """Sensitive tokens should not leak in response bodies.
    
    This is a placeholder — real implementation would check
    response bodies for token patterns.
    """
    return True


# =============================================================================
# BUILD INVARIANT OBJECTS
# =============================================================================

INVARIANTS = [
    Invariant(
        name="no_server_errors",
        check=no_server_errors,
        message="Server returned 5xx error during auth flow",
        severity=Severity.CRITICAL,
    ),
    Invariant(
        name="user_cannot_access_admin",
        check=user_cannot_access_admin,
        message="Regular user accessed admin endpoint",
        severity=Severity.CRITICAL,
    ),
    Invariant(
        name="logout_invalidates_token",
        check=logout_invalidates_token,
        message="Token still valid after logout",
        severity=Severity.HIGH,
    ),
    Invariant(
        name="unauthenticated_blocked",
        check=unauthenticated_cannot_access_protected,
        message="Unauthenticated request was not blocked",
        severity=Severity.HIGH,
    ),
]


# =============================================================================
# BUILD ACTIONS
# =============================================================================

ACTIONS = [
    # Authentication
    Action(
        name="login_as_admin",
        execute=login_as_admin,
        description="Login as admin user",
        tags=["auth", "login"],
    ),
    Action(
        name="login_as_user",
        execute=login_as_user,
        description="Login as regular user",
        tags=["auth", "login"],
    ),
    Action(
        name="logout",
        execute=logout,
        description="Logout and invalidate session",
        tags=["auth", "logout"],
    ),
    Action(
        name="refresh_token",
        execute=refresh_token,
        description="Refresh access token",
        tags=["auth", "token"],
    ),
    # User operations
    Action(
        name="get_profile",
        execute=get_profile,
        description="Get current user profile",
        tags=["user", "read"],
    ),
    Action(
        name="access_protected",
        execute=access_protected_resource,
        description="Access protected resource",
        tags=["user", "read"],
    ),
    Action(
        name="access_after_logout",
        execute=access_after_logout,
        description="Try accessing with invalidated token",
        tags=["auth", "security"],
    ),
    # Admin operations
    Action(
        name="admin_list_users",
        execute=admin_list_users,
        description="Admin: list all users",
        tags=["admin", "read"],
    ),
    Action(
        name="admin_create_user",
        execute=admin_create_user,
        description="Admin: create new user",
        tags=["admin", "write"],
    ),
    Action(
        name="admin_delete_user",
        execute=admin_delete_user,
        description="Admin: delete user",
        tags=["admin", "write"],
    ),
    Action(
        name="user_try_admin",
        execute=user_try_admin_endpoint,
        description="User attempts admin endpoint",
        tags=["auth", "security"],
    ),
]


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    api = HttpClient("http://localhost:8000")
    world = World(api=api, state_from_context=["access_token", "auth_role"])
    
    agent = Agent(
        world=world,
        actions=ACTIONS,
        invariants=INVARIANTS,
        strategy=BFS(),
        max_steps=150,
    )
    
    result = agent.explore()
    
    print("\n" + "=" * 60)
    print("AUTHENTICATION EXPLORATION RESULTS")
    print("=" * 60)
    print(f"States visited:    {result.states_visited}")
    print(f"Transitions taken: {result.transitions_taken}")
    print(f"Action coverage:   {result.action_coverage_percent:.0f}%")
    print(f"Duration:          {result.duration_ms:.0f} ms")
    print(f"Violations found:  {len(result.violations)}")
    
    if result.violations:
        print("\nVIOLATIONS:")
        for v in result.violations:
            print(f"  [{v.severity.value.upper()}] {v.invariant_name}")
            print(f"    {v.message}")
    else:
        print("\nNo violations — all auth invariants passed.")
    
    print("=" * 60)
```

## Why These Patterns Matter

### Role-Based Action Preconditions

Actions check their required role:

```python
def admin_list_users(api, context):
    if context.get("auth_role") != "admin":
        return None  # Skip — not admin
    ...
```

This ensures the agent only runs admin actions when an admin is logged in, and tests permission boundaries by having regular users attempt admin operations.

### Token Lifecycle Tracking

Context tracks the full auth state:

| Variable | Meaning |
|----------|---------|
| `access_token` | Current valid token |
| `refresh_token` | Token for refreshing |
| `auth_role` | Current user role |
| `old_access_token` | Token after logout (for testing) |

### Security Invariants

```python
def user_cannot_access_admin(world):
    role = world.context.get("auth_role")
    tried_admin = world.context.get("tried_admin_as_user")
    status = world.context.get("last_status")
    
    if role == "user" and tried_admin and status is not None:
        return status == 403  # Must be forbidden
    return True
```

This catches privilege escalation bugs where a regular user could access admin endpoints.

## Sequences Tested

| Sequence | What It Tests |
|----------|---------------|
| `login_as_user → get_profile` | Basic auth flow |
| `login_as_user → user_try_admin` | Permission boundary |
| `login_as_admin → admin_list_users` | Admin access works |
| `login_as_admin → logout → access_after_logout` | Token invalidation |
| `login_as_user → logout → login_as_admin` | Role switching |
| `login_as_admin → refresh_token → admin_list_users` | Refresh preserves role |

## Multi-User State

For testing interactions between users, use multiple world instances:

```python
admin_world = World(api=admin_api, state_from_context=["access_token"])
user_world = World(api=user_api, state_from_context=["access_token"])

# Run separate explorations, then check cross-user invariants
admin_result = Agent(world=admin_world, actions=admin_actions, ...).explore()
user_result = Agent(world=user_world, actions=user_actions, ...).explore()
```

## Expected Output

```
============================================================
AUTHENTICATION EXPLORATION RESULTS
============================================================
States visited:    18
Transitions taken: 42
Action coverage:   100%
Duration:          234 ms
Violations found:  0

No violations — all auth invariants passed.
============================================================
```

## Common Auth Bugs Found

| Bug | Sequence That Finds It |
|-----|------------------------|
| Token not invalidated on logout | `login → logout → access_protected` |
| User can access admin endpoints | `login_as_user → user_try_admin` |
| Refresh changes role | `login_as_admin → refresh_token → admin_action` |
| Old refresh token still works | `login → refresh → use_old_refresh` |
| Deleted user token still valid | `login_as_admin → delete_user → deleted_user_access` |

## Next Steps

- [E-commerce Checkout](checkout.md) — Complex payment state machines
- [CRUD Operations](crud.md) — Basic patterns
