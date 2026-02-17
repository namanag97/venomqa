"""OpenAPI 3.x scaffold — generate VenomQA action files from a spec."""

from __future__ import annotations

import json
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class EndpointDef:
    """A single (method, path) endpoint extracted from an OpenAPI spec."""

    method: str           # uppercase: GET, POST, PUT, PATCH, DELETE
    path: str             # e.g. /users/{id}
    func_name: str        # Python-safe function name, e.g. post_users
    summary: str          # Human-readable description
    expected_status: list[int]  # from spec responses, e.g. [200, 201]
    path_params: list[str]      # e.g. ["id"] from /users/{id}
    has_body: bool        # True if method has requestBody
    response_has_id: bool  # True if success response schema has "id" field
    tag: str              # resource name inferred from path, e.g. "user"


def _sanitize_name(method: str, path: str) -> str:
    """Convert method + path to a valid Python function name.

    Examples:
        POST /users          → post_users
        GET  /users/{id}     → get_users_by_id
        DELETE /orders/{id}  → delete_orders_by_id
        PATCH /users/{id}/profile → patch_users_by_id_profile
    """
    # Replace path params {x} with "by_x"
    parts = re.sub(r"\{(\w+)\}", r"by_\1", path)
    # Split on non-alphanumeric, filter empties
    segments = [s for s in re.split(r"[^a-zA-Z0-9]+", parts) if s]
    return f"{method.lower()}_{'_'.join(segments)}"


def _infer_tag(path: str) -> str:
    """Infer a resource tag from a path.

    /users/{id} → user
    /orders     → order
    /v1/items   → item
    """
    segments = [s for s in path.split("/") if s and not s.startswith("{") and not re.match(r"v\d+", s)]
    if segments:
        tag = segments[0].rstrip("s")  # naive singularise: "users" → "user"
        return re.sub(r"[^a-z0-9_]", "_", tag.lower())
    return "resource"


def _expected_statuses(method: str, responses: dict[str, Any]) -> list[int]:
    """Extract expected HTTP status codes from the spec responses dict."""
    statuses = []
    for code_str in responses:
        try:
            code = int(code_str)
            if 200 <= code < 300:
                statuses.append(code)
        except (ValueError, TypeError):
            pass
    if not statuses:
        # Fallback by method convention
        defaults = {"POST": 201, "GET": 200, "PUT": 200, "PATCH": 200, "DELETE": 204}
        statuses = [defaults.get(method.upper(), 200)]
    return sorted(statuses)


def _schema_has_id(response_spec: dict[str, Any]) -> bool:
    """Return True if the response schema has a top-level 'id' property."""
    content = response_spec.get("content", {})
    for media in content.values():
        schema = media.get("schema", {})
        props = schema.get("properties", {})
        if "id" in props:
            return True
        # Handle $ref (we don't resolve refs — just check inline schema)
        items = schema.get("items", {})
        if "id" in items.get("properties", {}):
            return True
    return False


