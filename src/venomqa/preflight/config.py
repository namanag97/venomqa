"""Configuration for preflight smoke tests.

Provides dataclasses that define which smoke tests to run and how, plus
utilities for loading configuration from YAML files with environment
variable substitution.

Example (from YAML file):
    >>> config = PreflightConfig.from_yaml("preflight.yaml")

Example (programmatic):
    >>> config = PreflightConfig(
    ...     base_url="http://localhost:8000",
    ...     health_checks=[HealthCheckConfig(path="/health")],
    ... )
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Environment variable substitution
# ---------------------------------------------------------------------------

# Pattern matches ${VAR} and ${VAR:default}
_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _random_hex(length: int = 8) -> str:
    """Return a random hex string."""
    return uuid.uuid4().hex[:length]


def substitute_env_vars(value: str) -> str:
    """Replace ``${VAR}`` and ``${VAR:default}`` with environment values.

    Special variables:
        - ``${RANDOM}`` -- random 8-char hex string (unique per substitution).
        - ``${UUID}`` -- random UUID4 string.
        - ``${TIMESTAMP}`` -- current UNIX timestamp as an integer string.

    Args:
        value: A string potentially containing ``${...}`` placeholders.

    Returns:
        The string with all placeholders resolved. Unresolved ``${VAR}``
        references (no matching env var, no default) are left as-is to
        support template placeholders like ``${id}`` in cleanup paths.
    """
    import time as _time

    def _replace(match: re.Match[str]) -> str:
        expr = match.group(1)

        # Special variables
        if expr == "RANDOM":
            return _random_hex()
        if expr == "UUID":
            return str(uuid.uuid4())
        if expr == "TIMESTAMP":
            return str(int(_time.time()))

        # ${VAR:default} form
        if ":" in expr:
            var_name, default = expr.split(":", 1)
            return os.environ.get(var_name.strip(), default.strip())

        # ${VAR} form (no default)
        env_val = os.environ.get(expr.strip())
        if env_val is None:
            # Leave unresolved -- this may be a template placeholder
            # (e.g. ${id} in cleanup_path) rather than an env var.
            return match.group(0)
        return env_val

    return _ENV_VAR_PATTERN.sub(_replace, value)


def _substitute_recursive(data: Any) -> Any:
    """Walk a nested dict/list structure and substitute env vars in strings."""
    if isinstance(data, str):
        return substitute_env_vars(data)
    if isinstance(data, dict):
        return {k: _substitute_recursive(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_substitute_recursive(item) for item in data]
    return data


# ---------------------------------------------------------------------------
# Check config dataclasses
# ---------------------------------------------------------------------------

@dataclass
class HealthCheckConfig:
    """Configuration for a single health-check endpoint.

    Attributes:
        path: The health endpoint path (e.g. ``/health``).
        expected_status: HTTP status codes considered successful.
        expected_json: If set, the response body must be a JSON superset of this dict.
        timeout: Per-check timeout override (uses global timeout if ``None``).
    """

    path: str = "/health"
    expected_status: list[int] = field(default_factory=lambda: [200])
    expected_json: dict[str, Any] | None = None
    timeout: float | None = None


@dataclass
class AuthCheckConfig:
    """Configuration for an authentication check.

    Attributes:
        path: An auth-protected endpoint to probe.
        method: HTTP method to use (default ``GET``).
        expected_status: HTTP status codes considered successful.
    """

    path: str = "/api/v1/me"
    method: str = "GET"
    expected_status: list[int] = field(default_factory=lambda: [200])


@dataclass
class CRUDCheckConfig:
    """Configuration for a create-resource check.

    Attributes:
        name: Human-readable label for the check.
        path: The POST endpoint path.
        payload: JSON body to send.
        method: HTTP method (default ``POST``).
        expected_status: Status codes considered successful (includes 409 by default).
        cleanup_path: Optional DELETE path template (e.g. ``/api/v1/items/${id}``).
    """

    path: str = "/api/v1/resources"
    payload: dict[str, Any] = field(default_factory=dict)
    name: str | None = None
    method: str = "POST"
    expected_status: list[int] = field(default_factory=lambda: [200, 201, 409])
    cleanup_path: str | None = None


@dataclass
class ListCheckConfig:
    """Configuration for a list-endpoint check.

    Attributes:
        path: The GET endpoint path.
        expected_status: Status codes considered successful.
        expected_type: ``"array"`` for a bare JSON array, ``"paginated"`` for an
            object wrapping an array.
    """

    path: str = "/api/v1/resources"
    expected_status: list[int] = field(default_factory=lambda: [200])
    expected_type: str = "array"


@dataclass
class CustomCheckConfig:
    """Configuration for a fully custom HTTP check.

    Attributes:
        name: Human-readable label.
        method: HTTP method.
        path: Endpoint path.
        payload: Optional JSON body.
        headers: Optional extra headers (merged with auth headers).
        expected_status: Status codes considered successful.
        expected_json: If set, the response body must be a JSON superset of this dict.
    """

    name: str = "Custom check"
    method: str = "GET"
    path: str = "/"
    payload: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    expected_status: list[int] = field(default_factory=lambda: [200])
    expected_json: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# PreflightConfig -- the top-level config object
# ---------------------------------------------------------------------------

@dataclass
class PreflightConfig:
    """Configuration for preflight smoke tests.

    This is the top-level container that holds all check configurations.
    It can be constructed directly, from a Python dict, or from a YAML file.

    Attributes:
        base_url: Root URL of the API under test.
        timeout: Default HTTP timeout in seconds.
        token: Explicit auth token value.
        token_env_var: Name of an environment variable holding the auth token.
        auth_header: HTTP header name for the token (default ``Authorization``).
        auth_prefix: Prefix before the token value (default ``Bearer``).
        health_checks: List of health-check configurations.
        auth_checks: List of authentication-check configurations.
        crud_checks: List of CRUD-check configurations.
        list_checks: List of list-endpoint-check configurations.
        custom_checks: List of custom-check configurations.
    """

    # Base settings
    base_url: str = "http://localhost:8000"
    timeout: float = 10.0

    # Auth settings
    token: str | None = None
    token_env_var: str | None = None
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer"

    # Check lists
    health_checks: list[HealthCheckConfig] = field(default_factory=list)
    auth_checks: list[AuthCheckConfig] = field(default_factory=list)
    crud_checks: list[CRUDCheckConfig] = field(default_factory=list)
    list_checks: list[ListCheckConfig] = field(default_factory=list)
    custom_checks: list[CustomCheckConfig] = field(default_factory=list)

    def resolve_token(self) -> str | None:
        """Return the effective auth token.

        Prefers an explicit ``token`` over ``token_env_var``.

        Returns:
            The resolved token string, or ``None`` if neither is set.
        """
        if self.token:
            return self.token
        if self.token_env_var:
            return os.environ.get(self.token_env_var)
        return None

    # ----- Factory methods -----

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PreflightConfig:
        """Create a ``PreflightConfig`` from a plain dictionary.

        The dictionary structure mirrors the YAML format. Environment
        variable placeholders (``${VAR}``) in string values are resolved.

        Args:
            data: Configuration dictionary.

        Returns:
            A fully populated ``PreflightConfig``.

        Raises:
            ValueError: If required fields are missing or invalid.
        """
        # Substitute environment variables throughout
        data = _substitute_recursive(data)

        # Base settings
        base_url = data.get("base_url", "http://localhost:8000")
        timeout = float(data.get("timeout", 10.0))

        # Auth settings
        auth_data = data.get("auth", {})
        token = auth_data.get("token") or data.get("token")
        token_env_var = auth_data.get("token_env_var") or data.get("token_env_var")
        auth_header = auth_data.get("header", "Authorization")
        auth_prefix = auth_data.get("prefix", "Bearer")

        # Health checks
        health_checks: list[HealthCheckConfig] = []
        for hc in data.get("health_checks", []):
            if isinstance(hc, str):
                health_checks.append(HealthCheckConfig(path=hc))
            elif isinstance(hc, dict):
                health_checks.append(HealthCheckConfig(
                    path=hc.get("path", "/health"),
                    expected_status=hc.get("expected_status", [200]),
                    expected_json=hc.get("expected_json"),
                    timeout=hc.get("timeout"),
                ))
            else:
                raise ValueError(f"Invalid health check config: {hc!r}")

        # Auth checks
        auth_checks: list[AuthCheckConfig] = []
        for ac in data.get("auth_checks", []):
            if isinstance(ac, str):
                auth_checks.append(AuthCheckConfig(path=ac))
            elif isinstance(ac, dict):
                auth_checks.append(AuthCheckConfig(
                    path=ac.get("path", "/api/v1/me"),
                    method=ac.get("method", "GET"),
                    expected_status=ac.get("expected_status", [200]),
                ))
            else:
                raise ValueError(f"Invalid auth check config: {ac!r}")

        # CRUD checks
        crud_checks: list[CRUDCheckConfig] = []
        for cc in data.get("crud_checks", []):
            if not isinstance(cc, dict):
                raise ValueError(f"CRUD check config must be a dict, got: {type(cc).__name__}")
            crud_checks.append(CRUDCheckConfig(
                path=cc.get("path", "/api/v1/resources"),
                payload=cc.get("payload", {}),
                name=cc.get("name"),
                method=cc.get("method", "POST"),
                expected_status=cc.get("expected_status", [200, 201, 409]),
                cleanup_path=cc.get("cleanup_path"),
            ))

        # List checks
        list_checks: list[ListCheckConfig] = []
        for lc in data.get("list_checks", []):
            if isinstance(lc, str):
                list_checks.append(ListCheckConfig(path=lc))
            elif isinstance(lc, dict):
                list_checks.append(ListCheckConfig(
                    path=lc.get("path", "/api/v1/resources"),
                    expected_status=lc.get("expected_status", [200]),
                    expected_type=lc.get("expected_type", "array"),
                ))
            else:
                raise ValueError(f"Invalid list check config: {lc!r}")

        # Custom checks
        custom_checks: list[CustomCheckConfig] = []
        for xc in data.get("custom_checks", []):
            if not isinstance(xc, dict):
                raise ValueError(f"Custom check config must be a dict, got: {type(xc).__name__}")
            custom_checks.append(CustomCheckConfig(
                name=xc.get("name", "Custom check"),
                method=xc.get("method", "GET"),
                path=xc.get("path", "/"),
                payload=xc.get("payload"),
                headers=xc.get("headers"),
                expected_status=xc.get("expected_status", [200]),
                expected_json=xc.get("expected_json"),
            ))

        return cls(
            base_url=base_url,
            timeout=timeout,
            token=token,
            token_env_var=token_env_var,
            auth_header=auth_header,
            auth_prefix=auth_prefix,
            health_checks=health_checks,
            auth_checks=auth_checks,
            crud_checks=crud_checks,
            list_checks=list_checks,
            custom_checks=custom_checks,
        )

    @classmethod
    def from_yaml(cls, path: str) -> PreflightConfig:
        """Load configuration from a YAML file.

        Environment variable placeholders (``${VAR}`` and ``${VAR:default}``)
        in string values are resolved after parsing.

        Args:
            path: Path to the YAML configuration file.

        Returns:
            A fully populated ``PreflightConfig``.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the YAML content is invalid.
        """
        import yaml

        with open(path) as f:
            raw = yaml.safe_load(f)

        if not isinstance(raw, dict):
            raise ValueError(
                f"Expected a YAML mapping at the top level, got {type(raw).__name__}"
            )

        return cls.from_dict(raw)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the config to a plain dictionary (for debugging / export).

        Returns:
            A dictionary representation of the configuration.
        """
        result: dict[str, Any] = {
            "base_url": self.base_url,
            "timeout": self.timeout,
        }

        # Auth
        auth: dict[str, Any] = {}
        if self.token:
            auth["token"] = self.token
        if self.token_env_var:
            auth["token_env_var"] = self.token_env_var
        if self.auth_header != "Authorization":
            auth["header"] = self.auth_header
        if self.auth_prefix != "Bearer":
            auth["prefix"] = self.auth_prefix
        if auth:
            result["auth"] = auth

        # Checks
        if self.health_checks:
            result["health_checks"] = [
                {
                    "path": hc.path,
                    "expected_status": hc.expected_status,
                    **({"expected_json": hc.expected_json} if hc.expected_json else {}),
                    **({"timeout": hc.timeout} if hc.timeout else {}),
                }
                for hc in self.health_checks
            ]
        if self.auth_checks:
            result["auth_checks"] = [
                {
                    "path": ac.path,
                    "method": ac.method,
                    "expected_status": ac.expected_status,
                }
                for ac in self.auth_checks
            ]
        if self.crud_checks:
            result["crud_checks"] = [
                {
                    "path": cc.path,
                    "payload": cc.payload,
                    **({"name": cc.name} if cc.name else {}),
                    "method": cc.method,
                    "expected_status": cc.expected_status,
                    **({"cleanup_path": cc.cleanup_path} if cc.cleanup_path else {}),
                }
                for cc in self.crud_checks
            ]
        if self.list_checks:
            result["list_checks"] = [
                {
                    "path": lc.path,
                    "expected_status": lc.expected_status,
                    "expected_type": lc.expected_type,
                }
                for lc in self.list_checks
            ]
        if self.custom_checks:
            result["custom_checks"] = [
                {
                    "name": xc.name,
                    "method": xc.method,
                    "path": xc.path,
                    **({"payload": xc.payload} if xc.payload else {}),
                    **({"headers": xc.headers} if xc.headers else {}),
                    "expected_status": xc.expected_status,
                    **({"expected_json": xc.expected_json} if xc.expected_json else {}),
                }
                for xc in self.custom_checks
            ]

        return result


