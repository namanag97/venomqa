"""OpenAPI response schema invariant.

Validates every API response against the OpenAPI spec automatically.
Catches missing required fields, wrong types, and schema drift without
writing individual invariants per endpoint.

Usage::

    from venomqa.v1.invariants import OpenAPISchemaInvariant
    from venomqa.v1 import Severity

    invariants = [
        OpenAPISchemaInvariant(
            spec_url="http://localhost:8000/openapi.json",
            severity=Severity.HIGH,
        )
    ]

Or from a local file::

    invariants = [
        OpenAPISchemaInvariant(spec_path="api-spec.yaml")
    ]
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from venomqa.v1.world import World


class OpenAPISchemaInvariant:
    """Validates every HTTP response against the OpenAPI spec schema.

    After each action, checks that the response body matches the schema
    defined in the spec for that path + method + status code.

    Catches:
    - Missing required fields in responses
    - Wrong types (string where integer expected)
    - Schema drift between spec and implementation
    - Undocumented fields (when additionalProperties=false)

    This invariant wraps itself as a VenomQA Invariant when added to
    Agent(invariants=[...]). It can be used directly or instantiated
    and passed as-is — the Agent accepts objects with a .check() method
    and .name / .message / .severity / .timing attributes.

    Args:
        spec_url: HTTP/HTTPS URL to a live OpenAPI JSON endpoint.
        spec_path: Path to a local .yaml, .yml, or .json spec file.
        severity: Violation severity (default: HIGH).
        ignore_paths: List of path prefixes to skip (e.g. ["/health"]).
            Useful for internal endpoints with non-standard schemas.
    """

    name = "openapi_schema"
    timing: Any = None  # set to InvariantTiming.POST_ACTION at first use

    def __init__(
        self,
        spec_url: str | None = None,
        spec_path: str | None = None,
        severity: Any | None = None,
        ignore_paths: list[str] | None = None,
    ) -> None:
        if spec_url is None and spec_path is None:
            raise ValueError("Provide either spec_url= or spec_path=")

        from venomqa.v1.cli.scaffold import load_spec
        from venomqa.v1.core.invariant import InvariantTiming, Severity

        source = spec_url or spec_path
        self._spec = load_spec(source)  # type: ignore[arg-type]
        self._route_map = _build_route_map(self._spec)
        self.severity = severity or Severity.HIGH
        self.timing = InvariantTiming.POST_ACTION
        self.ignore_paths = ignore_paths or []
        self._last_error: str = ""
        self.message = "API response does not match OpenAPI schema"

    def check(self, world: World) -> bool:
        """Check last response against the OpenAPI spec.

        Returns True (pass) if:
        - No action result yet
        - The endpoint is not in the spec
        - The status code is not documented (not our problem)
        - Response body matches the schema

        Returns False (violation) if the response body violates the schema.
        """
        ar = world.last_action_result
        if ar is None or ar.response is None:
            return True

        req = ar.request
        resp = ar.response

        # Extract path from URL (strip base URL)
        raw_url = req.url
        try:
            parsed = urlparse(raw_url)
            path = parsed.path
        except Exception:
            return True

        # Skip ignored paths
        for prefix in self.ignore_paths:
            if path.startswith(prefix):
                return True

        method = req.method.lower()
        status = resp.status_code

        # Find matching spec route
        schema = _lookup_schema(self._route_map, method, path, status)
        if schema is None:
            return True  # not in spec → skip

        # Validate response body
        body = resp.body
        ok, error = _validate(body, schema)
        if not ok:
            self._last_error = error
            self.message = (
                f"Response schema violation for {req.method} {path} → {status}: {error}"
            )
            return False

        return True

    # Make this object duck-type compatible with Invariant
    # so it can be passed directly to Agent(invariants=[...])
    def __call__(self, world: World) -> bool:
        return self.check(world)


# ─── Route map builder ────────────────────────────────────────────────────────

def _build_route_map(
    spec: dict[str, Any],
) -> list[tuple[re.Pattern[str], str, dict[int, dict[str, Any]]]]:
    """Parse spec paths into a list of (path_regex, method, {status: schema}) tuples."""
    routes: list[tuple[re.Pattern[str], str, dict[int, dict[str, Any]]]] = []
    http_methods = {"get", "post", "put", "patch", "delete", "head", "options"}

    for path_pattern, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        # Convert /users/{id} → regex ^/users/[^/]+$
        regex_str = re.sub(r"\{[^}]+\}", r"[^/]+", path_pattern)
        regex_str = "^" + regex_str.rstrip("/") + "/?$"
        try:
            path_re = re.compile(regex_str)
        except re.error:
            continue

        for method, operation in path_item.items():
            if method.lower() not in http_methods:
                continue
            if not isinstance(operation, dict):
                continue

            status_schemas: dict[int, dict[str, Any]] = {}
            for code_str, response_spec in operation.get("responses", {}).items():
                try:
                    code = int(code_str)
                except (ValueError, TypeError):
                    continue
                if not isinstance(response_spec, dict):
                    continue
                schema = _extract_schema(response_spec)
                if schema:
                    status_schemas[code] = schema

            if status_schemas:
                routes.append((path_re, method.lower(), status_schemas))

    return routes


def _extract_schema(response_spec: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the inline JSON schema from a response object (no $ref resolution)."""
    content = response_spec.get("content", {})
    for _, media_obj in content.items():
        if not isinstance(media_obj, dict):
            continue
        schema = media_obj.get("schema")
        if schema and isinstance(schema, dict) and "$ref" not in schema:
            return schema
    return None


