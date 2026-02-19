"""Auto-discovery of API endpoints for preflight testing.

AutoPreflight can inspect an OpenAPI specification to automatically
determine which endpoints to smoke test, what payloads to use, and
where health endpoints live -- without any manual configuration.

Example:
    >>> from venomqa.preflight.auto import AutoPreflight
    >>> auto = AutoPreflight.from_openapi("http://localhost:8000/openapi.json")
    >>> report = auto.run()
    >>> report.print_report()
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from venomqa.preflight.checks import (
    AuthCheck,
    CRUDCheck,
    HealthCheck,
    ListCheck,
    SmokeTestResult,
)
from venomqa.preflight.smoke import SmokeTest, SmokeTestReport

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def _generate_sample_value(schema: dict[str, Any]) -> Any:
    """Generate a plausible sample value from an OpenAPI schema object."""
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    if "enum" in schema:
        return schema["enum"][0]

    typ = schema.get("type", "string")
    fmt = schema.get("format", "")

    if typ == "string":
        if fmt == "email":
            return "test@example.com"
        if fmt == "uri" or fmt == "url":
            return "https://example.com"
        if fmt == "date":
            return "2024-01-01"
        if fmt == "date-time":
            return "2024-01-01T00:00:00Z"
        if fmt == "uuid":
            return "00000000-0000-0000-0000-000000000000"
        if fmt == "password":
            return "TestPassword123!"
        min_len = schema.get("minLength", 1)
        return "test" * max(1, min_len // 4)
    if typ == "integer":
        return schema.get("minimum", 1)
    if typ == "number":
        return schema.get("minimum", 1.0)
    if typ == "boolean":
        return True
    if typ == "array":
        items = schema.get("items", {"type": "string"})
        return [_generate_sample_value(items)]
    if typ == "object":
        props = schema.get("properties", {})
        required = set(schema.get("required", props.keys()))
        obj: dict[str, Any] = {}
        for key, prop_schema in props.items():
            if key in required:
                obj[key] = _generate_sample_value(prop_schema)
        return obj

    return "test"


def _resolve_ref(spec: dict[str, Any], ref: str) -> dict[str, Any]:
    """Resolve a $ref pointer within the spec."""
    parts = ref.lstrip("#/").split("/")
    node: Any = spec
    for part in parts:
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict):
            node = node.get(part, {})
        else:
            return {}
    return node if isinstance(node, dict) else {}


def _resolve_schema(spec: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively resolve $ref in a schema."""
    if "$ref" in schema:
        return _resolve_schema(spec, _resolve_ref(spec, schema["$ref"]))
    return schema


# ---------------------------------------------------------------------------
# AutoPreflight
# ---------------------------------------------------------------------------

