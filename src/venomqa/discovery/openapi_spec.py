"""OpenAPISpec - Unified parsed OpenAPI specification."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from venomqa.discovery.endpoint import (
    CrudType,
    Endpoint,
    infer_crud_type,
    singularize,
)
from venomqa.discovery.ref_resolver import RefResolver


@dataclass
class ResourceHierarchy:
    """Describes parent-child relationships between API resources.

    Built automatically from URL path structure. For example,
    ``/workspaces/{workspace_id}/uploads`` implies that "upload"
    is a child of "workspace".

    Attributes:
        parents: Map from resource type to its parent type.
            e.g., {"upload": "workspace"}
        children: Map from resource type to its child types.
            e.g., {"workspace": ["upload"]}
    """

    parents: dict[str, str] = field(default_factory=dict)
    children: dict[str, list[str]] = field(default_factory=dict)

    def parent_of(self, resource: str) -> str | None:
        """Get the parent of a resource type."""
        return self.parents.get(resource)

    def children_of(self, resource: str) -> list[str]:
        """Get the children of a resource type."""
        return self.children.get(resource, [])

    def is_root(self, resource: str) -> bool:
        """True if the resource has no parent."""
        return resource not in self.parents


@dataclass
class OpenAPISpec:
    """Unified parsed OpenAPI specification.

    Provides structured access to all information in an OpenAPI spec:
    endpoints, schemas, and resource hierarchy.

    Example::

        spec = OpenAPISpec.from_file("openapi.yaml")
        for ep in spec.endpoints:
            print(f"{ep.method} {ep.path} -> {ep.crud.value} {ep.resource}")

        # Resource hierarchy
        print(spec.resource_hierarchy.parent_of("upload"))  # "workspace"

    Attributes:
        title: API title from the spec.
        version: API version from the spec.
        description: API description.
        base_url: Base URL from the servers section.
        endpoints: All parsed endpoints.
        schemas: Raw schema definitions from components/schemas.
        resource_hierarchy: Parent-child relationships between resources.
    """

    title: str
    version: str
    description: str = ""
    base_url: str = ""
    endpoints: list[Endpoint] = field(default_factory=list)
    schemas: dict[str, dict[str, Any]] = field(default_factory=dict)
    resource_hierarchy: ResourceHierarchy = field(default_factory=ResourceHierarchy)

    @classmethod
    def from_dict(cls, spec: dict[str, Any]) -> OpenAPISpec:
        """Parse an OpenAPI spec from a dictionary.

        Args:
            spec: The raw OpenAPI specification as a dict.

        Returns:
            A fully parsed OpenAPISpec.
        """
        info = spec.get("info", {})
        servers = spec.get("servers", [])
        base_url = servers[0].get("url", "") if servers else ""

        resolver = RefResolver(spec)

        endpoints: list[Endpoint] = []
        hierarchy = ResourceHierarchy()

        for path, path_item in spec.get("paths", {}).items():
            if not isinstance(path_item, dict):
                continue

            for method, operation in path_item.items():
                if method not in ("get", "post", "put", "patch", "delete"):
                    continue
                if not isinstance(operation, dict):
                    continue

                ep = _parse_endpoint(path, method, operation, resolver)
                endpoints.append(ep)

                # Build resource hierarchy from endpoint
                if ep.resource and ep.requires:
                    # The last require is the immediate parent
                    parent = ep.requires[-1]
                    if ep.resource != parent:
                        hierarchy.parents[ep.resource] = parent
                        hierarchy.children.setdefault(parent, [])
                        if ep.resource not in hierarchy.children[parent]:
                            hierarchy.children[parent].append(ep.resource)

        # Extract schemas
        schemas = spec.get("components", {}).get("schemas", {})

        return cls(
            title=info.get("title", "API"),
            version=info.get("version", "1.0.0"),
            description=info.get("description", ""),
            base_url=base_url,
            endpoints=endpoints,
            schemas=schemas,
            resource_hierarchy=hierarchy,
        )

    @classmethod
    def from_file(cls, path: str | Path) -> OpenAPISpec:
        """Parse an OpenAPI spec from a file (JSON or YAML).

        Args:
            path: Path to the spec file.

        Returns:
            A fully parsed OpenAPISpec.

        Raises:
            FileNotFoundError: If the file does not exist.
            ImportError: If PyYAML is needed but not installed.
        """
        filepath = Path(path)
        content = filepath.read_text(encoding="utf-8")

        if filepath.suffix in (".yaml", ".yml"):
            try:
                import yaml

                spec_dict = yaml.safe_load(content)
            except ImportError:
                raise ImportError(
                    "PyYAML is required to load YAML OpenAPI specs. "
                    "Install it with: pip install pyyaml"
                )
        else:
            spec_dict = json.loads(content)

        return cls.from_dict(spec_dict)

    def get_endpoints_by_resource(self, resource: str) -> list[Endpoint]:
        """Get all endpoints for a given resource type.

        Args:
            resource: Resource type name (e.g., "workspace").

        Returns:
            List of endpoints operating on that resource.
        """
        return [ep for ep in self.endpoints if ep.resource == resource]

    def get_endpoints_by_crud(self, crud: CrudType) -> list[Endpoint]:
        """Get all endpoints of a given CRUD type.

        Args:
            crud: The CRUD type to filter by.

        Returns:
            List of matching endpoints.
        """
        return [ep for ep in self.endpoints if ep.crud == crud]

    @property
    def resource_types(self) -> list[str]:
        """All unique resource types found in the spec."""
        types = set()
        for ep in self.endpoints:
            if ep.resource:
                types.add(ep.resource)
        return sorted(types)


def _parse_endpoint(
    path: str,
    method: str,
    operation: dict[str, Any],
    resolver: RefResolver,
) -> Endpoint:
    """Parse a single endpoint from an OpenAPI path item.

    Args:
        path: URL path template.
        method: HTTP method (lowercase).
        operation: The operation object from the spec.
        resolver: RefResolver for the spec.

    Returns:
        A parsed Endpoint.
    """
    # Extract path parameters
    path_params: list[str] = []
    segments: list[str] = []
    for part in path.split("/"):
        if not part:
            continue
        if part.startswith("{") and part.endswith("}"):
            path_params.append(part[1:-1])
        else:
            segments.append(part)

    # Infer resource type from last segment
    resource: str | None = None
    if segments:
        resource = singularize(segments[-1])

    # Infer CRUD type
    crud = infer_crud_type(method, path, path_params)

    # Infer required resources
    requires: list[str] = []
    for param in path_params:
        if param.endswith("_id"):
            req_type = param[:-3]
            # Don't require self for read/update/delete
            if req_type != resource or crud in (CrudType.CREATE, CrudType.LIST):
                requires.append(req_type)

    # Extract request body schema
    request_body_schema: dict[str, Any] | None = None
    if "requestBody" in operation:
        content = operation["requestBody"].get("content", {})
        json_content = content.get("application/json", {})
        schema = json_content.get("schema")
        if schema:
            request_body_schema = resolver.resolve_schema(schema)

    # Extract response schema (from 200/201 response)
    response_schema: dict[str, Any] | None = None
    for status in ("200", "201"):
        if status in operation.get("responses", {}):
            content = operation["responses"][status].get("content", {})
            json_content = content.get("application/json", {})
            schema = json_content.get("schema")
            if schema:
                response_schema = resolver.resolve_schema(schema)
            break

    # Extract tags
    tags = tuple(operation.get("tags", []))

    return Endpoint(
        path=path,
        method=method.upper(),
        crud=crud,
        resource=resource,
        operation_id=operation.get("operationId"),
        summary=operation.get("summary"),
        path_params=tuple(path_params),
        requires=tuple(requires),
        request_body_schema=request_body_schema,
        response_schema=response_schema,
        tags=tags,
    )


__all__ = ["OpenAPISpec", "ResourceHierarchy"]
