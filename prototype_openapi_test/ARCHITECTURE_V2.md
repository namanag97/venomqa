# VenomQA v2 Architecture

## Design Philosophy

> **VenomQA owns the test environment. Users provide code, VenomQA provides everything else.**

The user's only input is their existing `docker-compose.yml`. VenomQA handles:
- Spinning up isolated containers
- Discovering the API
- Generating tests
- Controlling state
- Finding bugs

---

## Core User Experience

```bash
# That's it. Nothing else.
cd my-project
venomqa test

# Output:
# 🔍 VenomQA v2.0
#
# [1/5] Starting environment...
#       ✓ postgres:15 (healthy)
#       ✓ my-api:latest (healthy, port 8000)
#
# [2/5] Discovering API...
#       ✓ OpenAPI 3.0 found at /openapi.json
#       ✓ 47 endpoints, 12 resource types
#
# [3/5] Generating tests...
#       ✓ 47 actions
#       ✓ 23 auto-invariants (CRUD + schema)
#
# [4/5] Exploring state graph...
#       ████████████████████ 100%
#       312 states, 891 transitions, 2.3s
#
# [5/5] Results
#       ✗ 2 bugs found
#
# BUG 1: Double-delete succeeds (should 404)
#   POST /users → DELETE /users/1 → DELETE /users/1
#   Expected: 404, Got: 200
#
#   curl -X DELETE http://localhost:8000/users/1
#
# BUG 2: Response missing required field 'email'
#   POST /users → GET /users/1
#   Schema requires: ["id", "email", "name"]
#   Response has: ["id", "name"]
```

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              VENOMQA ENGINE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────┐   ┌────────────────┐   ┌────────────────┐               │
│  │   CLI Layer    │   │  Config Layer  │   │  Output Layer  │               │
│  │                │   │                │   │                │               │
│  │  venomqa test  │   │  venomqa.yaml  │   │  Console/JSON  │               │
│  │  venomqa init  │   │  (optional)    │   │  HTML Report   │               │
│  └───────┬────────┘   └───────┬────────┘   └───────┬────────┘               │
│          │                    │                    │                        │
│          └────────────────────┼────────────────────┘                        │
│                               ▼                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      ORCHESTRATOR                                     │   │
│  │                                                                       │   │
│  │   Coordinates all phases of test execution                           │   │
│  │   Handles errors, retries, timeouts                                  │   │
│  │   Manages lifecycle of test environment                              │   │
│  └───────────────────────────────┬──────────────────────────────────────┘   │
│                                  │                                          │
│          ┌───────────────────────┼───────────────────────┐                  │
│          ▼                       ▼                       ▼                  │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐              │
│  │ Environment  │      │  Discovery   │      │  Generator   │              │
│  │   Manager    │      │    Engine    │      │    Engine    │              │
│  │              │      │              │      │              │              │
│  │ Docker/      │      │ OpenAPI      │      │ Actions      │              │
│  │ Compose      │      │ Parser       │      │ Invariants   │              │
│  │ Control      │      │ Schema       │      │ Data Gen     │              │
│  └──────┬───────┘      └──────┬───────┘      └──────┬───────┘              │
│         │                     │                     │                       │
│         └─────────────────────┼─────────────────────┘                       │
│                               ▼                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      EXPLORATION ENGINE                               │   │
│  │                                                                       │   │
│  │   State graph exploration (BFS/DFS/MCTS)                             │   │
│  │   Invariant checking                                                 │   │
│  │   Violation detection                                                │   │
│  │   Reproduction path generation                                       │   │
│  └───────────────────────────────┬──────────────────────────────────────┘   │
│                                  │                                          │
│                                  ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      STATE MANAGER                                    │   │
│  │                                                                       │   │
│  │   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                │   │
│  │   │ DB Snapshots│   │ API State   │   │ Resource    │                │   │
│  │   │ (optional)  │   │ Tracking    │   │ Graph       │                │   │
│  │   └─────────────┘   └─────────────┘   └─────────────┘                │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TEST ENVIRONMENT                                     │
│                        (Docker Containers)                                   │
│                                                                              │
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐           │
│  │   Database      │   │   API Server    │   │   Other         │           │
│  │   Container     │◄─►│   Container     │◄─►│   Services      │           │
│  │                 │   │                 │   │   (Redis, etc)  │           │
│  │  postgres:15    │   │  user-api:test  │   │                 │           │
│  └─────────────────┘   └─────────────────┘   └─────────────────┘           │
│          ▲                     ▲                                            │
│          │                     │                                            │
│          │    VenomQA has full control over these containers               │
│          │    - Start/stop                                                 │
│          │    - Health checks                                              │
│          │    - Network access                                             │
│          │    - DB snapshots (if configured)                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Models

