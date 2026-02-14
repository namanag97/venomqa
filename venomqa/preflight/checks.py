"""Individual preflight check implementations.

Each check class encapsulates the logic for a specific kind of API
health validation. Checks are designed to be fast, independent, and
to produce clear error messages with actionable suggestions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx


# ---------------------------------------------------------------------------
# Suggestions -- reusable hints attached to failed checks
# ---------------------------------------------------------------------------

SUGGESTIONS: dict[str, dict[int | str, str]] = {
    "health": {
        0: "Could not connect to the server. Is it running?",
        404: "Health endpoint not found. Verify the path is correct (try /health, /healthz, /api/health).",
        500: "Health endpoint returned 500. The server may be starting up or misconfigured.",
        503: "Service unavailable. The server may still be initializing.",
    },
    "auth": {
        0: "Could not connect to the server. Is it running?",
        401: (
            "Authentication failed. Verify your token is valid and not expired. "
            "Check that the user referenced in the JWT actually exists in the database."
        ),
        403: (
            "Authorization denied. The token may be valid but lacks permissions. "
            "Check role assignments and workspace access."
        ),
        404: "Endpoint not found. Verify the API path is correct.",
        500: (
            "Server returned 500 on authenticated request. Common causes: "
            "JWT user doesn't exist in DB, workspace_ids reference non-existent workspaces, "
            "missing database records, FK violations."
        ),
    },
    "create": {
        0: "Could not connect to the server. Is it running?",
        401: "Authentication failed on create request. Check your token.",
        403: "Authorization denied on create. Check permissions.",
        404: "Create endpoint not found. Verify the API path.",
        409: "Resource already exists (conflict). This may be expected if data was seeded.",
        422: (
            "Validation error on create. The payload may not match the API schema. "
            "Check required fields and data types."
        ),
        500: (
            "Server returned 500 on create. Check server logs for stack trace. "
            "Common causes: missing database records, FK violations, unhandled exceptions."
        ),
    },
    "list": {
        0: "Could not connect to the server. Is it running?",
        401: "Authentication failed on list request. Check your token.",
        403: "Authorization denied on list. Check permissions.",
        404: "List endpoint not found. Verify the API path and that the resource/workspace exists.",
        500: "Server returned 500 on list. Check server logs for stack trace.",
    },
    "database": {
        500: (
            "Database operation failed. Common causes: "
            "missing migrations, FK constraint violations, "
            "user referenced in JWT doesn't exist in users table."
        ),
    },
    "openapi": {
        0: "Could not connect to the server. Is it running?",
        404: (
            "OpenAPI spec not found. Common paths: "
            "/openapi.json, /docs/openapi.json, /api/openapi.json, /swagger.json"
        ),
        500: "Server error when fetching OpenAPI spec.",
    },
    "connection": {
        "refused": "Connection refused. Is the server running on the expected host and port?",
        "timeout": "Connection timed out. The server may be overloaded or the port may be wrong.",
        "dns": "DNS resolution failed. Check the hostname is correct.",
    },
}


def _get_suggestion(category: str, status_code: int | str) -> str | None:
    """Look up a suggestion for a given category and status code."""
    cat = SUGGESTIONS.get(category, {})
    return cat.get(status_code)


def _connection_suggestion(error: Exception) -> str:
    """Derive a suggestion from a connection-level exception."""
    err_str = str(error).lower()
    if "refused" in err_str:
        return SUGGESTIONS["connection"]["refused"]
    if "timed out" in err_str or "timeout" in err_str:
        return SUGGESTIONS["connection"]["timeout"]
    if "name or service not known" in err_str or "nodename nor servname" in err_str:
        return SUGGESTIONS["connection"]["dns"]
    return f"Could not connect: {error}"


# ---------------------------------------------------------------------------
# SmokeTestResult -- returned by every check
# ---------------------------------------------------------------------------

@dataclass
class SmokeTestResult:
    """Result of a single smoke test check.

    Attributes:
        name: Human-readable check name (e.g. "Health check").
        passed: Whether the check succeeded.
        status_code: HTTP status code received, or None if connection failed.
        error: Error description when the check failed.
        duration_ms: How long the check took in milliseconds.
        suggestion: Actionable hint for fixing the failure.
        response_body: Optional truncated response body for diagnostics.
    """

    name: str
    passed: bool
    status_code: int | None = None
    error: str | None = None
    duration_ms: float = 0.0
    suggestion: str | None = None
    response_body: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        d: dict[str, Any] = {
            "name": self.name,
            "passed": self.passed,
            "duration_ms": round(self.duration_ms, 2),
        }
        if self.status_code is not None:
            d["status_code"] = self.status_code
        if self.error:
            d["error"] = self.error
        if self.suggestion:
            d["suggestion"] = self.suggestion
        return d


# ---------------------------------------------------------------------------
# Base check
# ---------------------------------------------------------------------------

class BaseCheck:
    """Base class for all preflight checks."""

    name: str = "base"

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        timeout: float = 10.0,
        auth_header: str = "Authorization",
        auth_prefix: str = "Bearer",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.auth_header = auth_header
        self.auth_prefix = auth_prefix

    def _headers(self) -> dict[str, str]:
        """Build request headers including auth if available."""
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "VenomQA-Preflight/1.0",
        }
        if self.token:
            prefix_lower = self.auth_prefix.lower() + " "
            # Support both raw tokens and pre-formatted "Bearer <token>"
            if self.token.lower().startswith(prefix_lower):
                headers[self.auth_header] = self.token
            else:
                headers[self.auth_header] = f"{self.auth_prefix} {self.token}"
        return headers

    def _url(self, path: str) -> str:
        """Build a full URL from a path."""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}{path}" if path.startswith("/") else f"{self.base_url}/{path}"

    def run(self) -> SmokeTestResult:
        """Execute the check. Subclasses must override this."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# HealthCheck
