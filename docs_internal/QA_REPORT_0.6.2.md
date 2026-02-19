# VenomQA 0.6.2 — First-Time User QA Report
**Date:** 2026-02-19
**Version tested:** `venomqa==0.6.2` (installed from PyPI, clean virtualenv)
**Method:** Full install from PyPI in `/tmp/venomqa-qa-test/`, zero project code used

---

## Executive Summary

| Category | Result |
|---|---|
| PyPI install | PASS |
| Package imports (118 exports) | PASS |
| CLI entry points (7 commands) | PASS |
| `venomqa demo` (flagship) | PASS |
| `venomqa init --with-sample` | PASS |
| `venomqa doctor` | PASS |
| Core API (write + run a test) | **FAIL** — 4 doc bugs, all in CLAUDE.md |
| `venomqa` no-args onboarding | PARTIAL — context-aware, not a standalone intro |

**Overall:** The installed package is functional. The demo, CLI, and scaffolding all work. All 118 public exports load cleanly. The broken 0.6.1 import crash is fixed. However, **the CLAUDE.md quick-start code examples are completely wrong** — a developer following them would fail immediately.

---

## Test Results

### ✅ T1 — PyPI install
```
pip install venomqa  →  venomqa-0.6.2 installed
python3 -c "import venomqa; print(venomqa.__version__)"  →  0.6.2
```

### ✅ T2 — All 118 public exports present
```python
missing = [n for n in venomqa.__all__ if not hasattr(venomqa, n)]
# → []
```
No missing symbols. The 0.6.1 `SchemaValidatorclaude` crash is confirmed fixed.

### ✅ T3 — CLI `--help`
All 7 subcommands present and responsive:
```
✓ venomqa demo
✓ venomqa init
✓ venomqa doctor
✓ venomqa generate
✓ venomqa generate-graphql
✓ venomqa record
✓ venomqa llm-docs
```

### ✅ T4 — `venomqa demo`
Demo ran end-to-end: started mock Order API, ran unit tests (all pass), then found the planted double-refund bug via BFS sequence exploration.
```
CRITICAL VIOLATION: create_order → refund → refund
Order amount: $100 — Refunded: $200 (exceeds order!)
```
Core engine is working correctly.

### ✅ T5 — `venomqa doctor`
Correctly identifies present and missing dependencies. No false positives.
```
OK  Python 3.13.5
OK  httpx, pydantic, rich, click, pyyaml
OK  v1 module ready
OK  Docker, Docker Compose, psycopg3
--  DATABASE_URL not set (expected)
--  PostgreSQL not reachable (expected)
--  redis-py not installed (optional)
```

### ✅ T6 — `venomqa init --with-sample`
Scaffolds correctly:
```
venomqa/actions/sample_actions.py
venomqa/actions/__init__.py
venomqa/journeys/sample_journey.py
venomqa/journeys/__init__.py
venomqa/venomqa.yaml
venomqa/docker-compose.qa.yml
venomqa/llm-context.md
venomqa/README.md
venomqa/.env.example
```

### ✅ T7 — `venomqa generate-graphql`
Shows graceful "not yet available" message instead of crashing. Fixed in 0.6.2.

### ⚠️ T8 — `venomqa` (no args)
**Behavior:** Detects project context and shows context-aware guidance.
In a directory with `docker-compose.yml` but no `openapi.yaml`:
```
✓ Found docker-compose.yml
✗ Missing openapi.yaml
Next:  venomqa init --with-sample
```
In a completely empty directory: shows a rich intro panel (correct).
**Assessment:** Acceptable behavior — not broken, but the guidance panel is minimal. Not blocking.

### ❌ T9 — Core API (write and run a test)
A developer following the CLAUDE.md quick-start would write this and **fail with 4 separate errors**:

```python
# CLAUDE.md example — DOES NOT WORK
world = World(actions=[action], invariants=[inv])   # ❌ Wrong constructor
agent = Agent(world=world, strategy=BFS(max_depth=3))  # ❌ Wrong BFS args
result = agent.run()  # ❌ Method doesn't exist
```

All four errors documented below.

---

## Bugs Found

### BUG-1 — CRITICAL: `agent.run()` does not exist
**File:** `CLAUDE.md`, `src/venomqa/v1/agent/__init__.py`
**Impact:** Any developer following the docs gets `AttributeError: 'Agent' object has no attribute 'run'`
**Fix:** Method is `agent.explore()` — always has been.

```python
# Wrong (in CLAUDE.md):
result = agent.run()

# Correct:
result = agent.explore()
```

### BUG-2 — CRITICAL: `World` does not accept `actions` or `invariants`
**File:** `CLAUDE.md` concept table
**Impact:** `TypeError: World.__init__() got an unexpected keyword argument 'actions'`
**Fix:** `actions` and `invariants` are `Agent` parameters, not `World`.

```python
# Wrong:
world = World(actions=[...], invariants=[...])

# Correct:
world = World(api=api, state_from_context=['key'])
agent = Agent(world=world, actions=[...], invariants=[...])
```

### BUG-3 — CRITICAL: `World(api=api)` alone raises `ValueError`
**Impact:** A bare `World(api=api)` with no `systems` or `state_from_context` raises:
```
ValueError: No database/systems registered in World.
VenomQA needs a rollbackable system to explore state graphs.
```
The minimal working form for context-only state is:
```python
world = World(api=api, state_from_context=['my_key'])
```

### BUG-4 — CRITICAL: `BFS(max_depth=3)` raises `TypeError`
**Impact:** `TypeError: BFS.__init__() got an unexpected keyword argument 'max_depth'`
**Fix:** `BFS()` takes no arguments. Depth is controlled via `Agent(max_steps=N)`.

```python
# Wrong:
strategy=BFS(max_depth=3)

# Correct:
agent = Agent(world=world, actions=[...], strategy=BFS(), max_steps=30)
```

---

## Correct Minimal API (verified working)

```python
from venomqa import Action, Agent, BFS, Invariant, Severity, World
from venomqa.adapters.http import HttpClient

# 1. Actions: callable (api, context) -> response
def create_item(api, context):
    resp = api.post("/items", json={"name": "test"})
    context.set("item_id", resp.json()["id"])
    return resp

# 2. Invariants: callable (world) -> bool
never_500 = Invariant(
    name="no_server_errors",
    check=lambda world: True,  # check world.context, world.last_response, etc.
    severity=Severity.CRITICAL,
)

# 3. World — needs state_from_context OR a systems adapter
api = HttpClient(base_url="http://localhost:8000")
world = World(api=api, state_from_context=["item_id"])

# 4. Agent — actions and invariants go HERE, not on World
agent = Agent(
    world=world,
    actions=[Action(name="create_item", execute=create_item)],
    invariants=[never_500],
    strategy=BFS(),
    max_steps=50,
)

# 5. Run — method is .explore(), not .run()
result = agent.explore()
print(f"States: {result.states_visited}, Violations: {result.violations}")
```

---

## Root Cause of Doc Bugs

All 4 bugs trace to a single stale CLAUDE.md concept table that was never updated when the API evolved. The `llm-docs` command output is **correct** — it uses `agent.explore()` and the right constructor signatures. Only CLAUDE.md is wrong.

---

## Fixes Applied

- [x] `CLAUDE.md` — corrected all 4 API examples
- [x] `MEMORY.md` — updated `agent.run()` → `agent.explore()`, added `state_from_context` requirement
- [x] `tests/v1/test_public_api.py` — added `test_core_api_works()` that actually runs `agent.explore()` so this class of regression is caught by CI
