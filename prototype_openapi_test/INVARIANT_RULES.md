# VenomQA v2: Invariant Generation Rules

## Overview

VenomQA auto-generates invariants from the OpenAPI spec. This document defines the exact rules for generation.

---

## Rule Categories

### 1. CRUD Invariants

Generated based on HTTP method semantics.

#### CREATE (POST to collection)

| Pattern | Invariant | Severity |
|---------|-----------|----------|
| `POST /resources` | Response status is 201 | HIGH |
| `POST /resources` | Response body has `id` field | HIGH |
| `POST /resources` | Response content-type is application/json | MEDIUM |

**Generated invariant:**
```python
GeneratedInvariant(
    name="create_user_returns_201",
    description="POST /users should return 201 Created",
    source=InvariantSource.CRUD,
    severity=Severity.HIGH,
    _check=lambda world: world.last_action_result.status_code == 201,
)
```

#### READ (GET with ID)

| Pattern | Invariant | Severity |
|---------|-----------|----------|
| `GET /resources/{id}` after CREATE | Status is 200 | HIGH |
| `GET /resources/{id}` after DELETE | Status is 404 | HIGH |
| `GET /resources/{id}` non-existent | Status is 404 | MEDIUM |

**Generated invariant:**
```python
GeneratedInvariant(
    name="get_user_returns_200_after_create",
    description="GET /users/{id} returns 200 after user is created",
    source=InvariantSource.CRUD,
    severity=Severity.HIGH,
    # Check implemented as sequence invariant
)
```

#### UPDATE (PUT/PATCH with ID)

| Pattern | Invariant | Severity |
|---------|-----------|----------|
| `PUT /resources/{id}` existing | Status is 200 | HIGH |
| `PUT /resources/{id}` non-existent | Status is 404 | MEDIUM |
| `PATCH /resources/{id}` existing | Status is 200 | HIGH |

#### DELETE

| Pattern | Invariant | Severity |
|---------|-----------|----------|
| `DELETE /resources/{id}` existing | Status is 200 or 204 | HIGH |
| `DELETE /resources/{id}` twice | Second returns 404 | HIGH |
| `DELETE /resources/{id}` non-existent | Status is 404 | MEDIUM |

**The Double-Delete Invariant (key bug finder):**
```python
GeneratedInvariant(
    name="delete_user_idempotent",
    description="DELETE /users/{id} twice should return 404 on second call",
    source=InvariantSource.CRUD,
    severity=Severity.HIGH,
    # This is a sequence invariant, checked after DELETE
    _check=lambda world: (
        world.last_action_result.status_code == 404
        if world.context.get("_second_delete")
        else True
    ),
)
```

#### LIST (GET collection)

| Pattern | Invariant | Severity |
|---------|-----------|----------|
| `GET /resources` | Status is 200 | HIGH |
| `GET /resources` | Response is array or has items field | MEDIUM |

---

### 2. Schema Invariants

Generated from OpenAPI response schemas.

#### Required Fields

| Schema | Invariant | Severity |
|--------|-----------|----------|
| `required: ["id", "name"]` | Response has all required fields | HIGH |

**Generated invariant:**
```python
GeneratedInvariant(
    name="get_user_has_required_fields",
    description="GET /users/{id} response must have: id, name, email",
    source=InvariantSource.SCHEMA,
    severity=Severity.HIGH,
    _check=lambda world: all(
        field in world.last_action_result.body
        for field in ["id", "name", "email"]
    ),
)
```

#### Type Constraints

| Schema | Invariant | Severity |
|--------|-----------|----------|
| `type: "string"` | Field is string | MEDIUM |
| `type: "integer"` | Field is integer | MEDIUM |
| `type: "array"` | Field is array | MEDIUM |
| `type: "object"` | Field is object | MEDIUM |

#### Value Constraints

