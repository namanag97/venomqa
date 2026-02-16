# Writing Invariants

Invariants are rules that must always be true. They are your oracle — how you know if the system is correct.

This guide explains how to write effective Invariants.

## Anatomy of an Invariant

```python
Invariant(
    name="order_count_consistent",
    check=lambda world: (
        world.systems["db"].query("SELECT COUNT(*) FROM orders")[0][0]
        == len(world.api.get("/orders").json()["orders"])
    ),
    message="Database order count must match API response",
    severity=Severity.CRITICAL,
)
```

| Field | Purpose |
|-------|---------|
| `name` | Unique identifier, used in violation reports |
| `check` | Function that returns True if invariant holds |
| `message` | Human-readable explanation of what went wrong |
| `severity` | How serious is a violation |

## The Check Function

The `check` function receives the entire World and returns `True` if the invariant holds, `False` if violated.

### Access to Everything

The World gives you access to:

```python
def check(world: World) -> bool:
    # Query the database
    db_count = world.systems["db"].query("SELECT COUNT(*) FROM orders")[0][0]

    # Call the API
    api_response = world.api.get("/orders").json()

    # Check the cache
    cache_keys = world.systems["cache"].observe().data["keys"]

    # Check the queue
    pending_jobs = world.systems["queue"].observe().data["pending"]

    # Compare across systems
    return db_count == len(api_response["orders"])
```

### Return Value

- Return `True` → invariant holds, no violation
- Return `False` → invariant violated, bug found

```python
# Invariant holds
Invariant(
    name="always_true",
    check=lambda world: True,  # Never violates
)

# Invariant violated
Invariant(
    name="always_false",
    check=lambda world: False,  # Always violates
)
```

## Types of Invariants

### 1. Consistency Invariants

Ensure data is consistent across systems:

```python
# Database count matches API count
Invariant(
    name="order_count_consistent",
    check=lambda world: (
        world.systems["db"].query("SELECT COUNT(*) FROM orders")[0][0]
        == len(world.api.get("/orders").json()["orders"])
    ),
    message="Database order count must match API response",
    severity=Severity.CRITICAL,
)

# Cache reflects database
Invariant(
    name="user_cache_consistent",
    check=lambda world: all(
        world.systems["cache"].get(f"user:{row['id']}") is not None
        for row in world.systems["db"].query("SELECT id FROM users WHERE active=true")
    ),
    message="Active users must be cached",
    severity=Severity.HIGH,
)

# Search index matches database
Invariant(
    name="search_index_consistent",
    check=lambda world: (
        set(world.systems["search"].query("*"))
        == set(row["id"] for row in world.systems["db"].query(
            "SELECT id FROM products WHERE deleted=false"
        ))
    ),
    message="Search index must contain all non-deleted products",
    severity=Severity.HIGH,
)
```

### 2. Business Rule Invariants

Ensure business rules are enforced:

```python
# No negative balances
Invariant(
    name="no_negative_balance",
    check=lambda world: all(
        row["balance"] >= 0
        for row in world.systems["db"].query("SELECT balance FROM accounts")
    ),
    message="Account balance must never be negative",
    severity=Severity.CRITICAL,
)

# Orders must have items
Invariant(
    name="orders_have_items",
    check=lambda world: all(
        row["item_count"] > 0
        for row in world.systems["db"].query(
            "SELECT COUNT(*) as item_count FROM order_items GROUP BY order_id"
        )
    ),
    message="Every order must have at least one item",
    severity=Severity.HIGH,
)

# Shipped orders must have tracking
Invariant(
    name="shipped_orders_have_tracking",
    check=lambda world: all(
        row["tracking_number"] is not None
        for row in world.systems["db"].query(
            "SELECT tracking_number FROM orders WHERE status='shipped'"
        )
    ),
    message="Shipped orders must have tracking numbers",
    severity=Severity.MEDIUM,
)
```

### 3. Security Invariants

Ensure security properties hold:

```python
# Passwords are hashed
Invariant(
    name="passwords_hashed",
    check=lambda world: all(
        row["password"].startswith("$2b$")  # bcrypt hash prefix
        for row in world.systems["db"].query("SELECT password FROM users")
    ),
    message="Passwords must be hashed with bcrypt",
    severity=Severity.CRITICAL,
)

# Deleted data not accessible
Invariant(
    name="deleted_not_accessible",
    check=lambda world: all(
        world.api.get(f"/users/{row['id']}").status_code == 404
        for row in world.systems["db"].query("SELECT id FROM users WHERE deleted=true")
    ),
    message="Deleted users must not be accessible via API",
    severity=Severity.CRITICAL,
)

# No SQL injection artifacts
Invariant(
    name="no_sql_injection",
    check=lambda world: all(
        "DROP TABLE" not in str(row) and "DELETE FROM" not in str(row)
        for row in world.systems["db"].query("SELECT * FROM audit_log")
    ),
    message="No SQL injection patterns in audit log",
    severity=Severity.CRITICAL,
)
```

