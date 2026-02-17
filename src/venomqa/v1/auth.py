"""Built-in auth helpers for VenomQA.

Eliminates the _auth(context) helper copy-pasted in every action file.

Usage::

    from venomqa.v1 import World, BearerTokenAuth, MultiRoleAuth
    from venomqa.v1.adapters.http import HttpClient

    # Single-role: token injected automatically in every request
    world = World(
        api=HttpClient("http://localhost:8000"),
        auth=BearerTokenAuth(token_fn=lambda ctx: ctx.get("token")),
    )

    def create_connection(api, context):
        # No manual headers needed — token auto-injected
        return api.post("/connections", json={"name": "test"})

    # Multi-role RBAC testing
    world = World(
        api=HttpClient("http://localhost:8000"),
        auth=MultiRoleAuth(
            roles={
                "admin":  BearerTokenAuth(lambda ctx: ctx.get("token")),
                "viewer": BearerTokenAuth(lambda ctx: ctx.get("viewer_token")),
            },
            default="admin",
        ),
    )

    def viewer_cannot_delete(api, context):
        return api.delete("/resource/1", role="viewer")  # uses viewer token

    def viewer_api_client(api, context):
        viewer = api.with_role("viewer")     # locked to viewer token
        return viewer.delete("/resource/1")  # always viewer
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from venomqa.v1.adapters.http import HttpClient
    from venomqa.v1.core.action import ActionResult
    from venomqa.v1.core.context import Context


class BearerTokenAuth:
    """Injects an Authorization: Bearer <token> header into every request.

    Args:
        token_fn: Callable that receives the current Context and returns
            the token string. If it returns None or empty, no header is added.
        header: Header name (default: "Authorization").
        scheme: Auth scheme prefix (default: "Bearer").
    """

    def __init__(
        self,
        token_fn: Callable[[Context], str | None],
        header: str = "Authorization",
        scheme: str = "Bearer",
    ) -> None:
        self.token_fn = token_fn
        self.header = header
        self.scheme = scheme

    def get_headers(self, context: Context, role: str | None = None) -> dict[str, str]:
        """Return headers dict with the auth token, or {} if token is absent."""
        token = self.token_fn(context)
        if not token:
            return {}
        return {self.header: f"{self.scheme} {token}"}


class ApiKeyAuth:
    """Injects a static or context-derived API key header into every request.

    Args:
        key_fn: Callable that receives Context and returns the API key string.
        header: Header name (default: "X-API-Key").
    """

    def __init__(
        self,
        key_fn: Callable[[Context], str | None],
        header: str = "X-API-Key",
    ) -> None:
        self.key_fn = key_fn
        self.header = header

    def get_headers(self, context: Context, role: str | None = None) -> dict[str, str]:
        key = self.key_fn(context)
        if not key:
            return {}
        return {self.header: key}


class MultiRoleAuth:
    """Routes auth header injection to one of several named auth providers.

    Used for RBAC testing: each role has its own token or API key.

    Args:
        roles: Dict mapping role name → auth provider (BearerTokenAuth or ApiKeyAuth).
        default: Role name used when no role is specified.

    Usage::

        auth = MultiRoleAuth(
            roles={
                "admin":  BearerTokenAuth(lambda ctx: ctx.get("token")),
                "viewer": BearerTokenAuth(lambda ctx: ctx.get("viewer_token")),
            },
            default="admin",
        )
        world = World(api=HttpClient("http://localhost:8000"), auth=auth)

        # In actions:
        def delete_as_viewer(api, context):
            return api.delete("/resource/1", role="viewer")
    """

    def __init__(
        self,
        roles: dict[str, BearerTokenAuth | ApiKeyAuth],
        default: str,
    ) -> None:
        if default not in roles:
            raise ValueError(
                f"Default role '{default}' is not in roles dict. "
                f"Available: {list(roles.keys())}"
            )
        self.roles = roles
        self.default = default

    def get_headers(self, context: Context, role: str | None = None) -> dict[str, str]:
        resolved = role or self.default
        auth = self.roles.get(resolved)
        if auth is None:
            available = list(self.roles.keys())
            raise KeyError(
                f"Unknown role '{resolved}'. "
                f"Available roles: {available}. "
                f"Register via MultiRoleAuth(roles={{'{resolved}': BearerTokenAuth(...)}})"
            )
        return auth.get_headers(context)


class _RoleClient:
    """An HttpClient proxy locked to a specific auth role.

    Returned by AuthHttpClient.with_role(role). Every request uses
    the specified role's token — no need to pass role= on every call.

    Usage::

        def test_viewer_access(api, context):
            viewer = api.with_role("viewer")
            return viewer.delete("/resource/1")  # always viewer
    """

    def __init__(self, auth_client: AuthHttpClient, role: str) -> None:
        self._auth_client = auth_client
        self._role = role
        # Mirror base attributes for compatibility with code that reads these
        self.base_url = auth_client.base_url
        self.timeout = auth_client.timeout
        self.default_headers = auth_client.default_headers

    def get(self, path: str, **kwargs: Any) -> ActionResult:
        return self._auth_client.get(path, role=self._role, **kwargs)

    def post(self, path: str, **kwargs: Any) -> ActionResult:
        return self._auth_client.post(path, role=self._role, **kwargs)

    def put(self, path: str, **kwargs: Any) -> ActionResult:
        return self._auth_client.put(path, role=self._role, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> ActionResult:
        return self._auth_client.patch(path, role=self._role, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> ActionResult:
        return self._auth_client.delete(path, role=self._role, **kwargs)

    def with_role(self, role: str) -> _RoleClient:
        return _RoleClient(self._auth_client, role)

    def with_headers(self, headers: dict[str, str]) -> _RoleClient:
        new_auth = self._auth_client.with_headers(headers)
        return _RoleClient(new_auth, self._role)  # type: ignore[arg-type]


class AuthHttpClient:
    """HttpClient wrapper that auto-injects auth headers on every request.

    Created by World when auth= is passed. Wraps the raw HttpClient and
    calls auth.get_headers(context) before every request, merging the
    result with any caller-supplied headers.

    The context is read at call time (not construction time) so token
    changes during exploration (e.g. after login) are picked up immediately.
    """

    def __init__(
        self,
        client: HttpClient,
        auth: BearerTokenAuth | ApiKeyAuth | MultiRoleAuth,
        context: Context,
    ) -> None:
        self._client = client
        self._auth = auth
        self._context = context
        # Mirror base attributes for compatibility
        self.base_url = client.base_url
        self.timeout = client.timeout
        self.default_headers = client.default_headers

    def _merged_headers(
        self,
        extra: dict[str, str] | None,
        role: str | None,
    ) -> dict[str, str]:
        """Auth headers + caller-supplied headers (caller wins on conflicts)."""
        auth_headers = self._auth.get_headers(self._context, role)
        return {**auth_headers, **(extra or {})}

    def get(self, path: str, *, role: str | None = None, headers: dict[str, str] | None = None, **kwargs: Any) -> ActionResult:
        return self._client.get(path, headers=self._merged_headers(headers, role), **kwargs)

    def post(self, path: str, *, role: str | None = None, headers: dict[str, str] | None = None, **kwargs: Any) -> ActionResult:
        return self._client.post(path, headers=self._merged_headers(headers, role), **kwargs)

    def put(self, path: str, *, role: str | None = None, headers: dict[str, str] | None = None, **kwargs: Any) -> ActionResult:
        return self._client.put(path, headers=self._merged_headers(headers, role), **kwargs)

    def patch(self, path: str, *, role: str | None = None, headers: dict[str, str] | None = None, **kwargs: Any) -> ActionResult:
        return self._client.patch(path, headers=self._merged_headers(headers, role), **kwargs)

    def delete(self, path: str, *, role: str | None = None, headers: dict[str, str] | None = None, **kwargs: Any) -> ActionResult:
        return self._client.delete(path, headers=self._merged_headers(headers, role), **kwargs)

    def with_role(self, role: str) -> _RoleClient:
        """Return a client locked to a specific auth role.

        Every request made through the returned client uses that role's token
        without needing to pass role= on each call.

        Raises:
            KeyError: If the role is not registered in MultiRoleAuth.
        """
        return _RoleClient(self, role)

    def with_headers(self, headers: dict[str, str]) -> AuthHttpClient:
        """Return a new AuthHttpClient with additional static headers."""
        new_client = self._client.with_headers(headers)
        return AuthHttpClient(new_client, self._auth, self._context)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> AuthHttpClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


__all__ = [
    "BearerTokenAuth",
    "ApiKeyAuth",
    "MultiRoleAuth",
    "AuthHttpClient",
]
