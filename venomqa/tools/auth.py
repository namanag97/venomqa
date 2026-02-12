"""Authentication helpers for QA testing.

This module provides reusable authentication action functions supporting:
- OAuth2 (Authorization Code, Client Credentials)
- JWT (JSON Web Tokens)
- API Key authentication
- Basic authentication

Example:
    >>> from venomqa.tools import oauth2_login, jwt_login, set_auth_context
    >>>
    >>> # OAuth2 login
    >>> oauth2_login(client, context, client_id, client_secret)
    >>>
    >>> # JWT login
    >>> jwt_login(client, context, username, password)
    >>>
    >>> # Subsequent requests will include auth headers
    >>> response = get(client, context, "/api/protected")
"""

from __future__ import annotations

import base64
import json
import time
from typing import TYPE_CHECKING, Any

import httpx

from venomqa.errors import VenomQAError

if TYPE_CHECKING:
    from venomqa.client import Client
    from venomqa.state.context import Context


class AuthError(VenomQAError):
    """Raised when authentication fails."""

    pass


def _get_base_url(client: Client, context: Context) -> str:
    """Get base URL from client or context."""
    if hasattr(client, "base_url") and client.base_url:
        return client.base_url.rstrip("/")
    if hasattr(context, "config") and hasattr(context.config, "base_url"):
        return context.config.base_url.rstrip("/")
    return ""


def set_auth_context(
    context: Context,
    auth_type: str,
    token: str | None = None,
    username: str | None = None,
    password: str | None = None,
    api_key: str | None = None,
    api_key_header: str = "X-API-Key",
    expires_at: float | None = None,
    refresh_token: str | None = None,
) -> None:
    """Set authentication context for subsequent requests.

    Args:
        context: Test context to update.
        auth_type: Type of authentication ('bearer', 'basic', 'api_key').
        token: Bearer token for bearer auth.
        username: Username for basic auth.
        password: Password for basic auth.
        api_key: API key for api_key auth.
        api_key_header: Header name for API key (default: 'X-API-Key').
        expires_at: Token expiration timestamp.
        refresh_token: Refresh token for token renewal.

    Example:
        >>> set_auth_context(
        ...     context,
        ...     auth_type="bearer",
        ...     token="eyJhbGciOiJIUzI1NiIs...",
        ...     expires_at=time.time() + 3600,
        ...     refresh_token="refresh_token_value"
        ... )
    """
    if not hasattr(context, "_auth"):
        context._auth = {}

    context._auth["type"] = auth_type
    context._auth["expires_at"] = expires_at
    context._auth["refresh_token"] = refresh_token

    if auth_type == "bearer" and token:
        context._auth["token"] = token
        context._auth["header"] = f"Bearer {token}"
    elif auth_type == "basic" and username and password:
        context._auth["username"] = username
        context._auth["password"] = password
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        context._auth["header"] = f"Basic {credentials}"
    elif auth_type == "api_key" and api_key:
        context._auth["api_key"] = api_key
        context._auth["api_key_header"] = api_key_header


def get_auth_headers(context: Context) -> dict[str, str]:
    """Get authentication headers from context.

    Args:
        context: Test context containing auth information.

    Returns:
        dict: Headers to include in requests.

    Example:
        >>> headers = get_auth_headers(context)
        >>> # {'Authorization': 'Bearer token...'}
    """
    auth = getattr(context, "_auth", {})
    if not auth:
        return {}

    expires_at = auth.get("expires_at")
    if expires_at and time.time() > expires_at:
        return {}

    auth_type = auth.get("type")
    headers = {}

    if auth_type == "bearer":
        if auth.get("header"):
            headers["Authorization"] = auth["header"]
    elif auth_type == "basic":
        if auth.get("header"):
            headers["Authorization"] = auth["header"]
    elif auth_type == "api_key":
        header_name = auth.get("api_key_header", "X-API-Key")
        if auth.get("api_key"):
            headers[header_name] = auth["api_key"]

    return headers


