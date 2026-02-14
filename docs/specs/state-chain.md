# VenomQA State Chain Specification

> The definitive spec for context-aware state exploration that mimics human QA

## The Problem

Current "exploration" is broken:
- Calls endpoints with placeholder values (`{todoId}` instead of real IDs)
- Each call is independent - no context passing
- Results in 404s and dead-ends everywhere
- NOT how a human QA works

## The Vision

A human QA does this:
1. Creates something → Gets back an ID
2. Uses that ID in the next call
3. Gets back more data (file IDs, tokens, statuses)
4. Uses THAT data in subsequent calls
5. Builds a CHAIN of connected states

## Core Concept: State Chain

```
Action → Response → Extract Context → Next Action (using context) → Response → ...
```

### Example Chain

```
POST /todos {"title": "Test"}
    │
    ▼ Response: {"id": 42, "title": "Test", "completed": false}
    │
    │ EXTRACT: todo_id = 42
    │
    ▼
GET /todos/42  ← Uses extracted todo_id
    │
    ▼ Response: {"id": 42, "title": "Test", "completed": false}
    │
    ▼
PUT /todos/42 {"completed": true}  ← Same todo_id
    │
    ▼ Response: {"id": 42, "completed": true}
    │
    │ STATE CHANGED: todo is now completed
    │
    ▼
POST /todos/42/attachments {file: binary}
    │
    ▼ Response: {"id": "abc-123", "filename": "doc.pdf", "todo_id": 42}
    │
    │ EXTRACT: attachment_id = "abc-123"
    │
    ▼
GET /todos/42/attachments/abc-123  ← Uses BOTH extracted IDs
    │
    ▼ Response: <file content>
    │
    ▼
DELETE /todos/42/attachments/abc-123
    │
    ▼ Response: 204 No Content
    │
    │ STATE CHANGED: attachment removed
    │
    ▼
DELETE /todos/42
    │
    ▼ Response: 204 No Content
    │
    │ STATE CHANGED: todo deleted
    │
    ▼
GET /todos/42  ← Verify deletion
    │
    ▼ Response: 404 {"error": "Not found"}  ← EXPECTED!
```

## Context Object

The context accumulates data through the chain:

```python
context = {
    "todo_id": None,        # Extracted from POST /todos
    "attachment_id": None,  # Extracted from POST /attachments
    "auth_token": None,     # Extracted from POST /login
    "user_id": None,        # Extracted from auth response
    "order_id": None,       # Extracted from POST /orders
    # ... any ID or token from any response
}
```

## Context Extraction Rules

From each response, extract:

1. **IDs**: Any field ending in `_id`, `Id`, or named `id`
2. **Tokens**: `token`, `access_token`, `refresh_token`, `api_key`
3. **References**: `href`, `url`, `link` fields
4. **Status**: `status`, `state`, `completed`, `active`

```python
def extract_context(response_json, context):
    """Extract relevant data from response into context."""

    # Extract IDs
    for key, value in flatten(response_json):
        if key == "id" or key.endswith("_id") or key.endswith("Id"):
            # Infer context key from endpoint or response structure
            context_key = infer_context_key(key, endpoint)
            context[context_key] = value

        if key in ["token", "access_token", "auth_token"]:
            context["auth_token"] = value

    return context
```

## Path Parameter Substitution

Before executing an action, substitute context values:

```python
def substitute_path_params(endpoint, context):
    """Replace {param} with actual values from context."""

    # /todos/{todoId} + context["todo_id"]=42 → /todos/42
    # /todos/{todoId}/attachments/{fileId} + context → /todos/42/attachments/abc-123

    result = endpoint
    for match in re.findall(r'\{(\w+)\}', endpoint):
        # Try exact match
        if match in context:
            result = result.replace(f'{{{match}}}', str(context[match]))
        # Try common variations
        elif match.lower() + "_id" in context:
            result = result.replace(f'{{{match}}}', str(context[match.lower() + "_id"]))
        elif match.replace("Id", "_id") in context:
            result = result.replace(f'{{{match}}}', str(context[match.replace("Id", "_id")]))

    return result
```

## State Definition

A state is defined by:

```python
@dataclass
class ChainState:
    """State in the exploration chain."""

    id: str                          # Unique identifier
    name: str                        # Human-readable name
    context: Dict[str, Any]          # Accumulated context (IDs, tokens)
    response: Dict[str, Any]         # Response that led to this state
    available_actions: List[Action]  # What can be done from here
    depth: int                       # How deep in the chain
    parent_state: Optional[str]      # Previous state ID
    parent_action: Optional[Action]  # Action that led here
```

## Chain Exploration Algorithm

