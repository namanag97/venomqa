# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## App Goal

VenomQA is an autonomous QA agent that explores APIs like an exhaustive human tester. Instead of writing linear test scripts, users define **Actions** (what can be done) and **Invariants** (what must always be true), and VenomQA explores every path through the application's state graph -- using DB savepoints/rollbacks to branch and reset state between paths.

## Commands

```bash
# Development setup
pip install -e ".[dev]"

# Testing
make test                        # All tests
make test-unit                   # Exclude integration/stress
make test-integration            # Integration only
make test-coverage               # With coverage (80% threshold)
pytest tests/ -k "test_name"     # Single test
pytest tests/ --run-slow         # Include slow tests
pytest tests/ --run-integration  # Include integration tests

# Code quality
make lint        # ruff check venomqa tests
make typecheck   # mypy venomqa --strict
make format      # black formatting
make ci          # lint + typecheck + test-coverage

# CLI
venomqa --help
venomqa run      # Run explorations
venomqa doctor   # System diagnostics
venomqa watch    # Auto-rerun on file changes
```

## Architecture

### Import Style

All imports use the top-level `venomqa` package:
```python
from venomqa import State, Action, World, Agent, Invariant, Journey, explore
from venomqa.adapters.http import HttpClient
from venomqa.adapters.postgres import PostgresAdapter
from venomqa.core.action import Action, ActionResult
```

### Module Map

| Module | Purpose |
|--------|---------|
| `core/` | `State`, `Action`, `ActionResult`, `Invariant`, `Violation`, `Graph`, `Transition` |
| `world/` | `World` sandbox with `checkpoint()` / `rollback()` orchestration |
| `agent/` | `Agent`, `Scheduler`, exploration strategies (BFS, DFS, Random, CoverageGuided, Weighted) |
| `dsl/` | `Journey`, `Step`, `Branch` DSL + `@action`/`@invariant` decorators + compiler |
| `adapters/` | `HttpClient`, `PostgresAdapter`, `RedisAdapter`, `MockQueue`, `MockMail`, etc. |
| `reporters/` | `ConsoleReporter`, `HTMLTraceReporter`, `JSONReporter`, `JUnitReporter`, `MarkdownReporter` |
| `generators/` | `generate_actions` from OpenAPI specs |
| `recording/` | `RequestRecorder`, `generate_journey_code` |
| `invariants/` | `OpenAPISchemaInvariant` |

### Legacy Components (backwards compatible)

| Module | Purpose |
|--------|---------|
| `explorer/engine.py` (69KB) | Core state-graph exploration algorithm |
| `core/models.py` | `Journey`, `Step`, `Branch`, `Checkpoint`, `Path`, `Issue` |
| `runner/` | `JourneyRunner` -- executes journeys, caches results |
| `state/` | Pluggable DB backends: `postgres`, `mysql`, `sqlite`, `memory` via factory |
| `ports/` | Abstract protocol interfaces (`DatabasePort`, `CachePort`, etc.) |
| `http/` | REST, GraphQL, gRPC, WebSocket clients |
| `cli/commands.py` (118KB) | All CLI subcommands |
| `security/` | Security-specific test checks |
| `preflight/` | Smoke tests before full exploration |
| `plugins/` | Plugin system via `venomqa.plugins` entry point |

### Internal Structure

The main API is implemented in `src/venomqa/v1/` and re-exported at the top level.
Internal v1 code uses `venomqa.v1.*` imports. External/user code should use `venomqa.*`.

### Rollback Mechanism

State exploration branches using per-system rollback:
- **PostgreSQL**: `SAVEPOINT` / `ROLLBACK TO SAVEPOINT` -- entire run is one uncommitted transaction
- **Redis**: `DUMP` all keys -> `FLUSHALL` + `RESTORE`
- **Queues/Mail**: in-memory copy + restore

### Test Markers

```python
@pytest.mark.slow         # skipped by default
@pytest.mark.integration  # skipped by default (needs live services)
@pytest.mark.stress
@pytest.mark.branching
@pytest.mark.concurrency
@pytest.mark.performance
```

### Configuration (`venomqa.yaml`)

```yaml
base_url: "http://localhost:3000"
timeout: 30
retry: {max_attempts: 3, delay: 1, backoff_multiplier: 2}
report: {formats: [html, json, junit], output_dir: "./reports"}
parallel_paths: 4
```

### Entry Points (Plugin System)

Registered in `pyproject.toml` -- extend via:
- `venomqa.state_backends` -- custom DB backends
- `venomqa.reporters` -- custom report formats
- `venomqa.plugins` -- lifecycle hooks
- `venomqa.adapters` -- injectable services

## Key Files for Orientation

- `venomqa/__init__.py` -- public API (clean, ~100 exports)
- `venomqa/v1/` -- internal implementation
- `venomqa/explorer/engine.py` -- core exploration loop
- `tests/v1/` -- best examples of usage
- `examples/` -- user-facing examples

## Tech Stack

- Python 3.10+, pydantic v2, httpx, click, rich
- pytest + pytest-asyncio (`asyncio_mode = "auto"`)
- mypy (strict), ruff (line-length 100), black
- psycopg3 for PostgreSQL