def basic_auth(
    client: Client,
    context: Context,
    username: str,
    password: str,
) -> None:
    """Set up Basic authentication.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        username: Username for basic auth.
        password: Password for basic auth.

    Example:
        >>> basic_auth(client, context, "admin", "secret123")
        >>> response = get(client, context, "/api/protected")
    """
    set_auth_context(
        context=context,
        auth_type="basic",
        username=username,
        password=password,
    )


def api_key_auth(
    client: Client,
    context: Context,
    api_key: str,
    header_name: str = "X-API-Key",
) -> None:
    """Set up API Key authentication.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        api_key: API key value.
        header_name: Header name for the API key (default: 'X-API-Key').

    Example:
        >>> api_key_auth(client, context, "sk-api-key-12345")
        >>> # Or with custom header
        >>> api_key_auth(client, context, "sk-api-key-12345", header_name="Authorization")
    """
    set_auth_context(
        context=context,
        auth_type="api_key",
        api_key=api_key,
        api_key_header=header_name,
    )


def bearer_token_auth(
    client: Client,
    context: Context,
    token: str,
    expires_in: int | None = None,
    refresh_token: str | None = None,
) -> None:
    """Set up Bearer token authentication.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        token: Bearer token value.
        expires_in: Token expiration time in seconds from now.
        refresh_token: Refresh token for token renewal.

    Example:
        >>> bearer_token_auth(
        ...     client, context,
        ...     token="eyJhbGciOiJIUzI1NiIs...",
        ...     expires_in=3600,
        ...     refresh_token="refresh_token_value"
        ... )
    """
    expires_at = None
    if expires_in:
        expires_at = time.time() + expires_in

    set_auth_context(
        context=context,
        auth_type="bearer",
        token=token,
        expires_at=expires_at,
        refresh_token=refresh_token,
    )


