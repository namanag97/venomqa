# VenomQA Architecture

> Technical architecture overview for developers and maintainers.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              USER LAYER                                  │
├─────────────────────────────────────────────────────────────────────────┤
│   CLI (click)              Python API            Config (YAML)          │
│   venomqa run              from venomqa import   venomqa.yaml           │
│   venomqa demo             Journey, StateGraph                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           ORCHESTRATION LAYER                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌─────────────────┐          ┌─────────────────┐                      │
│   │  JourneyRunner  │          │   StateGraph    │                      │
│   │                 │          │    Explorer     │                      │
│   │  - Sequential   │          │                 │                      │
│   │  - Branching    │          │  - BFS/DFS      │                      │
│   │  - Checkpoints  │          │  - Invariants   │                      │
│   └────────┬────────┘          └────────┬────────┘                      │
│            │                            │                                │
│            └──────────┬─────────────────┘                                │
│                       ▼                                                  │
│            ┌─────────────────┐                                           │
│            │ ExecutionContext│  (shared state between steps)             │
│            └────────┬────────┘                                           │
│                     │                                                    │
└─────────────────────┼────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            CORE LAYER                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│   │  Client  │  │  State   │  │ Assertions│  │ Reporters│               │
│   │  (HTTP)  │  │ Manager  │  │           │  │          │               │
│   └────┬─────┘  └────┬─────┘  └─────┬─────┘  └────┬─────┘               │
│        │             │              │              │                     │
└────────┼─────────────┼──────────────┼──────────────┼─────────────────────┘
         │             │              │              │
         ▼             ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          PORTS LAYER (Interfaces)                        │
├─────────────────────────────────────────────────────────────────────────┤
│   ClientPort   DatabasePort   CachePort   QueuePort   StoragePort  ...  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         ADAPTERS LAYER (Implementations)                 │
├─────────────────────────────────────────────────────────────────────────┤
│   httpx        PostgreSQL      Redis       Celery       S3              │
│   requests     MySQL           Memcached   Redis Queue  GCS             │
│                SQLite                                   Azure Blob      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Journey & Step

```python
Journey
├── name: str
├── description: str
├── steps: list[Step | Checkpoint | Branch]
└── tags: list[str]

Step
├── name: str
├── action: Callable[[Client, Context], Response]
├── args: dict
├── timeout: float
├── retries: int
└── expect_failure: bool
```

**Flow:**
```
Step 1 → Step 2 → Checkpoint → Branch
                      │         ├── Path A → Step 3a → Step 4a
                      │         └── Path B → Step 3b → Step 4b
                      │
                (save state)  (restore & fork)
```

### 2. StateGraph

```python
StateGraph
├── nodes: dict[str, StateNode]      # States
├── edges: dict[str, list[Edge]]     # Transitions
├── invariants: list[Invariant]      # Rules
└── _initial_node: str

StateNode
├── id: str
├── description: str
└── checker: Callable -> bool        # "Am I in this state?"

Edge
├── from_node: str
├── to_node: str
├── action: Callable
└── name: str

Invariant
├── name: str
├── check: Callable -> bool          # "Is this rule satisfied?"
├── severity: Severity
└── description: str
```

**Exploration Algorithm:**
```
BFS from initial node:
  1. Check invariants at current node
  2. Get outgoing edges
  3. For each edge:
     a. Execute action
     b. Move to target node
     c. Check invariants
     d. Add to queue
  4. Stop at max_depth or no more edges
```

### 3. Client (HTTP)

```python
Client
├── base_url: str
├── session: httpx.Client
├── history: list[RequestRecord]     # All requests made
├── retry_policy: RetryPolicy
├── circuit_breaker: CircuitBreaker
└── auth_token: str | None

# Every request is recorded:
RequestRecord
├── method: str
├── url: str
├── request_body: Any
├── response_status: int
├── response_body: Any
├── duration_ms: float
└── error: str | None
```

### 4. ExecutionContext

```python
ExecutionContext
├── _data: dict[str, Any]            # User data (context["key"])
├── _step_results: dict[str, Any]    # Results by step name
├── state_manager: StateManager      # For checkpoints
└── snapshot() -> dict               # For branching
└── restore(snapshot: dict)          # After rollback
```

---

## Data Flow

### Journey Execution

