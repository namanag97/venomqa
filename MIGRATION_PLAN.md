# VenomQA v1 Migration Plan

## Overview

Migrate from current sprawling architecture (~100 files, 300+ exports) to clean v1 architecture (~25 files, 18 exports).

**Core Principle**: Build v1 alongside existing code. No breaking changes until v1 is proven.

---

## Phase 1: Core Foundation (Week 1)

Build the fundamental data objects and protocols.

### 1.1 Directory Structure

```
venomqa/
└── v1/
    ├── __init__.py
    ├── core/
    │   ├── __init__.py
    │   ├── state.py
    │   ├── action.py
    │   ├── transition.py
    │   ├── graph.py
    │   ├── invariant.py
    │   └── result.py
    ├── world/
    │   ├── __init__.py
    │   ├── rollbackable.py
    │   └── checkpoint.py
    └── agent/
        ├── __init__.py
        └── strategies.py
```

### 1.2 Tasks

| ID | Task | File | Dependencies |
|----|------|------|--------------|
| 1.1 | Create v1 directory structure | - | - |
| 1.2 | Implement State, Observation | `core/state.py` | 1.1 |
| 1.3 | Implement Action, ActionResult | `core/action.py` | 1.1 |
| 1.4 | Implement Transition | `core/transition.py` | 1.2, 1.3 |
| 1.5 | Implement Graph | `core/graph.py` | 1.2, 1.3, 1.4 |
| 1.6 | Implement Invariant, Violation, Severity | `core/invariant.py` | 1.2 |
| 1.7 | Implement ExplorationResult | `core/result.py` | 1.5, 1.6 |
| 1.8 | Implement Rollbackable protocol | `world/rollbackable.py` | 1.2 |
| 1.9 | Implement Checkpoint, SystemCheckpoint | `world/checkpoint.py` | 1.8 |
| 1.10 | Implement World class | `world/__init__.py` | 1.8, 1.9 |
| 1.11 | Implement Strategy protocol | `agent/strategies.py` | 1.5 |
| 1.12 | Implement Agent class | `agent/__init__.py` | 1.10, 1.5, 1.6, 1.11 |
| 1.13 | Write unit tests for core | `tests/v1/test_core.py` | 1.2-1.7 |
| 1.14 | Write unit tests for world | `tests/v1/test_world.py` | 1.8-1.10 |
| 1.15 | Write unit tests for agent | `tests/v1/test_agent.py` | 1.11-1.12 |

### 1.3 Deliverable

```python
from venomqa.v1 import State, Action, Graph, World, Agent, Invariant
# All core objects work in isolation
```

---

## Phase 2: Adapters (Week 2)

Implement Rollbackable adapters for each system type.

### 2.1 Directory Structure

```
venomqa/v1/
└── adapters/
    ├── __init__.py
    ├── http.py
    ├── postgres.py
    ├── mysql.py
    ├── sqlite.py
    ├── redis.py
    ├── mock_queue.py
    ├── mock_mail.py
    ├── mock_storage.py
    ├── mock_time.py
    └── wiremock.py
```

### 2.2 Tasks

| ID | Task | File | Dependencies |
|----|------|------|--------------|
| 2.1 | Implement HttpClient | `adapters/http.py` | 1.3 |
| 2.2 | Implement PostgresAdapter with savepoints | `adapters/postgres.py` | 1.8 |
| 2.3 | Implement MySQLAdapter with savepoints | `adapters/mysql.py` | 1.8 |
| 2.4 | Implement SQLiteAdapter with file copy | `adapters/sqlite.py` | 1.8 |
| 2.5 | Implement RedisAdapter with dump/restore | `adapters/redis.py` | 1.8 |
| 2.6 | Implement MockQueue | `adapters/mock_queue.py` | 1.8 |
| 2.7 | Implement MockMail | `adapters/mock_mail.py` | 1.8 |
| 2.8 | Implement MockStorage | `adapters/mock_storage.py` | 1.8 |
| 2.9 | Implement MockTime | `adapters/mock_time.py` | 1.8 |
| 2.10 | Implement WireMockAdapter | `adapters/wiremock.py` | 1.8 |
| 2.11 | Write integration tests for PostgresAdapter | `tests/v1/test_postgres.py` | 2.2 |
| 2.12 | Write integration tests for RedisAdapter | `tests/v1/test_redis.py` | 2.5 |
| 2.13 | Write unit tests for mock adapters | `tests/v1/test_mocks.py` | 2.6-2.9 |

