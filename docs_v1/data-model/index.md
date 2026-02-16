# Data Model

This document defines every data object in VenomQA, their fields, and their relationships.

## Object Overview

VenomQA has 16 data objects organized into four categories:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  CATEGORY           OBJECTS                           PURPOSE               │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Core Domain        State                             Snapshot of world     │
│                     Observation                       Data from one system  │
│                     Action                            Changes the world     │
│                     Transition                        State→Action→State    │
│                     Graph                             All states/transitions│
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  World              World                             Sandbox environment   │
│                     Rollbackable (protocol)           System interface      │
│                     Checkpoint                        Saved world state     │
│                     SystemCheckpoint                  Saved system state    │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Verification       Invariant                         Rule that must hold   │
│                     Violation                         Failed invariant      │
│                     Severity                          How bad is it         │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Execution          Agent                             The explorer          │
│                     Strategy (protocol)               Picking algorithm     │
│                     ActionResult                      Result of action      │
│                     ExplorationResult                 Final output          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Object Relationships

```
                                    Agent
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
                  World            Graph          Invariant
                    │                 │                 │
          ┌─────────┼─────────┐       │                 │
          │         │         │       │                 │
          ▼         ▼         ▼       │                 │
       APIClient  Systems  Checkpoints│                 │
                    │         │       │                 │
                    │         │       │                 │
                    ▼         │       ▼                 │
              Rollbackable    │   Transition ◄──────────┤
                    │         │       │                 │
                    │         │       │                 │
                    ▼         ▼       ▼                 ▼
               Observation  Checkpoint State ◄───── Violation
                    │                   │
                    │                   │
                    └───────────────────┘

Legend:
  ──▶  contains/references
  ◄──  checked against / produces
```

---

# Core Domain Objects

## State

A snapshot of the entire world at a moment in time.

```python
@dataclass(frozen=True)
class State:
    id: StateID
    observations: dict[str, Observation]
    checkpoint_id: CheckpointID | None
    created_at: datetime
    parent_transition_id: TransitionID | None
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `StateID` (str) | Yes | Unique identifier. Format: `s_{uuid}` |
| `observations` | `dict[str, Observation]` | Yes | Observations keyed by system name |
| `checkpoint_id` | `CheckpointID \| None` | No | If set, we can rollback to this state |
| `created_at` | `datetime` | Yes | When this state was observed |
| `parent_transition_id` | `TransitionID \| None` | No | The transition that created this state. None for initial state |

### Semantics

- States are **immutable**. Once created, they never change.
- States are **nodes** in the exploration graph.
- Two states with identical observations may have different IDs (they occurred at different times or via different paths).
- A state with `checkpoint_id=None` cannot be rolled back to.

### Example

```python
State(
    id="s_a1b2c3d4",
    observations={
        "db": Observation(
            system="db",
            data={"users_count": 5, "orders_count": 3},
            observed_at=datetime(2024, 1, 15, 10, 30, 0),
        ),
        "cache": Observation(
            system="cache",
            data={"sessions": ["sess_1", "sess_2"]},
            observed_at=datetime(2024, 1, 15, 10, 30, 0),
        ),
    },
    checkpoint_id="cp_xyz789",
    created_at=datetime(2024, 1, 15, 10, 30, 0),
    parent_transition_id="t_def456",
)
```

---

## Observation

Data observed from a single system at a moment in time.

```python
@dataclass(frozen=True)
class Observation:
    system: str
    data: dict[str, Any]
    observed_at: datetime
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `system` | `str` | Yes | Name of the system (e.g., "db", "cache") |
| `data` | `dict[str, Any]` | Yes | The observed data. Schema depends on system |
| `observed_at` | `datetime` | Yes | When the observation was made |

### Semantics

- Observations are **immutable**.
- The `data` schema is system-specific. A database adapter might return table counts; a cache adapter might return key names.
- Observations are always taken **after** an action completes.

### Example

```python
# Database observation
Observation(
    system="db",
    data={
        "tables": {
            "users": {"count": 5},
            "orders": {"count": 3, "last_id": 42},
        },
    },
    observed_at=datetime(2024, 1, 15, 10, 30, 0),
)

# Cache observation
Observation(
    system="cache",
    data={
        "keys": ["user:1", "user:2", "session:abc"],
        "memory_used_bytes": 1024,
    },
    observed_at=datetime(2024, 1, 15, 10, 30, 0),
)

# Queue observation
Observation(
    system="queue",
    data={
        "pending": 5,
        "processing": 2,
        "failed": 0,
    },
    observed_at=datetime(2024, 1, 15, 10, 30, 0),
)
```