def oauth2_login(
    client: Client,
    context: Context,
    client_id: str,
    client_secret: str,
    token_url: str | None = None,
    scope: str | None = None,
    username: str | None = None,
    password: str | None = None,
    redirect_uri: str | None = None,
    authorization_url: str | None = None,
) -> dict[str, Any]:
    """Perform OAuth2 login (Resource Owner Password Credentials or Client Credentials).

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        client_id: OAuth2 client ID.
        client_secret: OAuth2 client secret.
        token_url: Token endpoint URL. If None, uses /oauth/token.
        scope: OAuth2 scope.
        username: Username for password grant (optional).
        password: Password for password grant (optional).
        redirect_uri: Redirect URI for authorization code flow.
        authorization_url: Authorization URL for authorization code flow.

    Returns:
        dict: Token response containing access_token, refresh_token, etc.

    Raises:
        AuthError: If OAuth2 login fails.

    Example:
        >>> # Client Credentials flow
        >>> tokens = oauth2_login(
        ...     client, context,
        ...     client_id="my-client-id",
        ...     client_secret="my-client-secret"
        ... )
        >>>
        >>> # Resource Owner Password Credentials flow
        >>> tokens = oauth2_login(
        ...     client, context,
        ...     client_id="my-client-id",
        ...     client_secret="my-client-secret",
        ...     username="user@example.com",
        ...     password="password123"
        ... )
    """
    base_url = _get_base_url(client, context)

    if not token_url:
        token_url = f"{base_url}/oauth/token"
    elif not token_url.startswith("http"):
        token_url = f"{base_url}/{token_url.lstrip('/')}"

    data: dict[str, str] = {
        "client_id": client_id,
        "client_secret": client_secret,
    }

    if username and password:
        data["grant_type"] = "password"
        data["username"] = username
        data["password"] = password
    else:
        data["grant_type"] = "client_credentials"

    if scope:
        data["scope"] = scope

    http_client = getattr(client, "http_client", None) or httpx.Client()

    try:
        response = http_client.post(
            token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        token_data = response.json()
    except httpx.HTTPError as e:
        raise AuthError(f"OAuth2 login failed: {token_url}") from e

    access_token = token_data.get("access_token")
    if not access_token:
        raise AuthError("OAuth2 response missing access_token")

    expires_in = token_data.get("expires_in")
    refresh_token = token_data.get("refresh_token")

    set_auth_context(
        context=context,
        auth_type="bearer",
        token=access_token,
        expires_at=time.time() + expires_in if expires_in else None,
        refresh_token=refresh_token,
    )

    context.oauth2_tokens = token_data
    return token_data


def oauth2_client_credentials(
    client: Client,
    context: Context,
    client_id: str,
    client_secret: str,
    token_url: str | None = None,
    scope: str | None = None,
) -> dict[str, Any]:
    """Perform OAuth2 Client Credentials flow.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        client_id: OAuth2 client ID.
        client_secret: OAuth2 client secret.
        token_url: Token endpoint URL. If None, uses /oauth/token.
        scope: OAuth2 scope.

    Returns:
        dict: Token response containing access_token, etc.

    Raises:
        AuthError: If OAuth2 login fails.

    Example:
        >>> tokens = oauth2_client_credentials(
        ...     client, context,
        ...     client_id="my-client-id",
        ...     client_secret="my-client-secret",
        ...     scope="read write"
        ... )
    """
    return oauth2_login(
        client=client,
        context=context,
        client_id=client_id,
        client_secret=client_secret,
        token_url=token_url,
        scope=scope,
    )


def oauth2_refresh_token(
    client: Client,
    context: Context,
    client_id: str | None = None,
    client_secret: str | None = None,
    token_url: str | None = None,
) -> dict[str, Any]:
    """Refresh OAuth2 access token using refresh token.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        client_id: OAuth2 client ID. If None, uses stored credentials.
        client_secret: OAuth2 client secret. If None, uses stored credentials.
        token_url: Token endpoint URL.

    Returns:
        dict: New token response.

    Raises:
        AuthError: If refresh fails or no refresh token available.

    Example:
        >>> new_tokens = oauth2_refresh_token(client, context)
    """
    auth = getattr(context, "_auth", {})
    oauth2_tokens = getattr(context, "oauth2_tokens", {})

    refresh_token = auth.get("refresh_token") or oauth2_tokens.get("refresh_token")
    if not refresh_token:
        raise AuthError("No refresh token available")

    client_id = client_id or oauth2_tokens.get("client_id")
    client_secret = client_secret or oauth2_tokens.get("client_secret")

    if not client_id:
        raise AuthError("Client ID required for token refresh")

    base_url = _get_base_url(client, context)
    if not token_url:
        token_url = f"{base_url}/oauth/token"
    elif not token_url.startswith("http"):
        token_url = f"{base_url}/{token_url.lstrip('/')}"

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }

    if client_secret:
        data["client_secret"] = client_secret

    http_client = getattr(client, "http_client", None) or httpx.Client()

    try:
        response = http_client.post(
            token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        token_data = response.json()
    except httpx.HTTPError as e:
        raise AuthError(f"OAuth2 token refresh failed: {token_url}") from e

    access_token = token_data.get("access_token")
    if not access_token:
        raise AuthError("OAuth2 refresh response missing access_token")

    expires_in = token_data.get("expires_in")
    new_refresh_token = token_data.get("refresh_token", refresh_token)

    set_auth_context(
        context=context,
        auth_type="bearer",
        token=access_token,
        expires_at=time.time() + expires_in if expires_in else None,
        refresh_token=new_refresh_token,
    )

    context.oauth2_tokens = {**token_data, "client_id": client_id, "client_secret": client_secret}
    return token_data


def jwt_login(
    client: Client,
    context: Context,
    username: str,
    password: str,
    login_url: str | None = None,
    token_field: str = "token",
    username_field: str = "username",
    password_field: str = "password",
    expires_in_field: str | None = "expires_in",
    refresh_token_field: str | None = "refresh_token",
) -> dict[str, Any]:
    """Perform JWT-based login.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        username: Username for login.
        password: Password for login.
        login_url: Login endpoint URL. If None, uses /auth/login.
        token_field: Field name in response containing the token.
        username_field: Field name for username in request body.
        password_field: Field name for password in request body.
        expires_in_field: Field name for expiration time (optional).
        refresh_token_field: Field name for refresh token (optional).

    Returns:
        dict: Login response data.

    Raises:
        AuthError: If login fails.

    Example:
        >>> tokens = jwt_login(
        ...     client, context,
        ...     username="user@example.com",
        ...     password="password123"
        ... )
        >>>
        >>> # With custom field names
        >>> tokens = jwt_login(
        ...     client, context,
        ...     username="user@example.com",
        ...     password="password123",
        ...     token_field="access_token",
        ...     login_url="/api/auth/signin"
        ... )
    """
    base_url = _get_base_url(client, context)

    if not login_url:
        login_url = f"{base_url}/auth/login"
    elif not login_url.startswith("http"):
        login_url = f"{base_url}/{login_url.lstrip('/')}"

    payload = {
        username_field: username,
        password_field: password,
    }

    http_client = getattr(client, "http_client", None) or httpx.Client()

    try:
        response = http_client.post(login_url, json=payload)
        response.raise_for_status()
        login_data = response.json()
    except httpx.HTTPError as e:
        raise AuthError(f"JWT login failed: {login_url}") from e

    token = login_data.get(token_field)
    if not token:
        raise AuthError(f"Login response missing '{token_field}' field")

    expires_in = None
    if expires_in_field and expires_in_field in login_data:
        expires_in = login_data[expires_in_field]

    refresh_token = None
    if refresh_token_field and refresh_token_field in login_data:
        refresh_token = login_data[refresh_token_field]

    set_auth_context(
        context=context,
        auth_type="bearer",
        token=token,
        expires_at=time.time() + expires_in if expires_in else None,
        refresh_token=refresh_token,
    )

    context.jwt_data = login_data
    return login_data


def decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode JWT payload without verification.

    Args:
        token: JWT token string.

    Returns:
        dict: Decoded payload.

    Raises:
        AuthError: If token is invalid.

    Example:
        >>> payload = decode_jwt_payload(token)
        >>> print(payload["sub"])  # user ID
        >>> print(payload["exp"])  # expiration time
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthError("Invalid JWT format")

        payload = parts[1]
        padding = len(payload) % 4
        if padding:
            payload += "=" * (4 - padding)

        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception as e:
        raise AuthError("Failed to decode JWT") from e


def is_token_expired(context: Context, buffer_seconds: int = 60) -> bool:
    """Check if the current auth token is expired or about to expire.

    Args:
        context: Test context containing auth information.
        buffer_seconds: Seconds before actual expiration to consider expired.

    Returns:
        bool: True if token is expired or about to expire.

    Example:
        >>> if is_token_expired(context):
        ...     oauth2_refresh_token(client, context)
    """
    auth = getattr(context, "_auth", {})
    expires_at = auth.get("expires_at")

    if not expires_at:
        return False

    return time.time() >= (expires_at - buffer_seconds)


def ensure_authenticated(
    client: Client,
    context: Context,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> None:
    """Ensure the context has valid authentication, refreshing if needed.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        client_id: OAuth2 client ID for refresh.
        client_secret: OAuth2 client secret for refresh.

    Raises:
        AuthError: If token is expired and cannot be refreshed.

    Example:
        >>> ensure_authenticated(client, context)
        >>> response = get(client, context, "/api/protected")
    """
    auth = getattr(context, "_auth", {})
    if not auth:
        raise AuthError("No authentication set in context")

    if is_token_expired(context):
        refresh_token = auth.get("refresh_token")
        if refresh_token:
            oauth2_refresh_token(
                client=client,
                context=context,
                client_id=client_id,
                client_secret=client_secret,
            )
        else:
            raise AuthError("Token expired and no refresh token available")