# ---------------------------------------------------------------------------
# Example config YAML generation
# ---------------------------------------------------------------------------

EXAMPLE_PREFLIGHT_YAML = """\
# VenomQA Preflight Configuration
# Configure smoke tests for your API.
# Documentation: https://venomqa.dev/docs/preflight-configuration

# Base URL of the API under test.
# Supports environment variable substitution: ${VAR} and ${VAR:default}
base_url: "${API_URL:http://localhost:8000}"
timeout: 10.0

# Authentication
auth:
  # Read token from an environment variable (recommended for CI):
  token_env_var: "API_TOKEN"
  # Or hardcode for local development:
  # token: "eyJ..."
  header: "Authorization"
  prefix: "Bearer"

# Health checks - verify the API is running
health_checks:
  - path: /health
    expected_status: [200]
    # Optionally assert on response body:
    # expected_json:
    #   status: "healthy"

# Auth checks - verify authentication works
auth_checks:
  - path: /api/v1/me
    expected_status: [200]

# CRUD checks - verify basic create operations work
crud_checks:
  - name: "Create test resource"
    path: /api/v1/resources
    payload:
      name: "Preflight Test ${RANDOM}"
    expected_status: [201, 409]
    # Optional cleanup (DELETE after test):
    # cleanup_path: /api/v1/resources/${id}

# List checks - verify list endpoints return data
list_checks:
  - path: /api/v1/resources
    expected_type: array  # or "paginated"

# Custom checks - any additional HTTP validation
custom_checks:
  - name: "OpenAPI spec available"
    method: GET
    path: /openapi.json
    expected_status: [200]
"""


def generate_example_config() -> str:
    """Return a complete example YAML configuration string.

    This is used by the ``venomqa preflight --init`` command to bootstrap
    a new configuration file.
    """
    return EXAMPLE_PREFLIGHT_YAML