### 2.3 Deliverable

```python
from venomqa.v1.adapters import (
    HttpClient, PostgresAdapter, RedisAdapter,
    MockQueue, MockMail, MockStorage, MockTime,
)
# All adapters implement Rollbackable and pass tests
```

---

## Phase 3: Integration (Week 3)

Connect everything: World + Adapters + Agent working together.

### 3.1 Tasks

| ID | Task | File | Dependencies |
|----|------|------|--------------|
| 3.1 | World integration with adapters | `world/__init__.py` | 2.1-2.10 |
| 3.2 | Agent exploration loop complete | `agent/__init__.py` | 3.1 |
| 3.3 | BFS strategy implementation | `agent/strategies.py` | 1.11 |
| 3.4 | DFS strategy implementation | `agent/strategies.py` | 1.11 |
| 3.5 | Random strategy implementation | `agent/strategies.py` | 1.11 |
| 3.6 | End-to-end test: simple exploration | `tests/v1/test_e2e.py` | 3.1-3.3 |
| 3.7 | End-to-end test: with rollback | `tests/v1/test_e2e.py` | 3.6 |
| 3.8 | End-to-end test: invariant violation | `tests/v1/test_e2e.py` | 3.6 |
| 3.9 | Convenience function: explore() | `v1/__init__.py` | 3.2 |

### 3.2 Deliverable

```python
from venomqa.v1 import World, Agent, Action, Invariant, explore

world = World(api=HttpClient(...), systems={"db": PostgresAdapter(...)})
agent = Agent(world, actions, invariants)
result = agent.explore()  # Full exploration works!
```

---

## Phase 4: DSL Layer (Week 4)

Implement the Journey DSL that compiles to core objects.

### 4.1 Directory Structure

```
venomqa/v1/
└── dsl/
    ├── __init__.py
    ├── journey.py
    ├── compiler.py
    └── decorators.py
```

### 4.2 Tasks

| ID | Task | File | Dependencies |
|----|------|------|--------------|
| 4.1 | Implement Journey, Step, Checkpoint | `dsl/journey.py` | 1.3, 1.6 |
| 4.2 | Implement Branch, Path | `dsl/journey.py` | 4.1 |
| 4.3 | Implement compile() function | `dsl/compiler.py` | 4.1, 4.2, 1.5 |
| 4.4 | Implement @action decorator | `dsl/decorators.py` | 1.3 |
| 4.5 | Implement @invariant decorator | `dsl/decorators.py` | 1.6 |
| 4.6 | Unit tests for Journey objects | `tests/v1/test_dsl.py` | 4.1-4.2 |
| 4.7 | Unit tests for compiler | `tests/v1/test_compiler.py` | 4.3 |
| 4.8 | Integration: Journey → explore | `tests/v1/test_journey_e2e.py` | 4.3, 3.9 |

### 4.3 Deliverable

```python
from venomqa.v1 import Journey, Step, Checkpoint, Branch, Path, explore

journey = Journey(
    name="test",
    steps=[
        Step("login", login_action),
        Checkpoint("logged_in"),
        Branch(from_checkpoint="logged_in", paths=[...]),
    ],
)

result = explore("http://localhost:8000", journey, db_url="postgres://...")
```

---

## Phase 5: Reporters (Week 5)

Implement output formats for exploration results.

### 5.1 Directory Structure

```
venomqa/v1/
└── reporters/
    ├── __init__.py
    ├── console.py
    ├── markdown.py
    ├── json.py
    └── junit.py
```

### 5.2 Tasks

