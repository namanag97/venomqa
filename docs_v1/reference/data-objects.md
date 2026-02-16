# Data Objects Reference

Complete reference of all data objects in VenomQA.

## Summary Table

| Object | Category | Purpose |
|--------|----------|---------|
| `State` | Core | Snapshot of world at a moment |
| `Observation` | Core | Data from one system |
| `Action` | Core | Something that changes the world |
| `ActionResult` | Core | Result of executing an action |
| `Transition` | Core | Record of state change |
| `Graph` | Core | All states and transitions |
| `World` | Environment | Sandbox with all systems |
| `Rollbackable` | Environment | Protocol for systems |
| `Checkpoint` | Environment | Saved world state |
| `SystemCheckpoint` | Environment | Saved system state |
| `Invariant` | Verification | Rule that must hold |
| `Violation` | Verification | Failed invariant record |
| `Severity` | Verification | Violation severity level |
| `Agent` | Execution | The explorer |
| `Strategy` | Execution | Exploration algorithm |
| `ExplorationResult` | Execution | Final output |
| `Journey` | DSL | User-friendly flow definition |
| `Step` | DSL | Single action in journey |
| `Checkpoint` (DSL) | DSL | Named savepoint |
| `Branch` | DSL | Fork from checkpoint |
| `Path` | DSL | Sequence in branch |

---

## Core Objects

### State

```python
@dataclass(frozen=True)
class State:
    id: StateID                              # "s_{uuid}"
    observations: dict[str, Observation]     # System name → Observation
    checkpoint_id: CheckpointID | None       # If rollbackable
    created_at: datetime                     # When observed
    parent_transition_id: TransitionID | None  # How we got here
```

### Observation

```python
@dataclass(frozen=True)
class Observation:
    system: str              # "db", "cache", "queue", etc.
    data: dict[str, Any]     # System-specific data
    observed_at: datetime    # When observed
```

### Action

```python
@dataclass
class Action:
    name: str                                        # Unique identifier
    execute: Callable[[APIClient], ActionResult]     # The function
    preconditions: list[Callable[[State], bool]]     # When valid
    description: str                                 # Human-readable
    tags: list[str]                                  # Categorization
```

### ActionResult

```python
@dataclass
class ActionResult:
    success: bool              # Did execution complete?
    request: HTTPRequest       # What was sent
    response: HTTPResponse | None  # What was received
    error: str | None          # Error if success=False
    duration_ms: float         # How long it took
    timestamp: datetime        # When executed
```

### Transition

```python
@dataclass(frozen=True)
class Transition:
    id: TransitionID           # "t_{uuid}"
    from_state_id: StateID     # Starting state
    action_name: str           # Action taken
    to_state_id: StateID       # Resulting state
    result: ActionResult       # Full result
    timestamp: datetime        # When occurred
```

### Graph

```python
class Graph:
    states: dict[StateID, State]          # All states
    transitions: list[Transition]          # All transitions
    actions: dict[str, Action]            # All actions
    explored: set[tuple[StateID, str]]    # Explored pairs
    initial_state_id: StateID             # Starting point

    def add_state(state: State) → None
    def add_transition(transition: Transition) → None
    def get_valid_actions(state: State) → list[Action]
    def get_unexplored() → list[tuple[State, Action]]
    def is_explored(state_id: StateID, action_name: str) → bool
    def get_path_to(state_id: StateID) → list[Transition]
```

---

## Environment Objects

### World

```python
class World:
    api: APIClient                              # HTTP client
    systems: dict[str, Rollbackable]            # Named systems
    checkpoints: dict[CheckpointID, Checkpoint] # Saved states

    def act(action: Action) → ActionResult
    def observe() → State
    def checkpoint(name: str) → CheckpointID
    def rollback(checkpoint_id: CheckpointID) → None
```

### Rollbackable (Protocol)

```python
class Rollbackable(Protocol):
    def checkpoint(name: str) → SystemCheckpoint
    def rollback(checkpoint: SystemCheckpoint) → None
    def observe() → Observation
```

### Checkpoint

```python
@dataclass
class Checkpoint:
    id: CheckpointID                             # "cp_{uuid}"
    name: str                                    # Human-readable name
    system_checkpoints: dict[str, SystemCheckpoint]  # Per-system data
    created_at: datetime                         # When created
```

### SystemCheckpoint

```python
SystemCheckpoint = Any  # Implementation-specific

# Examples:
# PostgreSQL: "savepoint_name"
# Redis: {"key": b"value", ...}
# MockQueue: [Message, Message, ...]
```

---

## Verification Objects

### Invariant

```python
@dataclass
class Invariant:
    name: str                          # Unique identifier
    check: Callable[[World], bool]     # Returns True if holds
    message: str                       # What went wrong
    severity: Severity                 # How serious
```

### Violation

