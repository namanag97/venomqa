# runtime-core

A standalone, zero-dependency library providing the core abstractions for state-machine exploration tools. It is the reusable foundation that VenomQA's v2 architecture is built on, and can be embedded in any project that needs typed resource tracking with checkpoint/rollback.

## What it provides

| Module | Purpose |
|--------|---------|
| `protocols.py` | Abstract interfaces: `TypeSystem`, `RuntimeContext`, `Action`, `Explorer`, `Snapshot` |
| `type_system.py` | `ResourceType` and `ResourceSchema` — define hierarchical resource types (static schema) |
| `resource_graph.py` | `ResourceGraph` — track live resource instances with `checkpoint()` / `rollback()` |
| `openapi_parser.py` | `OpenAPIParser` — infer a `ResourceSchema` automatically from an OpenAPI spec |

## Core concepts

**Static schema vs. dynamic state.** `ResourceSchema` describes what types of resources *can* exist (e.g., `workspace -> upload -> version`). `ResourceGraph` tracks what resources *do* exist at runtime and supports branching exploration via snapshots.

**Cascade destroy.** Calling `graph.destroy("workspace", "ws-1")` automatically removes all child and grandchild resources so actions do not need manual cleanup logic.

**Checkpoint / rollback.** Before branching into a new path, take a snapshot; after exploring that branch, restore it. This is the same mechanism VenomQA uses with Postgres savepoints and SQLite file copies.

**Auto-preconditions.** Actions declare `requires = ["workspace"]`; the `Agent` calls `action.can_run(ctx)` which checks `graph.exists("workspace")` before executing — no manual guard code needed.

## Quick start

```python
from runtime_core import ResourceType, ResourceSchema, ResourceGraph, OpenAPIParser

# Option A: define schema manually
schema = ResourceSchema(types={
    "workspace": ResourceType(name="workspace"),
    "upload": ResourceType(name="upload", parent="workspace"),
})

# Option B: parse from an OpenAPI spec
parser = OpenAPIParser()
schema = parser.parse("openapi.json")  # or openapi.yaml with the [yaml] extra

# Track resources at runtime
graph = ResourceGraph(schema)
ws = graph.create("workspace", "ws-1", data={"name": "My Project"})
up = graph.create("upload", "up-1", parent_id="ws-1")

# Branch: checkpoint, explore, rollback
snap = graph.checkpoint()
graph.destroy("workspace", "ws-1")  # cascades to upload
graph.rollback(snap)                # ws-1 and up-1 are back
```

## Installation

```bash
# From the repo root (editable)
pip install -e runtime-core/

# With YAML support for openapi.yaml files
pip install -e "runtime-core/[yaml]"
```

## Running tests

```bash
pytest runtime-core/tests/
```

## Relationship to VenomQA

`runtime-core` is intentionally a separate package with no VenomQA dependency. VenomQA's `ResourceGraphAdapter` wraps `ResourceGraph` to implement the `Rollbackable` protocol and plugs into `World`. This separation keeps the graph logic testable and reusable outside of VenomQA.
