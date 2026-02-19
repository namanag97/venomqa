"""Generate VenomQA Actions from OpenAPI specifications.

This module parses OpenAPI specs and generates Action objects with:
- Proper HTTP method and path
- Resource requirements (requires=[...]) for precondition checking
- Auto-detection of CRUD operations
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from venomqa.v1.adapters.resource_graph import (
    ResourceSchema,
    schema_from_openapi,
)
from venomqa.v1.core.action import Action, ActionResult, HTTPRequest

OperationType = Literal["create", "read", "update", "delete", "list", "action"]


@dataclass
class EndpointInfo:
    """Information about an API endpoint."""

    path: str
    method: str
    operation_id: str | None
    resource_type: str | None
    operation: OperationType
    requires: list[str]
    path_params: list[str]
    summary: str | None = None
    request_body_schema: dict[str, Any] | None = None
    response_schema: dict[str, Any] | None = None


def load_openapi_spec(spec_path: str | Path) -> dict[str, Any]:
    """Load an OpenAPI spec from a file.

    Supports JSON and YAML formats.
    """
    path = Path(spec_path)
    content = path.read_text()

    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml

            return yaml.safe_load(content)
        except ImportError:
            raise ImportError(
                "PyYAML is required to load YAML OpenAPI specs. "
                "Install it with: pip install pyyaml"
            )
    else:
        return json.loads(content)


def parse_openapi_endpoints(spec: dict[str, Any]) -> list[EndpointInfo]:
    """Parse OpenAPI spec into endpoint information.

    Extracts:
    - Path and method
    - Resource type (inferred from path)
    - Operation type (create, read, update, delete, list)
    - Required resources (parent types that must exist)
    - Path parameters
    """
    endpoints = []

    for path, path_item in spec.get("paths", {}).items():
        for method, operation in path_item.items():
            if method in ("get", "post", "put", "patch", "delete"):
                endpoint = _parse_endpoint(path, method, operation)
                endpoints.append(endpoint)

    return endpoints


def _parse_endpoint(path: str, method: str, operation: dict[str, Any]) -> EndpointInfo:
    """Parse a single endpoint."""
    # Extract path parameters
    path_params = []
    segments = []
    for part in path.split("/"):
        if not part:
            continue
        if part.startswith("{") and part.endswith("}"):
            path_params.append(part[1:-1])
        else:
            segments.append(part)

    # Infer resource type from last segment
    resource_type = None
    if segments:
        resource_type = _singularize(segments[-1])

    # Infer operation type
    op_type = _infer_operation_type(method, path, path_params)

    # Infer required resources (all path params except the last one for create/list)
    requires = []
    for param in path_params:
        # Extract resource type from param name (e.g., "workspace_id" -> "workspace")
        if param.endswith("_id"):
            req_type = param[:-3]
            # Don't require self for read/update/delete
            if req_type != resource_type or op_type in ("create", "list"):
                requires.append(req_type)

    # Get request body schema
    request_body_schema = None
    if "requestBody" in operation:
        content = operation["requestBody"].get("content", {})
        json_content = content.get("application/json", {})
        request_body_schema = json_content.get("schema")

    # Get response schema (from 200/201 response)
    response_schema = None
    for status in ("200", "201"):
        if status in operation.get("responses", {}):
            content = operation["responses"][status].get("content", {})
            json_content = content.get("application/json", {})
            response_schema = json_content.get("schema")
            break

    return EndpointInfo(
        path=path,
        method=method.upper(),
        operation_id=operation.get("operationId"),
        resource_type=resource_type,
        operation=op_type,
        requires=requires,
        path_params=path_params,
        summary=operation.get("summary"),
        request_body_schema=request_body_schema,
        response_schema=response_schema,
    )


def _infer_operation_type(method: str, path: str, path_params: list[str]) -> OperationType:
    """Infer CRUD operation type from HTTP method and path structure."""
    method = method.lower()

    if method == "post":
        return "create"
    elif method == "get":
        # GET with ID param = read, GET without = list
        segments = [p for p in path.split("/") if p and not p.startswith("{")]
        params = [p for p in path.split("/") if p and p.startswith("{")]
        if params and segments:
            # Check if last segment is a param (read) or resource name (list)
            last_part = path.rstrip("/").split("/")[-1]
            if last_part.startswith("{"):
                return "read"
        return "list"
    elif method == "put":
        return "update"
    elif method == "patch":
        return "update"
    elif method == "delete":
        return "delete"
    else:
        return "action"


def _singularize(name: str) -> str:
    """Convert plural to singular."""
    if name.endswith("ies"):
        return name[:-3] + "y"
    if name.endswith("ses") or name.endswith("xes") or name.endswith("ches") or name.endswith("shes"):
        return name[:-2]
    if name.endswith("s") and not name.endswith("ss"):
        return name[:-1]
    return name


def generate_actions(
    spec: dict[str, Any] | str | Path,
    *,
    base_url: str = "",
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> list[Action]:
    """Generate VenomQA Actions from an OpenAPI spec.

    Args:
        spec: OpenAPI spec dict, or path to spec file
        base_url: Base URL to prepend to paths (optional, can be set on HttpClient)
        include_patterns: Only include paths matching these patterns (glob-style)
        exclude_patterns: Exclude paths matching these patterns

    Returns:
        List of Action objects ready to use with Agent

    Example:
        from venomqa.v1.generators.openapi_actions import generate_actions

        actions = generate_actions("openapi.yaml")
        agent = Agent(world=world, actions=actions, invariants=[...])
    """
    if isinstance(spec, (str, Path)):
        spec = load_openapi_spec(spec)

    endpoints = parse_openapi_endpoints(spec)

    # Filter by patterns
    if include_patterns:
        endpoints = [e for e in endpoints if _matches_any(e.path, include_patterns)]
    if exclude_patterns:
        endpoints = [e for e in endpoints if not _matches_any(e.path, exclude_patterns)]

    actions = []
    for endpoint in endpoints:
        action = _endpoint_to_action(endpoint, base_url)
        actions.append(action)

    return actions


def _matches_any(path: str, patterns: list[str]) -> bool:
    """Check if path matches any of the glob patterns."""
    import fnmatch

    return any(fnmatch.fnmatch(path, p) for p in patterns)


def _endpoint_to_action(endpoint: EndpointInfo, base_url: str) -> Action:
    """Convert an EndpointInfo to a VenomQA Action."""

    # Generate action name
    if endpoint.operation_id:
        name = endpoint.operation_id
    else:
        name = f"{endpoint.method.lower()}_{endpoint.resource_type or 'unknown'}"
        if endpoint.operation == "list":
            name = f"list_{endpoint.resource_type}s" if endpoint.resource_type else "list"

    # Create the execute function
    def make_execute(ep: EndpointInfo, base: str):
        def execute(api, context):
            # Build URL with path parameters
            url = ep.path
            for param in ep.path_params:
                value = context.get(param)
                if value is None:
                    # Try without _id suffix
                    alt_key = param[:-3] + "_id" if not param.endswith("_id") else param[:-3]
                    value = context.get(alt_key)
                if value:
                    url = url.replace("{" + param + "}", str(value))

            full_url = base + url if base else url

            # Make request
            request = HTTPRequest(method=ep.method, url=full_url)

            try:
                if ep.method == "GET":
                    resp = api.get(full_url)
                elif ep.method == "POST":
                    body = context.get("_request_body", {})
                    resp = api.post(full_url, json=body)
                elif ep.method == "PUT":
                    body = context.get("_request_body", {})
                    resp = api.put(full_url, json=body)
                elif ep.method == "PATCH":
                    body = context.get("_request_body", {})
                    resp = api.patch(full_url, json=body)
                elif ep.method == "DELETE":
                    resp = api.delete(full_url)
                else:
                    resp = api.request(ep.method, full_url)

                # Extract ID from response for create operations
                if ep.operation == "create" and resp.ok:
                    try:
                        data = resp.json()
                        if isinstance(data, dict) and "id" in data:
                            id_key = f"{ep.resource_type}_id"
                            context.set(id_key, data["id"])
                    except Exception:
                        pass

                return resp

            except Exception as e:
                return ActionResult.from_error(request, str(e))

        return execute

    action = Action(
        name=name,
        execute=make_execute(endpoint, base_url),
        description=endpoint.summary or f"{endpoint.method} {endpoint.path}",
    )

    # Set requires attribute for ResourceGraph integration
    action.requires = endpoint.requires

    return action


def generate_schema_and_actions(
    spec: dict[str, Any] | str | Path,
    **kwargs,
) -> tuple[ResourceSchema, list[Action]]:
    """Generate both ResourceSchema and Actions from an OpenAPI spec.

    Convenience function that returns everything needed for exploration.

    Returns:
        (schema, actions) tuple
    """
    if isinstance(spec, (str, Path)):
        spec = load_openapi_spec(spec)

    schema = schema_from_openapi(spec)
    actions = generate_actions(spec, **kwargs)

    return schema, actions


__all__ = [
    "EndpointInfo",
    "OperationType",
    "generate_actions",
    "generate_schema_and_actions",
    "load_openapi_spec",
    "parse_openapi_endpoints",
]
