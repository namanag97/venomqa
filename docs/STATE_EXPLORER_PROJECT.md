# VenomQA State Explorer Project Plan

## Project Vision

The **State Explorer** is an autonomous QA agent that automatically explores application state graphs, mimicking how a skilled human QA engineer would systematically test an application. Instead of writing individual test cases, the State Explorer:

1. **Discovers** available API endpoints and actions
2. **Explores** the application by executing actions and observing state changes
3. **Maps** the entire state space into a navigable graph
4. **Identifies** issues like dead ends, unreachable states, infinite loops, and errors
5. **Reports** coverage and generates visual state diagrams

Think of it as a robot that walks through every possible path in your application, recording what it finds and flagging anything suspicious.

### Key Differentiators

- **Zero Configuration**: Point it at an OpenAPI spec or base URL and it starts exploring
- **Intelligent State Detection**: Infers application state from response patterns
- **Exhaustive Coverage**: Systematically explores BFS/DFS to find edge cases humans miss
- **Visual Output**: Generates state diagrams showing all discovered paths
- **Issue Detection**: Automatically flags errors, cycles, dead ends, and anomalies

---

## Core Components

### 1. StateExplorer
**The main orchestrator and public API entry point.**

Coordinates all other components, manages the exploration lifecycle, and provides the user-facing interface. Handles configuration, starts/stops exploration, and aggregates results.

```python
class StateExplorer:
    """Main entry point for state exploration."""

    def __init__(
        self,
        base_url: str,
        openapi_spec: Optional[str] = None,
        max_depth: int = 10,
        max_states: int = 1000,
        strategy: ExplorationStrategy = ExplorationStrategy.BFS,
        auth: Optional[AuthConfig] = None,
    ): ...

    def explore(self) -> ExplorationResult: ...
    def explore_async(self) -> AsyncIterator[ExplorationProgress]: ...
    def resume(self, checkpoint: Checkpoint) -> ExplorationResult: ...
```

### 2. APIDiscoverer
**Finds available endpoints and actions.**

Parses OpenAPI/Swagger specs or crawls the application to discover available endpoints. Extracts parameter schemas, request/response models, and authentication requirements.

```python
class APIDiscoverer:
    """Discovers API endpoints from specs or crawling."""

    def from_openapi(self, spec_path: str) -> List[Endpoint]: ...
    def from_crawl(self, base_url: str) -> List[Endpoint]: ...
    def merge_discoveries(self, *discoveries: List[Endpoint]) -> List[Endpoint]: ...
```

### 3. StateDetector
**Infers current application state from responses.**

Analyzes HTTP responses to determine what "state" the application is in. Uses heuristics, response fingerprinting, and configurable rules to identify distinct states.

```python
class StateDetector:
    """Detects and fingerprints application states."""

    def detect_state(self, response: Response, context: Context) -> State: ...
    def fingerprint(self, response: Response) -> StateFingerprint: ...
    def are_equivalent(self, state1: State, state2: State) -> bool: ...
    def register_detector(self, detector: CustomDetector) -> None: ...
```

### 4. ActionGenerator
**Generates valid requests for exploration.**

Creates HTTP requests with valid payloads based on endpoint schemas. Handles parameter generation, authentication injection, and request variation.

```python
class ActionGenerator:
    """Generates actions (requests) for exploration."""

    def generate_actions(self, endpoint: Endpoint, state: State) -> List[Action]: ...
    def generate_payload(self, schema: JSONSchema) -> Dict[str, Any]: ...
    def add_generator(self, field_type: str, generator: Callable): ...
```

### 5. StateGraph
**Data structure for states and transitions.**

A directed graph where nodes are states and edges are transitions (actions). Supports efficient traversal, cycle detection, and serialization.

```python
class StateGraph:
    """Graph data structure for state exploration."""

    def add_state(self, state: State) -> StateId: ...
    def add_transition(self, from_state: StateId, to_state: StateId, action: Action) -> None: ...
    def get_neighbors(self, state_id: StateId) -> List[Transition]: ...
    def find_path(self, from_state: StateId, to_state: StateId) -> Optional[List[Transition]]: ...
    def detect_cycles(self) -> List[Cycle]: ...
    def to_dict(self) -> Dict: ...
    def from_dict(self, data: Dict) -> "StateGraph": ...
```

### 6. ExplorationEngine
**Implements exploration strategies.**

Executes BFS, DFS, or hybrid exploration through the state space. Manages the exploration frontier, tracks visited states, and handles backtracking.

```python
class ExplorationEngine:
    """Engine for exploring state space."""

    def explore_bfs(self, start_state: State) -> ExplorationResult: ...
    def explore_dfs(self, start_state: State, max_depth: int) -> ExplorationResult: ...
    def explore_random(self, start_state: State, iterations: int) -> ExplorationResult: ...
    def explore_guided(self, start_state: State, heuristic: Callable) -> ExplorationResult: ...
```

### 7. CoverageTracker
**Tracks exploration coverage metrics.**

Monitors which endpoints, states, and transitions have been explored. Calculates coverage percentages and identifies unexplored areas.

```python
class CoverageTracker:
    """Tracks exploration coverage."""

    def record_visit(self, state: State, action: Action) -> None: ...
    def get_endpoint_coverage(self) -> Dict[str, float]: ...
    def get_state_coverage(self) -> float: ...
    def get_transition_coverage(self) -> float: ...
    def get_unexplored(self) -> List[Endpoint]: ...
    def to_report(self) -> CoverageReport: ...
```

### 8. GraphVisualizer
**Renders state diagrams.**

Generates visual representations of the state graph in various formats (PNG, SVG, DOT, HTML interactive).

```python
class GraphVisualizer:
    """Visualizes state graphs."""

    def render_png(self, graph: StateGraph, output_path: str) -> None: ...
    def render_svg(self, graph: StateGraph, output_path: str) -> None: ...
    def render_dot(self, graph: StateGraph) -> str: ...
    def render_html(self, graph: StateGraph, output_path: str) -> None: ...
    def render_mermaid(self, graph: StateGraph) -> str: ...
```