### 4. Referential Integrity Invariants

Ensure foreign keys are valid:

```python
# Orders reference valid users
Invariant(
    name="orders_reference_valid_users",
    check=lambda world: all(
        world.systems["db"].query(
            f"SELECT COUNT(*) FROM users WHERE id={row['user_id']}"
        )[0][0] > 0
        for row in world.systems["db"].query("SELECT user_id FROM orders")
    ),
    message="All orders must reference existing users",
    severity=Severity.CRITICAL,
)

# Order items reference valid products
Invariant(
    name="order_items_reference_valid_products",
    check=lambda world: all(
        world.systems["db"].query(
            f"SELECT COUNT(*) FROM products WHERE id={row['product_id']}"
        )[0][0] > 0
        for row in world.systems["db"].query("SELECT product_id FROM order_items")
    ),
    message="All order items must reference existing products",
    severity=Severity.CRITICAL,
)
```

### 5. State Machine Invariants

Ensure valid state transitions:

```python
# Order status transitions are valid
VALID_TRANSITIONS = {
    "pending": ["paid", "cancelled"],
    "paid": ["shipped", "refunded"],
    "shipped": ["delivered", "returned"],
    "delivered": ["returned"],
    "cancelled": [],
    "refunded": [],
    "returned": [],
}

Invariant(
    name="valid_order_transitions",
    check=lambda world: all(
        row["new_status"] in VALID_TRANSITIONS.get(row["old_status"], [])
        for row in world.systems["db"].query(
            "SELECT old_status, new_status FROM order_status_history"
        )
    ),
    message="Order status transitions must follow valid paths",
    severity=Severity.HIGH,
)
```

### 6. Performance Invariants

Ensure performance requirements:

```python
# API response time
Invariant(
    name="api_response_time",
    check=lambda world: (
        world.api.get("/health").elapsed.total_seconds() < 0.5
    ),
    message="API response time must be under 500ms",
    severity=Severity.MEDIUM,
)

# Query performance
Invariant(
    name="query_performance",
    check=lambda world: (
        world.systems["db"].query_with_timing(
            "SELECT * FROM orders WHERE user_id=1"
        )["duration_ms"] < 100
    ),
    message="Order query must complete in under 100ms",
    severity=Severity.LOW,
)
```

## Writing Effective Invariants

### 1. Be Specific

```python
# Good: Specific about what must hold
Invariant(
    name="order_total_matches_items",
    check=lambda world: all(
        row["total"] == sum(
            item["price"] * item["quantity"]
            for item in world.systems["db"].query(
                f"SELECT price, quantity FROM order_items WHERE order_id={row['id']}"
            )
        )
        for row in world.systems["db"].query("SELECT id, total FROM orders")
    ),
    message="Order total must equal sum of item prices",
)

# Bad: Vague
Invariant(
    name="orders_are_valid",
    check=lambda world: True,  # What does "valid" mean?
)
```

### 2. Make Failures Debuggable

Include context in the message:

```python
def check_order_totals(world: World) -> bool:
    orders = world.systems["db"].query("SELECT id, total FROM orders")
    for order in orders:
        items = world.systems["db"].query(
            f"SELECT price, quantity FROM order_items WHERE order_id={order['id']}"
        )
        expected = sum(i["price"] * i["quantity"] for i in items)
        if order["total"] != expected:
            # Log details for debugging
            print(f"Order {order['id']}: expected {expected}, got {order['total']}")
            return False
    return True

Invariant(
    name="order_total_correct",
    check=check_order_totals,
    message="Order total must equal sum of item prices",
)
```

### 3. Handle Empty Cases

```python
# Good: Handles empty case
Invariant(
    name="all_orders_have_items",
    check=lambda world: all(
        row["item_count"] > 0
        for row in world.systems["db"].query(
            "SELECT COUNT(*) as item_count FROM order_items GROUP BY order_id"
        )
    ) if world.systems["db"].query("SELECT COUNT(*) FROM orders")[0][0] > 0 else True,
    # If no orders, invariant trivially holds
)

# Bad: Crashes on empty
Invariant(
    name="all_orders_have_items",
    check=lambda world: min(  # min() fails on empty sequence
        row["item_count"]
        for row in world.systems["db"].query(...)
    ) > 0,
)
```

### 4. Use Appropriate Severity