| Schema | Invariant | Severity |
|--------|-----------|----------|
| `enum: ["a", "b"]` | Field value in enum | HIGH |
| `minimum: 0` | Field >= minimum | MEDIUM |
| `maximum: 100` | Field <= maximum | MEDIUM |
| `minLength: 1` | String length >= minLength | LOW |
| `maxLength: 255` | String length <= maxLength | LOW |
| `pattern: "^[a-z]+$"` | String matches pattern | LOW |

#### Format Constraints

| Schema | Invariant | Severity |
|--------|-----------|----------|
| `format: "email"` | Field is valid email | LOW |
| `format: "uri"` | Field is valid URI | LOW |
| `format: "date-time"` | Field is valid ISO datetime | LOW |
| `format: "uuid"` | Field is valid UUID | LOW |

**Generated invariant:**
```python
GeneratedInvariant(
    name="user_email_is_valid",
    description="User email field must be valid email format",
    source=InvariantSource.SCHEMA,
    severity=Severity.LOW,
    _check=lambda world: is_valid_email(
        world.last_action_result.body.get("email", "")
    ),
)
```

---

### 3. Relationship Invariants

Generated from URL hierarchy.

#### Parent-Child Dependencies

| Pattern | Invariant | Severity |
|---------|-----------|----------|
| `POST /parents/{pid}/children` | Parent must exist | HIGH |
| `GET /parents/{pid}/children` | Returns children of that parent | MEDIUM |
| `DELETE /parents/{pid}` | Children should be deleted or return 404 | MEDIUM |

**Example URL hierarchy:**
```
/organizations/{org_id}/teams/{team_id}/members/{member_id}
```

**Generated invariants:**
```python
# Team requires organization
GeneratedInvariant(
    name="create_team_requires_organization",
    description="Cannot create team without existing organization",
    source=InvariantSource.RELATIONSHIP,
    severity=Severity.HIGH,
)

# Member requires team (and transitively, organization)
GeneratedInvariant(
    name="create_member_requires_team",
    description="Cannot create member without existing team",
    source=InvariantSource.RELATIONSHIP,
    severity=Severity.HIGH,
)

# Cascade delete check
GeneratedInvariant(
    name="delete_org_cascades_to_teams",
    description="Deleting organization should delete or orphan teams",
    source=InvariantSource.RELATIONSHIP,
    severity=Severity.MEDIUM,
)
```

---

## Generation Algorithm

```python
def generate_invariants(api: DiscoveredAPI) -> list[GeneratedInvariant]:
    invariants = []

    # 1. CRUD invariants
    for endpoint in api.endpoints:
        invariants.extend(generate_crud_invariants(endpoint))

    # 2. Schema invariants
    for endpoint in api.endpoints:
        for status_code, schema in endpoint.success_responses.items():
            invariants.extend(generate_schema_invariants(endpoint, schema))

    # 3. Relationship invariants
    for resource_type in api.resource_types.values():
        if resource_type.parent:
            invariants.extend(generate_relationship_invariants(resource_type))

    return invariants


def generate_crud_invariants(endpoint: DiscoveredEndpoint) -> list[GeneratedInvariant]:
    invariants = []

    if endpoint.crud_type == CRUDType.CREATE:
        # POST should return 201
        invariants.append(GeneratedInvariant(
            name=f"create_{endpoint.resource_type}_returns_201",
            description=f"POST {endpoint.path} should return 201",
            source=InvariantSource.CRUD,
            severity=Severity.HIGH,
            endpoint=endpoint,
        ))

        # Response should have ID
        invariants.append(GeneratedInvariant(
            name=f"create_{endpoint.resource_type}_has_id",
            description=f"POST {endpoint.path} response should have id field",
            source=InvariantSource.CRUD,
            severity=Severity.HIGH,
            endpoint=endpoint,
        ))

    elif endpoint.crud_type == CRUDType.DELETE:
        # DELETE should return 200/204
        invariants.append(GeneratedInvariant(
            name=f"delete_{endpoint.resource_type}_returns_success",
            description=f"DELETE {endpoint.path} should return 200 or 204",
            source=InvariantSource.CRUD,
            severity=Severity.HIGH,
            endpoint=endpoint,
        ))

        # Double DELETE should 404
        invariants.append(GeneratedInvariant(
            name=f"delete_{endpoint.resource_type}_twice_returns_404",
            description=f"DELETE {endpoint.path} twice should return 404 on second call",
            source=InvariantSource.CRUD,
            severity=Severity.HIGH,
            endpoint=endpoint,
        ))

    # ... etc for READ, UPDATE, LIST

    return invariants


def generate_schema_invariants(
    endpoint: DiscoveredEndpoint,
    schema: SchemaSpec
) -> list[GeneratedInvariant]:
    invariants = []

    # Required fields
    if schema.required:
        invariants.append(GeneratedInvariant(
            name=f"{endpoint.name}_has_required_fields",
            description=f"Response must have fields: {', '.join(schema.required)}",
            source=InvariantSource.SCHEMA,
            severity=Severity.HIGH,
            endpoint=endpoint,
            schema=schema,
        ))

    # Enum constraints
    for prop_name, prop_schema in schema.properties.items():
        if prop_schema.enum:
            invariants.append(GeneratedInvariant(
                name=f"{endpoint.name}_{prop_name}_in_enum",
                description=f"Field {prop_name} must be one of: {prop_schema.enum}",
                source=InvariantSource.SCHEMA,
                severity=Severity.HIGH,
                endpoint=endpoint,
            ))

    return invariants
```