### 9. IssueDetector
**Finds errors, dead ends, and anomalies.**

Analyzes the exploration results to identify potential issues: HTTP errors, dead ends (states with no outgoing transitions), unreachable states, infinite loops, and suspicious patterns.

```python
class IssueDetector:
    """Detects issues during exploration."""

    def detect_errors(self, graph: StateGraph) -> List[Issue]: ...
    def detect_dead_ends(self, graph: StateGraph) -> List[Issue]: ...
    def detect_cycles(self, graph: StateGraph) -> List[Issue]: ...
    def detect_orphans(self, graph: StateGraph) -> List[Issue]: ...
    def detect_anomalies(self, graph: StateGraph) -> List[Issue]: ...
    def all_issues(self, graph: StateGraph) -> List[Issue]: ...
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACE                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        StateExplorer (Main API)                      │   │
│  │   explorer = StateExplorer(base_url, openapi_spec)                   │   │
│  │   result = explorer.explore()                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DISCOVERY LAYER                                   │
│  ┌────────────────────┐    ┌────────────────────┐                          │
│  │   APIDiscoverer    │───▶│     Endpoint[]     │                          │
│  │  ┌──────────────┐  │    │  - path            │                          │
│  │  │ OpenAPI      │  │    │  - method          │                          │
│  │  │ Parser       │  │    │  - parameters      │                          │
│  │  ├──────────────┤  │    │  - request_body    │                          │
│  │  │ Crawler      │  │    │  - responses       │                          │
│  │  └──────────────┘  │    └────────────────────┘                          │
│  └────────────────────┘                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EXPLORATION LAYER                                  │
│                                                                              │
│  ┌────────────────────┐         ┌────────────────────┐                     │
│  │  ExplorationEngine │◀───────▶│    StateGraph      │                     │
│  │  ┌──────────────┐  │         │  ┌──────────────┐  │                     │
│  │  │ BFS Strategy │  │         │  │ States (V)   │  │                     │
│  │  ├──────────────┤  │         │  ├──────────────┤  │                     │
│  │  │ DFS Strategy │  │         │  │Transitions(E)│  │                     │
│  │  ├──────────────┤  │         │  └──────────────┘  │                     │
│  │  │ Random Walk  │  │         └────────────────────┘                     │
│  │  └──────────────┘  │                   ▲                                 │
│  └────────────────────┘                   │                                 │
│            │                              │                                 │
│            ▼                              │                                 │
│  ┌────────────────────┐         ┌────────────────────┐                     │
│  │  ActionGenerator   │────────▶│   StateDetector    │                     │
│  │  - generate_payload│         │  - fingerprint     │                     │
│  │  - inject_auth     │         │  - detect_state    │                     │
│  │  - vary_params     │         │  - classify        │                     │
│  └────────────────────┘         └────────────────────┘                     │
│            │                              │                                 │
│            ▼                              ▼                                 │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │                         HTTP Client (httpx)                         │   │
│  │   Execute requests, capture responses, handle retries              │   │
│  └────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            ANALYSIS LAYER                                    │
│                                                                              │
│  ┌────────────────────┐    ┌────────────────────┐    ┌──────────────────┐  │
│  │   IssueDetector    │    │  CoverageTracker   │    │ GraphVisualizer  │  │
│  │  ┌──────────────┐  │    │  ┌──────────────┐  │    │ ┌──────────────┐ │  │
│  │  │ Error Check  │  │    │  │ Endpoint %   │  │    │ │ PNG/SVG      │ │  │
│  │  ├──────────────┤  │    │  ├──────────────┤  │    │ ├──────────────┤ │  │
│  │  │ Dead Ends    │  │    │  │ State %      │  │    │ │ DOT/Mermaid  │ │  │
│  │  ├──────────────┤  │    │  ├──────────────┤  │    │ ├──────────────┤ │  │
│  │  │ Cycles       │  │    │  │ Transition % │  │    │ │ Interactive  │ │  │
│  │  ├──────────────┤  │    │  └──────────────┘  │    │ │ HTML         │ │  │
│  │  │ Orphans      │  │    └────────────────────┘    │ └──────────────┘ │  │
│  │  └──────────────┘  │                              └──────────────────┘  │
│  └────────────────────┘                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             OUTPUT LAYER                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        ExplorationResult                             │   │
│  │   - graph: StateGraph                                                │   │
│  │   - coverage: CoverageReport                                         │   │
│  │   - issues: List[Issue]                                              │   │
│  │   - duration: timedelta                                              │   │
│  │   - metadata: Dict                                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Interaction Flow

```
1. START
     │
     ▼
2. APIDiscoverer parses OpenAPI spec
     │
     ▼
3. ActionGenerator creates initial actions
     │
     ▼
4. ExplorationEngine begins exploration loop:
     │
     ├──▶ Execute action via HTTP client
     │         │
     │         ▼
     │    StateDetector analyzes response
     │         │
     │         ▼
     │    StateGraph updated with new state/transition
     │         │
     │         ▼
     │    CoverageTracker records visit
     │         │
     │         ▼
     │    ActionGenerator creates next actions
     │         │
     └────────┘ (loop until done)
     │
     ▼
5. IssueDetector analyzes final graph
     │
     ▼
6. GraphVisualizer renders output
     │
     ▼