def _lookup_schema(
    route_map: list[tuple[re.Pattern[str], str, dict[int, dict[str, Any]]]],
    method: str,
    path: str,
    status: int,
) -> dict[str, Any] | None:
    """Find the schema for a given (method, path, status) combination."""
    for path_re, route_method, status_schemas in route_map:
        if route_method != method.lower():
            continue
        if not path_re.match(path.rstrip("/")):
            continue
        return status_schemas.get(status)
    return None


# ─── Validator ───────────────────────────────────────────────────────────────

def _validate(body: Any, schema: dict[str, Any]) -> tuple[bool, str]:
    """Validate a response body against an inline OpenAPI schema.

    Tries jsonschema first (full validation). Falls back to a structural
    check (required fields + type) if jsonschema is not installed.

    Returns (True, "") on pass, (False, error_message) on failure.
    """
    try:
        import jsonschema  # type: ignore[import-untyped]
        try:
            jsonschema.validate(instance=body, schema=schema)
            return True, ""
        except jsonschema.ValidationError as exc:
            return False, exc.message
        except jsonschema.SchemaError:
            return True, ""  # malformed schema → don't block
    except ImportError:
        pass  # jsonschema not installed → fall back to basic check

    return _basic_validate(body, schema)


def _basic_validate(body: Any, schema: dict[str, Any]) -> tuple[bool, str]:
    """Basic structural validation without jsonschema.

    Checks:
    - Schema type matches actual type
    - Required fields are present (for object types)
    """
    schema_type = schema.get("type")

    if schema_type == "object":
        if not isinstance(body, dict):
            return False, f"Expected object, got {type(body).__name__}"
        required = schema.get("required", [])
        missing = [k for k in required if k not in body]
        if missing:
            return False, f"Missing required field(s): {missing}"

    elif schema_type == "array":
        if not isinstance(body, list):
            return False, f"Expected array, got {type(body).__name__}"

    elif schema_type == "string":
        if not isinstance(body, str):
            return False, f"Expected string, got {type(body).__name__}"

    elif schema_type == "integer":
        if not isinstance(body, int) or isinstance(body, bool):
            return False, f"Expected integer, got {type(body).__name__}"

    elif schema_type == "number":
        if not isinstance(body, (int, float)) or isinstance(body, bool):
            return False, f"Expected number, got {type(body).__name__}"

    elif schema_type == "boolean":
        if not isinstance(body, bool):
            return False, f"Expected boolean, got {type(body).__name__}"

    return True, ""