### 1. Configuration

```python
@dataclass
class VenomQAConfig:
    """Main configuration - mostly auto-detected."""

    # Environment
    compose_file: Path = Path("docker-compose.yml")
    dockerfile: Path | None = None  # Alternative to compose

    # API Discovery
    api_service: str | None = None  # Auto-detect if None
    api_port: int | None = None     # Auto-detect if None
    openapi_path: str = "/openapi.json"  # Try common paths

    # Database (optional)
    db_service: str | None = None   # None = no DB rollback
    db_type: Literal["postgres", "mysql", "sqlite"] | None = None

    # Exploration
    strategy: Literal["bfs", "dfs", "mcts"] = "bfs"
    max_steps: int = 1000
    timeout_seconds: int = 300

    # Output
    output_format: Literal["console", "json", "html"] = "console"
    verbose: bool = False
```

### 2. Test Environment

```python
@dataclass
class Container:
    """A running Docker container."""
    id: str
    name: str
    image: str
    status: Literal["starting", "healthy", "unhealthy", "stopped"]
    ports: dict[int, int]  # container_port -> host_port
    health_check: str | None


@dataclass
class TestEnvironment:
    """The isolated test environment."""

    # Containers
    containers: dict[str, Container]
    network_name: str

    # Detected services
    api_container: Container | None
    api_url: str | None  # e.g., "http://localhost:32789"

    db_container: Container | None
    db_connection: str | None  # e.g., "postgresql://..."

    # Lifecycle
    started_at: datetime
    status: Literal["starting", "ready", "exploring", "stopped"]

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def restart(self) -> None: ...
    def health_check(self) -> bool: ...
```

### 3. API Discovery

```python
@dataclass
class DiscoveredEndpoint:
    """An endpoint discovered from OpenAPI."""

    path: str                    # "/users/{user_id}"
    method: str                  # "GET"
    operation_id: str | None     # "getUser"

    # Inferred semantics
    resource_type: str | None    # "user"
    operation: CRUDType          # "read"

    # Parameters
    path_params: list[str]       # ["user_id"]
    query_params: list[ParamSpec]
    header_params: list[ParamSpec]

    # Request/Response
    request_body: SchemaSpec | None
    responses: dict[int, SchemaSpec]  # status_code -> schema

    # Dependencies
    requires_resources: list[str]  # ["organization"] (parent resources)
    requires_auth: bool


@dataclass
class ParamSpec:
    """A parameter specification."""
    name: str
    location: Literal["path", "query", "header", "cookie"]
    required: bool
    schema: SchemaSpec


@dataclass
class SchemaSpec:
    """A JSON Schema specification (resolved, no $refs)."""
    type: str
    properties: dict[str, SchemaSpec] | None
    required: list[str] | None
    items: SchemaSpec | None  # For arrays
    enum: list[Any] | None
    minimum: float | None
    maximum: float | None
    pattern: str | None
    format: str | None

    # Original for reference
    raw: dict[str, Any]


@dataclass
class DiscoveredAPI:
    """Everything we learn from the OpenAPI spec."""

    # Metadata
    title: str
    version: str
    openapi_version: str

    # Content
    endpoints: list[DiscoveredEndpoint]
    schemas: dict[str, SchemaSpec]  # component schemas

    # Inferred structure
    resource_types: list[ResourceType]
    resource_hierarchy: dict[str, str | None]  # child -> parent

    # Security
    security_schemes: dict[str, SecurityScheme]

    @classmethod
    def from_spec(cls, spec: dict, resolve_refs: bool = True) -> "DiscoveredAPI":
        """Parse OpenAPI spec into structured data."""
        ...
```

### 4. Generated Artifacts

```python
@dataclass
class GeneratedAction:
    """An action generated from an endpoint."""

    name: str
    endpoint: DiscoveredEndpoint

    # Execution
    execute: Callable[[HttpClient, Context], ActionResult]

    # Preconditions (auto-generated)
    preconditions: list[Precondition]

    # Request body generator
    body_generator: Callable[[], dict] | None

    # Expected responses
    expected_success_codes: list[int]  # [200, 201]
    expected_error_codes: list[int]    # [400, 404]


@dataclass
class GeneratedInvariant:
    """An invariant generated from the API spec."""

    name: str
    description: str
    source: Literal["crud", "schema", "custom"]

    # The check function
    check: Callable[[World], bool | str]

    # What triggered generation
    endpoint: DiscoveredEndpoint | None
    schema: SchemaSpec | None


@dataclass
class GeneratedArtifacts:
    """All generated test artifacts."""

    actions: list[GeneratedAction]
    invariants: list[GeneratedInvariant]
    resource_schema: ResourceSchema

    # Statistics
    endpoints_processed: int
    invariants_by_type: dict[str, int]  # {"crud": 15, "schema": 8}
```