7. Return ExplorationResult
```

---

## Data Models

```python
"""
Data models for the State Explorer.

Located at: venomqa/explorer/models.py
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field
import hashlib
import json


# ============================================================================
# Enums
# ============================================================================

class HttpMethod(str, Enum):
    """HTTP methods supported by the explorer."""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class ExplorationStrategy(str, Enum):
    """Exploration strategies."""
    BFS = "bfs"           # Breadth-first search
    DFS = "dfs"           # Depth-first search
    RANDOM = "random"     # Random walk
    GUIDED = "guided"     # Heuristic-guided


class IssueType(str, Enum):
    """Types of issues that can be detected."""
    HTTP_ERROR = "http_error"           # 4xx/5xx responses
    DEAD_END = "dead_end"               # State with no outgoing transitions
    UNREACHABLE = "unreachable"         # State that can't be reached
    INFINITE_LOOP = "infinite_loop"     # Cycle that can't be escaped
    TIMEOUT = "timeout"                 # Request timeout
    VALIDATION_ERROR = "validation"     # Schema validation failure
    ANOMALY = "anomaly"                 # Unusual behavior pattern
    SECURITY = "security"               # Security concern


class IssueSeverity(str, Enum):
    """Issue severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class StateType(str, Enum):
    """Classification of state types."""
    INITIAL = "initial"         # Starting state
    NORMAL = "normal"           # Regular application state
    ERROR = "error"             # Error state
    TERMINAL = "terminal"       # End state (no outgoing transitions)
    AUTHENTICATED = "authenticated"   # User is logged in
    UNAUTHENTICATED = "unauthenticated"  # User is not logged in


# ============================================================================
# Core Models
# ============================================================================

class StateFingerprint(BaseModel):
    """Unique fingerprint for identifying equivalent states."""

    status_code: int
    response_schema_hash: str
    key_fields: Dict[str, Any] = Field(default_factory=dict)
    auth_state: Optional[str] = None

    def __hash__(self) -> int:
        return hash((
            self.status_code,
            self.response_schema_hash,
            tuple(sorted(self.key_fields.items())),
            self.auth_state,
        ))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, StateFingerprint):
            return False
        return (
            self.status_code == other.status_code
            and self.response_schema_hash == other.response_schema_hash
            and self.key_fields == other.key_fields
            and self.auth_state == other.auth_state
        )


class State(BaseModel):
    """Represents a unique application state."""

    id: str = Field(description="Unique state identifier")
    name: str = Field(description="Human-readable state name")
    fingerprint: StateFingerprint
    state_type: StateType = StateType.NORMAL

    # State data
    response_data: Optional[Dict[str, Any]] = None
    headers: Dict[str, str] = Field(default_factory=dict)

    # Metadata
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    visit_count: int = 0

    # Context
    context: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        frozen = True  # States are immutable once created

    @classmethod
    def create_initial(cls) -> "State":
        """Create the initial/root state."""
        return cls(
            id="state_initial",
            name="Initial State",
            fingerprint=StateFingerprint(
                status_code=0,
                response_schema_hash="",
            ),
            state_type=StateType.INITIAL,
        )

    def __hash__(self) -> int:
        return hash(self.id)


class Action(BaseModel):
    """Represents an action that causes a state transition."""

    id: str = Field(description="Unique action identifier")
    name: str = Field(description="Human-readable action name")

    # HTTP details
    method: HttpMethod
    path: str
    headers: Dict[str, str] = Field(default_factory=dict)
    query_params: Dict[str, Any] = Field(default_factory=dict)
    body: Optional[Dict[str, Any]] = None

    # Source endpoint
    endpoint_id: Optional[str] = None

    # Execution details
    timeout: float = 30.0
    retries: int = 0

    # Metadata
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    def to_request_kwargs(self, base_url: str) -> Dict[str, Any]:
        """Convert to httpx request kwargs."""
        url = f"{base_url.rstrip('/')}/{self.path.lstrip('/')}"
        kwargs = {
            "method": self.method.value,
            "url": url,
            "headers": self.headers,
            "params": self.query_params,
            "timeout": self.timeout,
        }
        if self.body is not None:
            kwargs["json"] = self.body
        return kwargs


class Transition(BaseModel):
    """Represents a transition between states."""

    id: str = Field(description="Unique transition identifier")
    from_state_id: str
    to_state_id: str
    action: Action

    # Response details
    status_code: int
    response_time_ms: float
    response_body: Optional[Dict[str, Any]] = None
    response_headers: Dict[str, str] = Field(default_factory=dict)

    # Metadata
    executed_at: datetime = Field(default_factory=datetime.utcnow)
    execution_count: int = 1

    # Error info (if any)
    error: Optional[str] = None

    def is_successful(self) -> bool:
        """Check if the transition resulted in a successful response."""
        return 200 <= self.status_code < 400

    def is_error(self) -> bool:
        """Check if the transition resulted in an error."""
        return self.status_code >= 400 or self.error is not None


class Endpoint(BaseModel):
    """Represents a discovered API endpoint."""

    id: str
    path: str
    method: HttpMethod

    # Schema information
    parameters: List[Dict[str, Any]] = Field(default_factory=list)
    request_body_schema: Optional[Dict[str, Any]] = None
    response_schemas: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    # Metadata
    summary: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    # Requirements
    requires_auth: bool = False
    deprecated: bool = False


# ============================================================================
# Issue Model
# ============================================================================

class Issue(BaseModel):
    """Represents an issue detected during exploration."""

    id: str
    issue_type: IssueType
    severity: IssueSeverity
    title: str
    description: str

    # Location
    state_id: Optional[str] = None
    transition_id: Optional[str] = None
    endpoint_path: Optional[str] = None

    # Evidence
    evidence: Dict[str, Any] = Field(default_factory=dict)
    reproduction_steps: List[str] = Field(default_factory=list)

    # Metadata
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    tags: List[str] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "type": self.issue_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "state_id": self.state_id,
            "transition_id": self.transition_id,
            "endpoint_path": self.endpoint_path,
            "evidence": self.evidence,
            "reproduction_steps": self.reproduction_steps,
            "detected_at": self.detected_at.isoformat(),
            "tags": self.tags,
        }


# ============================================================================
# Coverage Model
# ============================================================================

