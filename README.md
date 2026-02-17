# VenomQA

**Autonomous QA agent that exhaustively explores APIs** — define actions and invariants, let VenomQA find every bug sequence your linear tests miss.

[![PyPI version](https://badge.fury.io/py/venomqa.svg)](https://pypi.org/project/venomqa/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://pypi.org/project/venomqa/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install venomqa
```

---

## How It Works

Instead of writing linear test scripts, you give VenomQA:

1. **Actions** — things that can happen (create issue, close issue, create refund…)
2. **Invariants** — rules that must always hold (open issues never contain closed ones, refund ≤ payment)

VenomQA explores every reachable state sequence using BFS, checkpointing and rolling back state between branches so each path starts clean.

---

## Quickstart (v1 API)

```python
from venomqa.v1 import Action, Invariant, Agent, World, BFS, Severity
from venomqa.v1.adapters.http import HttpClient

# 1. Define actions — signature is always (api, context)
def create_todo(api, context):
    resp = api.post("/todos", json={"title": "Test"})
    context.set("todo_id", resp.json()["id"])
    return resp

def delete_todo(api, context):
    return api.delete(f"/todos/{context.get('todo_id')}")

def list_todos(api, context):
    resp = api.get("/todos")
    context.set("todos", resp.json())
    return resp

# 2. Define invariants — check() receives the World object
def count_is_non_negative(world):
    todos = world.context.get("todos") or []
    return len(todos) >= 0

invariant = Invariant(
    name="count_non_negative",
    check=count_is_non_negative,
    message="Todo count must never be negative",
    severity=Severity.CRITICAL,
)

# 3. Explore
api = HttpClient("http://localhost:8000")
world = World(api=api)

agent = Agent(
    world=world,
    actions=[
        Action(name="create_todo", execute=create_todo),
        Action(name="delete_todo", execute=delete_todo),
        Action(name="list_todos",  execute=list_todos),
    ],
    invariants=[invariant],
    strategy=BFS(),
    max_steps=200,
)

result = agent.explore()
print(f"States: {result.states_visited}, Violations: {len(result.violations)}")
for v in result.violations:
    print(f"  [{v.severity.value.upper()}] {v.invariant_name}: {v.message}")
```

---

## Core Concepts

| Concept | What it is |
|---------|-----------|
| `Action` | A callable `(api, context) -> response` that mutates or reads API state |
| `Invariant` | A rule `(world) -> bool` checked after every action |
| `World` | Sandbox owning the HTTP client + rollbackable systems + shared context |
| `Agent` | Orchestrates exploration using a strategy (BFS, DFS, Random…) |
| `Context` | Key-value store shared across actions — use `.set()` / `.get()` |
| `Violation` | A recorded invariant failure with severity + reproduction path |

---

## Action Signatures

Actions always receive `(api, context)` in that order:

```python
# Minimal — no context needed
def health_check(api, context):
    return api.get("/health")

# Read from context (set by a previous action)
def get_item(api, context):
    item_id = context.get("item_id")
    return api.get(f"/items/{item_id}")

# Write to context for downstream actions
def create_item(api, context):
    resp = api.post("/items", json={"name": "Test"})
    context.set("item_id", resp.json()["id"])
    return resp
```

> **Note:** `context` is a `Context` object, not a dict. Use `context.set(key, val)` and `context.get(key)` — not `context[key]`.

---

## Invariant Signatures

Invariants receive a single `World` argument:

```python
# Access shared context
def ids_are_set(world):
    return world.context.has("user_id") and world.context.has("item_id")

# Access the API client directly
def api_is_reachable(world):
    resp = world.api.get("/health")
    return resp.status_code == 200

invariant = Invariant(
    name="ids_set",
    check=ids_are_set,
    message="user_id and item_id must be set",   # 'message', not 'description'
    severity=Severity.HIGH,
)
```

> **Note:** The field is `message=`, not `description=`.

---

## Rollback / Branching

VenomQA checkpoints and rolls back state between paths. Adapters that support rollback:

| System | Mechanism |
|--------|-----------|
| PostgreSQL | `SAVEPOINT` / `ROLLBACK TO SAVEPOINT` |
| Redis | `DUMP` + `FLUSHALL` + `RESTORE` |
| In-memory (queue, mail, storage) | Copy + restore |
| Custom | Subclass `MockHTTPServer` (3-method interface) |

```python
from venomqa.v1.adapters.postgres import PostgresAdapter
from venomqa.v1.adapters.redis import RedisAdapter

world = World(
    api=HttpClient("http://localhost:8000"),
    systems={
        "db":    PostgresAdapter("postgresql://localhost/mydb"),
        "cache": RedisAdapter("redis://localhost:6379"),
    },
)
```

---

## Exploration Strategies

```python
from venomqa.v1 import BFS, DFS, Random, CoverageGuided, Weighted

agent = Agent(..., strategy=BFS())            # breadth-first (default, best for bug finding)
agent = Agent(..., strategy=DFS())            # depth-first
agent = Agent(..., strategy=CoverageGuided()) # maximize state coverage
```

---

## Reporters

```python
from venomqa.v1 import ConsoleReporter, HTMLTraceReporter, JSONReporter

# Console output
ConsoleReporter().report(result)

# HTML — report() returns a string, write it yourself
html = HTMLTraceReporter()
with open("trace.html", "w") as f:
    f.write(html.report(result))   # D3 force-graph of the state space
```

---

## Working Example

`examples/github_stripe_qa/` contains a full multi-API example with two deliberately planted bugs that VenomQA catches automatically:

```bash
cd examples/github_stripe_qa
python3 main.py
```

---

## Development Setup

```bash
git clone https://github.com/namanag97/venomqa
cd venomqa
pip install -e ".[dev]"

make test          # all unit tests
make lint          # ruff
make typecheck     # mypy --strict
make ci            # lint + typecheck + coverage
```

---

## CLI

```bash
# V1 stateful exploration (recommended)
venomqa explore journey.py --base-url http://localhost:8000   # run exploration
venomqa validate journey.py                                   # check journey syntax
venomqa record   journey.py --base-url http://localhost:8000  # record + generate skeleton

# General
venomqa run        # run V0 journeys
venomqa doctor     # system diagnostics
venomqa llm-docs   # print LLM context document (paste into any AI assistant)
venomqa --help
```

---

## Using with an AI Assistant

Run `venomqa llm-docs` to get a complete context document you can paste into ChatGPT, Claude, Cursor, or any AI assistant. It includes all correct API signatures, patterns, and examples so the AI can help you write VenomQA tests accurately.

---

## License

MIT — built by [Naman Agarwal](https://github.com/namanag97)