```
1. JourneyRunner.run(journey)
   │
   ├── 2. For each step:
   │      │
   │      ├── 3. Execute step.action(client, context)
   │      │      │
   │      │      ├── 4. Client makes HTTP request
   │      │      │      └── Record in history
   │      │      │
   │      │      └── 5. Store result in context
   │      │
   │      └── 6. Check assertions, record issues
   │
   ├── 7. At Checkpoint:
   │      └── state_manager.checkpoint(name)
   │
   ├── 8. At Branch:
   │      │
   │      └── For each path:
   │           ├── state_manager.rollback(checkpoint_name)
   │           ├── context.restore(snapshot)
   │           └── Execute path steps
   │
   └── 9. Return JourneyResult
```

### StateGraph Exploration

```
1. graph.explore(client, db)
   │
   ├── 2. Start at initial_node
   │
   ├── 3. BFS queue: [(node, path, edges, context)]
   │
   └── 4. While queue not empty:
          │
          ├── 5. Check all invariants
          │      └── If violation: record & continue
          │
          ├── 6. Get outgoing edges
          │
          └── 7. For each edge:
                 ├── Execute edge.action(client, context)
                 ├── Add (target_node, path+[edge], context) to queue
                 └── Stop at max_depth
```

---

## Module Dependencies

```
venomqa/
│
├── __init__.py          # Public API exports
│
├── core/
│   ├── models.py        # Journey, Step, Branch, etc.
│   ├── graph.py         # StateGraph, Edge, Invariant
│   └── context.py       # ExecutionContext
│
├── runner/
│   └── __init__.py      # JourneyRunner (depends on: core, client)
│
├── client/
│   └── __init__.py      # Client (depends on: httpx)
│
├── ports/               # Abstract interfaces (no dependencies)
│   ├── client.py
│   ├── database.py
│   ├── cache.py
│   └── ...
│
├── adapters/            # Implementations (depends on: ports, external libs)
│   ├── postgres.py
│   ├── redis_cache.py
│   └── ...
│
├── reporters/           # Output formatters (depends on: core)
│   ├── html.py
│   ├── junit.py
│   └── ...
│
├── cli/                 # CLI commands (depends on: everything)
│   ├── commands.py
│   └── demo.py
│
└── errors/              # Error hierarchy (no dependencies)
    └── base.py
```

---

## Key Design Decisions

### 1. Ports & Adapters Pattern
**Why:** Allows swapping implementations without changing test code.
```python
# Port (interface)
class DatabasePort(Protocol):
    def query(self, sql: str) -> list[dict]: ...

# Adapter (implementation)
class PostgresAdapter(DatabasePort):
    def query(self, sql: str) -> list[dict]:
        return self.conn.execute(sql).fetchall()
```

### 2. Context Passing (not global state)
**Why:** Makes tests deterministic, enables parallel execution.
```python
def step1(client, context):
    context["token"] = "abc"  # Explicit passing

def step2(client, context):
    token = context["token"]  # Explicit receiving
```

### 3. Checkpoint = Database Snapshot
**Why:** Enables true state isolation between branches.
```python
Checkpoint(name="cart_ready")
# Internally: CREATE DATABASE SAVEPOINT cart_ready;
# Or: pg_dump / pg_restore for full isolation
```

### 4. Invariants as First-Class Citizens
**Why:** Catches bugs that individual tests miss.
```python
graph.add_invariant(
    "count_matches",
    check=lambda c, db, ctx: api_count == db_count
)
# Checked after EVERY edge execution
```

---

## Extension Points

| Extension | How | Example |
|-----------|-----|---------|
| New adapter | Implement port interface | `class MongoAdapter(DatabasePort)` |
| New reporter | Extend `BaseReporter` | `class SlackReporter(BaseReporter)` |
| Custom assertions | Add to `assertions/` | `def assert_latency_under(ms)` |
| Plugins | Use plugin registry | `@plugin("my_plugin")` |
| New CLI command | Add to `cli/commands.py` | `@cli.command()` |

---

## Performance Considerations

| Area | Current | Optimization |
|------|---------|--------------|
| HTTP requests | Sync | Could use async (`httpx.AsyncClient`) |
| Parallel paths | Thread pool | Could use asyncio |
| State snapshots | pg_dump | Could use COW filesystems |
| Large responses | In memory | Could stream to disk |

---

## Security Model

| Component | Security Measure |
|-----------|------------------|
| Credentials | `SecretsManager` with Vault/env backend |
| Sensitive data | `SensitiveDataFilter` redacts in logs |
| Input validation | `InputValidator` sanitizes user input |
| HTTP | TLS by default, configurable certs |
