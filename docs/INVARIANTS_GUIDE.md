# Understanding Violations in VenomQA

## What is a Violation?

A **violation** occurs when an **invariant** returns `False`.

- **Invariant** = A rule that must ALWAYS be true, no matter what sequence of actions was executed
- **Violation** = The invariant returned `False` — something is broken

## How Developers Define What's a Violation

### Step 1: Identify Business Rules

Before writing code, list your business rules:

```
1. A user can't have negative balance
2. Refunds can't exceed the original payment
3. Deleted resources must return 404
4. Open issues list must not contain closed issues
5. Order total must equal sum of line items
```

### Step 2: Write the Invariant Function

Each invariant is a function that returns `True` (pass) or `False` (violation):

```python
def refund_cannot_exceed_payment(world):
    """VIOLATION if refunded_amount > payment_amount."""
    refund = world.context.get("refund_amount") or 0
    payment = world.context.get("payment_amount") or 0

    # Return True = OK, False = VIOLATION
    return refund <= payment
```

### Step 3: Register with Severity

```python
from venomqa.v1 import Invariant, Severity

Invariant(
    name="refund_cannot_exceed_payment",
    check=refund_cannot_exceed_payment,
    message="Refunded amount exceeds original payment. Billing integrity bug!",
    severity=Severity.CRITICAL,  # CRITICAL, HIGH, MEDIUM, LOW
)
```

## Severity Guidelines

| Severity | When to Use | Examples |
|----------|-------------|----------|
| `CRITICAL` | Data corruption, security breach, money issues | Over-refund, data leak, auth bypass |
| `HIGH` | Major feature broken | Can't checkout, can't login |
| `MEDIUM` | Partial functionality loss | Wrong count displayed, slow response |
| `LOW` | Minor issues | Typo in response, extra whitespace |

## Common Invariant Patterns

### Pattern 1: Check Context State
```python
def user_must_exist_after_login(world):
    """After login action runs, user_id must be set."""
    if not world.context.has("logged_in"):
        return True  # Login hasn't run yet, skip
    return world.context.get("user_id") is not None
```

### Pattern 2: Make Live API Call
```python
def deleted_resource_returns_404(world):
    """After delete, GET must return 404."""
    deleted_id = world.context.get("deleted_resource_id")
    if not deleted_id:
        return True  # Nothing deleted yet

    resp = world.api.get(f"/resources/{deleted_id}")
    return resp.status_code == 404
```

### Pattern 3: Cross-Reference Data
```python
def order_total_matches_items(world):
    """Order total must equal sum of line items."""
    order = world.context.get("order")
    if not order:
        return True

    expected_total = sum(item["price"] * item["qty"] for item in order["items"])
    return order["total"] == expected_total
```

### Pattern 4: Compare API vs Database
```python
def api_count_matches_db(world):
    """API response count must match database count."""
    api_count = world.context.get("api_item_count")

    # Query database directly (if db adapter registered)
    db = world.systems.get("db")
    if not db or api_count is None:
        return True

    db_count = db.query_one("SELECT COUNT(*) FROM items")
    return api_count == db_count
```

## Understanding Violation Output

When a violation is detected:

```
[CRITICAL] refund_cannot_exceed_payment
  Message: Refunded amount exceeds original payment. Billing integrity bug!

  Reproduction Path:
    -> create_customer
    -> create_payment_intent
    -> confirm_payment
    -> create_refund           ← This action triggered the violation

  Request: POST http://localhost:8102/refunds
  Response: 200
  Body: {"id": "re_123", "amount": 2000, ...}
```

**Key information:**
- **Invariant name**: Which rule was broken
- **Message**: Human explanation of the issue
- **Reproduction path**: Exact sequence of actions to reproduce
- **Request/Response**: The HTTP call that led to the violation

## Good Defaults for Complex Projects

### Recommended Config (`venomqa.yaml`)