| ID | Task | File | Dependencies |
|----|------|------|--------------|
| 5.1 | Implement ConsoleReporter | `reporters/console.py` | 1.7 |
| 5.2 | Implement MarkdownReporter | `reporters/markdown.py` | 1.7 |
| 5.3 | Implement JSONReporter | `reporters/json.py` | 1.7 |
| 5.4 | Implement JUnitReporter | `reporters/junit.py` | 1.7 |
| 5.5 | Reporter tests | `tests/v1/test_reporters.py` | 5.1-5.4 |

---

## Phase 6: CLI (Week 5)

Update CLI to use v1.

### 6.1 Tasks

| ID | Task | File | Dependencies |
|----|------|------|--------------|
| 6.1 | Create v1 CLI commands | `v1/cli/main.py` | 3.9, 5.1-5.4 |
| 6.2 | `venomqa explore` command | `v1/cli/main.py` | 6.1 |
| 6.3 | `venomqa validate` command | `v1/cli/main.py` | 6.1 |
| 6.4 | CLI tests | `tests/v1/test_cli.py` | 6.1-6.3 |

---

## Phase 7: Bridge Layer (Week 6)

Allow gradual migration from old to new.

### 7.1 Tasks

| ID | Task | File | Dependencies |
|----|------|------|--------------|
| 7.1 | StateManager → Rollbackable adapter | `v1/bridge/state_manager.py` | 1.8 |
| 7.2 | Old Journey → New Journey converter | `v1/bridge/journey.py` | 4.1 |
| 7.3 | Old Client → HttpClient adapter | `v1/bridge/client.py` | 2.1 |
| 7.4 | Bridge tests | `tests/v1/test_bridge.py` | 7.1-7.3 |
| 7.5 | Migration guide documentation | `docs_v1/guides/migration.md` | 7.1-7.3 |

### 7.2 Deliverable

```python
# Old code still works
from venomqa import Journey, JourneyRunner

# Can migrate incrementally
from venomqa.v1.bridge import adapt_journey, adapt_state_manager

new_journey = adapt_journey(old_journey)
rollbackable_db = adapt_state_manager(old_state_manager)
```

---

## Phase 8: Promotion (Week 7)

Make v1 the default.

### 8.1 Tasks

| ID | Task | File | Dependencies |
|----|------|------|--------------|
| 8.1 | Move old code to venomqa/legacy/ | - | 7.4 |
| 8.2 | Update venomqa/__init__.py to export v1 | `__init__.py` | 8.1 |
| 8.3 | Add deprecation warnings to legacy | `legacy/__init__.py` | 8.1 |
| 8.4 | Update all documentation | `docs/` | 8.2 |
| 8.5 | Update README | `README.md` | 8.2 |
| 8.6 | Update examples | `examples/` | 8.2 |

---

## Phase 9: Cleanup (Week 8)

Remove deprecated code in next major version.

### 9.1 Tasks

| ID | Task | File | Dependencies |
|----|------|------|--------------|
| 9.1 | Delete legacy/ directory | - | 8.6 + user feedback |
| 9.2 | Remove bridge code | - | 9.1 |
| 9.3 | Final v1 → main promotion | - | 9.2 |
| 9.4 | Release v1.0.0 | - | 9.3 |

---

## File Count Comparison

| Category | Current | v1 |
|----------|---------|-----|
| Core domain | ~20 files | 6 files |
| World/Environment | ~25 files (ports, state, context) | 3 files |
| Adapters | ~30 files | 10 files |
| DSL | ~10 files | 3 files |
| Reporters | ~10 files | 4 files |
| CLI | ~5 files | 2 files |
| **Total** | **~100 files** | **~28 files** |

## Export Count Comparison

| Current | v1 |
|---------|-----|
| 300+ exports in `__init__.py` | 18 exports |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking existing users | Build v1 parallel, bridge layer for migration |
| Missing functionality | Map all current features to v1 equivalents before starting |
| Adapter bugs | Extensive integration tests for each adapter |
| Performance regression | Benchmark exploration speed before/after |

---

## Success Criteria

1. **All v1 tests pass** - Unit, integration, e2e
2. **Old journeys work via bridge** - No breaking changes
3. **Documentation complete** - All objects documented
4. **Examples updated** - All examples use v1 syntax
5. **Performance maintained** - No regression in exploration speed