class AutoPreflight:
    """Automatically discover and test API endpoints.

    Can be created from an OpenAPI spec URL or from a pre-parsed spec dict.
    Discovers health endpoints, CRUD endpoints, and generates sample payloads.

    Attributes:
        base_url: The API root URL.
        spec: Parsed OpenAPI specification dictionary.
        token: Optional auth token.
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str,
        spec: dict[str, Any],
        token: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.spec = spec
        self.token = token
        self.timeout = timeout

    @classmethod
    def from_openapi(
        cls,
        spec_url: str,
        token: str | None = None,
        timeout: float = 10.0,
    ) -> AutoPreflight:
        """Create an AutoPreflight from an OpenAPI spec URL.

        Fetches and parses the spec, then extracts the base URL from the
        spec's ``servers`` field (or falls back to the spec URL's origin).

        Args:
            spec_url: Full URL to the OpenAPI JSON spec.
            token: Optional auth token.
            timeout: HTTP timeout in seconds.

        Returns:
            Configured AutoPreflight instance.

        Raises:
            httpx.HTTPError: If the spec cannot be fetched.
            ValueError: If the response is not valid JSON.
        """
        headers: dict[str, str] = {"Accept": "application/json"}
        if token:
            if token.lower().startswith("bearer "):
                headers["Authorization"] = token
            else:
                headers["Authorization"] = f"Bearer {token}"

        with httpx.Client(timeout=timeout) as client:
            resp = client.get(spec_url, headers=headers)
            resp.raise_for_status()
            spec = resp.json()

        # Determine base URL from spec or fall back to spec_url origin
        base_url = spec_url.rsplit("/", 1)[0]  # strip the filename
        servers = spec.get("servers", [])
        if servers and isinstance(servers[0], dict) and "url" in servers[0]:
            server_url = servers[0]["url"]
            if server_url.startswith("http"):
                base_url = server_url

        return cls(
            base_url=base_url,
            spec=spec,
            token=token,
            timeout=timeout,
        )

    @classmethod
    def from_spec_dict(
        cls,
        base_url: str,
        spec: dict[str, Any],
        token: str | None = None,
        timeout: float = 10.0,
    ) -> AutoPreflight:
        """Create from a pre-parsed spec dictionary.

        Args:
            base_url: API root URL.
            spec: Parsed OpenAPI spec.
            token: Optional auth token.
            timeout: HTTP timeout in seconds.
        """
        return cls(base_url=base_url, spec=spec, token=token, timeout=timeout)

    # ----- Discovery methods -----

    def discover_health_endpoints(self) -> list[str]:
        """Find health/readiness/liveness endpoints in the spec.

        Looks for paths containing common health-check keywords. Falls back
        to well-known paths if nothing is found in the spec.

        Returns:
            List of endpoint paths (e.g. ["/health", "/readyz"]).
        """
        health_keywords = {"health", "healthz", "ready", "readyz", "live", "livez", "ping", "status"}
        found: list[str] = []

        paths = self.spec.get("paths", {})
        for path in paths:
            segments = {s.lower() for s in path.strip("/").split("/")}
            if segments & health_keywords:
                found.append(path)

        if not found:
            # Fall back to common paths
            found = ["/health", "/healthz", "/api/health"]

        return found

    def discover_crud_endpoints(self) -> list[tuple[str, str, dict[str, Any]]]:
        """Find POST endpoints with request bodies for create-resource checks.

        Parses the OpenAPI spec to find endpoints that accept POST requests
        with JSON bodies, then generates sample payloads from the schemas.

        Returns:
            List of (path, method, sample_payload) tuples.
        """
        endpoints: list[tuple[str, str, dict[str, Any]]] = []
        paths = self.spec.get("paths", {})

        for path, methods in paths.items():
            if not isinstance(methods, dict):
                continue

            for method in ("post", "put"):
                operation = methods.get(method)
                if not operation or not isinstance(operation, dict):
                    continue

                # Skip if it looks like auth/login
                op_id = (operation.get("operationId") or "").lower()
                summary = (operation.get("summary") or "").lower()
                tags = [t.lower() for t in operation.get("tags", [])]
                if any(kw in (op_id + summary + " ".join(tags)) for kw in ("login", "auth", "token", "session")):
                    continue

                # Extract request body schema
                request_body = operation.get("requestBody", {})
                if not isinstance(request_body, dict):
                    continue

                # Resolve $ref on requestBody
                if "$ref" in request_body:
                    request_body = _resolve_ref(self.spec, request_body["$ref"])

                content = request_body.get("content", {})
                json_content = content.get("application/json", {})
                schema = json_content.get("schema", {})

                if not schema:
                    continue

                resolved = _resolve_schema(self.spec, schema)
                payload = _generate_sample_value(resolved)
                if isinstance(payload, dict):
                    endpoints.append((path, method, payload))

        return endpoints

    def discover_list_endpoints(self) -> list[str]:
        """Find GET endpoints that return arrays/lists.

        Returns:
            List of endpoint paths that appear to return collections.
        """
        list_endpoints: list[str] = []
        paths = self.spec.get("paths", {})

        for path, methods in paths.items():
            if not isinstance(methods, dict):
                continue

            get_op = methods.get("get")
            if not get_op or not isinstance(get_op, dict):
                continue

            # Skip paths with path parameters (these are detail views)
            if "{" in path:
                continue

            # Check if response schema is an array or paginated
            responses = get_op.get("responses", {})
            success_resp = responses.get("200") or responses.get("201") or {}
            if "$ref" in success_resp:
                success_resp = _resolve_ref(self.spec, success_resp["$ref"])

            content = success_resp.get("content", {})
            json_content = content.get("application/json", {})
            schema = json_content.get("schema", {})

            if schema:
                resolved = _resolve_schema(self.spec, schema)
                if resolved.get("type") == "array":
                    list_endpoints.append(path)
                    continue
                # Paginated response (object with array property)
                if resolved.get("type") == "object":
                    props = resolved.get("properties", {})
                    for prop_schema in props.values():
                        prop_resolved = _resolve_schema(self.spec, prop_schema)
                        if prop_resolved.get("type") == "array":
                            list_endpoints.append(path)
                            break
                    continue

            # If no schema info, include paths that look like collections
            segments = path.rstrip("/").split("/")
            if segments and not segments[-1].startswith("{"):
                list_endpoints.append(path)

        return list_endpoints

    # ----- Run -----

    def run(self) -> SmokeTestReport:
        """Run all discovered checks against the API.

        Executes:
        1. Health checks on discovered health endpoints
        2. Auth check (if token provided)
        3. Create checks on discovered POST endpoints (up to 3)
        4. List checks on discovered GET endpoints (up to 3)

        Returns:
            SmokeTestReport with all results.
        """
        SmokeTest(
            base_url=self.base_url,
            token=self.token,
            timeout=self.timeout,
        )

        results: list[SmokeTestResult] = []
        start = time.perf_counter()

        # Health checks
        health_paths = self.discover_health_endpoints()
        for hp in health_paths[:2]:  # test up to 2 health endpoints
            check = HealthCheck(self.base_url, self.token, self.timeout, path=hp)
            results.append(check.run())

        # Auth check
        if self.token:
            list_eps = self.discover_list_endpoints()
            auth_path = list_eps[0] if list_eps else "/api/v1/workspaces"
            check = AuthCheck(self.base_url, self.token, self.timeout, path=auth_path)
            results.append(check.run())

        # Create checks
        crud_eps = self.discover_crud_endpoints()
        for path, method, payload in crud_eps[:3]:
            check = CRUDCheck(
                self.base_url, self.token, self.timeout,
                path=path, payload=payload,
            )
            check.name = f"Create: {method.upper()} {path}"
            results.append(check.run())

        # List checks
        list_eps = self.discover_list_endpoints()
        for lp in list_eps[:3]:
            check = ListCheck(self.base_url, self.token, self.timeout, path=lp)
            check.name = f"List: GET {lp}"
            results.append(check.run())

        total_duration = (time.perf_counter() - start) * 1000

        return SmokeTestReport(
            results=results,
            total_duration_ms=total_duration,
        )