# ---------------------------------------------------------------------------

class HealthCheck(BaseCheck):
    """Check that a health endpoint is accessible and returns 2xx.

    This is the most basic check -- if the health endpoint doesn't respond,
    nothing else will work.
    """

    name = "Health check"

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        timeout: float = 10.0,
        path: str = "/health",
    ) -> None:
        super().__init__(base_url, token, timeout)
        self.path = path

    def run(self) -> SmokeTestResult:
        start = time.perf_counter()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(
                    self._url(self.path),
                    headers=self._headers(),
                )
            duration = (time.perf_counter() - start) * 1000

            if 200 <= resp.status_code < 300:
                return SmokeTestResult(
                    name=self.name,
                    passed=True,
                    status_code=resp.status_code,
                    duration_ms=duration,
                )

            return SmokeTestResult(
                name=self.name,
                passed=False,
                status_code=resp.status_code,
                error=f"Expected 2xx, got {resp.status_code}",
                duration_ms=duration,
                suggestion=_get_suggestion("health", resp.status_code),
            )

        except (httpx.ConnectError, httpx.ConnectTimeout, OSError) as exc:
            duration = (time.perf_counter() - start) * 1000
            return SmokeTestResult(
                name=self.name,
                passed=False,
                status_code=None,
                error=str(exc),
                duration_ms=duration,
                suggestion=_connection_suggestion(exc),
            )
        except httpx.HTTPError as exc:
            duration = (time.perf_counter() - start) * 1000
            return SmokeTestResult(
                name=self.name,
                passed=False,
                status_code=None,
                error=str(exc),
                duration_ms=duration,
                suggestion=_get_suggestion("health", 0),
            )


# ---------------------------------------------------------------------------
# AuthCheck
# ---------------------------------------------------------------------------