```python
def explore_chain(initial_actions, max_depth=10):
    """BFS exploration with context passing."""

    context = {}  # Shared context accumulates through chain
    graph = StateGraph()
    queue = [(initial_state, context.copy(), 0)]  # (state, context, depth)

    while queue:
        current_state, current_context, depth = queue.pop(0)

        if depth >= max_depth:
            continue

        for action in current_state.available_actions:
            # 1. Substitute path parameters with context values
            resolved_endpoint = substitute_path_params(action.endpoint, current_context)

            # 2. Skip if we can't resolve all parameters
            if '{' in resolved_endpoint:
                continue  # Missing required context

            # 3. Execute the action
            response = execute(action.method, resolved_endpoint, action.body)

            # 4. Extract new context from response
            new_context = current_context.copy()
            extract_context(response.json(), new_context)

            # 5. Determine the new state
            new_state = create_state(response, new_context, depth + 1)

            # 6. Record transition
            graph.add_transition(current_state, action, new_state)

            # 7. Queue for further exploration
            if new_state not in visited:
                queue.append((new_state, new_context, depth + 1))

    return graph
```

## State Naming

States should have meaningful names based on context:

```python
def generate_state_name(context, response):
    """Generate human-readable state name."""

    parts = []

    if context.get("auth_token"):
        parts.append("Authenticated")
    else:
        parts.append("Anonymous")

    if context.get("todo_id"):
        parts.append(f"Todo:{context['todo_id']}")

    if context.get("attachment_id"):
        parts.append(f"Attachment:{context['attachment_id']}")

    if response.get("completed"):
        parts.append("Completed")

    return " | ".join(parts) or "Initial"
```

## Expected State Graph (Todo App)

```
                        [Anonymous]
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         [GET /health]  [GET /todos]  [POST /todos]
              │              │              │
              ▼              ▼              ▼
          [Healthy]    [Empty List]   [Todo:1 Created]
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    ▼                      ▼                      ▼
             [GET /todos/1]         [PUT /todos/1]         [DELETE /todos/1]
                    │                      │                      │
                    ▼                      ▼                      ▼
             [Viewing Todo:1]       [Todo:1 Completed]      [Todo:1 Deleted]
                    │                      │                      │
                    ▼                      ▼                      ▼
          [POST /todos/1/attach]    [POST /todos/1/attach]  [GET /todos/1]
                    │                      │                      │
                    ▼                      ▼                      ▼
          [Todo:1 + Attach:abc]    [Todo:1 Completed       [404 - Expected]
                    │               + Attach:xyz]
                    ▼
          [GET /todos/1/attach/abc]
                    │
                    ▼
          [Downloaded File]
                    │
                    ▼
          [DELETE /todos/1/attach/abc]
                    │
                    ▼
          [Todo:1 No Attachments]
```

## Key Differences from Current Implementation

| Current (Broken) | Required (Real) |
|------------------|-----------------|
| `GET /todos/{todoId}` with literal `{todoId}` | `GET /todos/42` with real ID |
| Context ignored | Context passed through chain |
| Flat graph, all from initial | Deep tree, states depend on parents |
| 404s are failures | 404s after DELETE are expected |
| No relationship between calls | Each call builds on previous |

## Success Criteria

1. **Zero placeholder 404s** - All path params resolved from context
2. **Deep chains** - At least 5-6 levels deep for CRUD apps
3. **Context accumulation** - IDs extracted and reused
4. **Meaningful state names** - Based on context, not random hashes
5. **Expected errors identified** - 404 after DELETE is OK, 404 on GET is bug

## Implementation Checklist

- [ ] Context object passed through exploration
- [ ] `extract_context()` pulls IDs/tokens from responses
- [ ] `substitute_path_params()` replaces `{param}` with context values
- [ ] Actions skipped if path params can't be resolved
- [ ] State names generated from context
- [ ] Parent-child relationships tracked
- [ ] Deep exploration (not just initial → first level)

## Files to Modify

1. `venomqa/explorer/engine.py` - Add context passing to BFS/DFS
2. `venomqa/explorer/detector.py` - Add `extract_context()` function
3. `venomqa/explorer/models.py` - Add `ChainState` with context field
4. `venomqa/explorer/explorer.py` - Wire up context-aware exploration

## Example Usage (Target API)

```python
from venomqa.explorer import StateExplorer

explorer = StateExplorer(
    base_url="http://localhost:5001",
    openapi_spec="openapi.yaml"
)

# This should produce a DEEP, CONNECTED state graph
result = explorer.explore_with_context()

# States should have meaningful names
for state in result.graph.states.values():
    print(state.name)
    # "Anonymous"
    # "Anonymous | Todo:1"
    # "Anonymous | Todo:1 | Completed"
    # "Anonymous | Todo:1 | Attachment:abc"
    # "Anonymous | Todo:1 Deleted"

# Transitions should use real IDs
for t in result.graph.transitions:
    print(f"{t.from_state} --[{t.action.endpoint}]--> {t.to_state}")
    # "Anonymous --[POST /todos]--> Anonymous | Todo:1"
    # "Anonymous | Todo:1 --[GET /todos/1]--> Anonymous | Todo:1 | Viewing"
    # "Anonymous | Todo:1 --[PUT /todos/1]--> Anonymous | Todo:1 | Completed"
```

---

**This is the spec. No more placeholder garbage. Real context-aware state chains.**