def parse_openapi(spec: dict[str, Any]) -> list[EndpointDef]:
    """Parse an OpenAPI 3.x spec dict and return a list of EndpointDef objects.

    Only processes paths/methods. Does not resolve $ref schemas.

    Raises:
        ValueError: If the spec is not OpenAPI 3.x format.
    """
    if "openapi" not in spec:
        raise ValueError(
            "Not an OpenAPI 3.x spec (missing 'openapi' key). "
            "Swagger 2.0 (with 'swagger' key) is not supported."
        )

    paths = spec.get("paths", {})
    if not paths:
        raise ValueError("OpenAPI spec has no 'paths' defined — nothing to scaffold.")

    http_methods = {"get", "post", "put", "patch", "delete"}
    endpoints: list[EndpointDef] = []

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        # Extract path params from path string: /users/{id} → ["id"]
        path_params = re.findall(r"\{(\w+)\}", path)

        for method, operation in path_item.items():
            if method.lower() not in http_methods:
                continue
            if not isinstance(operation, dict):
                continue

            method_upper = method.upper()
            responses = operation.get("responses", {})
            expected = _expected_statuses(method_upper, responses)

            # Does the success response schema have an 'id' field?
            response_has_id = False
            for code_str, resp_spec in responses.items():
                try:
                    code = int(code_str)
                except (ValueError, TypeError):
                    continue
                if 200 <= code < 300 and isinstance(resp_spec, dict):
                    if _schema_has_id(resp_spec):
                        response_has_id = True
                        break

            has_body = "requestBody" in operation and method_upper in ("POST", "PUT", "PATCH")
            summary = operation.get("summary", operation.get("description", ""))

            endpoints.append(EndpointDef(
                method=method_upper,
                path=path,
                func_name=_sanitize_name(method_upper, path),
                summary=summary,
                expected_status=expected,
                path_params=path_params,
                has_body=has_body,
                response_has_id=response_has_id,
                tag=_infer_tag(path),
            ))

    return endpoints


def _generate_action_function(ep: EndpointDef) -> str:
    """Generate the Python source for a single action function."""
    lines: list[str] = []

    # Docstring
    desc = ep.summary or f"{ep.method} {ep.path}"
    lines.append(f'def {ep.func_name}(api, context):')
    lines.append(f'    """{desc}"""')

    # Build path: replace {param} with context.get(f"tag_param")
    rendered_path = ep.path
    context_reads: list[str] = []
    for param in ep.path_params:
        var_name = f"{ep.tag}_{param}"
        context_reads.append(f'    {var_name} = context.get("{var_name}")')
        rendered_path = rendered_path.replace(f"{{{param}}}", f"{{{var_name}}}")

    for line in context_reads:
        lines.append(line)

    # The request call
    if "{" in rendered_path:
        path_expr = f'f"{rendered_path}"'
    else:
        path_expr = f'"{rendered_path}"'

    if ep.has_body:
        lines.append(f'    resp = api.{ep.method.lower()}({path_expr}, json={{}})')
    else:
        lines.append(f'    resp = api.{ep.method.lower()}({path_expr})')

    # Store id if response returns one
    if ep.response_has_id and ep.method in ("POST", "PUT"):
        lines.append(f'    if resp.response and resp.response.status_code in {ep.expected_status}:')
        lines.append('        body = resp.response.body or {}')
        lines.append('        if isinstance(body, dict) and "id" in body:')
        lines.append(f'            context.set("{ep.tag}_id", body["id"])')

    lines.append('    return resp')
    return "\n".join(lines)