class AuthCheck(BaseCheck):
    """Check that an authenticated request succeeds (not 401/403).

    This catches the common problem where a JWT references a user or
    workspace that doesn't exist in the database.
    """

    name = "Auth check"

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        timeout: float = 10.0,
        path: str = "/api/v1/workspaces",
    ) -> None:
        super().__init__(base_url, token, timeout)
        self.path = path

    def run(self) -> SmokeTestResult:
        if not self.token:
            return SmokeTestResult(
                name=self.name,
                passed=True,
                status_code=None,
                duration_ms=0.0,
                suggestion="No token provided; skipping auth check.",
            )

        start = time.perf_counter()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(
                    self._url(self.path),
                    headers=self._headers(),
                )
            duration = (time.perf_counter() - start) * 1000

            if resp.status_code in (401, 403):
                return SmokeTestResult(
                    name=self.name,
                    passed=False,
                    status_code=resp.status_code,
                    error=f"Authentication/authorization failed: HTTP {resp.status_code}",
                    duration_ms=duration,
                    suggestion=_get_suggestion("auth", resp.status_code),
                )

            if resp.status_code >= 500:
                # A 500 on an auth-protected endpoint often means the JWT user
                # doesn't exist or workspace references are broken.
                body_preview = resp.text[:500] if resp.text else ""
                return SmokeTestResult(
                    name=self.name,
                    passed=False,
                    status_code=resp.status_code,
                    error=f"Server error on authenticated request: HTTP {resp.status_code}",
                    duration_ms=duration,
                    suggestion=_get_suggestion("auth", resp.status_code),
                    response_body=body_preview,
                )

            return SmokeTestResult(
                name=self.name,
                passed=True,
                status_code=resp.status_code,
                duration_ms=duration,
            )

        except (httpx.ConnectError, httpx.ConnectTimeout, OSError) as exc:
            duration = (time.perf_counter() - start) * 1000
            return SmokeTestResult(
                name=self.name,
                passed=False,
                status_code=None,
                error=str(exc),
                duration_ms=duration,
                suggestion=_connection_suggestion(exc),
            )
        except httpx.HTTPError as exc:
            duration = (time.perf_counter() - start) * 1000
            return SmokeTestResult(
                name=self.name,
                passed=False,
                status_code=None,
                error=str(exc),
                duration_ms=duration,
                suggestion=_get_suggestion("auth", 0),
            )


# ---------------------------------------------------------------------------
# CRUDCheck
# ---------------------------------------------------------------------------

class CRUDCheck(BaseCheck):
    """Check that a basic create (POST) operation succeeds.

    This catches server errors like FK violations, missing records, and
    unhandled exceptions that would cause every test to fail.
    """

    name = "Create resource check"

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        timeout: float = 10.0,
        path: str = "/api/v1/resources",
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(base_url, token, timeout)
        self.path = path
        self.payload = payload or {}

    def run(self) -> SmokeTestResult:
        start = time.perf_counter()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    self._url(self.path),
                    json=self.payload,
                    headers=self._headers(),
                )
            duration = (time.perf_counter() - start) * 1000

            if resp.status_code in (200, 201):
                return SmokeTestResult(
                    name=self.name,
                    passed=True,
                    status_code=resp.status_code,
                    duration_ms=duration,
                )

            if resp.status_code == 409:
                # Conflict -- resource already exists, which is acceptable
                return SmokeTestResult(
                    name=self.name,
                    passed=True,
                    status_code=resp.status_code,
                    duration_ms=duration,
                    suggestion=_get_suggestion("create", 409),
                )

            body_preview = resp.text[:500] if resp.text else ""
            return SmokeTestResult(
                name=self.name,
                passed=False,
                status_code=resp.status_code,
                error=f"Create failed: HTTP {resp.status_code}",
                duration_ms=duration,
                suggestion=_get_suggestion("create", resp.status_code),
                response_body=body_preview,
            )

        except (httpx.ConnectError, httpx.ConnectTimeout, OSError) as exc:
            duration = (time.perf_counter() - start) * 1000
            return SmokeTestResult(
                name=self.name,
                passed=False,
                status_code=None,
                error=str(exc),
                duration_ms=duration,
                suggestion=_connection_suggestion(exc),
            )
        except httpx.HTTPError as exc:
            duration = (time.perf_counter() - start) * 1000
            return SmokeTestResult(
                name=self.name,
                passed=False,
                status_code=None,
                error=str(exc),
                duration_ms=duration,
                suggestion=_get_suggestion("create", 0),
            )


# ---------------------------------------------------------------------------
# ListCheck
# ---------------------------------------------------------------------------

