# OpenAPI Parsing Prototype: Findings

## Executive Summary

Tested VenomQA's OpenAPI parsing against 10 real-world specs. **7/10 succeeded**, parsing **3,688 endpoints** into actions.

**Key finding**: The current parser works but has significant gaps that prevent zero-config usage.

---

## Test Results

| Spec | Version | Paths | Endpoints | Actions | Status |
|------|---------|-------|-----------|---------|--------|
| Swagger Petstore | 3.0.4 | 13 | 19 | 19 | ✓ |
| Stripe API | 3.0.0 | 415 | 588 | 588 | ✓ |
| GitHub REST API | 3.0.3 | 721 | 1,080 | 1,080 | ✓ |
| Kubernetes API | 2.0 | 537 | 1,055 | 1,055 | ✓ |
| Slack Web API | 2.0 | 174 | 174 | 174 | ✓ |
| Discord API | 3.1.0 | 137 | 227 | 227 | ✓ |
| DigitalOcean API | 3.0.0 | 356 | 545 | 545 | ✓ |
| OpenAI API | - | - | - | - | ✗ (404) |
| Xero API | - | - | - | - | ✗ (datetime bug) |
| Asana API | - | - | - | - | ✗ (404) |

**Totals**: 2,353 paths → 3,688 endpoints → 3,688 actions (100% conversion)

---

## Edge Cases Discovered

| Issue | Occurrences | Impact |
|-------|-------------|--------|
| DEEP_NESTING (4+ path params) | 19 | Complicates preconditions |
| ALLOF_SCHEMA | 17 | Schema composition not handled |
| ONEOF_SCHEMA | 16 | Variant types not handled |
| NO_REQUEST_SCHEMA | 7 | Can't generate request bodies |
| NO_RESPONSE_SCHEMA | 7 | Can't generate response invariants |
| USES_REFS | 6 specs | All specs rely heavily on $ref |
| ANYOF_SCHEMA | 4 | Alternative types not handled |

---

## Problem 1: Resource Type Inference is Broken

### What Happens
```
Path: /pet/findByStatus
Inferred resources: ["pet", "findByStatu"]  ← WRONG

Path: /user/login
Inferred resources: ["user", "login"]  ← WRONG
```

### Why It's Wrong
The parser treats every path segment as a potential resource type. But:
- `findByStatus` is a **query**, not a resource
- `login` is an **action**, not a resource
- `uploadImage` is an **operation**, not a resource

### Fix Required
Detect action-like segments:
```python
ACTION_VERBS = {"find", "get", "create", "update", "delete", "login", "logout",
               "upload", "download", "search", "list", "count", "verify"}

def is_resource_segment(segment: str) -> bool:
    # Check if starts with verb
    for verb in ACTION_VERBS:
        if segment.lower().startswith(verb):
            return False
    # Check camelCase verbs
    if any(segment.lower().startswith(v) for v in ACTION_VERBS):
        return False
    return True
```

---

## Problem 2: $ref Not Resolved

### What Happens
```yaml
requestBody:
  content:
    application/json:
      schema:
        $ref: "#/components/schemas/Pet"  ← Not resolved
```

VenomQA sees: `request_body_schema = {"$ref": "#/components/schemas/Pet"}`

But needs: The actual Pet schema to generate request bodies.

### Scale of Problem
| Spec | $ref Count |
|------|-----------|
| Petstore | 43 |
| Slack | 644 |
| Stripe | 3,732 |
| Discord | 3,582 |
| DigitalOcean | 6,338 |
| Kubernetes | 8,939 |

**Every real spec uses $ref extensively.**

### Fix Required
Resolve references before processing:
```python
def resolve_refs(spec: dict, root: dict = None) -> dict:
    """Recursively resolve all $ref in spec."""
    if root is None:
        root = spec

    if isinstance(spec, dict):
        if "$ref" in spec:
            ref_path = spec["$ref"]
            if ref_path.startswith("#/"):
                # Internal ref
                resolved = get_by_path(root, ref_path[2:])
                return resolve_refs(resolved, root)
        return {k: resolve_refs(v, root) for k, v in spec.items()}
    elif isinstance(spec, list):
        return [resolve_refs(item, root) for item in spec]
    return spec
```

---

## Problem 3: Complex Schemas Not Handled

### oneOf (Union Types)
```yaml
Pet:
  oneOf:
    - $ref: "#/components/schemas/Dog"
    - $ref: "#/components/schemas/Cat"
```

**Need**: Generate separate test cases for Dog and Cat.

### anyOf (Optional Combinations)
```yaml
PaymentSource:
  anyOf:
    - $ref: "#/components/schemas/Card"
    - $ref: "#/components/schemas/BankAccount"
```