```yaml
# Target API
base_url: "http://localhost:8000"
timeout: 30

# Retry configuration
retry:
  max_attempts: 3
  delay: 1
  backoff_multiplier: 2
  max_delay: 30
  retry_on_status: [429, 500, 502, 503, 504]

# Exploration settings
exploration:
  strategy: "bfs"           # bfs, dfs, random, coverage_guided
  max_steps: 500            # Increase for more coverage
  stop_on_first_violation: false  # Set true for fast feedback

# Reporting
report:
  formats: [html, json, junit]
  output_dir: "./reports"
  include_request_response: true  # Show full HTTP payloads

# For CI/CD
fail_on_severity: "high"    # Fail pipeline if HIGH or CRITICAL found
```

### Recommended Project Structure

```
qa/
├── venomqa.yaml           # Config
├── actions/
│   ├── __init__.py
│   ├── auth.py            # Login, logout, register
│   ├── users.py           # CRUD for users
│   └── orders.py          # Order operations
├── invariants/
│   ├── __init__.py
│   ├── auth.py            # Auth invariants
│   ├── data_integrity.py  # Cross-reference checks
│   └── security.py        # Security invariants
├── journeys/
│   ├── auth_flow.py       # Focused: auth actions only
│   ├── order_flow.py      # Focused: order actions only
│   └── full_exploration.py # All actions (needs more steps)
└── reports/
```

### Recommended Invariants by Domain

**Authentication:**
```python
INVARIANTS = [
    Invariant(name="logged_out_cant_access_protected", check=..., severity=Severity.CRITICAL),
    Invariant(name="session_expires_correctly", check=..., severity=Severity.HIGH),
    Invariant(name="password_not_in_response", check=..., severity=Severity.CRITICAL),
]
```

**E-commerce:**
```python
INVARIANTS = [
    Invariant(name="cart_total_matches_items", check=..., severity=Severity.CRITICAL),
    Invariant(name="inventory_not_negative", check=..., severity=Severity.CRITICAL),
    Invariant(name="order_total_correct", check=..., severity=Severity.CRITICAL),
    Invariant(name="refund_within_bounds", check=..., severity=Severity.CRITICAL),
]
```

**Data Integrity:**
```python
INVARIANTS = [
    Invariant(name="deleted_returns_404", check=..., severity=Severity.HIGH),
    Invariant(name="created_is_retrievable", check=..., severity=Severity.CRITICAL),
    Invariant(name="list_count_matches_db", check=..., severity=Severity.MEDIUM),
]
```

## Testing Your Invariants

### 1. Plant Known Bugs

Create a mock server with deliberate bugs to verify detection:

```python
# mock_server.py
@app.post("/refunds")
def create_refund(amount: int):
    # BUG: No validation - allows over-refund
    return {"refund_id": "123", "amount": amount}
```

Then run exploration:
```bash
python3 qa/journeys/payment_flow.py
```

Expected: VenomQA should find the `refund_cannot_exceed_payment` violation.

### 2. Run Focused Explorations

Don't start with 50 actions. Start focused:

```python
# Test just auth (5 actions, finds bugs in ~30 steps)
agent = Agent(
    actions=[login, logout, register, change_password, delete_account],
    invariants=AUTH_INVARIANTS,
    max_steps=100,
)

# Test just payments (5 actions, finds bugs in ~30 steps)
agent = Agent(
    actions=[create_customer, create_payment, confirm, refund, get_status],
    invariants=PAYMENT_INVARIANTS,
    max_steps=100,
)
```

### 3. Verify Reproduction Paths

When a violation is found, manually replay the path:

```bash
# Violation says: create_user -> create_order -> apply_discount -> checkout
curl -X POST localhost:8000/users -d '{"name": "test"}'
curl -X POST localhost:8000/orders -d '{"user_id": 1}'
curl -X POST localhost:8000/orders/1/discount -d '{"code": "50OFF"}'
curl -X POST localhost:8000/orders/1/checkout
# Verify the bug exists
```

## Quick Reference

| Question | Answer |
|----------|--------|
| What's a violation? | Invariant returned `False` |
| What severity to use? | CRITICAL for money/security, HIGH for broken features |
| How many actions? | Start with 5-10 per exploration |
| How many steps? | 100-500 depending on action count |
| BFS vs DFS? | BFS finds shallow bugs faster |
| When to check invariants? | After every action (default) |