def generate_actions_code(
    endpoints: list[EndpointDef],
    base_url: str = "http://localhost:8000",
    journey_name: str = "generated_journey",
) -> str:
    """Generate a complete Python file with VenomQA actions from endpoint defs.

    The output is a runnable Python file with:
    - One action function per endpoint
    - A list of Action objects
    - A ready-to-run Agent setup at the bottom (commented out)
    """
    if not endpoints:
        raise ValueError("No endpoints to generate code for.")

    sections: list[str] = []

    # Header
    sections.append(textwrap.dedent(f'''\
        """
        Auto-generated VenomQA actions from OpenAPI spec.
        Journey: {journey_name}
        Base URL: {base_url}

        Review and adjust:
          - Add context.set() calls where responses carry IDs you need later
          - Add preconditions= to actions that require prior actions to have run
          - Add real invariants (the ones below are stubs)
        """

        from venomqa import Action, Agent, BFS, Invariant, Severity, World
        from venomqa.adapters.http import HttpClient

    '''))

    # Action functions
    for ep in endpoints:
        sections.append(_generate_action_function(ep))
        sections.append("")

    # Action list
    sections.append("")
    sections.append("# ── Actions ──────────────────────────────────────────────────────────")
    sections.append("ACTIONS = [")
    for ep in endpoints:
        status_list = repr(ep.expected_status)
        expect_failure = "True" if all(s >= 400 for s in ep.expected_status) else "False"
        sections.append('    Action(')
        sections.append(f'        name="{ep.func_name}",')
        sections.append(f'        execute={ep.func_name},')
        if ep.summary:
            sections.append(f'        description={ep.summary!r},')
        sections.append(f'        expected_status={status_list},')
        if expect_failure == "True":
            sections.append('        expect_failure=True,')
        sections.append('    ),')
    sections.append("]")

    # Stub invariants
    sections.append("")
    sections.append("# ── Invariants (stubs — add real checks) ────────────────────────────")
    sections.append("INVARIANTS = [")
    sections.append("    # Example:")
    sections.append("    # Invariant(")
    sections.append("    #     name=\"no_server_errors\",")
    sections.append("    #     check=lambda world: True,  # replace with real check")
    sections.append('    #     message="API must not return 5xx errors",')
    sections.append("    #     severity=Severity.CRITICAL,")
    sections.append("    # ),")
    sections.append("]")

    # Agent setup
    sections.append("")
    sections.append("# ── Run ──────────────────────────────────────────────────────────────")
    sections.append("if __name__ == \"__main__\":")
    sections.append(f'    api = HttpClient("{base_url}")')
    sections.append("    world = World(api=api)")
    sections.append("    agent = Agent(")
    sections.append("        world=world,")
    sections.append("        actions=ACTIONS,")
    sections.append("        invariants=INVARIANTS,")
    sections.append("        strategy=BFS(),")
    sections.append("        max_steps=500,")
    sections.append("    )")
    sections.append("    result = agent.explore()")
    sections.append("    from venomqa.reporters.console import ConsoleReporter")
    sections.append("    ConsoleReporter().report(result)")

    return "\n".join(sections) + "\n"


def load_spec(path: str | Path) -> dict[str, Any]:
    """Load an OpenAPI spec from a YAML/JSON file or a live HTTP/HTTPS URL.

    URL example (FastAPI, Django Ninja, etc. serve /openapi.json by default):
        load_spec("http://localhost:8000/openapi.json")

    File example:
        load_spec("api-spec.yaml")

    Raises:
        FileNotFoundError: If a file path does not exist.
        ValueError: If the spec cannot be parsed or the URL is unreachable.
    """
    path_str = str(path)

    # ── HTTP/HTTPS URL ──────────────────────────────────────────────────────
    if path_str.startswith("http://") or path_str.startswith("https://"):
        try:
            import httpx
            resp = httpx.get(path_str, timeout=15, follow_redirects=True)
            resp.raise_for_status()
        except ImportError:
            raise ImportError("httpx is required to fetch specs from URLs.") from None
        except Exception as exc:
            raise ValueError(
                f"Could not fetch spec from {path_str!r}: {exc}\n"
                "Is the server running? Try: curl " + path_str
            ) from exc
        try:
            return resp.json()
        except Exception as exc:
            raise ValueError(
                f"Server at {path_str!r} returned non-JSON content. "
                "OpenAPI JSON endpoints must return application/json."
            ) from exc

    # ── Local file ──────────────────────────────────────────────────────────
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Spec file not found: {p}")

    text = p.read_text(encoding="utf-8")

    if p.suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]
            return yaml.safe_load(text)  # type: ignore[no-any-return]
        except ImportError:
            raise ImportError(
                "PyYAML is required to parse YAML specs. "
                "Install it: pip install pyyaml"
            ) from None
        except Exception as exc:
            raise ValueError(f"Failed to parse YAML spec: {exc}") from exc

    if p.suffix == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to parse JSON spec: {exc}") from exc

    raise ValueError(
        f"Unsupported spec file extension: {p.suffix!r}. "
        "Use .yaml, .yml, .json, or an http(s):// URL"
    )
