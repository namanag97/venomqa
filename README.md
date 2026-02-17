# VenomQA

**Autonomous QA agent that exhaustively explores APIs** — define actions and invariants, let VenomQA find every bug sequence your linear tests miss.

[![PyPI version](https://badge.fury.io/py/venomqa.svg)](https://pypi.org/project/venomqa/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://pypi.org/project/venomqa/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Install

```bash
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

# 1. Define actions
def create_todo(ctx, api):
    resp = api.post("/todos", json={"title": "Test"})
    ctx["todo_id"] = resp.json()["id"]
    return resp

def delete_todo(ctx, api):
    return api.delete(f"/todos/{ctx['todo_id']}")

def list_todos(ctx, api):
    resp = api.get("/todos")
    ctx["todos"] = resp.json()
    return resp

# 2. Define invariants (rules that must always be true)
def count_matches(state, ctx):
    api_count = len(ctx.get("todos", []))
    db_count = state.get_observation("db").data.get("count", 0)
    return api_count == db_count

invariant = Invariant(
    name="count_matches_db",
    check=count_matches,
    description="API list count must match DB",
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
| `Action` | A callable that mutates or reads API state |
| `Invariant` | A rule checked after every action |
| `World` | Sandbox that owns HTTP client + rollbackable systems (DB, Redis, queues) |
| `Agent` | Orchestrates exploration using a strategy (BFS, DFS, Random…) |
| `Violation` | A recorded invariant failure with severity + context |

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

agent = Agent(..., strategy=BFS())           # breadth-first (default, best for bug finding)
agent = Agent(..., strategy=DFS())           # depth-first
agent = Agent(..., strategy=CoverageGuided()) # maximize state coverage
```

---

## Reporters

```python
from venomqa.v1 import ConsoleReporter, HTMLTraceReporter, JSONReporter

reporter = ConsoleReporter()
reporter.report(result)

html = HTMLTraceReporter()
html.report(result, path="trace.html")   # D3 force-graph of the state space
```

---

## Working Example

`examples/github_stripe_qa/` contains a full multi-API example with two deliberately planted bugs that VenomQA catches automatically:

```bash
cd examples/github_stripe_qa
python main.py
```

---

## Development Setup

```bash
git clone https://github.com/namanagarwal/venomQA
cd venomQA
pip install -e ".[dev]"

make test          # all unit tests
make lint          # ruff
make typecheck     # mypy --strict
make ci            # lint + typecheck + coverage
```

---

## CLI

```bash
venomqa run        # run explorations
venomqa doctor     # system diagnostics
venomqa record     # record HTTP traffic → generate test code
venomqa --help
```

---

## License

MIT — built by [Naman Agarwal](https://github.com/namanagarwal)