class ListCheck(BaseCheck):
    """Check that a list endpoint returns a valid response.

    Verifies the endpoint returns 2xx and the body looks like a list
    (JSON array) or a paginated response (object with common pagination keys).
    """

    name = "List resources check"

    _PAGINATION_KEYS = {"data", "results", "items", "records", "entries", "content", "edges"}

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        timeout: float = 10.0,
        path: str = "/api/v1/resources",
    ) -> None:
        super().__init__(base_url, token, timeout)
        self.path = path

    def run(self) -> SmokeTestResult:
        start = time.perf_counter()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(
                    self._url(self.path),
                    headers=self._headers(),
                )
            duration = (time.perf_counter() - start) * 1000

            if resp.status_code >= 400:
                return SmokeTestResult(
                    name=self.name,
                    passed=False,
                    status_code=resp.status_code,
                    error=f"List endpoint returned HTTP {resp.status_code}",
                    duration_ms=duration,
                    suggestion=_get_suggestion("list", resp.status_code),
                )

            # Try to parse JSON and validate shape
            try:
                body = resp.json()
            except Exception:
                # Non-JSON response is acceptable -- some APIs return CSV, etc.
                return SmokeTestResult(
                    name=self.name,
                    passed=True,
                    status_code=resp.status_code,
                    duration_ms=duration,
                    suggestion="Response is not JSON; could not validate list shape.",
                )

            if isinstance(body, list):
                return SmokeTestResult(
                    name=self.name,
                    passed=True,
                    status_code=resp.status_code,
                    duration_ms=duration,
                )

            if isinstance(body, dict):
                # Check for common pagination wrapper keys
                if body.keys() & self._PAGINATION_KEYS:
                    return SmokeTestResult(
                        name=self.name,
                        passed=True,
                        status_code=resp.status_code,
                        duration_ms=duration,
                    )
                # Even if the keys don't match known pagination, a 200 dict is OK
                return SmokeTestResult(
                    name=self.name,
                    passed=True,
                    status_code=resp.status_code,
                    duration_ms=duration,
                    suggestion="Response is a JSON object but doesn't look like a standard list/paginated response.",
                )

            return SmokeTestResult(
                name=self.name,
                passed=True,
                status_code=resp.status_code,
                duration_ms=duration,
            )

        except (httpx.ConnectError, httpx.ConnectTimeout, OSError) as exc:
            duration = (time.perf_counter() - start) * 1000
            return SmokeTestResult(
                name=self.name,
                passed=False,
                status_code=None,
                error=str(exc),
                duration_ms=duration,
                suggestion=_connection_suggestion(exc),
            )
        except httpx.HTTPError as exc:
            duration = (time.perf_counter() - start) * 1000
            return SmokeTestResult(
                name=self.name,
                passed=False,
                status_code=None,
                error=str(exc),
                duration_ms=duration,
                suggestion=_get_suggestion("list", 0),
            )


# ---------------------------------------------------------------------------
# DatabaseCheck
# ---------------------------------------------------------------------------