### 5. Exploration & Results

```python
@dataclass
class ExplorationState:
    """State during exploration."""

    # Identity (content-based)
    id: str

    # What we observed
    resource_counts: dict[str, int]  # {"user": 3, "order": 5}
    context_snapshot: dict[str, Any]

    # For rollback
    checkpoint_id: str | None
    db_snapshot_id: str | None


@dataclass
class Transition:
    """A state transition (action execution)."""

    from_state_id: str
    action_name: str
    to_state_id: str

    # What happened
    result: ActionResult
    duration_ms: float

    # Any violations triggered
    violations: list[str]  # invariant names


@dataclass
class Bug:
    """A bug found during exploration."""

    id: str

    # What failed
    invariant_name: str
    invariant_description: str

    # Where it failed
    state_id: str
    action_name: str

    # How to reproduce
    reproduction_path: list[Transition]
    reproduction_curl: list[str]  # curl commands

    # Details
    expected: str
    actual: str
    response: ActionResult | None

    # Metadata
    severity: Literal["critical", "high", "medium", "low"]
    found_at: datetime


@dataclass
class ExplorationResult:
    """Final results of an exploration run."""

    # Environment info
    api_title: str
    api_version: str

    # What was tested
    actions_count: int
    invariants_count: int

    # Exploration stats
    states_visited: int
    transitions_taken: int
    duration_ms: float

    # Findings
    bugs: list[Bug]
    warnings: list[str]

    # Coverage
    actions_executed: set[str]
    actions_not_executed: set[str]
    coverage_percentage: float
```

### 6. State Management

```python
@dataclass
class DBSnapshot:
    """A database snapshot for rollback."""

    id: str
    created_at: datetime

    # How to restore
    type: Literal["savepoint", "dump", "copy"]
    reference: str  # savepoint name, dump file, etc.


class StateManager(Protocol):
    """Protocol for state management backends."""

    def checkpoint(self, name: str) -> str:
        """Create a checkpoint, return ID."""
        ...

    def rollback(self, checkpoint_id: str) -> None:
        """Rollback to a checkpoint."""
        ...

    def observe(self) -> dict[str, Any]:
        """Get current state observation."""
        ...


@dataclass
class PostgresStateManager:
    """State management via Postgres savepoints."""

    connection: Any  # psycopg connection
    savepoints: dict[str, str]  # checkpoint_id -> savepoint_name

    def checkpoint(self, name: str) -> str:
        # SAVEPOINT name
        ...

    def rollback(self, checkpoint_id: str) -> None:
        # ROLLBACK TO SAVEPOINT name
        ...


@dataclass
class ResourceTrackingStateManager:
    """State management via resource tracking (no DB access)."""

    resources: dict[tuple[str, str], bool]  # (type, id) -> alive
    snapshots: dict[str, dict]

    def checkpoint(self, name: str) -> str:
        # Copy resources dict
        ...

    def rollback(self, checkpoint_id: str) -> None:
        # Restore resources dict
        ...
```

---