```python
@dataclass
class Violation:
    id: ViolationID                    # "v_{uuid}"
    invariant_name: str                # Which invariant
    state: State                       # Where detected
    action: Action | None              # What caused it
    message: str                       # From invariant
    severity: Severity                 # From invariant
    reproduction_path: list[Transition]  # How to reproduce
    timestamp: datetime                # When detected
```

### Severity

```python
class Severity(Enum):
    CRITICAL = "critical"  # Data corruption, security
    HIGH = "high"          # Major feature broken
    MEDIUM = "medium"      # Partial functionality
    LOW = "low"            # Minor issues
```

---

## Execution Objects

### Agent

```python
class Agent:
    world: World                       # The sandbox
    graph: Graph                       # Being explored
    invariants: list[Invariant]        # Rules to check
    strategy: Strategy                 # How to pick next
    violations: list[Violation]        # Found so far

    def explore() → ExplorationResult
    def step() → Transition | None
```

### Strategy (Protocol)

```python
class Strategy(Protocol):
    def pick(graph: Graph) → tuple[State, Action] | None
```

**Implementations:**
- `BFS` — Breadth-first search
- `DFS` — Depth-first search
- `Random` — Random selection
- `CoverageGuided` — Prioritize coverage

### ExplorationResult

```python
@dataclass
class ExplorationResult:
    graph: Graph                       # Complete graph
    violations: list[Violation]        # All violations
    states_visited: int                # Unique states
    transitions_taken: int             # Actions executed
    actions_total: int                 # Available actions
    coverage_percent: float            # Explored percentage
    duration_ms: float                 # Total time
    started_at: datetime               # Start time
    finished_at: datetime              # End time

    @property
    def success() → bool               # No violations?
    @property
    def critical_violations() → list[Violation]
```

---

## DSL Objects

### Journey

```python
@dataclass
class Journey:
    name: str                          # Unique identifier
    steps: list[Step | Checkpoint | Branch]  # Ordered elements
    invariants: list[Invariant]        # Rules to check
    description: str                   # Human-readable
```

### Step

```python
@dataclass
class Step:
    name: str                          # Step identifier
    action: Callable[[APIClient], ActionResult]  # The action
    description: str                   # Human-readable
```

### Checkpoint (DSL)

```python
@dataclass
class Checkpoint:
    name: str                          # Checkpoint identifier
```

### Branch

```python
@dataclass
class Branch:
    from_checkpoint: str               # Checkpoint to branch from
    paths: list[Path]                  # Paths to explore
```

### Path

```python
@dataclass
class Path:
    name: str                          # Path identifier
    steps: list[Step | Checkpoint]     # Steps in this path
```

---

## Type Aliases

```python
StateID = str           # Format: "s_{uuid}"
TransitionID = str      # Format: "t_{uuid}"
CheckpointID = str      # Format: "cp_{uuid}"
ViolationID = str       # Format: "v_{uuid}"
ActionName = str        # Matches Action.name
SystemName = str        # Key in World.systems
SystemCheckpoint = Any  # Implementation-specific
Predicate = Callable[[State], bool]
```

---

## Object Creation Examples

### Creating a State

```python
state = State(
    id="s_abc123",
    observations={
        "db": Observation(
            system="db",
            data={"users": 5, "orders": 3},
            observed_at=datetime.now(),
        ),
    },
    checkpoint_id="cp_xyz789",
    created_at=datetime.now(),
    parent_transition_id=None,
)
```

### Creating an Action

```python
action = Action(
    name="create_order",
    execute=lambda api: ActionResult.from_response(
        api.post("/orders", json={"product_id": 1})
    ),
    preconditions=[
        lambda s: s.observations["db"].data.get("logged_in", False),
    ],
    description="Create a new order",
    tags=["orders", "critical"],
)
```

### Creating an Invariant

```python
invariant = Invariant(
    name="order_count_consistent",
    check=lambda world: (
        world.systems["db"].query("SELECT COUNT(*) FROM orders")[0][0]
        == len(world.api.get("/orders").json()["orders"])
    ),
    message="Database count must match API response",
    severity=Severity.CRITICAL,
)
```

### Creating a World

```python
world = World(
    api=HttpClient("http://localhost:8000"),
    systems={
        "db": PostgresAdapter("postgres://localhost/test"),
        "cache": RedisAdapter("redis://localhost:6379"),
        "queue": MockQueue(),
    },
)
```

### Creating an Agent

```python
agent = Agent(
    world=world,
    actions=[action1, action2, action3],
    invariants=[invariant1, invariant2],
    strategy=BFS(),
)
```

### Creating a Journey

```python
journey = Journey(
    name="checkout_flow",
    steps=[
        Step("login", login_action),
        Checkpoint("logged_in"),
        Step("add_to_cart", add_action),
        Checkpoint("cart_ready"),
        Branch(
            from_checkpoint="cart_ready",
            paths=[
                Path("buy", [Step("checkout", checkout_action)]),
                Path("abandon", [Step("clear", clear_action)]),
            ],
        ),
    ],
    invariants=[order_invariant],
    description="Test checkout with buy/abandon paths",
)
```
