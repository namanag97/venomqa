"""Runtime Core - A standalone library for state-machine exploration tools.

This library provides the core abstractions for building state-machine
exploration systems, including:

- **Protocols**: Abstract interfaces (TypeSystem, RuntimeContext, Action, Explorer)
- **Type System**: Resource type definitions and hierarchies
- **Resource Graph**: Live resource tracking with checkpoint/rollback
- **OpenAPI Parser**: Automatic schema extraction from API specifications

Example:
    >>> from runtime_core import (
    ...     ResourceType, ResourceSchema, ResourceGraph, OpenAPIParser
    ... )
    >>>
    >>> # Define a schema manually
    >>> schema = ResourceSchema(types={
    ...     "workspace": ResourceType(name="workspace"),
    ...     "upload": ResourceType(name="upload", parent="workspace"),
    ... })
    >>>
    >>> # Or parse from OpenAPI
    >>> parser = OpenAPIParser()
    >>> schema = parser.parse("openapi.json")
    >>>
    >>> # Track resources at runtime
    >>> graph = ResourceGraph(schema)
    >>> ws = graph.create("workspace", "ws-1", data={"name": "My Project"})
    >>> up = graph.create("upload", "up-1", parent_id="ws-1")
    >>>
    >>> # Checkpoint for branching exploration
    >>> snap = graph.checkpoint()
    >>> graph.destroy("workspace", "ws-1")  # Cascades to children
    >>> graph.rollback(snap)  # Everything restored
"""

from .protocols import (
    Action,
    Explorer,
    RuntimeContext,
    Snapshot,
    TypeSystem,
)
from .type_system import (
    ResourceSchema,
    ResourceType,
)
from .resource_graph import (
    Resource,
    ResourceGraph,
    ResourceSnapshot,
)
from .openapi_parser import (
    OpenAPIParser,
)

__version__ = "0.1.0"

__all__ = [
    # Protocols
    "Action",
    "Explorer",
    "RuntimeContext",
    "Snapshot",
    "TypeSystem",
    # Type System
    "ResourceSchema",
    "ResourceType",
    # Resource Graph
    "Resource",
    "ResourceGraph",
    "ResourceSnapshot",
    # OpenAPI Parser
    "OpenAPIParser",
]
