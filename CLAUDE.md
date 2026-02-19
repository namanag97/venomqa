# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## App Goal

VenomQA is an autonomous QA agent that explores APIs like an exhaustive human tester. Instead of writing linear test scripts, users define **Actions** (what can be done) and **Invariants** (what must always be true), and VenomQA explores every path through the application's state graph — using DB savepoints/rollbacks to branch and reset state between paths.

**Key insight**: Unit tests check endpoints one at a time. VenomQA tests *sequences* like `create → refund → refund` to find bugs that only appear in specific orderings.

## Quick Start (for new users)

```bash
pip install venomqa
venomqa              # Shows friendly intro
venomqa demo         # See it find a bug in 30 seconds
venomqa init --with-sample  # Set up a project
```

## Development Commands

```bash
# Setup
pip install -e ".[dev]"

# Testing
pytest tests/v1/ --ignore=tests/v1/test_postgres.py  # Unit tests (421 tests)
pytest tests/v1/ -k "test_name"                       # Single test
make test                                             # All tests
make ci                                               # lint + typecheck + test

# Code quality
ruff check src/ tests/    # Linting
make typecheck            # mypy

# CLI
venomqa --help
venomqa demo              # Demo with planted bug
venomqa doctor            # System diagnostics
venomqa init              # Create project

# Authentication (for APIs requiring auth)
venomqa --api-key KEY           # X-API-Key header
venomqa --auth-token TOKEN      # Bearer token
venomqa --basic-auth user:pass  # Basic auth
venomqa --skip-preflight        # Skip Docker/auth checks

# Or use environment variables
export VENOMQA_API_KEY=your-key
export VENOMQA_AUTH_TOKEN=your-token
```

## Architecture

### Import Style

All imports use the top-level `venomqa` package:
```python
from venomqa import Action, Invariant, Agent, World, BFS, Severity
from venomqa.adapters.http import HttpClient
from venomqa.adapters.postgres import PostgresAdapter
```

### Core Concepts

| Concept | Description |
|---------|-------------|
| `Action` | Callable `(api, context) -> response` — one API operation |
| `Invariant` | Rule `(world) -> bool` checked after every action |
| `World` | Sandbox: `World(api=api, state_from_context=[...])` or `World(api=api, systems={'db': adapter})` |
| `Agent` | `Agent(world, actions=[...], invariants=[...], strategy=BFS(), max_steps=N)` |
| `Context` | Key-value store: `context.set()` / `context.get()` |

**Critical API rules (verified against installed package):**
- `World` takes `api` + either `state_from_context=[...]` OR `systems={'db': adapter}` — bare `World(api=api)` raises `ValueError`
- `actions` and `invariants` are `Agent` parameters, **not** `World` parameters
- `BFS()` takes **no arguments** — control depth via `Agent(max_steps=N)`
- Run exploration with `agent.explore()` — **not** `agent.run()` (does not exist)

### Module Map

| Module | Purpose |
|--------|---------|
| `src/venomqa/v1/core/` | `Action`, `ActionResult`, `Invariant`, `Violation`, `State`, `Graph` |
| `src/venomqa/v1/world/` | `World` sandbox with `checkpoint()` / `rollback()` |
| `src/venomqa/v1/agent/` | `Agent`, strategies (BFS, DFS, CoverageGuided) |
| `src/venomqa/v1/adapters/` | `HttpClient`, `PostgresAdapter`, `SQLiteAdapter`, `ResourceGraph` |
| `src/venomqa/v1/reporters/` | `ConsoleReporter`, `HTMLTraceReporter`, `JSONReporter` |
| `src/venomqa/v1/generators/` | `generate_actions` from OpenAPI specs |
| `src/venomqa/cli/` | CLI commands including `demo`, `init`, `doctor` |

### Rollback Mechanism

State exploration branches using per-system rollback:
- **PostgreSQL**: `SAVEPOINT` / `ROLLBACK TO SAVEPOINT` — entire run is one uncommitted transaction
- **SQLite**: Copy file / restore
- **Redis**: `DUMP` all keys -> `FLUSHALL` + `RESTORE`
- **Mock systems**: In-memory copy + restore

### Test Markers

```python
@pytest.mark.slow         # skipped by default
@pytest.mark.integration  # skipped by default (needs live services)
```

## Key Files

| File | Purpose |
|------|---------|
| `src/venomqa/__init__.py` | Public API (~100 exports) |
| `src/venomqa/v1/agent/__init__.py` | Agent exploration engine |
| `src/venomqa/cli/demo.py` | Demo command with planted bug |
| `src/venomqa/cli/commands.py` | All CLI commands |
| `tests/v1/` | Unit tests (best usage examples) |
| `examples/github_stripe_qa/` | Full working example with 2 bugs |

## Tech Stack

- Python 3.10+, pydantic v2, httpx, click, rich
- pytest + pytest-asyncio
- mypy (strict), ruff
- psycopg3 for PostgreSQL