---

## Action

Something that changes the world. Usually an API call.

```python
@dataclass
class Action:
    name: str
    execute: Callable[[APIClient], ActionResult]
    preconditions: list[Callable[[State], bool]]
    description: str
    tags: list[str]
```

### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | `str` | Yes | - | Unique identifier for this action |
| `execute` | `Callable[[APIClient], ActionResult]` | Yes | - | Function that performs the action |
| `preconditions` | `list[Callable[[State], bool]]` | No | `[]` | Conditions that must be true |
| `description` | `str` | No | `""` | Human-readable description |
| `tags` | `list[str]` | No | `[]` | Tags for categorization |

### Semantics

- Action `name` must be unique within an exploration.
- `execute` receives an APIClient and must return an ActionResult.
- If any `precondition` returns False for the current state, the action is skipped.
- Actions are **edges** in the exploration graph.

### Example

```python
Action(
    name="create_order",
    execute=lambda api: ActionResult.from_response(
        api.post("/orders", json={"product_id": 1, "quantity": 2})
    ),
    preconditions=[
        lambda state: state.observations.get("db", {}).data.get("logged_in", False),
        lambda state: state.observations.get("db", {}).data.get("cart_items", 0) > 0,
    ],
    description="Create a new order from the current cart",
    tags=["orders", "checkout", "critical"],
)
```

---

## ActionResult

The result of executing an action.

```python
@dataclass
class ActionResult:
    success: bool
    request: HTTPRequest
    response: HTTPResponse | None
    error: str | None
    duration_ms: float
    timestamp: datetime
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `success` | `bool` | Yes | True if action executed without error |
| `request` | `HTTPRequest` | Yes | The HTTP request that was sent |
| `response` | `HTTPResponse \| None` | No | The HTTP response, if received |
| `error` | `str \| None` | No | Error message if execution failed |
| `duration_ms` | `float` | Yes | How long the action took |
| `timestamp` | `datetime` | Yes | When the action was executed |

### Semantics

- `success=True` means the action **executed** without error. It does not mean the HTTP response was 2xx.
- A 4xx or 5xx response still has `success=True` (the request completed).
- `success=False` with `error` set means the request could not be made (network error, timeout, etc.).

### Example

```python
# Successful request with 201 response
ActionResult(
    success=True,
    request=HTTPRequest(
        method="POST",
        url="http://localhost:8000/orders",
        headers={"Content-Type": "application/json"},
        body='{"product_id": 1}',
    ),
    response=HTTPResponse(
        status_code=201,
        headers={"Content-Type": "application/json"},
        body='{"id": 42, "status": "created"}',
    ),
    error=None,
    duration_ms=45.2,
    timestamp=datetime(2024, 1, 15, 10, 30, 0),
)

# Successful request with 400 response (still success=True)
ActionResult(
    success=True,
    request=HTTPRequest(...),
    response=HTTPResponse(status_code=400, ...),
    error=None,
    duration_ms=12.5,
    timestamp=datetime(...),
)

# Failed request (network error)
ActionResult(
    success=False,
    request=HTTPRequest(...),
    response=None,
    error="Connection refused: localhost:8000",
    duration_ms=5000.0,
    timestamp=datetime(...),
)
```

---

## Transition

A record of a state transition: State + Action → State.

```python
@dataclass(frozen=True)
class Transition:
    id: TransitionID
    from_state_id: StateID
    action_name: str
    to_state_id: StateID
    result: ActionResult
    timestamp: datetime
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `TransitionID` (str) | Yes | Unique identifier. Format: `t_{uuid}` |
| `from_state_id` | `StateID` | Yes | The state before the action |
| `action_name` | `str` | Yes | Name of the action that was executed |
| `to_state_id` | `StateID` | Yes | The state after the action |
| `result` | `ActionResult` | Yes | Full result of the action |
| `timestamp` | `datetime` | Yes | When this transition occurred |

### Semantics

- Transitions are **immutable**. They record history.
- Transitions are **edges** in the exploration graph.
- The sequence of transitions forms a path through the graph.

### Example