class CoverageReport(BaseModel):
    """Comprehensive coverage report."""

    # Endpoint coverage
    total_endpoints: int = 0
    visited_endpoints: int = 0
    endpoint_coverage_percent: float = 0.0
    unvisited_endpoints: List[str] = Field(default_factory=list)

    # State coverage
    total_states: int = 0
    unique_states: int = 0

    # Transition coverage
    total_transitions: int = 0
    unique_transitions: int = 0

    # Method coverage
    method_coverage: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    # Path coverage
    paths_discovered: List[str] = Field(default_factory=list)

    # Time spent
    exploration_duration: timedelta = timedelta()

    def summary(self) -> str:
        """Generate a human-readable summary."""
        return f"""
Coverage Report
===============
Endpoints: {self.visited_endpoints}/{self.total_endpoints} ({self.endpoint_coverage_percent:.1f}%)
States discovered: {self.unique_states}
Transitions recorded: {self.unique_transitions}
Duration: {self.exploration_duration}
        """.strip()


# ============================================================================
# Exploration Result Model
# ============================================================================

class ExplorationResult(BaseModel):
    """Complete result of a state exploration session."""

    # Core data
    states: List[State] = Field(default_factory=list)
    transitions: List[Transition] = Field(default_factory=list)
    issues: List[Issue] = Field(default_factory=list)

    # Reports
    coverage: CoverageReport = Field(default_factory=CoverageReport)

    # Metadata
    base_url: str
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    strategy: ExplorationStrategy = ExplorationStrategy.BFS

    # Configuration used
    config: Dict[str, Any] = Field(default_factory=dict)

    # Stats
    total_requests: int = 0
    failed_requests: int = 0

    @property
    def duration(self) -> timedelta:
        """Calculate exploration duration."""
        if self.completed_at:
            return self.completed_at - self.started_at
        return timedelta()

    @property
    def success_rate(self) -> float:
        """Calculate request success rate."""
        if self.total_requests == 0:
            return 0.0
        return (self.total_requests - self.failed_requests) / self.total_requests * 100

    def get_critical_issues(self) -> List[Issue]:
        """Get only critical and high severity issues."""
        return [
            issue for issue in self.issues
            if issue.severity in (IssueSeverity.CRITICAL, IssueSeverity.HIGH)
        ]

    def visualize(self, output_path: str, format: str = "png") -> None:
        """Generate a visualization of the state graph.

        This is a convenience method that delegates to GraphVisualizer.
        """
        from venomqa.explorer.visualizer import GraphVisualizer
        visualizer = GraphVisualizer()
        graph = self._to_state_graph()

        if format == "png":
            visualizer.render_png(graph, output_path)
        elif format == "svg":
            visualizer.render_svg(graph, output_path)
        elif format == "html":
            visualizer.render_html(graph, output_path)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _to_state_graph(self) -> "StateGraph":
        """Convert result to StateGraph for visualization."""
        from venomqa.explorer.graph import StateGraph
        graph = StateGraph()
        for state in self.states:
            graph.add_state(state)
        for transition in self.transitions:
            graph.add_transition(
                transition.from_state_id,
                transition.to_state_id,
                transition.action,
            )
        return graph

    def to_json(self, path: Optional[str] = None) -> str:
        """Export result to JSON."""
        data = self.model_dump(mode="json")
        json_str = json.dumps(data, indent=2, default=str)
        if path:
            with open(path, "w") as f:
                f.write(json_str)
        return json_str

    @classmethod
    def from_json(cls, path: str) -> "ExplorationResult":
        """Load result from JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls.model_validate(data)


# ============================================================================
# Configuration Models
# ============================================================================

class AuthConfig(BaseModel):
    """Authentication configuration."""

    type: str = "bearer"  # bearer, basic, api_key, oauth2
    token: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    api_key_header: str = "X-API-Key"


class ExplorationConfig(BaseModel):
    """Configuration for state exploration."""

    base_url: str
    openapi_spec: Optional[str] = None

    # Exploration limits
    max_depth: int = 10
    max_states: int = 1000
    max_transitions: int = 5000
    max_time_seconds: int = 3600  # 1 hour

    # Strategy
    strategy: ExplorationStrategy = ExplorationStrategy.BFS

    # Authentication
    auth: Optional[AuthConfig] = None

    # Request settings
    request_timeout: float = 30.0
    request_delay_ms: int = 100  # Delay between requests
    max_retries: int = 3

    # State detection
    state_equivalence_threshold: float = 0.9

    # Filtering
    include_paths: List[str] = Field(default_factory=list)  # Regex patterns
    exclude_paths: List[str] = Field(default_factory=list)  # Regex patterns
    include_methods: List[HttpMethod] = Field(
        default_factory=lambda: list(HttpMethod)
    )

    # Output
    output_dir: str = "./exploration_results"
    generate_visualization: bool = True
    visualization_format: str = "png"


# ============================================================================
# Progress Tracking Models
# ============================================================================

class ExplorationProgress(BaseModel):
    """Progress update during exploration."""

    states_discovered: int
    transitions_recorded: int
    current_depth: int
    current_state: Optional[str] = None
    current_action: Optional[str] = None
    issues_found: int
    elapsed_time: timedelta
    estimated_remaining: Optional[timedelta] = None
    percent_complete: float = 0.0


class Checkpoint(BaseModel):
    """Checkpoint for resumable exploration."""

    graph_state: Dict[str, Any]
    frontier: List[str]  # State IDs to explore
    visited: Set[str]    # Already visited state IDs
    config: Dict[str, Any]
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def save(self, path: str) -> None:
        """Save checkpoint to file."""
        with open(path, "w") as f:
            json.dump(self.model_dump(mode="json"), f, default=str)

    @classmethod
    def load(cls, path: str) -> "Checkpoint":
        """Load checkpoint from file."""
        with open(path) as f:
            data = json.load(f)
        return cls.model_validate(data)
```

---

## Implementation Phases

### Phase 1: Foundation (Week 1-2)
**Goal**: Core data structures and state management

| Task | Description | Complexity |
|------|-------------|------------|
| 1.1 | Create `models.py` with all Pydantic models | Medium |
| 1.2 | Implement `StateGraph` with add/query operations | Medium |
| 1.3 | Add cycle detection algorithm (Tarjan's) | Medium |
| 1.4 | Implement path finding (Dijkstra/BFS) | Low |
| 1.5 | Add serialization (to_dict, from_dict, JSON) | Low |
| 1.6 | Write comprehensive unit tests | Medium |

**Deliverables**:
- `venomqa/explorer/models.py`
- `venomqa/explorer/graph.py`
- `tests/explorer/test_models.py`
- `tests/explorer/test_graph.py`

### Phase 2: API Discovery (Week 2-3)
**Goal**: Parse OpenAPI specs and discover endpoints

| Task | Description | Complexity |
|------|-------------|------------|
| 2.1 | OpenAPI 3.0 parser | Medium |
| 2.2 | OpenAPI 2.0 (Swagger) parser | Medium |
| 2.3 | Endpoint extraction with schemas | Medium |
| 2.4 | Parameter and request body extraction | Medium |
| 2.5 | Response schema extraction | Low |
| 2.6 | Basic crawling fallback (optional) | High |
| 2.7 | Unit tests for parsers | Medium |

**Deliverables**:
- `venomqa/explorer/discovery.py`
- `venomqa/explorer/openapi_parser.py`
- `tests/explorer/test_discovery.py`

### Phase 3: State Detection (Week 3-4)
**Goal**: Detect and fingerprint application states

| Task | Description | Complexity |
|------|-------------|------------|
| 3.1 | Response fingerprinting algorithm | Medium |
| 3.2 | State equivalence detection | Medium |
| 3.3 | State classification (normal, error, auth) | Low |
| 3.4 | Custom detector registration | Low |
| 3.5 | Context tracking (session, auth state) | Medium |
| 3.6 | Unit tests | Medium |

**Deliverables**:
- `venomqa/explorer/state_detector.py`
- `tests/explorer/test_state_detector.py`

### Phase 4: Exploration Engine (Week 4-6)
**Goal**: Core exploration logic with BFS/DFS

| Task | Description | Complexity |
|------|-------------|------------|
| 4.1 | Action generator with payload generation | High |
| 4.2 | HTTP execution layer (httpx integration) | Medium |
| 4.3 | BFS exploration implementation | Medium |
| 4.4 | DFS exploration implementation | Medium |
| 4.5 | Random walk strategy | Low |
| 4.6 | Frontier management | Medium |
| 4.7 | Backtracking logic | Medium |
| 4.8 | Progress tracking and callbacks | Low |
| 4.9 | Checkpointing for resume | Medium |
| 4.10 | Integration tests | High |

**Deliverables**:
- `venomqa/explorer/action_generator.py`
- `venomqa/explorer/engine.py`
- `venomqa/explorer/strategies/bfs.py`
- `venomqa/explorer/strategies/dfs.py`
- `tests/explorer/test_engine.py`

### Phase 5: Issue Detection (Week 6-7)
**Goal**: Automatically detect problems

| Task | Description | Complexity |
|------|-------------|------------|
| 5.1 | HTTP error detection (4xx, 5xx) | Low |
| 5.2 | Dead end detection | Low |
| 5.3 | Unreachable state detection | Medium |
| 5.4 | Infinite loop detection | Medium |
| 5.5 | Anomaly detection (timing, patterns) | High |
| 5.6 | Security issue hints | Medium |
| 5.7 | Issue severity classification | Low |
| 5.8 | Reproduction step generation | Medium |
| 5.9 | Unit tests | Medium |

**Deliverables**:
- `venomqa/explorer/issue_detector.py`
- `tests/explorer/test_issue_detector.py`

### Phase 6: Visualization & Reporting (Week 7-8)
**Goal**: Generate visual outputs and reports

| Task | Description | Complexity |
|------|-------------|------------|
| 6.1 | DOT format generation | Low |
| 6.2 | PNG/SVG rendering (graphviz) | Medium |
| 6.3 | Interactive HTML visualization | High |
| 6.4 | Mermaid diagram generation | Low |
| 6.5 | Coverage report generation | Medium |
| 6.6 | JSON/HTML export | Low |
| 6.7 | CLI progress display | Medium |
| 6.8 | Unit tests | Medium |

**Deliverables**:
- `venomqa/explorer/visualizer.py`
- `venomqa/explorer/reports.py`
- `tests/explorer/test_visualizer.py`

### Phase 7: Integration (Week 8-9)
**Goal**: Integrate with VenomQA ecosystem

| Task | Description | Complexity |
|------|-------------|------------|
| 7.1 | StateExplorer main class | Medium |
| 7.2 | CLI commands (`venomqa explore`) | Medium |
| 7.3 | YAML configuration support | Low |
| 7.4 | Integration with existing reporters | Medium |
| 7.5 | Plugin hooks for custom extensions | Medium |
| 7.6 | Documentation | Medium |
| 7.7 | End-to-end tests with sample apps | High |

**Deliverables**:
- `venomqa/explorer/__init__.py`
- `venomqa/explorer/explorer.py`
- CLI integration
- Documentation
- E2E tests

---

## File Structure

```
venomqa/
└── explorer/
    ├── __init__.py              # Public API exports
    ├── explorer.py              # StateExplorer main class
    ├── models.py                # All Pydantic/dataclass models
    ├── graph.py                 # StateGraph implementation
    ├── discovery.py             # APIDiscoverer
    ├── openapi_parser.py        # OpenAPI spec parsing
    ├── state_detector.py        # StateDetector
    ├── action_generator.py      # ActionGenerator
    ├── engine.py                # ExplorationEngine
    ├── issue_detector.py        # IssueDetector
    ├── coverage.py              # CoverageTracker
    ├── visualizer.py            # GraphVisualizer
    ├── reports.py               # Report generation
    ├── strategies/
    │   ├── __init__.py
    │   ├── base.py              # Base strategy interface
    │   ├── bfs.py               # BFS implementation
    │   ├── dfs.py               # DFS implementation
    │   └── random.py            # Random walk
    ├── detectors/
    │   ├── __init__.py
    │   ├── base.py              # Base detector interface
    │   ├── http_error.py        # HTTP error detection
    │   ├── dead_end.py          # Dead end detection
    │   ├── cycle.py             # Cycle detection
    │   └── anomaly.py           # Anomaly detection
    └── utils/
        ├── __init__.py
        ├── fingerprint.py       # Response fingerprinting
        ├── payload.py           # Payload generation
        └── http.py              # HTTP utilities

tests/
└── explorer/
    ├── __init__.py
    ├── conftest.py              # Shared fixtures
    ├── test_models.py
    ├── test_graph.py
    ├── test_discovery.py
    ├── test_state_detector.py
    ├── test_action_generator.py
    ├── test_engine.py
    ├── test_issue_detector.py
    ├── test_visualizer.py
    └── test_integration.py      # E2E tests
```

---

## API Design

### Basic Usage

```python
from venomqa.explorer import StateExplorer

# Minimal configuration - just point to your API
explorer = StateExplorer(
    base_url="http://localhost:8000",
    openapi_spec="./openapi.json"
)

# Run exploration
result = explorer.explore()

# Check results
print(f"States discovered: {len(result.states)}")
print(f"Transitions: {len(result.transitions)}")
print(f"Issues found: {len(result.issues)}")

# Visualize
result.visualize("state_map.png")

# Get coverage report
print(result.coverage.summary())

# Export to JSON
result.to_json("exploration_result.json")
```

### With Authentication

```python
from venomqa.explorer import StateExplorer, AuthConfig

explorer = StateExplorer(
    base_url="http://localhost:8000",
    openapi_spec="./openapi.json",
    auth=AuthConfig(
        type="bearer",
        token="your-jwt-token"
    )
)

result = explorer.explore()
```

### With Custom Configuration

```python
from venomqa.explorer import (
    StateExplorer,
    ExplorationConfig,
    ExplorationStrategy,
)

config = ExplorationConfig(
    base_url="http://localhost:8000",
    openapi_spec="./openapi.json",
    strategy=ExplorationStrategy.DFS,
    max_depth=15,
    max_states=500,
    max_time_seconds=1800,  # 30 minutes
    request_delay_ms=50,
    exclude_paths=[r"/admin/.*", r"/internal/.*"],
    include_methods=["GET", "POST"],
)

explorer = StateExplorer.from_config(config)
result = explorer.explore()
```

### Async Exploration with Progress

```python
import asyncio
from venomqa.explorer import StateExplorer

async def explore_with_progress():
    explorer = StateExplorer(
        base_url="http://localhost:8000",
        openapi_spec="./openapi.json"
    )

    async for progress in explorer.explore_async():
        print(f"Progress: {progress.percent_complete:.1f}%")
        print(f"States: {progress.states_discovered}")
        print(f"Current: {progress.current_action}")

        if progress.percent_complete >= 100:
            return progress.result

result = asyncio.run(explore_with_progress())
```

### Resume from Checkpoint

```python
from venomqa.explorer import StateExplorer, Checkpoint

# First exploration (interrupted)
explorer = StateExplorer(base_url="http://localhost:8000")
try:
    result = explorer.explore()
except KeyboardInterrupt:
    explorer.save_checkpoint("checkpoint.json")
    print("Saved checkpoint, can resume later")

# Resume later
checkpoint = Checkpoint.load("checkpoint.json")
explorer = StateExplorer(base_url="http://localhost:8000")
result = explorer.resume(checkpoint)
```

### Custom State Detection

```python
from venomqa.explorer import StateExplorer
from venomqa.explorer.state_detector import StateDetector, CustomDetector

class MyCustomDetector(CustomDetector):
    def detect(self, response, context):
        # Custom logic to determine state
        if "logged_in" in response.json():
            return "authenticated"
        return None

explorer = StateExplorer(base_url="http://localhost:8000")
explorer.state_detector.register_detector(MyCustomDetector())
result = explorer.explore()
```

### CLI Usage

```bash
# Basic exploration
venomqa explore --url http://localhost:8000 --spec openapi.json

# With options
venomqa explore \
    --url http://localhost:8000 \
    --spec openapi.json \
    --strategy dfs \
    --max-depth 20 \
    --output ./results \
    --format html \
    --auth-token "Bearer xxx"

# Resume from checkpoint
venomqa explore --resume checkpoint.json

# Generate visualization only from previous results
venomqa explore visualize ./results/exploration.json --format svg
```

### Integration with VenomQA Journeys

```python
from venomqa import Journey
from venomqa.explorer import StateExplorer

class ExploratoryTestJourney(Journey):
    """Run state exploration as part of a journey."""

    async def run(self, ctx):
        explorer = StateExplorer(
            base_url=ctx.config.base_url,
            openapi_spec=ctx.config.openapi_spec,
        )

        result = await explorer.explore_async_complete()

        # Assert no critical issues
        critical_issues = result.get_critical_issues()
        assert len(critical_issues) == 0, f"Found issues: {critical_issues}"

        # Assert minimum coverage
        assert result.coverage.endpoint_coverage_percent >= 80, \
            f"Coverage too low: {result.coverage.endpoint_coverage_percent}%"

        # Store result for reporting
        ctx.store("exploration_result", result)
```

---

## Success Criteria

### Functional Requirements

1. **Discovery**
   - [ ] Successfully parse OpenAPI 3.0 specs
   - [ ] Successfully parse OpenAPI 2.0 (Swagger) specs
   - [ ] Extract all endpoints with full metadata
   - [ ] Handle $ref and schema composition

2. **Exploration**
   - [ ] Complete BFS exploration of simple APIs (< 20 endpoints)
   - [ ] Complete DFS exploration with configurable depth
   - [ ] Handle authentication (Bearer, Basic, API Key)
   - [ ] Generate valid payloads from schemas
   - [ ] Track and avoid infinite loops

3. **State Detection**
   - [ ] Correctly identify distinct application states
   - [ ] Handle state equivalence (same logical state, different data)
   - [ ] Detect authentication state changes
   - [ ] Support custom state detectors

4. **Issue Detection**
   - [ ] Detect all 4xx/5xx HTTP errors
   - [ ] Identify dead-end states
   - [ ] Find unreachable states
   - [ ] Detect potential infinite loops
   - [ ] Generate reproduction steps

5. **Visualization**
   - [ ] Generate PNG state diagrams
   - [ ] Generate SVG state diagrams
   - [ ] Generate interactive HTML views
   - [ ] Export to Mermaid format

6. **Reporting**
   - [ ] Calculate endpoint coverage percentage
   - [ ] Track state and transition coverage
   - [ ] Export results to JSON
   - [ ] Generate human-readable summaries

### Performance Requirements

- [ ] Process 100+ endpoint APIs in < 5 minutes
- [ ] Handle 1000+ states without memory issues
- [ ] Support request rate limiting
- [ ] Checkpoint every 100 transitions for recovery

### Quality Requirements

- [ ] 90%+ test coverage for core modules
- [ ] Type hints on all public APIs
- [ ] Comprehensive docstrings
- [ ] Example code in documentation

### Integration Requirements

- [ ] CLI command `venomqa explore` works
- [ ] Can be used within VenomQA journeys
- [ ] Compatible with existing reporters
- [ ] YAML configuration support

---

## Dependencies

### Required Dependencies

```toml
[project.dependencies]
# Already in VenomQA
httpx = ">=0.24.0"
pydantic = ">=2.0.0"
rich = ">=13.0.0"
pyyaml = ">=6.0"

# New dependencies
graphviz = ">=0.20"          # DOT rendering
networkx = ">=3.0"            # Graph algorithms
openapi-spec-validator = ">=0.6.0"  # OpenAPI validation
jsonschema = ">=4.0"          # JSON Schema validation
```

### Optional Dependencies

```toml
[project.optional-dependencies]
explorer = [
    "pyvis>=0.3.0",           # Interactive HTML graphs
    "hypothesis>=6.0",        # Property-based payload generation
    "faker>=18.0",            # Realistic data generation
]
```

### Development Dependencies

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "pytest-httpx>=0.22",
    "respx>=0.20",            # HTTP mocking
    "coverage>=7.0",
]
```

---

## Task Breakdown

### Phase 1: Foundation
| ID | Task | Est. Hours | Priority | Dependencies |
|----|------|------------|----------|--------------|
| 1.1 | Define all Pydantic models in `models.py` | 4 | P0 | None |
| 1.2 | Implement `StateGraph.add_state()` | 2 | P0 | 1.1 |
| 1.3 | Implement `StateGraph.add_transition()` | 2 | P0 | 1.1, 1.2 |
| 1.4 | Implement `StateGraph.get_neighbors()` | 1 | P0 | 1.2, 1.3 |
| 1.5 | Implement cycle detection (Tarjan's SCC) | 4 | P1 | 1.2, 1.3 |
| 1.6 | Implement path finding (BFS shortest path) | 2 | P1 | 1.2, 1.3 |
| 1.7 | JSON serialization/deserialization | 2 | P1 | 1.1 |
| 1.8 | Unit tests for models | 3 | P0 | 1.1 |
| 1.9 | Unit tests for graph | 4 | P0 | 1.2-1.6 |

### Phase 2: API Discovery
| ID | Task | Est. Hours | Priority | Dependencies |
|----|------|------------|----------|--------------|
| 2.1 | OpenAPI 3.0 spec loading | 2 | P0 | None |
| 2.2 | Parse paths and operations | 4 | P0 | 2.1 |
| 2.3 | Extract parameters (path, query, header) | 3 | P0 | 2.2 |
| 2.4 | Extract request body schemas | 3 | P0 | 2.2 |
| 2.5 | Handle $ref resolution | 4 | P0 | 2.2 |
| 2.6 | Extract response schemas | 2 | P1 | 2.2 |
| 2.7 | OpenAPI 2.0 (Swagger) support | 4 | P1 | 2.2-2.5 |
| 2.8 | Unit tests for discovery | 4 | P0 | 2.1-2.6 |

### Phase 3: State Detection
| ID | Task | Est. Hours | Priority | Dependencies |
|----|------|------------|----------|--------------|
| 3.1 | Response fingerprinting algorithm | 4 | P0 | 1.1 |
| 3.2 | State equivalence comparison | 3 | P0 | 3.1 |
| 3.3 | State type classification | 2 | P1 | 3.1 |
| 3.4 | Custom detector registration | 2 | P1 | 3.1 |
| 3.5 | Auth state tracking | 3 | P1 | 3.1 |
| 3.6 | Unit tests for state detector | 3 | P0 | 3.1-3.3 |

### Phase 4: Exploration Engine
| ID | Task | Est. Hours | Priority | Dependencies |
|----|------|------------|----------|--------------|
| 4.1 | Payload generation from JSON Schema | 6 | P0 | 2.4 |
| 4.2 | Action generator implementation | 4 | P0 | 4.1, 2.2 |
| 4.3 | HTTP execution layer | 4 | P0 | None |
| 4.4 | BFS strategy implementation | 4 | P0 | 1.2-1.4, 4.2, 4.3 |
| 4.5 | DFS strategy implementation | 3 | P0 | 4.4 |
| 4.6 | Frontier management | 3 | P0 | 4.4 |
| 4.7 | Visited state tracking | 2 | P0 | 3.1, 4.4 |
| 4.8 | Progress tracking/callbacks | 2 | P1 | 4.4 |
| 4.9 | Checkpointing | 4 | P1 | 4.4, 1.7 |
| 4.10 | Random walk strategy | 2 | P2 | 4.4 |
| 4.11 | Unit tests for engine | 6 | P0 | 4.4-4.7 |
| 4.12 | Integration tests | 8 | P0 | All Phase 4 |

### Phase 5: Issue Detection
| ID | Task | Est. Hours | Priority | Dependencies |
|----|------|------------|----------|--------------|
| 5.1 | HTTP error detector | 2 | P0 | 1.3 |
| 5.2 | Dead end detector | 2 | P0 | 1.2, 1.3 |
| 5.3 | Cycle/loop detector | 3 | P0 | 1.5 |
| 5.4 | Unreachable state detector | 3 | P1 | 1.2, 1.6 |
| 5.5 | Anomaly detector | 6 | P2 | All |
| 5.6 | Reproduction step generator | 4 | P1 | 1.6, 5.1-5.4 |
| 5.7 | Severity classification | 2 | P1 | 5.1-5.4 |
| 5.8 | Unit tests | 4 | P0 | 5.1-5.4 |

### Phase 6: Visualization & Reporting
| ID | Task | Est. Hours | Priority | Dependencies |
|----|------|------------|----------|--------------|
| 6.1 | DOT format generation | 3 | P0 | 1.2, 1.3 |
| 6.2 | PNG rendering via graphviz | 2 | P0 | 6.1 |
| 6.3 | SVG rendering | 1 | P1 | 6.1 |
| 6.4 | Interactive HTML (pyvis) | 6 | P2 | 1.2, 1.3 |
| 6.5 | Mermaid diagram export | 2 | P2 | 1.2, 1.3 |
| 6.6 | Coverage report generation | 4 | P0 | 1.2, 1.3, 2.2 |
| 6.7 | JSON export | 2 | P0 | All models |
| 6.8 | Unit tests | 4 | P0 | 6.1-6.7 |

### Phase 7: Integration
| ID | Task | Est. Hours | Priority | Dependencies |
|----|------|------------|----------|--------------|
| 7.1 | StateExplorer main class | 4 | P0 | All phases |
| 7.2 | CLI `explore` command | 4 | P0 | 7.1 |
| 7.3 | YAML config support | 2 | P1 | 7.1 |
| 7.4 | Reporter integration | 4 | P1 | 7.1, 6.6 |
| 7.5 | Plugin hooks | 4 | P2 | 7.1 |
| 7.6 | Documentation | 8 | P0 | All |
| 7.7 | E2E tests with todo app | 8 | P0 | All |
| 7.8 | E2E tests with sample APIs | 6 | P1 | All |

### Summary

| Phase | Total Hours | P0 Hours | P1 Hours | P2 Hours |
|-------|-------------|----------|----------|----------|
| Phase 1 | 24 | 16 | 8 | 0 |
| Phase 2 | 26 | 18 | 8 | 0 |
| Phase 3 | 17 | 10 | 7 | 0 |
| Phase 4 | 48 | 38 | 8 | 2 |
| Phase 5 | 26 | 14 | 6 | 6 |
| Phase 6 | 24 | 13 | 3 | 8 |
| Phase 7 | 40 | 24 | 8 | 8 |
| **Total** | **205** | **133** | **48** | **24** |

**Estimated Timeline**: 8-9 weeks with one developer at ~25 hours/week

---

## Open Questions

1. **State Equivalence**: How aggressively should we deduplicate states? Same endpoint + same status code = same state, or should we look at response structure too?

2. **Payload Generation**: Should we use purely schema-based generation or integrate with Faker/Hypothesis for more realistic data?

3. **Authentication Flow**: Should we auto-detect login endpoints and attempt authentication, or require it to be configured?

4. **Rate Limiting**: How should we handle APIs that rate-limit us during exploration?

5. **Stateful Actions**: How do we handle actions that modify server state (POST, DELETE)? Should we have a "safe mode" that only does GET?

6. **Parallelization**: Should exploration support concurrent requests to speed up large APIs?

---

## Appendix: Example Exploration Output

```
┌──────────────────────────────────────────────────────────────────┐
│                    STATE EXPLORATION COMPLETE                     │
├──────────────────────────────────────────────────────────────────┤
│  Base URL:     http://localhost:8000                             │
│  Strategy:     BFS                                               │
│  Duration:     00:03:45                                          │
├──────────────────────────────────────────────────────────────────┤
│  COVERAGE                                                         │
│  ─────────                                                        │
│  Endpoints:    18/20 (90.0%)                                     │
│  States:       42 unique states discovered                       │
│  Transitions:  127 transitions recorded                          │
│                                                                   │
│  ISSUES FOUND: 3                                                  │
│  ─────────────                                                    │
│  🔴 CRITICAL: 500 Internal Server Error on POST /api/orders      │
│  🟡 MEDIUM:   Dead end at state "empty_cart_checkout"            │
│  🔵 LOW:      Potential cycle: login → dashboard → logout → ...  │
│                                                                   │
│  ARTIFACTS                                                        │
│  ─────────                                                        │
│  State map:    ./results/state_map.png                           │
│  Full report:  ./results/exploration_report.json                 │
│  Issues:       ./results/issues.md                               │
└──────────────────────────────────────────────────────────────────┘
```

---

## References

- [OpenAPI Specification](https://spec.openapis.org/oas/v3.1.0)
- [Graphviz Documentation](https://graphviz.org/documentation/)
- [NetworkX Algorithms](https://networkx.org/documentation/stable/reference/algorithms/index.html)
- [Property-Based Testing with Hypothesis](https://hypothesis.readthedocs.io/)
- [State Machine Testing Concepts](https://en.wikipedia.org/wiki/Model-based_testing)

---

*Document Version: 1.0*
*Last Updated: 2026-02-13*
*Author: VenomQA Team*
