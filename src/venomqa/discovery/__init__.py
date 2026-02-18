"""Discovery Context - API specification parsing and endpoint discovery.

The Discovery context is responsible for:
- Parsing OpenAPI specifications into structured types
- Inferring CRUD operations from HTTP methods and paths
- Resolving $ref references in schemas
- Building resource hierarchies from URL structures
- Generating Actions from discovered endpoints

Core abstractions:
- OpenAPISpec: Unified parsed specification
- Endpoint: A single API endpoint with method, path, CRUD type
- CrudType: Enum for operation types (CREATE, READ, UPDATE, DELETE, LIST)
- RefResolver: Resolves $ref pointers in OpenAPI specs
"""

from venomqa.discovery.endpoint import CrudType, Endpoint
from venomqa.discovery.openapi_spec import OpenAPISpec
from venomqa.discovery.ref_resolver import RefResolver

# Re-export generation functions from v1 (will be migrated later)
from venomqa.v1.generators.openapi_actions import (
    generate_actions,
    generate_schema_and_actions,
    load_openapi_spec,
    parse_openapi_endpoints,
)

__all__ = [
    # Core types
    "OpenAPISpec",
    "Endpoint",
    "CrudType",
    "RefResolver",
    # Generation functions (re-exported from v1)
    "generate_actions",
    "generate_schema_and_actions",
    "load_openapi_spec",
    "parse_openapi_endpoints",
]
