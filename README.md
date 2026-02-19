# VenomQA

**Stateful API testing that finds sequence bugs your unit tests will never catch.**

VenomQA is an autonomous QA agent for REST APIs. You define **Actions** (API calls) and **Invariants** (rules that must always hold). VenomQA exhaustively explores every reachable *sequence* through your application's state graph — automatically, using real database rollbacks to branch between paths.

The insight that drives everything: **bugs in APIs are almost never in individual endpoints. They live in sequences.** `create → refund → refund`. `delete → create`. `update → delete → list`. Your pytest suite passes. Your users find the bug.

[![PyPI version](https://badge.fury.io/py/venomqa.svg)](https://pypi.org/project/venomqa/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://pypi.org/project/venomqa/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Downloads](https://pepy.tech/badge/venomqa)](https://pepy.tech/project/venomqa)
[![Tests](https://github.com/namanag97/venomqa/actions/workflows/test.yml/badge.svg)](https://github.com/namanag97/venomqa/actions/workflows/test.yml)

---

## See It Find a Bug (30 Seconds)

```bash
pip install venomqa
venomqa demo
```

```
Unit Test Results: 3/3 PASS ✓

VenomQA Exploration: 8 states, 20 transitions

╭─────────────────── CRITICAL VIOLATION ───────────────────╮
│ BUG FOUND!                                               │
│ Sequence: create_order → refund → refund                 │
│ Problem: Refunded $200 on a $100 order!                  │
╰──────────────────────────────────────────────────────────╯
```

Three unit tests pass. One double-refund bug survives. VenomQA finds it in 8 states because it tests the *sequence*, not the endpoint.

---

## The Problem: Your Tests Pass. Your Users Find the Bug.

Standard testing tools check individual endpoints or fixed, hand-written sequences. Real-world bugs hide in the *orderings* that no one thought to script.

**Common bugs that only appear in sequences:**

- **Double refund** — `refund(order)` twice both return `200`. Refunded amount exceeds order total.
- **Stale state after delete** — `delete(resource)` then `create(resource)` returns ghost data from the first.
- **Cascade delete doesn't clean up** — deleting a parent leaves orphaned children that corrupt future reads.
- **Role change doesn't invalidate session** — `demote(user)` then `admin_action(user)` succeeds when it should fail.
- **Race in create → update** — creating a resource and immediately updating it hits an uninitialized field.
- **Resource leak after failed creation** — partial create followed by retry creates duplicates.

```
PUT /orders/{id}/refund → 200   # passes in isolation
PUT /orders/{id}/refund → 200   # also passes in isolation
GET /orders/{id}        → 200   # refunded_amount: 200 > total: 100  ← BUG
```

These bugs do not appear in individual endpoint tests. They do not appear in a single happy-path integration test. They appear when you exhaustively explore *every ordering* — which is exactly what VenomQA does.

---

## VenomQA vs Other API Testing Tools

| Tool | What it tests | Finds sequence bugs? | Uses real DB state? | Autonomous? |
|---|---|---|---|---|
| pytest | Individual functions | No | No (mocked) | No |
| Schemathesis | Individual endpoints (random inputs) | No | No | Partial |
| Postman / Newman | Fixed sequences you wrote by hand | No (only what you script) | No | No |
| Dredd | OpenAPI contract compliance | No | No | No |
| Hypothesis | Property-based, single-function | No | No | No |
| **VenomQA** | **Every reachable sequence** | **Yes** | **Yes** | **Yes** |

**Unlike Schemathesis**, which fuzzes individual endpoints for schema violations, VenomQA composes actions into sequences and checks behavioral invariants across the entire path.

**Unlike Postman/Newman**, you do not write the test sequences. VenomQA generates and explores them automatically using BFS/DFS over the state graph.

**Unlike Hypothesis**, VenomQA is not property-based testing of a single function. It tests multi-step API flows against rules that must hold after *every* step in *every* sequence.

**Where pytest stops, VenomQA begins.** Pytest tests the function. VenomQA tests what happens when real users call your API in real sequences.

---

## When VenomQA Catches What pytest Misses

```python
# Your pytest suite. All three tests pass.

def test_create_order():
    resp = client.post("/orders", json={"amount": 100})
    assert resp.status_code == 201  # ✓ passes

def test_refund_order():
    order = client.post("/orders", json={"amount": 100}).json()
    resp = client.post(f"/orders/{order['id']}/refund", json={"amount": 100})
    assert resp.status_code == 200  # ✓ passes

def test_double_refund_rejected():
    order = client.post("/orders", json={"amount": 100}).json()
    client.post(f"/orders/{order['id']}/refund", json={"amount": 100})
    resp = client.post(f"/orders/{order['id']}/refund", json={"amount": 100})
    assert resp.status_code == 400  # ✓ passes (fresh order each time)

# But in production, the sequence that matters is:
#   POST /orders           → 201  (order_id = "abc123")
#   POST /orders/abc123/refund → 200  (refund #1 — same order, not a fresh one)
#   POST /orders/abc123/refund → 200  ← BUG: double refund on the same order!

# VenomQA explores this exact sequence automatically.
# You do not need to think of it. It finds it.
```

---

## How It Works

```
  You define:                VenomQA does:
  ┌─────────────┐            ┌─────────────────────────────────────────────┐
  │  Actions    │            │                                             │
  │  (API calls)│──────────▶ │   S0 ──[create]──▶ S1 ──[update]──▶ S2   │
  │             │            │   │                  │                  │   │
  │  Invariants │            │   └──[list]──▶ S3   └──[delete]──▶ S4  │   │
  │  (rules that│──────────▶ │              ✓ OK    ✓ OK      ✗ FAIL! │   │
  │  must hold) │            │                                             │
  └─────────────┘            │  After every step: checks ALL invariants.   │
                             │  Between branches: rolls back the database. │
                             └─────────────────────────────────────────────┘
```

1. VenomQA starts at the initial state (empty database).
2. It tries every available action, checking all invariants after each one.
3. When a sequence branches (multiple next actions are possible from state S1), it **checkpoints the database**, explores one branch, **rolls back** to the checkpoint, then explores the next branch.
4. This continues BFS or DFS until every reachable sequence has been tested or `max_steps` is reached.
5. Any invariant failure is recorded with the **exact reproduction path**.

**Why database access is required:**

To explore `S1 → branch A` and then `S1 → branch B`, VenomQA must reset the database to exactly S1 before taking branch B. Without real rollback, you cannot branch — you can only run linear sequences. This is the fundamental difference from tools that mock the database.

---

## Quick Start

### Install

```bash
pip install venomqa
```

### Zero-Config Run (OpenAPI + Docker)

If you have `docker-compose.yml` and `openapi.yaml` in your project:

```bash
venomqa              # reads your stack, spins up isolated containers, explores
venomqa --api-key YOUR_KEY          # if API requires X-API-Key
venomqa --auth-token YOUR_TOKEN     # if API requires Bearer token
venomqa --basic-auth user:pass      # if API requires Basic auth
```

VenomQA will:
1. Parse your `openapi.yaml` → generate actions for all endpoints
2. Spin up isolated test containers (your production database is never touched)
3. Explore sequences, check for 5xx errors and schema violations
4. Report violations with exact reproduction paths

### 5-Minute Code Example

```python
from venomqa import Action, Agent, BFS, Invariant, Severity, World
from venomqa.adapters.http import HttpClient

api = HttpClient(base_url="http://localhost:8000")

# Actions: what your API can do
def create_order(api, context):
    resp = api.post("/orders", json={"amount": 100})
    resp.expect_status(201)
    context.set("order_id", resp.expect_json_field("id")["id"])
    return resp

def refund_order(api, context):
    order_id = context.get("order_id")
    if order_id is None:
        return api.post("/orders/none/refund")  # will fail cleanly — never skip
    return api.post(f"/orders/{order_id}/refund", json={"amount": 100})

def get_order(api, context):
    order_id = context.get("order_id")
    if order_id is None:
        return api.get("/orders/none")
    return api.get(f"/orders/{order_id}")

# Invariants: rules that must hold after every action in every sequence
def no_over_refund(world):
    resp = world.api.get("/orders")
    if resp.status_code != 200:
        return True  # don't flag list failures here — separate invariant
    return all(
        o.get("refunded_amount", 0) <= o.get("total", 0)
        for o in resp.json()
    )

def no_server_errors(world):
    return world.context.get("last_status", 200) < 500

# Wire it together
world = World(api=api, state_from_context=["order_id"])

agent = Agent(
    world=world,
    actions=[
        Action(name="create_order", execute=create_order),
        Action(name="refund_order", execute=refund_order),
        Action(name="get_order",    execute=get_order),
    ],
    invariants=[
        Invariant(name="no_over_refund",   check=no_over_refund,   severity=Severity.CRITICAL),
        Invariant(name="no_server_errors", check=no_server_errors, severity=Severity.HIGH),
    ],
    strategy=BFS(),   # BFS() takes no arguments
    max_steps=100,
)

result = agent.explore()   # NOT .run() — that method does not exist
print(f"States visited: {result.states_visited}")
print(f"Violations found: {len(result.violations)}")
for v in result.violations:
    print(f"  [{v.severity}] {v.invariant_name}: {v.message}")
```

---

## Real Bugs VenomQA Has Caught

These are patterns that appear repeatedly in real APIs. VenomQA finds all of them by exploring sequences automatically.

| Bug Pattern | Sequence That Triggers It |
|---|---|
| Double refund / double cancel | `create → refund → refund` |
| Stale data after delete | `create → delete → create → list` |
| Orphaned children after parent delete | `create_parent → create_child → delete_parent → list_children` |
| Auth bypass after role change | `login_as_admin → demote → call_admin_endpoint` |
| Race in create → update | `create → update(uninitialized_field)` |
| Resource leak on failed creation | `create(bad_data) → create(good_data) → list` |
| Quota not enforced across resources | `create_a → create_b → create_c → check_quota` |
| Idempotency key reuse | `create(key=X) → create(key=X) → list` |

---

## Configuration Reference

### World

```python
from venomqa import World
from venomqa.adapters.http import HttpClient
from venomqa.adapters.postgres import PostgresAdapter

# Option A: with a real database (enables true branching)
world = World(
    api=HttpClient("http://localhost:8000"),
    systems={"db": PostgresAdapter("postgresql://user:pass@localhost/mydb")},
)

# Option B: context-based (no DB access required, limited branching)
world = World(
    api=HttpClient("http://localhost:8000"),
    state_from_context=["order_id", "user_id", "order_count"],
)

# Option C: multiple systems
world = World(
    api=HttpClient("http://localhost:8000"),
    systems={
        "db":    PostgresAdapter("postgresql://localhost/mydb"),
        "cache": RedisAdapter("redis://localhost:6379"),
    },
)
```

`World` requires either `systems` or `state_from_context`. A bare `World(api=api)` raises `ValueError`.

### Action

```python
from venomqa import Action

Action(
    name="create_order",          # unique name, used in violation paths
    execute=create_order,         # callable (api, context) → response
    expected_status=[201],        # optional: auto-checks status code
    preconditions=["create_order"], # optional: actions that must have run first
)
```

Action functions receive `(api, context)` — in that order. They must return the response object. Returning `None` raises `TypeError`. Use preconditions to skip, not `return None`.

### Invariant

```python
from venomqa import Invariant, Severity

Invariant(
    name="no_over_refund",
    check=lambda world: ...,   # (world) → bool — True means OK
    severity=Severity.CRITICAL,  # CRITICAL, HIGH, MEDIUM, LOW
    message="Refunded amount cannot exceed order total",
)
```

Severity is the third positional argument (after `name` and `check`).

### Agent

```python
from venomqa import Agent, BFS

Agent(
    world=world,
    actions=[...],       # list of Action — NOT a World parameter
    invariants=[...],    # list of Invariant — NOT a World parameter
    strategy=BFS(),      # BFS() or DFS() — BFS() takes no arguments
    max_steps=200,       # stop after this many transitions
)

result = agent.explore()   # returns ExplorationResult
```

**ExplorationResult fields:**
- `result.states_visited` — number of unique states explored
- `result.transitions_taken` — number of action executions
- `result.violations` — list of Violation objects
- `result.duration_ms` — total runtime in milliseconds
- `result.truncated_by_max_steps` — True if stopped at max_steps

### Strategies

```python
BFS()   # breadth-first — finds shortest violation path (recommended)
DFS()   # depth-first — required when using PostgreSQL savepoints
```

### Response Helpers

```python
resp.expect_status(201)              # raises if not 201
resp.expect_status(200, 201, 204)    # raises if not any of these
resp.expect_success()                # raises if not 2xx/3xx
data = resp.expect_json()            # raises if not valid JSON
data = resp.expect_json_field("id")  # raises if "id" missing, returns dict
items = resp.expect_json_list()      # raises if not a JSON array
resp.status_code                     # returns 0 on network error (safe)
resp.headers                         # returns {} on network error (safe)
```

---

## Rollback Backends

VenomQA uses these mechanisms to restore database state between branches:

| System | Mechanism |
|---|---|
| PostgreSQL | `SAVEPOINT` / `ROLLBACK TO SAVEPOINT` — entire run is one uncommitted transaction |
| SQLite | Copy file / restore file |
| Redis | `DUMP` all keys → `FLUSHALL` → `RESTORE` |
| MockQueue, MockMail, MockStorage, MockTime | In-memory copy + restore |
| Custom HTTP services | Subclass `MockHTTPServer` (3-method interface) |

---

## From an OpenAPI Spec

```bash
# Generate actions from your spec and run immediately
venomqa scaffold openapi https://api.example.com/openapi.json \
  --base-url https://api.example.com \
  --output actions.py

python3 actions.py
```

Or in Python:

```python
from venomqa.v1.generators.openapi_actions import generate_actions

actions = generate_actions("openapi.yaml", base_url="http://localhost:8000")
# Returns list[Action] for every endpoint in the spec
```

---

## Reporters

```python
from venomqa.reporters.console import ConsoleReporter
from venomqa.reporters.html_trace import HTMLTraceReporter
from venomqa.reporters.json_reporter import JSONReporter
from venomqa.reporters.markdown import MarkdownReporter

# Console output (default — rich colored terminal)
ConsoleReporter().report(result)

# D3 force-graph of the full state space
html = HTMLTraceReporter().report(result)
open("trace.html", "w").write(html)

# Machine-readable output
json_str = JSONReporter(indent=2).report(result)
md_str   = MarkdownReporter().report(result)
```

All reporters return a string. `ConsoleReporter` also writes to stdout.

---

## Authentication

```python
from venomqa.v1.auth import BearerTokenAuth, ApiKeyAuth, MultiRoleAuth

# Bearer token
auth = BearerTokenAuth(token_fn=lambda ctx: "my-token")

# API key header
auth = ApiKeyAuth(key_fn=lambda ctx: "my-key", header="X-API-Key")

# Multiple roles (useful for testing permission boundaries)
auth = MultiRoleAuth(
    roles={"admin": admin_auth, "user": user_auth},
    default="user",
)

# Use in HttpClient
api = HttpClient("http://localhost:8000", auth=auth)
```

Token functions receive the current `Context` and can return dynamic tokens (e.g., from a login action stored in context). Return `None` to omit the header for that request.

---

## CLI Reference

```bash
venomqa                        # auto-run if docker-compose + openapi detected
venomqa demo                   # 30-second demo with a planted double-refund bug
venomqa init                   # create a new VenomQA project
venomqa init --with-sample     # create project with working example
venomqa doctor                 # system diagnostics (Docker, dependencies, auth)

# Authentication flags
venomqa --api-key KEY          # sets X-API-Key header
venomqa --auth-token TOKEN     # sets Authorization: Bearer TOKEN
venomqa --basic-auth user:pass # sets Authorization: Basic ...
venomqa --skip-preflight       # skip Docker and auth checks

# Environment variables (alternatives to flags)
export VENOMQA_API_KEY=your-key
export VENOMQA_AUTH_TOKEN=your-token
venomqa
```

---

## Working Example: Two Real Bugs

`examples/github_stripe_qa/` contains a complete working example with two deliberately planted bugs:

```bash
cd examples/github_stripe_qa
python3 main.py

# Bug 1: GitHub open-issues endpoint leaks closed issues  [CRITICAL]
#         Sequence: list_open_issues → filter_closed → compare_counts
#
# Bug 2: Stripe allows refund > original charge amount    [CRITICAL]
#         Sequence: create_charge → refund → refund
```

Both bugs are found automatically. No bug sequence was hand-written.

---

## FAQ

**Q: How is this different from Schemathesis?**

Schemathesis tests individual endpoints by fuzzing inputs — it sends random or schema-derived values and checks that your API doesn't crash or violate the OpenAPI contract. It tests *one call at a time*. VenomQA tests *sequences* of calls and checks behavioral rules (invariants) that span multiple steps. The tools are complementary: use Schemathesis for input validation, use VenomQA for stateful sequence bugs.

**Q: How is this different from property-based testing (Hypothesis)?**

Hypothesis generates random inputs to test a single function. VenomQA generates sequences of API calls to test stateful behavior across multiple endpoints. They operate at different levels and solve different problems.

**Q: Do I need a real database?**

For full branching exploration you need database access — PostgreSQL, SQLite, or another supported backend. Without it, VenomQA can still explore using `state_from_context`, which tracks state changes in the context dictionary. This is useful for stateless APIs or quick exploration, but cannot catch bugs that depend on actual database state.

**Q: Will this break my production database?**

No. VenomQA connects to your API's database and wraps the entire exploration in a single uncommitted transaction (PostgreSQL) or uses file copies (SQLite). Nothing is committed. Your production database is never involved — you should point VenomQA at a test/staging database.

**Q: How does it know what sequences to try?**

VenomQA performs BFS or DFS over the state graph. From any state, it tries every available action. If multiple actions are possible, it checkpoints the database and explores each branch, rolling back between them. The state is determined either by the database contents (with a systems adapter) or by context keys you specify.

**Q: What if my API requires authentication?**

Pass `auth=` to `HttpClient`, use `BearerTokenAuth`, `ApiKeyAuth`, or `MultiRoleAuth`. For token-based auth where the token comes from a login action, your token function can read the token from the exploration context: `token_fn=lambda ctx: ctx.get("auth_token")`. On the CLI, use `--auth-token` or `--api-key`.

**Q: Can I use this with any API framework?**

Yes. VenomQA talks to your API over HTTP — it doesn't care whether the API is Flask, FastAPI, Django, Express, Rails, Spring, or anything else. As long as it speaks HTTP and writes to a supported database, VenomQA can test it.

**Q: Can I run this in CI?**

Yes. `agent.explore()` returns an `ExplorationResult`. Exit non-zero if `result.violations` is non-empty. See `examples/github_stripe_qa/` for a working CI-ready example.

**Q: What's the difference between `BFS()` and `DFS()`?**

BFS (breadth-first) finds the *shortest* violation path — the minimum number of steps to reproduce a bug. DFS (depth-first) explores deeper paths first. When using PostgreSQL savepoints, use `DFS()` (PostgreSQL savepoints require linear execution). For in-memory or SQLite backends, `BFS()` is recommended.

---

## Development

```bash
git clone https://github.com/namanag97/venomqa
cd venomqa
pip install -e ".[dev]"

make test       # unit tests (421 tests)
make lint       # ruff
make typecheck  # mypy --strict
make ci         # lint + typecheck + coverage

# Run specific tests
pytest tests/v1/ --ignore=tests/v1/test_postgres.py
pytest tests/v1/ -k "test_name"
```

Test markers:
- `@pytest.mark.slow` — skipped by default
- `@pytest.mark.integration` — requires live services, skipped by default

---

## Docs

Full documentation: [namanag97.github.io/venomqa](https://namanag97.github.io/venomqa)

---

MIT License — built by [Naman Agarwal](https://github.com/namanag97)