```python
Transition(
    id="t_abc123",
    from_state_id="s_state1",
    action_name="create_order",
    to_state_id="s_state2",
    result=ActionResult(success=True, ...),
    timestamp=datetime(2024, 1, 15, 10, 30, 0),
)
```

---

## Graph

The complete exploration graph: all states and transitions.

```python
class Graph:
    states: dict[StateID, State]
    transitions: list[Transition]
    actions: dict[str, Action]
    explored: set[tuple[StateID, str]]
    initial_state_id: StateID
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `states` | `dict[StateID, State]` | All observed states |
| `transitions` | `list[Transition]` | All transitions taken |
| `actions` | `dict[str, Action]` | All known actions |
| `explored` | `set[tuple[StateID, str]]` | (state_id, action_name) pairs that have been tried |
| `initial_state_id` | `StateID` | The starting state |

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `add_state` | `(state: State) → None` | Add a state to the graph |
| `add_transition` | `(transition: Transition) → None` | Add a transition and mark as explored |
| `get_valid_actions` | `(state: State) → list[Action]` | Actions whose preconditions pass |
| `get_unexplored` | `() → list[tuple[State, Action]]` | (state, action) pairs not yet tried |
| `is_explored` | `(state_id: StateID, action_name: str) → bool` | Has this pair been tried? |
| `get_path_to` | `(state_id: StateID) → list[Transition]` | Transitions to reach a state from initial |

### Semantics

- The graph grows as exploration proceeds.
- `get_unexplored()` only returns pairs where the state has a checkpoint (can be rolled back to).
- The graph is a directed graph (not a tree) — the same state might be reached via different paths.

---

# World Objects

## World

The sandbox environment. Coordinates all systems.

```python
class World:
    api: APIClient
    systems: dict[str, Rollbackable]
    checkpoints: dict[CheckpointID, Checkpoint]
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `api` | `APIClient` | HTTP client for executing actions |
| `systems` | `dict[str, Rollbackable]` | Named rollbackable systems |
| `checkpoints` | `dict[CheckpointID, Checkpoint]` | Saved checkpoints |

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `act` | `(action: Action) → ActionResult` | Execute action via API |
| `observe` | `() → State` | Query all systems, return current state |
| `checkpoint` | `(name: str) → CheckpointID` | Save ALL systems atomically |
| `rollback` | `(checkpoint_id: CheckpointID) → None` | Restore ALL systems atomically |

### Semantics

- `checkpoint` and `rollback` operate on **all systems together**.
- The World guarantees atomicity: either all systems checkpoint/rollback, or none do.
- The API client is not rollbackable — it just sends requests.

### Example

```python
world = World(
    api=HttpClient("http://localhost:8000"),
    systems={
        "db": PostgresAdapter("postgres://localhost/testdb"),
        "cache": RedisAdapter("redis://localhost:6379"),
        "queue": MockQueue(),
    },
)

# Execute an action
result = world.act(create_order)

# Observe current state
state = world.observe()

# Save checkpoint
cp_id = world.checkpoint("before_checkout")

# ... do more actions ...

# Rollback to checkpoint
world.rollback(cp_id)
```

---

## Rollbackable (Protocol)

The interface that systems must implement to be part of the World.

```python
class Rollbackable(Protocol):
    def checkpoint(self, name: str) → SystemCheckpoint: ...
    def rollback(self, checkpoint: SystemCheckpoint) → None: ...
    def observe(self) → Observation: ...
```

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `checkpoint` | `(name: str) → SystemCheckpoint` | Save current state, return opaque checkpoint |
| `rollback` | `(checkpoint: SystemCheckpoint) → None` | Restore to checkpoint state |
| `observe` | `() → Observation` | Return current observable state |

### Semantics

- `SystemCheckpoint` is opaque — its structure depends on the implementation.
- After `rollback(cp)`, the system must be indistinguishable from its state at `checkpoint()` time.
- Implementations exist for PostgreSQL, MySQL, Redis, and in-memory mocks.

### Implementations

| System | Checkpoint Method | Rollback Method |
|--------|-------------------|-----------------|
| PostgreSQL | `SAVEPOINT name` | `ROLLBACK TO SAVEPOINT name` |
| MySQL | `SAVEPOINT name` | `ROLLBACK TO SAVEPOINT name` |
| SQLite | Copy database file | Restore database file |
| Redis | `DUMP` all keys | `FLUSHALL` + `RESTORE` keys |
| MockQueue | Copy message list | Restore message list |
| MockMail | Save message count | Delete messages after count |

