"""Endpoint - Structured representation of an API endpoint."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CrudType(Enum):
    """The CRUD operation type for an endpoint.

    Inferred from the HTTP method and URL structure:
    - POST -> CREATE
    - GET + /{id} -> READ
    - GET (collection) -> LIST
    - PUT/PATCH -> UPDATE
    - DELETE -> DELETE
    - Other -> ACTION (non-CRUD operations like /reset-password)
    """

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LIST = "list"
    ACTION = "action"


@dataclass(frozen=True)
class Endpoint:
    """A single API endpoint with its metadata.

    Represents one operation on one path (e.g., POST /workspaces).

    Attributes:
        path: URL path template (e.g., "/workspaces/{workspace_id}").
        method: HTTP method in uppercase (e.g., "GET", "POST").
        crud: The inferred CRUD operation type.
        resource: The resource type this endpoint operates on
            (e.g., "workspace"), inferred from the last path segment.
        operation_id: The operationId from the OpenAPI spec (if present).
        summary: Short description from the spec.
        path_params: List of path parameter names.
        requires: Resource types that must exist before this endpoint
            can be called (inferred from parent path parameters).
        request_body_schema: The JSON Schema for the request body.
        response_schema: The JSON Schema for the success response.
        tags: Tags from the OpenAPI spec for grouping.
    """

    path: str
    method: str
    crud: CrudType
    resource: str | None = None
    operation_id: str | None = None
    summary: str | None = None
    path_params: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    request_body_schema: dict[str, Any] | None = None
    response_schema: dict[str, Any] | None = None
    tags: tuple[str, ...] = ()

    @property
    def is_collection(self) -> bool:
        """True if this endpoint operates on a collection (LIST or CREATE)."""
        return self.crud in (CrudType.LIST, CrudType.CREATE)

    @property
    def is_item(self) -> bool:
        """True if this endpoint operates on a single item (READ, UPDATE, DELETE)."""
        return self.crud in (CrudType.READ, CrudType.UPDATE, CrudType.DELETE)

    def __str__(self) -> str:
        return f"{self.method} {self.path}"


def infer_crud_type(method: str, path: str, path_params: list[str]) -> CrudType:
    """Infer the CRUD operation type from HTTP method and path structure.

    Args:
        method: HTTP method (case-insensitive).
        path: URL path template.
        path_params: List of path parameter names.

    Returns:
        The inferred CrudType.
    """
    method = method.lower()

    if method == "post":
        return CrudType.CREATE
    elif method == "get":
        # GET with trailing {param} = read, otherwise list
        last_part = path.rstrip("/").split("/")[-1]
        if last_part.startswith("{"):
            return CrudType.READ
        return CrudType.LIST
    elif method in ("put", "patch"):
        return CrudType.UPDATE
    elif method == "delete":
        return CrudType.DELETE
    else:
        return CrudType.ACTION


def singularize(name: str) -> str:
    """Convert a plural English word to singular.

    Simple heuristic-based singularization for API resource names.

    Args:
        name: Plural form (e.g., "workspaces", "entries").

    Returns:
        Singular form (e.g., "workspace", "entry").
    """
    if name.endswith("ies"):
        return name[:-3] + "y"
    if (
        name.endswith("ses")
        or name.endswith("xes")
        or name.endswith("ches")
        or name.endswith("shes")
    ):
        return name[:-2]
    if name.endswith("s") and not name.endswith("ss"):
        return name[:-1]
    return name


__all__ = [
    "CrudType",
    "Endpoint",
    "infer_crud_type",
    "singularize",
]