**Need**: Test with Card, BankAccount, and potentially both.

### allOf (Composition)
```yaml
Employee:
  allOf:
    - $ref: "#/components/schemas/Person"
    - type: object
      properties:
        employeeId: { type: string }
```

**Need**: Merge schemas before processing.

---

## Problem 4: Missing Invariant Generation

### What We Have
```
OpenAPI Spec → Actions[]
```

### What We Need
```
OpenAPI Spec → Actions[] + Invariants[]
```

### Invariants We CAN Auto-Generate

**From HTTP Method:**
```python
# POST should return 201
Invariant(
    name="create_returns_201",
    check=lambda w: w.last_action_result.status_code == 201,
)

# DELETE twice should 404 second time
Invariant(
    name="delete_idempotent",
    check=lambda w: ...,  # Check second DELETE returns 404
)
```

**From Response Schema:**
```python
# Response must match schema
Invariant(
    name="response_matches_schema",
    check=lambda w: validate_schema(w.last_action_result.json(), schema),
)
```

**From Required Fields:**
```python
# Response must have required fields
Invariant(
    name="response_has_required_fields",
    check=lambda w: all(f in w.last_action_result.json() for f in ["id", "name"]),
)
```

---

## Problem 5: No Request Body Generation

### What Happens
```python
# Current: expects user to provide body
body = context.get("_request_body", {})
resp = api.post(url, json=body)
```

### What We Need
```python
# Auto-generate from schema
schema = endpoint.request_body_schema
body = generate_from_schema(schema)  # Using hypothesis-jsonschema
resp = api.post(url, json=body)
```

---

## What VenomQA Can vs. Can't Auto-Generate

### CAN Generate from OpenAPI

| Signal | VenomQA Artifact |
|--------|------------------|
| `paths` | Actions |
| `operationId` | Action.name |
| HTTP method | CRUD type, expected status |
| Path params `{id}` | Preconditions |
| `requestBody.required` | Precondition |
| Response schema | Schema invariant |
| `required` fields | Field presence invariant |
| `enum` | Value constraint invariant |
| `minimum/maximum` | Range invariant |
| `security` | Auth precondition |
| URL hierarchy | Resource relationships |

### CANNOT Generate (Need User Input)

| Missing | Why | Example |
|---------|-----|---------|
| Business rules | Not in spec | `balance >= 0` |
| Side effects | Not described | "sends email" |
| State dependencies | Only implicit | "order needs user" |
| Idempotency rules | Not standardized | `DELETE` idempotent |
| Cross-entity rules | Not expressible | "deleted user can't order" |
| Rate limits | Not in OpenAPI 3.0 | "100 req/min" |

---

## Recommended Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     OPENAPI SPEC                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 PREPROCESSING LAYER                              │
│  • Resolve all $ref references                                   │
│  • Merge allOf schemas                                          │
│  • Normalize to OpenAPI 3.0 (if 2.0)                            │
└─────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ ACTION GENERATOR│  │INVARIANT GENER. │  │ DATA GENERATOR  │
│                 │  │                 │  │                 │
│ • Parse paths   │  │ • Schema check  │  │ • Request body  │
│ • Detect CRUD   │  │ • CRUD rules    │  │   from schema   │
│ • Set precond.  │  │ • Required      │  │ • hypothesis-   │
│ • Filter actions│  │   fields        │  │   jsonschema    │
└─────────────────┘  └─────────────────┘  └─────────────────┘
          │                   │                   │
          └───────────────────┼───────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     VENOMQA RUNTIME                              │
│  Agent(actions, invariants, world)                              │
│  • Explore state graph                                          │
│  • Check invariants                                             │
│  • Report violations                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Priority Fixes

### P0: Must Have for Zero-Config

1. **$ref resolution** - Without this, schemas are empty
2. **allOf merging** - Common pattern, breaks everything
3. **Better resource inference** - Current generates garbage

### P1: Should Have

4. **Auto-generate CRUD invariants** - This is VenomQA's value prop
5. **Schema-based response validation** - Easy win from spec
6. **oneOf/anyOf handling** - Generate multiple test variants

### P2: Nice to Have

7. **Request body generation** - Using hypothesis-jsonschema
8. **Security handling** - Auth token injection
9. **Link following** - OpenAPI 3.0 links for navigation

---

## Next Steps

1. **Implement $ref resolver** (~2 hours)
2. **Improve resource inference** (~1 hour)
3. **Add CRUD invariant generation** (~2 hours)
4. **Add schema validation invariants** (~2 hours)
5. **Test against same 10 specs** - Measure improvement
6. **Create `venomqa run <spec>` command** - Zero config CLI