---

## Checkpoint

A saved state of all systems at a moment.

```python
@dataclass
class Checkpoint:
    id: CheckpointID
    name: str
    system_checkpoints: dict[str, SystemCheckpoint]
    created_at: datetime
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `CheckpointID` (str) | Unique identifier. Format: `cp_{uuid}` |
| `name` | `str` | Human-readable name provided at creation |
| `system_checkpoints` | `dict[str, SystemCheckpoint]` | Per-system checkpoint data |
| `created_at` | `datetime` | When checkpoint was created |

### Semantics

- A Checkpoint contains a `SystemCheckpoint` for **every** system in the World.
- Rollback restores all systems using their respective `SystemCheckpoint`.

---

## SystemCheckpoint

Opaque checkpoint data for a single system.

```python
SystemCheckpoint = Any  # Implementation-specific
```

### Examples by System

```python
# PostgreSQL: just the savepoint name
SystemCheckpoint = "savepoint_abc123"

# Redis: dict of key -> serialized value
SystemCheckpoint = {
    "user:1": b"...",
    "session:xyz": b"...",
}

# MockQueue: list of messages
SystemCheckpoint = [
    {"id": "msg1", "body": {...}},
    {"id": "msg2", "body": {...}},
]
```

---

# Verification Objects

## Invariant

A rule that must always be true.

```python
@dataclass
class Invariant:
    name: str
    check: Callable[[World], bool]
    message: str
    severity: Severity
```

### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | `str` | Yes | - | Unique identifier |
| `check` | `Callable[[World], bool]` | Yes | - | Function that returns True if invariant holds |
| `message` | `str` | Yes | - | Human-readable description of what went wrong |
| `severity` | `Severity` | No | `Severity.HIGH` | How serious is a violation |

### Semantics

- The `check` function receives the entire World and can query any system.
- `check` returns True if the invariant holds, False if violated.
- Invariants are checked after **every** action.

### Example

```python
Invariant(
    name="order_count_consistent",
    check=lambda world: (
        world.systems["db"].query("SELECT COUNT(*) FROM orders")[0][0]
        == len(world.api.get("/orders").json()["orders"])
    ),
    message="Database order count must match API response",
    severity=Severity.CRITICAL,
)

Invariant(
    name="no_negative_balance",
    check=lambda world: all(
        row["balance"] >= 0
        for row in world.systems["db"].query("SELECT balance FROM accounts")
    ),
    message="Account balance must never be negative",
    severity=Severity.CRITICAL,
)

Invariant(
    name="deleted_not_in_search",
    check=lambda world: all(
        item["id"] not in world.systems["search"].query("*")
        for item in world.systems["db"].query("SELECT id FROM items WHERE deleted=true")
    ),
    message="Deleted items must not appear in search results",
    severity=Severity.HIGH,
)
```

---

## Violation

A record of an invariant that failed.

```python
@dataclass
class Violation:
    id: ViolationID
    invariant_name: str
    state: State
    action: Action | None
    message: str
    severity: Severity
    reproduction_path: list[Transition]
    timestamp: datetime
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `ViolationID` (str) | Unique identifier. Format: `v_{uuid}` |
| `invariant_name` | `str` | Name of the invariant that failed |
| `state` | `State` | The state where violation was detected |
| `action` | `Action \| None` | The action that led to this state (None for initial) |
| `message` | `str` | The invariant's message |
| `severity` | `Severity` | From the invariant |
| `reproduction_path` | `list[Transition]` | How to reach this state from initial |
| `timestamp` | `datetime` | When violation was detected |

### Semantics

- Violations are the **primary output** of exploration.
- `reproduction_path` allows replaying the exact sequence of actions that caused the bug.

---

## Severity

How serious a violation is.

```python
class Severity(Enum):
    CRITICAL = "critical"  # System unusable, data corruption
    HIGH = "high"          # Major feature broken
    MEDIUM = "medium"      # Feature partially working
    LOW = "low"            # Minor issue, cosmetic
```

---

# Execution Objects

## Agent

The explorer that traverses the state graph.

