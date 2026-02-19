"""Code generators for VenomQA.

Main generators (recommended):
    - generate_actions: Generate Actions from OpenAPI spec
    - generate_schema_and_actions: Generate ResourceSchema + Actions from OpenAPI spec

Legacy generators (backwards compatibility):
    - OpenAPIGenerator: Older style generator from OpenAPI specs.

Example:
    >>> from venomqa.generators.openapi_actions import generate_actions
    >>> actions = generate_actions(spec_path="openapi.yaml")
"""

from __future__ import annotations

import importlib
import sys

# Legacy generators
from venomqa.generators.openapi import (
    EndpointInfo,
    GeneratedAction,
    GeneratedFixture,
    GeneratorConfig,
    OpenAPIGenerator,
    OpenAPIParseError,
    OpenAPISchema,
    ParameterInfo,
    PropertyInfo,
    RequestBodyInfo,
    ResponseInfo,
    SchemaInfo,
)

# Main generator (from v1)
from venomqa.v1.generators.openapi_actions import generate_actions, generate_schema_and_actions

# Submodule aliasing: allow `from venomqa.generators.openapi_actions import generate_actions`
_V1_GENERATOR_SUBMODULES = ["openapi_actions"]

for _submod in _V1_GENERATOR_SUBMODULES:
    _v1_name = f"venomqa.v1.generators.{_submod}"
    _alias_name = f"venomqa.generators.{_submod}"
    if _alias_name not in sys.modules:
        try:
            _mod = importlib.import_module(_v1_name)
            sys.modules[_alias_name] = _mod
        except ImportError:
            pass

__all__ = [
    # Main
    "generate_actions",
    "generate_schema_and_actions",
    # Legacy
    "OpenAPIGenerator",
    "OpenAPISchema",
    "GeneratedAction",
    "GeneratedFixture",
    "GeneratorConfig",
    "OpenAPIParseError",
    "ParameterInfo",
    "PropertyInfo",
    "RequestBodyInfo",
    "ResponseInfo",
    "EndpointInfo",
    "SchemaInfo",
]