---

## Invariant Checking Strategy

### When to Check

| Invariant Type | Check Timing |
|----------------|--------------|
| Response status | Immediately after action |
| Response schema | Immediately after action |
| Double-delete | After second DELETE of same resource |
| Parent-child | Before child CREATE |
| Cascade delete | After parent DELETE |

### Sequence Invariants

Some invariants require checking across action sequences:

```python
# Track state for sequence invariants
class SequenceTracker:
    def __init__(self):
        self.deleted_resources: set[tuple[str, str]] = set()  # (type, id)
        self.created_resources: set[tuple[str, str]] = set()

    def on_action(self, action: GeneratedAction, result: ActionResult):
        if action.endpoint.crud_type == CRUDType.CREATE and result.is_success:
            resource_id = result.body.get("id")
            self.created_resources.add((action.endpoint.resource_type, resource_id))

        elif action.endpoint.crud_type == CRUDType.DELETE and result.is_success:
            # Extract ID from context or URL
            resource_id = ...
            self.deleted_resources.add((action.endpoint.resource_type, resource_id))

    def check_double_delete(self, action: GeneratedAction, result: ActionResult) -> bool:
        """Check if this is a second DELETE that should 404."""
        if action.endpoint.crud_type != CRUDType.DELETE:
            return True  # Not applicable

        resource_id = ...
        key = (action.endpoint.resource_type, resource_id)

        if key in self.deleted_resources:
            # This is a second delete - should be 404
            return result.status_code == 404

        return True  # First delete, no constraint
```

---

## Configuration Options

```yaml
# venomqa.yaml
invariants:
  # Enable/disable categories
  crud: true
  schema: true
  relationship: true

  # Severity threshold (only generate invariants at or above this level)
  min_severity: medium  # critical, high, medium, low

  # Custom invariants
  custom:
    - name: "balance_non_negative"
      description: "Account balance should never be negative"
      check: "response.body.get('balance', 0) >= 0"
      severity: critical
      endpoints: ["getAccount", "updateAccount"]

  # Ignore specific auto-generated invariants
  ignore:
    - "get_user_email_is_valid"  # We allow invalid emails in test mode
```

---

## Summary Statistics

For a typical REST API with 20 endpoints:

| Category | Invariants Generated |
|----------|---------------------|
| CRUD | ~30-40 |
| Schema | ~20-30 |
| Relationship | ~5-10 |
| **Total** | **~55-80** |

This gives comprehensive coverage with zero user effort.