```python
class Agent:
    world: World
    graph: Graph
    invariants: list[Invariant]
    strategy: Strategy
    violations: list[Violation]
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `world` | `World` | The sandbox environment |
| `graph` | `Graph` | The graph being explored |
| `invariants` | `list[Invariant]` | Rules to check after each action |
| `strategy` | `Strategy` | How to pick next (state, action) |
| `violations` | `list[Violation]` | Violations found so far |

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `explore` | `() → ExplorationResult` | Fully explore the graph |
| `step` | `() → Transition \| None` | Execute one exploration step |

### Semantics

- `explore()` runs until no unexplored (state, action) pairs remain.
- `step()` picks one (state, action), executes it, returns the transition.
- The Agent populates `graph` and `violations` as it explores.

---

## Strategy (Protocol)

How the Agent picks the next (state, action) to explore.

```python
class Strategy(Protocol):
    def pick(self, graph: Graph) → tuple[State, Action] | None: ...
```

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `pick` | `(graph: Graph) → tuple[State, Action] \| None` | Pick next pair, or None if done |

### Implementations

| Strategy | Behavior |
|----------|----------|
| `BFS` | Explore all actions from each state before going deeper (breadth-first) |
| `DFS` | Follow one path deeply before backtracking (depth-first) |
| `Random` | Pick randomly from unexplored pairs |
| `CoverageGuided` | Prioritize actions likely to increase code coverage |

---

## ExplorationResult

The complete result of an exploration run.

```python
@dataclass
class ExplorationResult:
    graph: Graph
    violations: list[Violation]
    states_visited: int
    transitions_taken: int
    actions_total: int
    coverage_percent: float
    duration_ms: float
    started_at: datetime
    finished_at: datetime
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `graph` | `Graph` | The complete explored graph |
| `violations` | `list[Violation]` | All violations found |
| `states_visited` | `int` | Number of unique states |
| `transitions_taken` | `int` | Number of actions executed |
| `actions_total` | `int` | Total number of distinct actions |
| `coverage_percent` | `float` | Percent of (state, action) pairs explored |
| `duration_ms` | `float` | Total exploration time |
| `started_at` | `datetime` | When exploration started |
| `finished_at` | `datetime` | When exploration finished |

### Computed Properties

| Property | Type | Description |
|----------|------|-------------|
| `success` | `bool` | True if no violations |
| `critical_violations` | `list[Violation]` | Violations with CRITICAL severity |
| `high_violations` | `list[Violation]` | Violations with HIGH or CRITICAL severity |

---

# Type Aliases

For clarity, VenomQA defines these type aliases:

```python
StateID = str           # Format: "s_{uuid}"
TransitionID = str      # Format: "t_{uuid}"
CheckpointID = str      # Format: "cp_{uuid}"
ViolationID = str       # Format: "v_{uuid}"
ActionName = str        # Matches Action.name
SystemName = str        # Matches key in World.systems
SystemCheckpoint = Any  # Implementation-specific
Predicate = Callable[[State], bool]
```

---

# Object Lifecycle

## State Lifecycle

```
World.observe()
      │
      ▼
┌─────────────┐
│   State     │ ──────► Immutable from this point
│   created   │
└─────────────┘
      │
      ├───────────────────────────────┐
      │                               │
      ▼                               ▼
 Added to Graph              Used in Violation
      │                        (if invariant fails)
      │
      ▼
 Referenced by future
 Transitions (as from_state or to_state)
```

## Checkpoint Lifecycle

```
World.checkpoint(name)
      │
      ▼
┌─────────────┐
│ Checkpoint  │
│  created    │
└─────────────┘
      │
      ├───────────────────────────────┐
      │                               │
      ▼                               ▼
 Stored in World.checkpoints    Associated with State
      │                         (state.checkpoint_id)
      │
      ▼
 World.rollback(checkpoint_id)
      │
      ▼
 All systems restored
```

## Exploration Lifecycle

```
Agent created
      │
      ▼
Initial state observed
      │
      ▼
Initial state checkpointed
      │
      ▼
┌─────────────────────────────────────────┐
│           EXPLORATION LOOP               │
│                                         │
│   while graph.get_unexplored():         │
│       (state, action) = strategy.pick() │
│       world.rollback(state.checkpoint)  │
│       cp = world.checkpoint()           │
│       result = world.act(action)        │
│       new_state = world.observe()       │
│       for inv in invariants:            │
│           if not inv.check(world):      │
│               record Violation          │
│       graph.add_transition(...)         │
│                                         │
└─────────────────────────────────────────┘
      │
      ▼
ExplorationResult returned
```