```python
# CRITICAL: Data corruption, security breach
Invariant(name="passwords_hashed", severity=Severity.CRITICAL, ...)
Invariant(name="no_negative_balance", severity=Severity.CRITICAL, ...)

# HIGH: Major feature broken
Invariant(name="orders_have_items", severity=Severity.HIGH, ...)
Invariant(name="deleted_not_accessible", severity=Severity.HIGH, ...)

# MEDIUM: Feature partially working
Invariant(name="cache_hit_rate", severity=Severity.MEDIUM, ...)
Invariant(name="search_index_fresh", severity=Severity.MEDIUM, ...)

# LOW: Minor issues
Invariant(name="api_response_time", severity=Severity.LOW, ...)
Invariant(name="log_format_correct", severity=Severity.LOW, ...)
```

### 5. Avoid Side Effects

Invariants should only observe, never modify:

```python
# Good: Pure observation
Invariant(
    name="order_count",
    check=lambda world: (
        world.systems["db"].query("SELECT COUNT(*) FROM orders")[0][0] >= 0
    ),
)

# Bad: Side effect (modifies data)
def bad_check(world):
    world.systems["db"].execute("UPDATE orders SET checked=true")  # DON'T DO THIS
    return True
```

## Combining Invariants

### Independent Invariants

Each invariant is checked independently:

```python
invariants = [
    Invariant(name="inv1", check=check1, ...),
    Invariant(name="inv2", check=check2, ...),
    Invariant(name="inv3", check=check3, ...),
]

# All three are checked after every action
# Multiple can fail simultaneously
```

### Compound Checks

Combine related checks in one invariant:

```python
def check_order_integrity(world: World) -> bool:
    """Multiple related checks for order integrity."""
    orders = world.systems["db"].query("SELECT * FROM orders")

    for order in orders:
        # Check 1: Has items
        items = world.systems["db"].query(
            f"SELECT * FROM order_items WHERE order_id={order['id']}"
        )
        if not items:
            return False

        # Check 2: Total matches
        expected = sum(i["price"] * i["quantity"] for i in items)
        if order["total"] != expected:
            return False

        # Check 3: User exists
        user = world.systems["db"].query(
            f"SELECT * FROM users WHERE id={order['user_id']}"
        )
        if not user:
            return False

    return True

Invariant(
    name="order_integrity",
    check=check_order_integrity,
    message="Orders must have items, correct total, and valid user",
)
```

## Common Patterns

### Database-API Consistency

```python
def db_api_consistent(table: str, endpoint: str) -> Invariant:
    return Invariant(
        name=f"{table}_api_consistent",
        check=lambda world: (
            world.systems["db"].query(f"SELECT COUNT(*) FROM {table}")[0][0]
            == len(world.api.get(endpoint).json())
        ),
        message=f"{table} count must match {endpoint} response",
        severity=Severity.HIGH,
    )

invariants = [
    db_api_consistent("users", "/users"),
    db_api_consistent("orders", "/orders"),
    db_api_consistent("products", "/products"),
]
```

### No Orphaned Records

```python
def no_orphans(child_table: str, parent_table: str, fk_column: str) -> Invariant:
    return Invariant(
        name=f"no_orphan_{child_table}",
        check=lambda world: world.systems["db"].query(f"""
            SELECT COUNT(*) FROM {child_table} c
            LEFT JOIN {parent_table} p ON c.{fk_column} = p.id
            WHERE p.id IS NULL
        """)[0][0] == 0,
        message=f"No orphaned records in {child_table}",
        severity=Severity.CRITICAL,
    )

invariants = [
    no_orphans("orders", "users", "user_id"),
    no_orphans("order_items", "orders", "order_id"),
    no_orphans("order_items", "products", "product_id"),
]
```

### Enum Value Validity

```python
VALID_STATUSES = ["pending", "paid", "shipped", "delivered", "cancelled"]

Invariant(
    name="valid_order_status",
    check=lambda world: all(
        row["status"] in VALID_STATUSES
        for row in world.systems["db"].query("SELECT status FROM orders")
    ),
    message=f"Order status must be one of {VALID_STATUSES}",
    severity=Severity.HIGH,
)
```

## Debugging Invariants

### Verbose Check Functions

```python
def check_with_logging(world: World) -> bool:
    db_count = world.systems["db"].query("SELECT COUNT(*) FROM orders")[0][0]
    api_response = world.api.get("/orders")
    api_count = len(api_response.json()["orders"])

    print(f"DB count: {db_count}")
    print(f"API count: {api_count}")
    print(f"API response: {api_response.json()}")

    if db_count != api_count:
        print(f"MISMATCH: {db_count} != {api_count}")
        return False

    return True
```

### Test Invariants in Isolation

```python
def test_invariant():
    world = World(...)

    # Set up known state
    world.systems["db"].execute("INSERT INTO orders ...")

    # Test invariant
    result = order_count_invariant.check(world)
    assert result == True  # or False, depending on test case
```