class DatabaseCheck(BaseCheck):
    """Check that database-backed operations don't fail with FK errors.

    This performs a lightweight create-then-read cycle to verify that the
    database schema is in a good state (migrations applied, seed data present).
    """

    name = "Database check"

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        timeout: float = 10.0,
        create_path: str | None = None,
        create_payload: dict[str, Any] | None = None,
        read_path: str | None = None,
    ) -> None:
        super().__init__(base_url, token, timeout)
        self.create_path = create_path
        self.create_payload = create_payload or {}
        self.read_path = read_path

    def run(self) -> SmokeTestResult:
        # If no paths configured, skip gracefully
        if not self.create_path and not self.read_path:
            return SmokeTestResult(
                name=self.name,
                passed=True,
                status_code=None,
                duration_ms=0.0,
                suggestion="No database check paths configured; skipping.",
            )

        start = time.perf_counter()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                # Step 1: Create
                if self.create_path:
                    resp = client.post(
                        self._url(self.create_path),
                        json=self.create_payload,
                        headers=self._headers(),
                    )
                    if resp.status_code >= 500:
                        duration = (time.perf_counter() - start) * 1000
                        return SmokeTestResult(
                            name=self.name,
                            passed=False,
                            status_code=resp.status_code,
                            error=f"Database create failed: HTTP {resp.status_code}",
                            duration_ms=duration,
                            suggestion=_get_suggestion("database", 500),
                            response_body=resp.text[:500] if resp.text else None,
                        )

                # Step 2: Read
                if self.read_path:
                    resp = client.get(
                        self._url(self.read_path),
                        headers=self._headers(),
                    )
                    if resp.status_code >= 500:
                        duration = (time.perf_counter() - start) * 1000
                        return SmokeTestResult(
                            name=self.name,
                            passed=False,
                            status_code=resp.status_code,
                            error=f"Database read failed: HTTP {resp.status_code}",
                            duration_ms=duration,
                            suggestion=_get_suggestion("database", 500),
                            response_body=resp.text[:500] if resp.text else None,
                        )

            duration = (time.perf_counter() - start) * 1000
            return SmokeTestResult(
                name=self.name,
                passed=True,
                status_code=200,
                duration_ms=duration,
            )

        except (httpx.ConnectError, httpx.ConnectTimeout, OSError) as exc:
            duration = (time.perf_counter() - start) * 1000
            return SmokeTestResult(
                name=self.name,
                passed=False,
                status_code=None,
                error=str(exc),
                duration_ms=duration,
                suggestion=_connection_suggestion(exc),
            )
        except httpx.HTTPError as exc:
            duration = (time.perf_counter() - start) * 1000
            return SmokeTestResult(
                name=self.name,
                passed=False,
                status_code=None,
                error=str(exc),
                duration_ms=duration,
            )


# ---------------------------------------------------------------------------
# OpenAPICheck
# ---------------------------------------------------------------------------

class OpenAPICheck(BaseCheck):
    """Check that an OpenAPI specification is available and valid.

    Verifies the spec endpoint returns JSON with the expected top-level
    keys (openapi/swagger, info, paths).
    """

    name = "OpenAPI spec check"

    _COMMON_PATHS = [
        "/openapi.json",
        "/docs/openapi.json",
        "/api/openapi.json",
        "/swagger.json",
        "/api-docs",
        "/api/v1/openapi.json",
    ]

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        timeout: float = 10.0,
        path: str | None = None,
    ) -> None:
        super().__init__(base_url, token, timeout)
        self.path = path

    def run(self) -> SmokeTestResult:
        start = time.perf_counter()
        paths_to_try = [self.path] if self.path else self._COMMON_PATHS

        last_error: str | None = None
        last_code: int | None = None

        try:
            with httpx.Client(timeout=self.timeout) as client:
                for p in paths_to_try:
                    try:
                        resp = client.get(
                            self._url(p),
                            headers=self._headers(),
                        )
                    except httpx.HTTPError:
                        continue

                    if resp.status_code == 200:
                        # Validate it looks like an OpenAPI spec
                        try:
                            body = resp.json()
                            if isinstance(body, dict) and (
                                "openapi" in body
                                or "swagger" in body
                                or "paths" in body
                            ):
                                duration = (time.perf_counter() - start) * 1000
                                return SmokeTestResult(
                                    name=self.name,
                                    passed=True,
                                    status_code=200,
                                    duration_ms=duration,
                                )
                        except Exception:
                            pass

                    last_code = resp.status_code
                    last_error = f"HTTP {resp.status_code} at {p}"

        except (httpx.ConnectError, httpx.ConnectTimeout, OSError) as exc:
            duration = (time.perf_counter() - start) * 1000
            return SmokeTestResult(
                name=self.name,
                passed=False,
                status_code=None,
                error=str(exc),
                duration_ms=duration,
                suggestion=_connection_suggestion(exc),
            )

        duration = (time.perf_counter() - start) * 1000
        return SmokeTestResult(
            name=self.name,
            passed=False,
            status_code=last_code,
            error=last_error or "No OpenAPI spec found at any common path",
            duration_ms=duration,
            suggestion=_get_suggestion("openapi", last_code or 404),
        )
