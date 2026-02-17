# VenomQA v2 Architecture

## Problem Statement

User feedback identified critical ergonomic issues:
1. **No preconditions on actions** - manual guards in every action
2. **No auto-invalidation** - 22 keys to clear when workspace deleted
3. **No loop detection** - `confirm_member x38` loops
4. **Context is unstructured** - relationships invisible to framework

## Solution: ResourceGraph

Add a typed resource graph that tracks:
- What resources exist (by type and ID)
- Parent-child relationships
- Auto-cascade deletes to children

## Core Data Models

### TypeSystem (Static)
```
ResourceSchema = { types: dict[str, ResourceType] }
ResourceType = { name, parent, id_field, path_param }
```

Defines what CAN exist and relationships between types.

### ResourceGraph (Dynamic)
```
Resource = { type, id, parent, data, alive }
ResourceGraph = { resources: dict[(type, id), Resource] }
```

Tracks what DOES exist at runtime.

### Operations
- `create(type, id, parent_id)` - add resource
- `destroy(type, id)` - remove resource + all descendants
- `exists(type, id)` - check if alive
- `checkpoint()` / `rollback(snapshot)` - state management

## Integration with VenomQA v1

### Layer 1: runtime-core/ (standalone)
Reusable library with:
- `ResourceGraph`
- `ResourceSchema`
- `OpenAPIParser`

### Layer 2: ResourceGraphAdapter
Implements `Rollbackable` protocol:
```python
class ResourceGraphAdapter(Rollbackable):
    def observe(self) -> Observation
    def checkpoint(name) -> SystemCheckpoint
    def rollback(cp) -> None
```

### Layer 3: World Integration
```python
world = World(
    api=http,
    systems={
        "db": PostgresAdapter(db_url),
        "resources": ResourceGraphAdapter(schema),
    },
)
```

### Layer 4: Agent Integration
```python
def _valid_actions(self, state):
    graph = self.world.systems.get("resources")
    for action in self.actions:
        if graph and not graph.can_execute(action.requires, bindings):
            continue  # skip - resources don't exist
        # ... existing precondition checks
```

## OpenAPI Action Generation

From spec:
```yaml
paths:
  /workspaces/{workspace_id}/uploads:
    post:
      responses:
        201:
          content:
            application/json:
              schema:
                properties:
                  id: {type: string}
```

Infer:
- `upload` is child of `workspace`
- `POST /workspaces/{id}/uploads` creates `upload`
- Requires `workspace` to exist

Generate:
```python
Action(
    name="create_upload",
    requires=["workspace"],
    execute=auto_generated_fn,
)
```

## User Experience

### Before (manual)
```python
def delete_workspace(api, ctx):
    resp = api.delete(f"/workspaces/{ctx['workspace_id']}")
    ctx.clear("workspace_id")
    ctx.clear("upload_id")  # manual
    ctx.clear("member_id")  # manual
    # ... 19 more keys
    return resp
```

### After (ResourceGraph)
```python
def delete_workspace(api, ctx, resources):
    resp = api.delete(f"/workspaces/{ctx['workspace_id']}")
    resources.destroy("workspace", ctx["workspace_id"])  # auto-cascades
    return resp
```

## Task Dependencies

```
Task 1: runtime-core/ template
    ↓
Task 2: ResourceGraphAdapter ──→ Task 3: Wire into World
    ↓                                    ↓
Task 5: OpenAPI generator         Task 4: Agent preconditions
    ↓                                    ↓
    └──────────→ Task 6: Integration tests ←────────┘
```

## Research Sources

- [QuickCheck State Machine](https://www.well-typed.com/blog/2019/01/qsm-in-depth/) - symbolic references
- [Hypothesis Stateful Testing](https://hypothesis.readthedocs.io/en/latest/stateful.html) - bundles, consumes()
- [RESTler](https://github.com/microsoft/restler-fuzzer) - producer-consumer inference
- [Schemathesis](https://schemathesis.io/) - OpenAPI-driven testing