## Processing Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 1: ENVIRONMENT SETUP                                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Input: docker-compose.yml                                       │
│                                                                  │
│  Steps:                                                          │
│  1. Parse compose file                                           │
│  2. Identify services (api, db, etc.)                           │
│  3. Create isolated network                                      │
│  4. Start containers                                             │
│  5. Wait for health checks                                       │
│  6. Detect API endpoint (port scanning + /health)               │
│                                                                  │
│  Output: TestEnvironment (running, healthy)                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 2: API DISCOVERY                                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Input: TestEnvironment.api_url                                  │
│                                                                  │
│  Steps:                                                          │
│  1. Try common OpenAPI paths (/openapi.json, /swagger.json)     │
│  2. Fetch and parse spec                                         │
│  3. Resolve all $ref references                                  │
│  4. Extract endpoints                                            │
│  5. Infer resource types from paths                             │
│  6. Build resource hierarchy                                     │
│  7. Extract schemas                                              │
│                                                                  │
│  Output: DiscoveredAPI                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 3: ARTIFACT GENERATION                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Input: DiscoveredAPI                                            │
│                                                                  │
│  Steps:                                                          │
│  1. Generate Action for each endpoint                            │
│     - Build execute function (HTTP call)                        │
│     - Generate preconditions from path params                   │
│     - Generate request body generator from schema               │
│                                                                  │
│  2. Generate Invariants                                          │
│     - CRUD invariants (POST→201, DELETE→404 on retry)           │
│     - Schema invariants (response matches schema)               │
│     - Required field invariants                                 │
│                                                                  │
│  3. Build ResourceSchema from hierarchy                          │
│                                                                  │
│  Output: GeneratedArtifacts                                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 4: STATE MANAGER SETUP                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Input: TestEnvironment, Config                                  │
│                                                                  │
│  Decision tree:                                                  │
│  - If db_service configured AND can connect:                    │
│      → Use PostgresStateManager (full rollback)                 │
│  - Else:                                                         │
│      → Use ResourceTrackingStateManager (API-level tracking)    │
│                                                                  │
│  Output: StateManager                                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 5: EXPLORATION                                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Input: GeneratedArtifacts, StateManager, Config                 │
│                                                                  │
│  Algorithm (BFS default):                                        │
│  1. Observe initial state, checkpoint                           │
│  2. While unexplored (state, action) pairs exist:               │
│     a. Pick next pair (via strategy)                            │
│     b. Rollback to state                                        │
│     c. Execute action                                           │
│     d. Check all invariants                                     │
│     e. Record violations as bugs                                │
│     f. Observe new state, checkpoint                            │
│     g. Add new pairs to frontier                                │
│  3. Generate reproduction paths for bugs                        │
│                                                                  │
│  Output: ExplorationResult                                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 6: REPORTING                                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Input: ExplorationResult                                        │
│                                                                  │
│  Outputs:                                                        │
│  - Console: Human-readable bug report with curl commands        │
│  - JSON: Machine-readable for CI integration                    │
│  - HTML: Interactive report with state graph visualization      │
│                                                                  │
│  Exit codes:                                                     │
│  - 0: No bugs found                                              │
│  - 1: Bugs found                                                 │
│  - 2: Exploration error (couldn't start, API down, etc.)       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 7: CLEANUP                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Steps:                                                          │
│  1. Stop all containers                                          │
│  2. Remove network                                               │
│  3. Clean up temp files                                          │
│                                                                  │
│  On error: Still cleanup (finally block)                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Invariant Generation Rules

### CRUD Invariants (Auto-Generated)

| Endpoint Pattern | Generated Invariant |
|------------------|---------------------|
| `POST /resources` | Response status is 201 |
| `POST /resources` | Response has `id` field |
| `GET /resources/{id}` after `POST` | Status is 200 |
| `GET /resources/{id}` after `DELETE` | Status is 404 |
| `DELETE /resources/{id}` | Status is 200 or 204 |
| `DELETE /resources/{id}` twice | Second returns 404 |
| `PUT /resources/{id}` | Status is 200 |
| `PUT /resources/{id}` (non-existent) | Status is 404 |

### Schema Invariants (Auto-Generated)

| Schema Property | Generated Invariant |
|-----------------|---------------------|
| `required: ["id", "name"]` | Response contains required fields |
| `type: "string"` | Field is string type |
| `enum: ["a", "b", "c"]` | Field value in enum |
| `minimum: 0` | Field value >= minimum |
| `maximum: 100` | Field value <= maximum |
| `pattern: "^[a-z]+$"` | Field matches pattern |
| `format: "email"` | Field is valid email |

### Relationship Invariants (Auto-Generated)

| Pattern | Generated Invariant |
|---------|---------------------|
| `/parents/{pid}/children` | Child requires parent to exist |
| `DELETE /parents/{pid}` | Children are deleted or orphaned |

---

## Directory Structure

```
venomqa/
├── src/venomqa/
│   ├── v2/                          # New architecture
│   │   ├── __init__.py              # Public API
│   │   ├── cli.py                   # CLI commands
│   │   ├── config.py                # Configuration
│   │   │
│   │   ├── environment/             # Docker management
│   │   │   ├── __init__.py
│   │   │   ├── compose.py           # docker-compose handling
│   │   │   ├── container.py         # Container abstraction
│   │   │   └── health.py            # Health checking
│   │   │
│   │   ├── discovery/               # API discovery
│   │   │   ├── __init__.py
│   │   │   ├── openapi.py           # OpenAPI parsing
│   │   │   ├── resolver.py          # $ref resolution
│   │   │   ├── inference.py         # Resource type inference
│   │   │   └── schema.py            # Schema parsing
│   │   │
│   │   ├── generation/              # Artifact generation
│   │   │   ├── __init__.py
│   │   │   ├── actions.py           # Action generation
│   │   │   ├── invariants.py        # Invariant generation
│   │   │   ├── data.py              # Request body generation
│   │   │   └── rules.py             # CRUD rules
│   │   │
│   │   ├── exploration/             # State exploration
│   │   │   ├── __init__.py
│   │   │   ├── engine.py            # Main exploration loop
│   │   │   ├── state.py             # State management
│   │   │   ├── strategies.py        # BFS, DFS, MCTS
│   │   │   └── graph.py             # State graph
│   │   │
│   │   ├── state/                   # State backends
│   │   │   ├── __init__.py
│   │   │   ├── postgres.py          # Postgres savepoints
│   │   │   ├── tracking.py          # Resource tracking
│   │   │   └── protocol.py          # StateManager protocol
│   │   │
│   │   └── reporting/               # Output
│   │       ├── __init__.py
│   │       ├── console.py           # CLI output
│   │       ├── json.py              # JSON output
│   │       └── html.py              # HTML report
│   │
│   └── v1/                          # Legacy (keep for compatibility)
│
├── tests/v2/                        # v2 tests
│
└── examples/                        # Example projects
    └── petstore/
        ├── docker-compose.yml
        └── README.md
```

---

## Configuration File (Optional)

```yaml
# venomqa.yaml - All fields optional, sensible defaults

# Environment (auto-detected from docker-compose.yml)
compose: docker-compose.yml
api_service: api           # Auto-detect if not specified
db_service: db             # Optional: enable DB rollback

# API Discovery
openapi_path: /openapi.json  # Try /openapi.json, /swagger.json, etc.

# Exploration
strategy: bfs              # bfs, dfs, mcts
max_steps: 1000
timeout: 300               # seconds

# Invariants
invariants:
  # CRUD invariants are always enabled
  schema_validation: true  # Validate responses against schema
  custom:                  # Additional custom invariants
    - name: "balance_non_negative"
      check: "response.balance >= 0"

# Output
output: console            # console, json, html
verbose: false
```

---

## Edge Cases & Error Handling

### Environment Setup Errors

| Error | Handling |
|-------|----------|
| docker-compose.yml not found | Clear error with `venomqa init` suggestion |
| Docker not running | Detect and show installation instructions |
| Port conflict | Use random port mapping |
| Container won't start | Show container logs, suggest fixes |
| Health check timeout | Configurable timeout, show partial logs |

### API Discovery Errors

| Error | Handling |
|-------|----------|
| No OpenAPI found | Try multiple paths, then fail with list tried |
| Invalid OpenAPI | Show parsing error, suggest validator |
| Empty paths | Warn but continue (maybe webhooks only) |
| Unresolvable $ref | Skip that schema, warn |

### Exploration Errors

| Error | Handling |
|-------|----------|
| API returns 500 | Record as potential bug, continue |
| Connection refused | Retry with backoff, then fail |
| Timeout | Configurable per-request timeout |
| Invalid response | Record as schema violation |

---

## Success Metrics

### User Experience
- **Time to first bug**: < 60 seconds from `venomqa test`
- **Setup required**: Zero (just need docker-compose.yml)
- **Learning curve**: None (single command)

### Technical
- **Endpoints covered**: 100% of OpenAPI spec
- **Invariants generated**: 1-3 per endpoint
- **False positive rate**: < 5%
- **Exploration speed**: 100+ transitions/second

---

## Migration Path

### Phase 1: Core (Week 1-2)
- [ ] Environment manager (Docker compose)
- [ ] OpenAPI discovery with $ref resolution
- [ ] Basic action generation
- [ ] CRUD invariant generation
- [ ] BFS exploration
- [ ] Console reporter

### Phase 2: Polish (Week 3)
- [ ] Schema validation invariants
- [ ] Request body generation
- [ ] HTML reporter
- [ ] Better error messages
- [ ] CI integration (exit codes, JSON output)

### Phase 3: Advanced (Week 4+)
- [ ] DB state management (Postgres savepoints)
- [ ] MCTS exploration strategy
- [ ] Custom invariants in config
- [ ] Watch mode (re-run on changes)
