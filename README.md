# VenomQA

**Autonomous QA agent that exhaustively explores APIs** — define actions and invariants, let VenomQA find every bug sequence your linear tests miss.

[![PyPI version](https://badge.fury.io/py/venomqa.svg)](https://pypi.org/project/venomqa/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://pypi.org/project/venomqa/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

![VenomQA demo](demo.gif)

---

## The Problem

Your unit tests check individual endpoints. Your integration tests check one happy path.
Neither catches bugs that only appear in a specific **sequence** of calls.

```
PUT /refund → 200   # fine alone
PUT /refund → 200   # fine again
GET /order  → 200   # refunded_amount > original_amount  ← BUG
```

VenomQA finds these. Automatically.

---

## How It Works

```
  You define:                VenomQA does:
  ┌─────────────┐            ┌─────────────────────────────────────────────┐
  │  Actions    │            │                                             │
  │  (API calls)│──────────▶ │   S0 ──[create]──▶ S1 ──[update]──▶ S2   │
  │             │            │   │                  │                  │   │
  │  Invariants │            │   └──[list]──▶ S3   └──[delete]──▶ S4  │   │
  │  (rules that│──────────▶ │              ✓OK    ✓OK        ✗FAIL!  │   │
  │  must hold) │            │                                             │
  └─────────────┘            │   After every step, checks ALL invariants.  │
                             │   Rolls back DB between branches.           │
                             └─────────────────────────────────────────────┘
```

**Schemathesis** tests endpoints one at a time with random inputs.
**VenomQA** tests *sequences* of endpoints — the bugs that only appear after `create → update → delete → create`.

---

## Why VenomQA Needs Database Access

VenomQA explores state graphs by **branching**:

```
State S0 ──[create_order]──▶ S1
   │                         │
   │                    [cancel_order]──▶ S2 (branch A)
   │                         │
   │                    [refund_order]──▶ S3 (branch B) ← BUG FOUND!
   │
   └──[list_orders]──▶ S4 (branch C)
```

To explore both branches A and B from state S1, VenomQA must:
1. Execute `create_order` → reach S1
2. Execute `cancel_order` → reach S2
3. **ROLLBACK database to S1** ← This is why you need DB access!
4. Execute `refund_order` → reach S3

**The database you connect must be the SAME one your API writes to.** VenomQA checkpoints and rolls back THAT database.

---

## Quickstart

```bash
pip install venomqa
```

### Step 1: Identify Your Database

**What database does your API use?**
- PostgreSQL → Use `PostgresAdapter` (most common)
- SQLite → Use `SQLiteAdapter`
- In-memory / No database → Use `state_from_context` (limited)

**CRITICAL**: Connect to the **exact same database** your API writes to:
- If your API uses `postgresql://prod:5432/myapp`, connect VenomQA to that same URL
- VenomQA wraps the entire exploration in a transaction and rolls back when done

### Step 2: Run Exploration

```python
import os
from venomqa.v1 import Action, Invariant, Agent, World, DFS, Severity
from venomqa.v1.adapters.http import HttpClient
from venomqa.v1.adapters.postgres import PostgresAdapter

# Connect to your API's database (same one the API writes to)
api = HttpClient("http://localhost:8000")
db = PostgresAdapter(os.environ["DATABASE_URL"])  # e.g. postgresql://user:pass@localhost/mydb

# 1. Define actions using expect_* helpers (cleanest pattern)
def create_order(api, context):
    resp = api.post("/orders", json={"product_id": 1, "qty": 2})
    resp.expect_status(201)                          # raises if not 201
    data = resp.expect_json_field("id", "total")     # raises if fields missing
    context.set("order_id", data["id"])
    context.set("order_total", data["total"])
    return resp

def refund_order(api, context):
    order_id = context.get("order_id")
    resp = api.post(f"/orders/{order_id}/refund", json={"amount": 100})
    resp.expect_status(200, 201)                     # 200 or 201
    return resp

def list_orders(api, context):
    resp = api.get("/orders")
    resp.expect_status(200)
    orders = resp.expect_json_list()                 # raises if not array
    context.set("orders", orders)
    return resp

# 2. Define invariants (rules that must always hold)
def no_over_refund(world):
    # GOOD: Make live API call to verify server state
    resp = world.api.get("/orders")
    if resp.status_code != 200:
        return False
    orders = resp.json()
    return all(o.get("refunded", 0) <= o.get("total", 0) for o in orders)

# 3. Explore every reachable sequence
agent = Agent(
    world=World(api=api, systems={"db": db}),  # ← REQUIRED: database adapter
    actions=[
        Action(name="create_order", execute=create_order, expected_status=[201]),
        Action(name="refund_order", execute=refund_order, preconditions=["create_order"]),
        Action(name="list_orders",  execute=list_orders,  expected_status=[200]),
    ],
    invariants=[
        Invariant(name="no_over_refund", check=no_over_refund,
                  message="Refunded amount cannot exceed order total",
                  severity=Severity.CRITICAL),
    ],
    strategy=DFS(),  # ← Use DFS with PostgreSQL
    max_steps=200,
)

result = agent.explore()
# States: 12, Violations: 1
# [CRITICAL] no_over_refund: Refunded amount cannot exceed order total
#   Reproduction path: create_order → refund_order → refund_order → list_orders
```

### No Database? Context-Based Mode

If your API is stateless or you can't access the database:

```python
# Context-based exploration - VenomQA tracks these keys to distinguish states
world = World(
    api=api,
    state_from_context=["order_id", "order_count", "user_id"],
)
```

---

## Validation Helpers

Use `expect_*` helpers in actions — VenomQA catches AssertionError as violations:

```python
resp.expect_status(201)              # raises if not 201
resp.expect_status(200, 201, 204)    # raises if not any of these
resp.expect_success()                # raises if not 2xx/3xx
data = resp.expect_json()            # raises if not JSON
data = resp.expect_json_field("id")  # raises if "id" missing, returns dict
items = resp.expect_json_list()      # raises if not array
resp.status_code                     # returns 0 on network error (safe)
resp.headers                         # returns {} on network error (safe)
```

---

## From OpenAPI Spec

```bash
# Generate actions from your spec, run immediately
venomqa scaffold openapi https://api.example.com/openapi.json \
  --base-url https://api.example.com \
  --output actions.py

python3 actions.py
# Runs BFS over all 19 endpoints, reports violations
```

---

## State Graph Exploration

```
                     ┌─── S0 (initial) ───┐
                     │                    │
                [create]              [list]
                     │                    │
                     ▼                    ▼
                    S1                   S2
                   /   \               (pass)
              [update] [delete]
                 /         \
                S3           S4
              (pass)      [✗ VIOLATION]
                          Invariant failed:
                          "delete then create
                           returns stale state"
```

VenomQA checkpoints the DB before each branch and rolls back after, so every path starts from a clean slate. No test pollution between branches.

---

## Core Concepts

| Concept | What it is |
|---------|-----------|
| `Action` | A callable `(api, context) → response` — one API call |
| `Invariant` | A rule `(world) → bool` checked after every action |
| `World` | Sandbox: HTTP client + rollbackable systems + shared context |
| `Agent` | Orchestrates BFS/DFS exploration, handles checkpoints |
| `Context` | Key-value store across actions — `context.set()` / `context.get()` |
| `Violation` | Recorded invariant failure with severity + exact reproduction path |

---

## Rollback Backends

| System | Mechanism |
|--------|-----------|
| PostgreSQL | `SAVEPOINT` / `ROLLBACK TO SAVEPOINT` — entire run is one transaction |
| Redis | `DUMP` + `FLUSHALL` + `RESTORE` — full key restore |
| In-memory (queue, mail, storage) | Copy + restore |
| Custom HTTP | Subclass `MockHTTPServer` (3-method interface) |

```python
world = World(
    api=HttpClient("http://localhost:8000"),
    systems={
        "db":    PostgresAdapter("postgresql://localhost/mydb"),
        "cache": RedisAdapter("redis://localhost:6379"),
    },
)
```

---

## Reporters

```python
from venomqa.v1.reporters.console import ConsoleReporter
from venomqa.v1.reporters.html_trace import HTMLTraceReporter

ConsoleReporter().report(result)           # colored terminal output

html = HTMLTraceReporter().report(result)  # D3 force-graph of the state space
open("trace.html", "w").write(html)
```

---

## Working Example

`examples/github_stripe_qa/` — two deliberately planted bugs that VenomQA catches automatically:

```bash
cd examples/github_stripe_qa && python3 main.py
# Bug 1: GitHub open-issues endpoint leaks closed issues  [CRITICAL]
# Bug 2: Stripe allows refund > original charge amount    [CRITICAL]
```

---

## CLI

```bash
venomqa scaffold openapi <spec>    # generate actions from OpenAPI spec
venomqa explore journey.py         # run stateful BFS exploration
venomqa validate journey.py        # check journey syntax
venomqa record journey.py          # record HTTP traffic → generate skeleton
venomqa replay report.json         # replay a violation's reproduction path
venomqa doctor                     # system diagnostics
venomqa llm-docs                   # print LLM context doc (paste into Claude/ChatGPT)
```

---

## Development

```bash
git clone https://github.com/namanag97/venomqa
cd venomqa
pip install -e ".[dev]"

make test       # all unit tests
make lint       # ruff
make typecheck  # mypy --strict
make ci         # lint + typecheck + coverage
```

---

## Docs

[namanag97.github.io/venomqa](https://namanag97.github.io/venomqa)

---

MIT — built by [Naman Agarwal](https://github.com/namanag97)
