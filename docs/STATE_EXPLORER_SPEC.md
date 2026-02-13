# VenomQA State Explorer - Technical Specification

## Overview

The State Explorer is an automated testing component that discovers and explores all possible application states by systematically executing API actions and tracking state transitions. It builds a complete state graph representation of the application, enabling comprehensive test coverage analysis and issue detection.

**Key Capabilities:**
- Automated state space exploration using BFS/DFS algorithms
- State signature computation from API responses
- State graph construction and visualization
- Issue detection (dead ends, cycles, errors, unreachable states)
- Coverage metrics computation
- Integration with existing VenomQA infrastructure

---

## 1. State Detection Algorithm

### 1.1 State Signature Computation

A **state signature** uniquely identifies an application state based on observable properties from API responses. The signature is computed as a hash of normalized state components.

#### State Components

```python
@dataclass
class StateComponents:
    """Components used to compute state signature."""

    # Authentication status
    auth_status: AuthStatus  # ANONYMOUS, AUTHENTICATED, ADMIN, etc.
    user_id: str | None      # Current user identifier

    # Entity presence and statuses
    entity_ids: frozenset[tuple[str, str]]  # Set of (entity_type, entity_id)
    entity_statuses: frozenset[tuple[str, str, str]]  # (type, id, status)

    # Resource counts (for aggregate state)
    resource_counts: frozenset[tuple[str, int]]  # (resource_type, count)

    # Feature flags / permissions
    permissions: frozenset[str]  # Active permission flags

class AuthStatus(Enum):
    ANONYMOUS = "anonymous"
    AUTHENTICATED = "authenticated"
    ADMIN = "admin"
    EXPIRED = "expired"
```

#### Signature Computation Algorithm

```python
import hashlib
import json
from typing import Any

class StateSignature:
    """Computes unique state signatures from API responses."""

    HASH_ALGORITHM = "sha256"
    SIGNATURE_LENGTH = 16  # First 16 chars of hex digest

    @classmethod
    def compute(cls, components: StateComponents) -> str:
        """Compute a deterministic state signature.

        Args:
            components: State components extracted from API response.

        Returns:
            16-character hex string uniquely identifying this state.
        """
        # Normalize components to ensure deterministic ordering
        normalized = {
            "auth_status": components.auth_status.value,
            "user_id": components.user_id,
            "entity_ids": sorted(list(components.entity_ids)),
            "entity_statuses": sorted(list(components.entity_statuses)),
            "resource_counts": sorted(list(components.resource_counts)),
            "permissions": sorted(list(components.permissions)),
        }

        # Serialize to canonical JSON
        canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"))

        # Compute hash
        digest = hashlib.new(cls.HASH_ALGORITHM, canonical.encode()).hexdigest()

        return digest[:cls.SIGNATURE_LENGTH]

    @classmethod
    def extract_components(
        cls,
        response: dict[str, Any],
        auth_header: str | None = None,
    ) -> StateComponents:
        """Extract state components from an API response.

        Args:
            response: Parsed JSON response from API.
            auth_header: Current authorization header value.

        Returns:
            StateComponents for signature computation.
        """
        # Determine auth status
        auth_status = cls._extract_auth_status(response, auth_header)
        user_id = cls._extract_user_id(response)

        # Extract entities
        entity_ids = cls._extract_entity_ids(response)
        entity_statuses = cls._extract_entity_statuses(response)

        # Extract counts
        resource_counts = cls._extract_resource_counts(response)

        # Extract permissions
        permissions = cls._extract_permissions(response)

        return StateComponents(
            auth_status=auth_status,
            user_id=user_id,
            entity_ids=frozenset(entity_ids),
            entity_statuses=frozenset(entity_statuses),
            resource_counts=frozenset(resource_counts),
            permissions=frozenset(permissions),
        )
```

### 1.2 State Inference Examples

#### Example 1: E-commerce Cart State

```json
// API Response: GET /api/cart
{
  "cart_id": "cart_123",
  "user_id": "user_456",
  "items": [
    {"product_id": "prod_1", "quantity": 2, "status": "available"},
    {"product_id": "prod_2", "quantity": 1, "status": "backordered"}
  ],
  "total": 149.99,
  "checkout_ready": false
}
```

**Extracted Components:**
```python
StateComponents(
    auth_status=AuthStatus.AUTHENTICATED,
    user_id="user_456",
    entity_ids=frozenset([
        ("cart", "cart_123"),
        ("product", "prod_1"),
        ("product", "prod_2"),
    ]),
    entity_statuses=frozenset([
        ("cart_item", "prod_1", "available"),
        ("cart_item", "prod_2", "backordered"),
        ("cart", "cart_123", "not_checkout_ready"),
    ]),
    resource_counts=frozenset([
        ("cart_items", 2),
    ]),
    permissions=frozenset(),
)
```

**Signature:** `"a3f2b1c9e8d7f6a5"`

#### Example 2: User Authentication State

```json
// API Response: GET /api/me
{
  "id": "user_456",
  "email": "user@example.com",
  "role": "admin",
  "permissions": ["read:users", "write:users", "delete:users"],
  "session_expires_at": "2024-01-15T10:00:00Z"
}
```

**Extracted Components:**
```python
StateComponents(
    auth_status=AuthStatus.ADMIN,
    user_id="user_456",
    entity_ids=frozenset([("user", "user_456")]),
    entity_statuses=frozenset([("user", "user_456", "active")]),
    resource_counts=frozenset(),
    permissions=frozenset(["read:users", "write:users", "delete:users"]),
)
```

**Signature:** `"7c8d9e0f1a2b3c4d"`

---

## 2. Exploration Algorithm

### 2.1 Algorithm Selection: BFS vs DFS

| Aspect | BFS (Breadth-First) | DFS (Depth-First) |
|--------|---------------------|-------------------|
| **Coverage** | Finds shortest paths first | Explores full depths first |
| **Memory** | O(branching_factor^depth) | O(depth) |
| **State Discovery** | Level-by-level | Path-by-path |
| **Best For** | Finding minimum-step transitions | Deep workflow testing |
| **Cycle Detection** | Early detection | Late detection |

**Recommended Default:** Hybrid approach with BFS for initial exploration and DFS for deep path verification.

### 2.2 Core Exploration Algorithm

```python
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterator

class ExplorationStrategy(Enum):
    BFS = "bfs"
    DFS = "dfs"
    HYBRID = "hybrid"  # BFS to depth N, then DFS

@dataclass
class ExplorationConfig:
    """Configuration for state exploration."""

    strategy: ExplorationStrategy = ExplorationStrategy.HYBRID
    max_depth: int = 10
    max_states: int = 1000
    max_transitions: int = 5000
    bfs_switch_depth: int = 3  # For HYBRID: switch to DFS after this depth
    timeout_seconds: float = 300.0
    parallel_workers: int = 4
    cycle_detection: bool = True
    rollback_on_mutation: bool = True

@dataclass
class ExplorationState:
    """State during exploration."""

    signature: str
    depth: int
    path: list[str]  # Sequence of action names leading here
    response_data: dict
    parent_signature: str | None = None
    action_from_parent: str | None = None

class StateExplorer:
    """Core state exploration engine."""

    def __init__(
        self,
        client: "BaseClient",
        state_manager: "StateManager",
        action_generator: "ActionGenerator",
        config: ExplorationConfig | None = None,
    ):
        self.client = client
        self.state_manager = state_manager
        self.action_generator = action_generator
        self.config = config or ExplorationConfig()

        # Exploration tracking
        self.visited_states: dict[str, ExplorationState] = {}
        self.transitions: list[StateTransition] = []
        self.frontier: deque[ExplorationState] = deque()

        # Metrics
        self.states_discovered = 0
        self.transitions_executed = 0
        self.cycles_detected = 0
        self.errors_encountered = 0

    def explore(self, initial_response: dict) -> StateGraph:
        """Execute state space exploration.

        Args:
            initial_response: Response from initial state query.

        Returns:
            Complete StateGraph of discovered states and transitions.
        """
        # Initialize with starting state
        initial_state = self._create_initial_state(initial_response)
        self.frontier.append(initial_state)
        self.visited_states[initial_state.signature] = initial_state

        # Create initial checkpoint for rollback
        self.state_manager.checkpoint("exploration_start")

        while self._should_continue():
            current = self._get_next_state()
            if current is None:
                break

            # Explore all available actions from current state
            for action in self.action_generator.generate_actions(current):
                self._explore_action(current, action)

        return self._build_graph()

    def _get_next_state(self) -> ExplorationState | None:
        """Get next state to explore based on strategy."""
        if not self.frontier:
            return None

        if self.config.strategy == ExplorationStrategy.BFS:
            return self.frontier.popleft()
        elif self.config.strategy == ExplorationStrategy.DFS:
            return self.frontier.pop()
        else:  # HYBRID
            # Use BFS until switch depth, then DFS
            if self.frontier and self.frontier[0].depth < self.config.bfs_switch_depth:
                return self.frontier.popleft()
            return self.frontier.pop()

    def _explore_action(
        self,
        current: ExplorationState,
        action: "GeneratedAction",
    ) -> None:
        """Execute an action and record the transition.

        Args:
            current: Current state.
            action: Action to execute.
        """
        # Checkpoint before mutation
        checkpoint_name = f"pre_{action.name}_{self.transitions_executed}"
        if self.config.rollback_on_mutation and action.is_mutation:
            self.state_manager.checkpoint(checkpoint_name)

        try:
            # Execute action
            start_time = time.time()
            response = self.client.request(
                method=action.method,
                url=action.url,
                json=action.body,
                headers=action.headers,
            )
            duration_ms = (time.time() - start_time) * 1000

            # Compute new state
            new_signature = StateSignature.compute(
                StateSignature.extract_components(response.json())
            )

            # Record transition
            transition = StateTransition(
                from_state=current.signature,
                to_state=new_signature,
                action=action.name,
                method=action.method,
                url=action.url,
                status_code=response.status_code,
                duration_ms=duration_ms,
                is_error=response.status_code >= 400,
            )
            self.transitions.append(transition)
            self.transitions_executed += 1

            # Handle new state discovery
            if new_signature not in self.visited_states:
                new_state = ExplorationState(
                    signature=new_signature,
                    depth=current.depth + 1,
                    path=current.path + [action.name],
                    response_data=response.json(),
                    parent_signature=current.signature,
                    action_from_parent=action.name,
                )

                if new_state.depth <= self.config.max_depth:
                    self.visited_states[new_signature] = new_state
                    self.frontier.append(new_state)
                    self.states_discovered += 1
            else:
                # Cycle detected
                self.cycles_detected += 1

        except Exception as e:
            self.errors_encountered += 1
            self._record_error(current, action, e)

        finally:
            # Rollback mutation
            if self.config.rollback_on_mutation and action.is_mutation:
                self.state_manager.rollback(checkpoint_name)

    def _should_continue(self) -> bool:
        """Check if exploration should continue."""
        if not self.frontier:
            return False
        if self.states_discovered >= self.config.max_states:
            return False
        if self.transitions_executed >= self.config.max_transitions:
            return False
        return True
```

### 2.3 Handling Infinite State Spaces

#### Depth Limiting

```python
@dataclass
class DepthLimitConfig:
    """Configuration for depth limiting."""

    # Hard maximum depth
    max_depth: int = 10

    # Per-action-type depth limits (some actions go deeper)
    action_depth_limits: dict[str, int] = field(default_factory=lambda: {
        "create": 5,
        "delete": 3,
        "update": 7,
        "read": 10,
    })

    # Depth penalty for repeated action types
    repetition_penalty: float = 0.5  # Each repeat costs 0.5 depth units
```

#### Cycle Detection

```python
class CycleDetector:
    """Detects and handles cycles in state exploration."""

    def __init__(self, max_cycle_visits: int = 2):
        self.max_cycle_visits = max_cycle_visits
        self.visit_counts: dict[str, int] = defaultdict(int)
        self.detected_cycles: list[Cycle] = []

    def should_explore(self, state_signature: str) -> bool:
        """Check if state should be explored again."""
        return self.visit_counts[state_signature] < self.max_cycle_visits

    def record_visit(self, state_signature: str) -> None:
        """Record a state visit."""
        self.visit_counts[state_signature] += 1

    def detect_cycle(
        self,
        current_path: list[str],
        new_signature: str,
        visited: dict[str, ExplorationState],
    ) -> Cycle | None:
        """Detect if transitioning creates a cycle.

        Returns:
            Cycle object if cycle detected, None otherwise.
        """
        if new_signature in visited:
            existing = visited[new_signature]

            # Find cycle start in path
            cycle_start_idx = len(existing.path)
            cycle_actions = current_path[cycle_start_idx:]

            return Cycle(
                start_state=new_signature,
                actions=cycle_actions,
                length=len(cycle_actions),
            )
        return None

@dataclass
class Cycle:
    """Represents a detected cycle in the state graph."""

    start_state: str
    actions: list[str]
    length: int

    @property
    def is_self_loop(self) -> bool:
        return self.length == 1
```

### 2.4 Parallel Exploration Strategy

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

class ParallelStateExplorer:
    """Parallel state exploration using worker pools."""

    def __init__(
        self,
        client_factory: Callable[[], "BaseClient"],
        state_manager: "StateManager",
        action_generator: "ActionGenerator",
        config: ExplorationConfig,
    ):
        self.client_factory = client_factory
        self.state_manager = state_manager
        self.action_generator = action_generator
        self.config = config

        # Shared state (thread-safe)
        self.visited_lock = asyncio.Lock()
        self.visited_states: dict[str, ExplorationState] = {}
        self.work_queue: asyncio.Queue[ExplorationState] = asyncio.Queue()
        self.results_queue: asyncio.Queue[StateTransition] = asyncio.Queue()

    async def explore_parallel(self, initial_response: dict) -> StateGraph:
        """Execute parallel state space exploration."""

        # Initialize
        initial_state = self._create_initial_state(initial_response)
        await self.work_queue.put(initial_state)

        # Create worker pool
        workers = [
            asyncio.create_task(self._worker(i))
            for i in range(self.config.parallel_workers)
        ]

        # Wait for completion or timeout
        try:
            await asyncio.wait_for(
                self._wait_for_completion(),
                timeout=self.config.timeout_seconds,
            )
        except asyncio.TimeoutError:
            pass  # Timeout reached, stop exploration

        # Cancel workers
        for worker in workers:
            worker.cancel()

        return self._build_graph()

    async def _worker(self, worker_id: int) -> None:
        """Worker coroutine for parallel exploration."""

        # Each worker gets its own client
        client = self.client_factory()
        client.connect()

        try:
            while True:
                # Get work item
                state = await asyncio.wait_for(
                    self.work_queue.get(),
                    timeout=5.0,
                )

                # Explore actions from this state
                for action in self.action_generator.generate_actions(state):
                    transition = await self._execute_action(
                        client, state, action
                    )

                    if transition and transition.to_state not in self.visited_states:
                        async with self.visited_lock:
                            if transition.to_state not in self.visited_states:
                                new_state = self._create_state_from_transition(
                                    state, transition
                                )
                                self.visited_states[transition.to_state] = new_state
                                await self.work_queue.put(new_state)

                    await self.results_queue.put(transition)
        finally:
            client.disconnect()
```

### 2.5 Rollback Strategy Using Database Savepoints

```python
class ExplorationRollbackManager:
    """Manages database state rollback during exploration."""

    def __init__(self, state_manager: "StateManager"):
        self.state_manager = state_manager
        self.checkpoint_stack: list[str] = []
        self.checkpoint_counter = 0

    def create_exploration_checkpoint(self, prefix: str = "explore") -> str:
        """Create a new checkpoint for exploration.

        Returns:
            Checkpoint name for later rollback.
        """
        self.checkpoint_counter += 1
        name = f"{prefix}_{self.checkpoint_counter}"
        self.state_manager.checkpoint(name)
        self.checkpoint_stack.append(name)
        return name

    def rollback_to_checkpoint(self, checkpoint_name: str) -> None:
        """Rollback to a specific checkpoint.

        Args:
            checkpoint_name: Name of checkpoint to rollback to.
        """
        self.state_manager.rollback(checkpoint_name)

        # Remove all checkpoints after this one
        while self.checkpoint_stack and self.checkpoint_stack[-1] != checkpoint_name:
            self.checkpoint_stack.pop()

    def rollback_last(self) -> None:
        """Rollback to the most recent checkpoint."""
        if self.checkpoint_stack:
            checkpoint_name = self.checkpoint_stack[-1]
            self.rollback_to_checkpoint(checkpoint_name)

    def release_checkpoint(self, checkpoint_name: str) -> None:
        """Release a checkpoint when no longer needed."""
        self.state_manager.release(checkpoint_name)
        if checkpoint_name in self.checkpoint_stack:
            self.checkpoint_stack.remove(checkpoint_name)

    def __enter__(self) -> "ExplorationRollbackManager":
        """Context manager entry."""
        self.state_manager.connect()
        self.create_exploration_checkpoint("exploration_root")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - cleanup all checkpoints."""
        # Rollback to root to clean up exploration changes
        if self.checkpoint_stack:
            root = self.checkpoint_stack[0]
            self.rollback_to_checkpoint(root)

        self.state_manager.disconnect()
```

---

## 3. Action Generation

### 3.1 OpenAPI Schema-Based Generation

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class GeneratedAction:
    """An action generated from API schema."""

    name: str
    method: str  # GET, POST, PUT, PATCH, DELETE
    url: str
    body: dict[str, Any] | None = None
    headers: dict[str, str] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)

    # Action metadata
    operation_id: str = ""
    tags: list[str] = field(default_factory=list)
    requires_auth: bool = False
    is_mutation: bool = False  # True for POST, PUT, PATCH, DELETE

class OpenAPIActionGenerator:
    """Generates valid API requests from OpenAPI specifications."""

    def __init__(
        self,
        spec: dict[str, Any],
        data_generator: "DataGenerator",
        base_url: str,
    ):
        self.spec = spec
        self.data_generator = data_generator
        self.base_url = base_url.rstrip("/")

        # Parse spec
        self.paths = spec.get("paths", {})
        self.schemas = spec.get("components", {}).get("schemas", {})
        self.security_schemes = spec.get("components", {}).get("securitySchemes", {})

    def generate_actions(
        self,
        current_state: ExplorationState,
        filter_tags: list[str] | None = None,
    ) -> Iterator[GeneratedAction]:
        """Generate all valid actions for current state.

        Args:
            current_state: Current application state.
            filter_tags: Optional tags to filter actions.

        Yields:
            GeneratedAction objects for each valid action.
        """
        for path, path_item in self.paths.items():
            for method, operation in path_item.items():
                if method.upper() not in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
                    continue

                # Check tag filter
                if filter_tags:
                    op_tags = operation.get("tags", [])
                    if not any(t in filter_tags for t in op_tags):
                        continue

                # Generate action
                action = self._generate_action(
                    path, method.upper(), operation, current_state
                )
                if action:
                    yield action

    def _generate_action(
        self,
        path: str,
        method: str,
        operation: dict,
        current_state: ExplorationState,
    ) -> GeneratedAction | None:
        """Generate a single action from operation spec."""

        # Resolve path parameters
        resolved_path = self._resolve_path_params(path, operation, current_state)
        if resolved_path is None:
            return None  # Cannot resolve required path params

        # Generate request body
        body = None
        if "requestBody" in operation:
            body = self._generate_request_body(operation["requestBody"])

        # Generate query parameters
        query_params = self._generate_query_params(operation, current_state)

        # Build URL with query params
        url = f"{self.base_url}{resolved_path}"
        if query_params:
            url += "?" + "&".join(f"{k}={v}" for k, v in query_params.items())

        # Determine if auth required
        requires_auth = bool(operation.get("security", self.spec.get("security", [])))

        return GeneratedAction(
            name=operation.get("operationId", f"{method}_{path}"),
            method=method,
            url=url,
            body=body,
            operation_id=operation.get("operationId", ""),
            tags=operation.get("tags", []),
            requires_auth=requires_auth,
            is_mutation=method in ["POST", "PUT", "PATCH", "DELETE"],
        )

    def _resolve_path_params(
        self,
        path: str,
        operation: dict,
        current_state: ExplorationState,
    ) -> str | None:
        """Resolve path parameters using current state context.

        Returns:
            Resolved path string, or None if required params unavailable.
        """
        import re

        resolved = path
        params = operation.get("parameters", [])

        for param in params:
            if param.get("in") != "path":
                continue

            param_name = param["name"]
            placeholder = f"{{{param_name}}}"

            if placeholder in resolved:
                # Try to get value from current state
                value = self._get_param_value_from_state(
                    param_name, param, current_state
                )

                if value is None:
                    if param.get("required", True):
                        return None  # Required param not available
                    # Generate a value
                    value = self.data_generator.generate_for_schema(
                        param.get("schema", {"type": "string"})
                    )

                resolved = resolved.replace(placeholder, str(value))

        return resolved

    def _get_param_value_from_state(
        self,
        param_name: str,
        param_spec: dict,
        current_state: ExplorationState,
    ) -> Any:
        """Extract parameter value from current state."""

        # Common mappings
        mappings = {
            "id": lambda s: self._extract_id(s.response_data),
            "user_id": lambda s: s.response_data.get("user_id"),
            "product_id": lambda s: self._extract_entity_id(s.response_data, "product"),
            "order_id": lambda s: self._extract_entity_id(s.response_data, "order"),
        }

        if param_name in mappings:
            return mappings[param_name](current_state)

        # Try to find in response data
        return current_state.response_data.get(param_name)

    def _generate_request_body(
        self,
        request_body_spec: dict,
    ) -> dict[str, Any] | None:
        """Generate request body from schema."""

        content = request_body_spec.get("content", {})

        # Prefer JSON
        if "application/json" in content:
            schema = content["application/json"].get("schema", {})
            return self.data_generator.generate_for_schema(schema)

        return None
```

### 3.2 Data Generation with Faker

```python
from typing import Any
from faker import Faker

class DataGenerator:
    """Generates valid test data for API requests."""

    def __init__(self, locale: str = "en_US", seed: int | None = None):
        self.faker = Faker(locale)
        if seed is not None:
            Faker.seed(seed)

        # Schema type generators
        self.type_generators: dict[str, Callable[[], Any]] = {
            "string": self._generate_string,
            "integer": lambda: self.faker.random_int(1, 10000),
            "number": lambda: round(self.faker.pyfloat(min_value=0, max_value=10000), 2),
            "boolean": lambda: self.faker.boolean(),
            "array": self._generate_array,
            "object": self._generate_object,
        }

        # Format-specific generators
        self.format_generators: dict[str, Callable[[], Any]] = {
            "email": lambda: self.faker.email(),
            "date": lambda: self.faker.date(),
            "date-time": lambda: self.faker.iso8601(),
            "uri": lambda: self.faker.url(),
            "uuid": lambda: str(self.faker.uuid4()),
            "phone": lambda: self.faker.phone_number(),
            "password": lambda: self.faker.password(length=16),
        }

    def generate_for_schema(
        self,
        schema: dict[str, Any],
        required_only: bool = False,
    ) -> Any:
        """Generate data matching an OpenAPI schema.

        Args:
            schema: OpenAPI schema definition.
            required_only: If True, only generate required fields.

        Returns:
            Generated data matching the schema.
        """
        # Handle $ref
        if "$ref" in schema:
            # Resolve reference (simplified)
            return self._generate_default_value(schema.get("type", "string"))

        # Handle enum
        if "enum" in schema:
            return self.faker.random_element(schema["enum"])

        # Handle format
        fmt = schema.get("format")
        if fmt and fmt in self.format_generators:
            return self.format_generators[fmt]()

        # Handle type
        schema_type = schema.get("type", "string")

        if schema_type == "object":
            return self._generate_object(schema, required_only)
        elif schema_type == "array":
            return self._generate_array(schema)
        elif schema_type in self.type_generators:
            return self.type_generators[schema_type]()

        return self._generate_default_value(schema_type)

    def _generate_object(
        self,
        schema: dict[str, Any],
        required_only: bool = False,
    ) -> dict[str, Any]:
        """Generate an object matching schema properties."""

        result = {}
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))

        for prop_name, prop_schema in properties.items():
            # Skip optional fields if required_only
            if required_only and prop_name not in required:
                continue

            # Generate value
            result[prop_name] = self.generate_for_schema(prop_schema)

        return result

    def _generate_array(self, schema: dict[str, Any]) -> list[Any]:
        """Generate an array matching schema items."""

        items_schema = schema.get("items", {"type": "string"})
        min_items = schema.get("minItems", 1)
        max_items = schema.get("maxItems", 3)

        count = self.faker.random_int(min_items, max_items)
        return [self.generate_for_schema(items_schema) for _ in range(count)]

    def _generate_string(self) -> str:
        """Generate a random string."""
        return self.faker.word()
```

### 3.3 Handling Authentication Requirements

```python
class AuthenticationHandler:
    """Manages authentication for action generation."""

    def __init__(
        self,
        auth_config: dict[str, Any],
        credentials_provider: Callable[[], dict[str, str]],
    ):
        self.auth_config = auth_config
        self.credentials_provider = credentials_provider
        self._cached_token: str | None = None
        self._token_expires_at: datetime | None = None

    def prepare_action(
        self,
        action: GeneratedAction,
        auth_status: AuthStatus,
    ) -> GeneratedAction:
        """Add authentication to action if required.

        Args:
            action: Action to authenticate.
            auth_status: Required authentication level.

        Returns:
            Action with authentication headers added.
        """
        if not action.requires_auth:
            return action

        if auth_status == AuthStatus.ANONYMOUS:
            return action  # No auth needed

        # Get or refresh token
        token = self._get_valid_token(auth_status)

        # Add auth header
        action.headers["Authorization"] = f"Bearer {token}"

        return action

    def _get_valid_token(self, auth_status: AuthStatus) -> str:
        """Get or refresh authentication token."""

        # Check cache
        if self._cached_token and self._token_expires_at:
            if datetime.now() < self._token_expires_at - timedelta(minutes=5):
                return self._cached_token

        # Get fresh credentials
        credentials = self.credentials_provider()

        # Exchange for token (implementation-specific)
        token_response = self._exchange_credentials(credentials, auth_status)

        self._cached_token = token_response["access_token"]
        self._token_expires_at = datetime.now() + timedelta(
            seconds=token_response.get("expires_in", 3600)
        )

        return self._cached_token
```

---

## 4. State Graph Data Structure

### 4.1 Adjacency List Representation

```python
from dataclasses import dataclass, field
from typing import Iterator

@dataclass
class StateTransition:
    """A transition between two states."""

    from_state: str  # Source state signature
    to_state: str    # Target state signature
    action: str      # Action name that caused transition
    method: str      # HTTP method
    url: str         # Request URL
    status_code: int # Response status code
    duration_ms: float
    is_error: bool = False
    error_message: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class StateNode:
    """A node in the state graph."""

    signature: str
    depth: int
    discovery_path: list[str]  # Actions leading to first discovery
    response_snapshot: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    # Graph properties
    is_terminal: bool = False  # No outgoing transitions
    is_error_state: bool = False
    visit_count: int = 0

    # Computed during analysis
    incoming_transitions: list[str] = field(default_factory=list)
    outgoing_transitions: list[str] = field(default_factory=list)

class StateGraph:
    """Directed graph representing application state space."""

    def __init__(self):
        # Adjacency list: state_signature -> list of transitions
        self._adjacency: dict[str, list[StateTransition]] = defaultdict(list)

        # Node storage
        self._nodes: dict[str, StateNode] = {}

        # Reverse adjacency for incoming edges
        self._reverse_adjacency: dict[str, list[StateTransition]] = defaultdict(list)

        # Root state
        self.root_state: str | None = None

    def add_node(self, node: StateNode) -> None:
        """Add a state node to the graph."""
        self._nodes[node.signature] = node
        if self.root_state is None:
            self.root_state = node.signature

    def add_transition(self, transition: StateTransition) -> None:
        """Add a transition edge to the graph."""
        self._adjacency[transition.from_state].append(transition)
        self._reverse_adjacency[transition.to_state].append(transition)

        # Update node edge lists
        if transition.from_state in self._nodes:
            self._nodes[transition.from_state].outgoing_transitions.append(
                transition.to_state
            )
        if transition.to_state in self._nodes:
            self._nodes[transition.to_state].incoming_transitions.append(
                transition.from_state
            )

    def get_node(self, signature: str) -> StateNode | None:
        """Get a node by signature."""
        return self._nodes.get(signature)

    def get_outgoing(self, signature: str) -> list[StateTransition]:
        """Get all outgoing transitions from a state."""
        return self._adjacency.get(signature, [])

    def get_incoming(self, signature: str) -> list[StateTransition]:
        """Get all incoming transitions to a state."""
        return self._reverse_adjacency.get(signature, [])

    @property
    def nodes(self) -> Iterator[StateNode]:
        """Iterate over all nodes."""
        return iter(self._nodes.values())

    @property
    def transitions(self) -> Iterator[StateTransition]:
        """Iterate over all transitions."""
        for transitions in self._adjacency.values():
            yield from transitions

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return sum(len(t) for t in self._adjacency.values())
```

### 4.2 Efficient Lookup and Traversal

```python
class StateGraphQuery:
    """Query interface for state graph analysis."""

    def __init__(self, graph: StateGraph):
        self.graph = graph

    def find_paths(
        self,
        from_state: str,
        to_state: str,
        max_depth: int = 10,
    ) -> list[list[StateTransition]]:
        """Find all paths between two states.

        Args:
            from_state: Source state signature.
            to_state: Target state signature.
            max_depth: Maximum path length.

        Returns:
            List of transition sequences (paths).
        """
        paths = []

        def dfs(current: str, path: list[StateTransition], visited: set[str]):
            if len(path) > max_depth:
                return

            if current == to_state:
                paths.append(path.copy())
                return

            for transition in self.graph.get_outgoing(current):
                if transition.to_state not in visited:
                    visited.add(transition.to_state)
                    path.append(transition)
                    dfs(transition.to_state, path, visited)
                    path.pop()
                    visited.remove(transition.to_state)

        dfs(from_state, [], {from_state})
        return paths

    def find_shortest_path(
        self,
        from_state: str,
        to_state: str,
    ) -> list[StateTransition] | None:
        """Find shortest path between two states using BFS."""

        if from_state == to_state:
            return []

        visited = {from_state}
        queue = deque([(from_state, [])])

        while queue:
            current, path = queue.popleft()

            for transition in self.graph.get_outgoing(current):
                if transition.to_state == to_state:
                    return path + [transition]

                if transition.to_state not in visited:
                    visited.add(transition.to_state)
                    queue.append((transition.to_state, path + [transition]))

        return None

    def find_dead_ends(self) -> list[StateNode]:
        """Find states with no outgoing transitions."""
        return [
            node for node in self.graph.nodes
            if not self.graph.get_outgoing(node.signature)
            and not node.is_error_state
        ]

    def find_unreachable_states(self) -> list[StateNode]:
        """Find states not reachable from root."""
        if not self.graph.root_state:
            return []

        reachable = set()
        queue = deque([self.graph.root_state])

        while queue:
            current = queue.popleft()
            if current in reachable:
                continue
            reachable.add(current)

            for transition in self.graph.get_outgoing(current):
                queue.append(transition.to_state)

        return [
            node for node in self.graph.nodes
            if node.signature not in reachable
        ]

    def find_cycles(self) -> list[list[str]]:
        """Detect all cycles in the graph using Tarjan's algorithm."""

        index_counter = [0]
        stack = []
        lowlink = {}
        index = {}
        on_stack = set()
        sccs = []  # Strongly connected components

        def strongconnect(node: str):
            index[node] = index_counter[0]
            lowlink[node] = index_counter[0]
            index_counter[0] += 1
            stack.append(node)
            on_stack.add(node)

            for transition in self.graph.get_outgoing(node):
                successor = transition.to_state
                if successor not in index:
                    strongconnect(successor)
                    lowlink[node] = min(lowlink[node], lowlink[successor])
                elif successor in on_stack:
                    lowlink[node] = min(lowlink[node], index[successor])

            if lowlink[node] == index[node]:
                scc = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    scc.append(w)
                    if w == node:
                        break
                if len(scc) > 1 or any(
                    t.to_state == node
                    for t in self.graph.get_outgoing(node)
                ):
                    sccs.append(scc)

        for node in self.graph._nodes:
            if node not in index:
                strongconnect(node)

        return sccs
```

### 4.3 Serialization Format (JSON)

```python
import json
from datetime import datetime
from typing import Any

class StateGraphSerializer:
    """Serializes state graph to/from JSON."""

    @classmethod
    def to_dict(cls, graph: StateGraph) -> dict[str, Any]:
        """Convert graph to dictionary representation."""

        return {
            "version": "1.0",
            "generated_at": datetime.now().isoformat(),
            "root_state": graph.root_state,
            "nodes": [
                cls._node_to_dict(node)
                for node in graph.nodes
            ],
            "transitions": [
                cls._transition_to_dict(t)
                for t in graph.transitions
            ],
            "metadata": {
                "node_count": graph.node_count,
                "edge_count": graph.edge_count,
            },
        }

    @classmethod
    def to_json(cls, graph: StateGraph, indent: int = 2) -> str:
        """Serialize graph to JSON string."""
        return json.dumps(cls.to_dict(graph), indent=indent, default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StateGraph:
        """Reconstruct graph from dictionary."""

        graph = StateGraph()
        graph.root_state = data.get("root_state")

        # Reconstruct nodes
        for node_data in data.get("nodes", []):
            node = cls._dict_to_node(node_data)
            graph.add_node(node)

        # Reconstruct transitions
        for trans_data in data.get("transitions", []):
            transition = cls._dict_to_transition(trans_data)
            graph.add_transition(transition)

        return graph

    @classmethod
    def from_json(cls, json_str: str) -> StateGraph:
        """Deserialize graph from JSON string."""
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def _node_to_dict(cls, node: StateNode) -> dict[str, Any]:
        return {
            "signature": node.signature,
            "depth": node.depth,
            "discovery_path": node.discovery_path,
            "response_snapshot": node.response_snapshot,
            "is_terminal": node.is_terminal,
            "is_error_state": node.is_error_state,
            "visit_count": node.visit_count,
            "metadata": node.metadata,
        }

    @classmethod
    def _transition_to_dict(cls, t: StateTransition) -> dict[str, Any]:
        return {
            "from_state": t.from_state,
            "to_state": t.to_state,
            "action": t.action,
            "method": t.method,
            "url": t.url,
            "status_code": t.status_code,
            "duration_ms": t.duration_ms,
            "is_error": t.is_error,
            "error_message": t.error_message,
            "timestamp": t.timestamp.isoformat() if t.timestamp else None,
        }
```

---

## 5. Issue Detection Rules

### 5.1 Issue Categories and Detection

```python
from enum import Enum
from dataclasses import dataclass

class IssueType(Enum):
    ERROR_RESPONSE = "error_response"
    DEAD_END = "dead_end"
    UNREACHABLE_STATE = "unreachable_state"
    CYCLE_DETECTED = "cycle_detected"
    SLOW_TRANSITION = "slow_transition"
    INCONSISTENT_STATE = "inconsistent_state"
    AUTHENTICATION_FAILURE = "authentication_failure"
    VALIDATION_ERROR = "validation_error"

@dataclass
class DetectedIssue:
    """An issue detected during exploration."""

    issue_type: IssueType
    severity: Severity
    state_signature: str | None
    transition: StateTransition | None
    message: str
    details: dict[str, Any]
    suggestion: str

class IssueDetector:
    """Detects issues in state graph exploration results."""

    def __init__(
        self,
        graph: StateGraph,
        config: "IssueDetectionConfig",
    ):
        self.graph = graph
        self.config = config
        self.detected_issues: list[DetectedIssue] = []

    def detect_all(self) -> list[DetectedIssue]:
        """Run all issue detection rules."""

        self.detected_issues = []

        # Run each detector
        self._detect_error_responses()
        self._detect_dead_ends()
        self._detect_unreachable_states()
        self._detect_cycles()
        self._detect_slow_transitions()
        self._detect_inconsistent_states()

        return self.detected_issues

    def _detect_error_responses(self) -> None:
        """Detect transitions resulting in error responses (4xx, 5xx)."""

        for transition in self.graph.transitions:
            if transition.is_error:
                severity = (
                    Severity.CRITICAL if transition.status_code >= 500
                    else Severity.HIGH if transition.status_code >= 400
                    else Severity.MEDIUM
                )

                self.detected_issues.append(DetectedIssue(
                    issue_type=IssueType.ERROR_RESPONSE,
                    severity=severity,
                    state_signature=transition.from_state,
                    transition=transition,
                    message=f"Action '{transition.action}' resulted in HTTP {transition.status_code}",
                    details={
                        "status_code": transition.status_code,
                        "error_message": transition.error_message,
                        "url": transition.url,
                        "method": transition.method,
                    },
                    suggestion=self._get_error_suggestion(transition.status_code),
                ))

    def _detect_dead_ends(self) -> None:
        """Detect states with no valid outgoing transitions."""

        query = StateGraphQuery(self.graph)
        dead_ends = query.find_dead_ends()

        for node in dead_ends:
            self.detected_issues.append(DetectedIssue(
                issue_type=IssueType.DEAD_END,
                severity=Severity.MEDIUM,
                state_signature=node.signature,
                transition=None,
                message=f"State '{node.signature[:8]}...' has no outgoing transitions",
                details={
                    "depth": node.depth,
                    "discovery_path": node.discovery_path,
                },
                suggestion="Consider adding recovery actions from this state or verify this is expected terminal state",
            ))

    def _detect_unreachable_states(self) -> None:
        """Detect states not reachable from root state."""

        query = StateGraphQuery(self.graph)
        unreachable = query.find_unreachable_states()

        for node in unreachable:
            self.detected_issues.append(DetectedIssue(
                issue_type=IssueType.UNREACHABLE_STATE,
                severity=Severity.HIGH,
                state_signature=node.signature,
                transition=None,
                message=f"State '{node.signature[:8]}...' is not reachable from initial state",
                details={
                    "incoming_transitions": node.incoming_transitions,
                },
                suggestion="This state may be orphaned or only reachable through external means",
            ))

    def _detect_cycles(self) -> None:
        """Detect cyclic transitions (potential infinite loops)."""

        query = StateGraphQuery(self.graph)
        cycles = query.find_cycles()

        for cycle in cycles:
            # Only report if cycle is short (likely problematic)
            if len(cycle) <= self.config.max_reportable_cycle_length:
                self.detected_issues.append(DetectedIssue(
                    issue_type=IssueType.CYCLE_DETECTED,
                    severity=Severity.LOW,
                    state_signature=cycle[0],
                    transition=None,
                    message=f"Cycle detected involving {len(cycle)} states",
                    details={
                        "cycle_states": cycle,
                        "cycle_length": len(cycle),
                    },
                    suggestion="Review if this cycle is intentional behavior or indicates missing exit conditions",
                ))

    def _detect_slow_transitions(self) -> None:
        """Detect transitions exceeding performance thresholds."""

        threshold_ms = self.config.slow_transition_threshold_ms

        for transition in self.graph.transitions:
            if transition.duration_ms > threshold_ms:
                self.detected_issues.append(DetectedIssue(
                    issue_type=IssueType.SLOW_TRANSITION,
                    severity=Severity.LOW,
                    state_signature=transition.from_state,
                    transition=transition,
                    message=f"Action '{transition.action}' took {transition.duration_ms:.0f}ms (threshold: {threshold_ms}ms)",
                    details={
                        "duration_ms": transition.duration_ms,
                        "threshold_ms": threshold_ms,
                        "url": transition.url,
                    },
                    suggestion="Consider optimizing this endpoint or increasing timeout thresholds",
                ))

    def _detect_inconsistent_states(self) -> None:
        """Detect same action producing different results from same state."""

        # Group transitions by (from_state, action)
        transition_groups: dict[tuple[str, str], list[StateTransition]] = defaultdict(list)

        for transition in self.graph.transitions:
            key = (transition.from_state, transition.action)
            transition_groups[key].append(transition)

        for (from_state, action), transitions in transition_groups.items():
            if len(transitions) < 2:
                continue

            # Check for different outcomes
            outcomes = set()
            for t in transitions:
                outcome = (t.to_state, t.status_code, t.is_error)
                outcomes.add(outcome)

            if len(outcomes) > 1:
                self.detected_issues.append(DetectedIssue(
                    issue_type=IssueType.INCONSISTENT_STATE,
                    severity=Severity.HIGH,
                    state_signature=from_state,
                    transition=transitions[0],
                    message=f"Action '{action}' produces inconsistent results from state '{from_state[:8]}...'",
                    details={
                        "action": action,
                        "outcome_count": len(outcomes),
                        "outcomes": [
                            {"to_state": t.to_state[:8], "status": t.status_code}
                            for t in transitions
                        ],
                    },
                    suggestion="Non-deterministic behavior detected - investigate race conditions or state-dependent logic",
                ))

    def _get_error_suggestion(self, status_code: int) -> str:
        """Generate suggestion based on HTTP status code."""

        suggestions = {
            400: "Check request validation - body or parameters may be malformed",
            401: "Authentication required - ensure valid credentials are provided",
            403: "Permission denied - check user roles and access control",
            404: "Resource not found - verify the resource exists in current state",
            409: "Conflict - resource may already exist or be in invalid state",
            422: "Validation failed - check request body against schema",
            429: "Rate limited - add delays between requests",
            500: "Server error - check backend logs for exception details",
            502: "Bad gateway - upstream service may be down",
            503: "Service unavailable - check service health",
            504: "Gateway timeout - upstream service too slow",
        }

        return suggestions.get(status_code, "Review error response for details")

@dataclass
class IssueDetectionConfig:
    """Configuration for issue detection."""

    slow_transition_threshold_ms: float = 5000.0
    max_reportable_cycle_length: int = 5
    detect_error_responses: bool = True
    detect_dead_ends: bool = True
    detect_cycles: bool = True
    detect_slow_transitions: bool = True
    detect_inconsistent_states: bool = True
```

---

## 6. Coverage Metrics

### 6.1 Metric Definitions

```python
from dataclasses import dataclass

@dataclass
class CoverageMetrics:
    """Coverage metrics from state exploration."""

    # State coverage
    states_visited: int
    states_discovered: int
    state_coverage_pct: float

    # Transition coverage
    transitions_executed: int
    transitions_possible: int
    transition_coverage_pct: float

    # Endpoint coverage
    endpoints_tested: int
    endpoints_total: int
    endpoint_coverage_pct: float

    # Path coverage
    unique_paths: int
    total_paths: int
    path_coverage_pct: float

    # Additional metrics
    max_depth_reached: int
    avg_path_length: float
    cycles_detected: int
    error_rate: float

class CoverageCalculator:
    """Calculates coverage metrics from exploration results."""

    def __init__(
        self,
        graph: StateGraph,
        openapi_spec: dict[str, Any] | None = None,
    ):
        self.graph = graph
        self.openapi_spec = openapi_spec

    def calculate(self) -> CoverageMetrics:
        """Calculate all coverage metrics."""

        # State coverage
        states_visited = len([n for n in self.graph.nodes if n.visit_count > 0])
        states_discovered = self.graph.node_count

        # Transition coverage
        transitions_executed = self.graph.edge_count
        transitions_possible = self._estimate_possible_transitions()

        # Endpoint coverage
        endpoints_tested = self._count_tested_endpoints()
        endpoints_total = self._count_total_endpoints()

        # Path coverage
        unique_paths = self._count_unique_paths()
        total_paths = self._estimate_total_paths()

        # Additional metrics
        max_depth = max((n.depth for n in self.graph.nodes), default=0)
        avg_path = self._calculate_avg_path_length()
        cycles = len(StateGraphQuery(self.graph).find_cycles())
        error_rate = self._calculate_error_rate()

        return CoverageMetrics(
            states_visited=states_visited,
            states_discovered=states_discovered,
            state_coverage_pct=self._pct(states_visited, states_discovered),
            transitions_executed=transitions_executed,
            transitions_possible=transitions_possible,
            transition_coverage_pct=self._pct(transitions_executed, transitions_possible),
            endpoints_tested=endpoints_tested,
            endpoints_total=endpoints_total,
            endpoint_coverage_pct=self._pct(endpoints_tested, endpoints_total),
            unique_paths=unique_paths,
            total_paths=total_paths,
            path_coverage_pct=self._pct(unique_paths, total_paths),
            max_depth_reached=max_depth,
            avg_path_length=avg_path,
            cycles_detected=cycles,
            error_rate=error_rate,
        )

    def _count_tested_endpoints(self) -> int:
        """Count unique endpoints that were tested."""
        endpoints = set()
        for transition in self.graph.transitions:
            # Normalize URL (remove path params)
            import re
            normalized = re.sub(r'/[a-f0-9-]{36}', '/{id}', transition.url)
            normalized = re.sub(r'/\d+', '/{id}', normalized)
            endpoints.add((transition.method, normalized))
        return len(endpoints)

    def _count_total_endpoints(self) -> int:
        """Count total endpoints from OpenAPI spec."""
        if not self.openapi_spec:
            return self._count_tested_endpoints()  # Best estimate

        count = 0
        for path, methods in self.openapi_spec.get("paths", {}).items():
            for method in methods:
                if method.upper() in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
                    count += 1
        return count

    def _count_unique_paths(self) -> int:
        """Count unique state paths discovered."""
        paths = set()
        for node in self.graph.nodes:
            paths.add(tuple(node.discovery_path))
        return len(paths)

    def _estimate_total_paths(self) -> int:
        """Estimate total possible paths (exponential)."""
        # Simplified estimate based on graph structure
        avg_branching = self.graph.edge_count / max(self.graph.node_count, 1)
        max_depth = max((n.depth for n in self.graph.nodes), default=0)
        return int(avg_branching ** max_depth)

    def _estimate_possible_transitions(self) -> int:
        """Estimate total possible transitions."""
        # Each state could potentially transition to any other state
        return self.graph.node_count * max(self._count_total_endpoints(), 1)

    def _calculate_avg_path_length(self) -> float:
        """Calculate average path length to states."""
        depths = [n.depth for n in self.graph.nodes]
        return sum(depths) / len(depths) if depths else 0.0

    def _calculate_error_rate(self) -> float:
        """Calculate percentage of error transitions."""
        errors = sum(1 for t in self.graph.transitions if t.is_error)
        total = self.graph.edge_count
        return self._pct(errors, total) if total > 0 else 0.0

    @staticmethod
    def _pct(numerator: int, denominator: int) -> float:
        return (numerator / denominator * 100) if denominator > 0 else 100.0
```

### 6.2 Coverage Report Generation

```python
class CoverageReporter:
    """Generates coverage reports."""

    def __init__(self, metrics: CoverageMetrics):
        self.metrics = metrics

    def to_summary(self) -> str:
        """Generate human-readable coverage summary."""

        m = self.metrics

        return f"""
State Explorer Coverage Report
==============================

State Coverage:
  - States Visited:    {m.states_visited}/{m.states_discovered} ({m.state_coverage_pct:.1f}%)

Transition Coverage:
  - Transitions:       {m.transitions_executed}/{m.transitions_possible} ({m.transition_coverage_pct:.1f}%)

Endpoint Coverage:
  - Endpoints Tested:  {m.endpoints_tested}/{m.endpoints_total} ({m.endpoint_coverage_pct:.1f}%)

Path Coverage:
  - Unique Paths:      {m.unique_paths}/{m.total_paths} ({m.path_coverage_pct:.1f}%)

Exploration Metrics:
  - Max Depth:         {m.max_depth_reached}
  - Avg Path Length:   {m.avg_path_length:.2f}
  - Cycles Detected:   {m.cycles_detected}
  - Error Rate:        {m.error_rate:.1f}%
"""
```

---

## 7. Visualization Specification

### 7.1 Graphviz DOT Format

```python
class GraphvizExporter:
    """Exports state graph to Graphviz DOT format."""

    COLOR_MAP = {
        "normal": "#22c55e",      # Green - OK
        "error": "#ef4444",       # Red - Error
        "warning": "#f59e0b",     # Yellow - Warning
        "terminal": "#6b7280",    # Gray - Terminal
        "start": "#3b82f6",       # Blue - Start
    }

    def __init__(self, graph: StateGraph):
        self.graph = graph

    def to_dot(self, title: str = "State Graph") -> str:
        """Generate DOT format string."""

        lines = [
            f'digraph "{title}" {{',
            '    rankdir=TB;',
            '    node [shape=box, style=rounded];',
            '',
        ]

        # Add nodes
        for node in self.graph.nodes:
            color = self._get_node_color(node)
            label = self._get_node_label(node)
            lines.append(
                f'    "{node.signature[:8]}" ['
                f'label="{label}", '
                f'fillcolor="{color}", '
                f'style="filled,rounded"'
                f'];'
            )

        lines.append('')

        # Add edges
        for transition in self.graph.transitions:
            color = self._get_edge_color(transition)
            label = self._get_edge_label(transition)
            lines.append(
                f'    "{transition.from_state[:8]}" -> "{transition.to_state[:8]}" ['
                f'label="{label}", '
                f'color="{color}"'
                f'];'
            )

        lines.append('}')

        return '\n'.join(lines)

    def _get_node_color(self, node: StateNode) -> str:
        if node.signature == self.graph.root_state:
            return self.COLOR_MAP["start"]
        if node.is_error_state:
            return self.COLOR_MAP["error"]
        if node.is_terminal:
            return self.COLOR_MAP["terminal"]
        return self.COLOR_MAP["normal"]

    def _get_node_label(self, node: StateNode) -> str:
        return f"{node.signature[:8]}\\ndepth: {node.depth}"

    def _get_edge_color(self, transition: StateTransition) -> str:
        if transition.is_error:
            return self.COLOR_MAP["error"]
        if transition.duration_ms > 1000:
            return self.COLOR_MAP["warning"]
        return self.COLOR_MAP["normal"]

    def _get_edge_label(self, transition: StateTransition) -> str:
        return f"{transition.method} {transition.action}\\n{transition.status_code}"
```

### 7.2 Mermaid Format

```python
class MermaidExporter:
    """Exports state graph to Mermaid diagram format."""

    def __init__(self, graph: StateGraph):
        self.graph = graph

    def to_mermaid(self) -> str:
        """Generate Mermaid flowchart syntax."""

        lines = [
            "```mermaid",
            "flowchart TD",
        ]

        # Define node styles
        lines.extend([
            "    classDef success fill:#dcfce7,stroke:#22c55e",
            "    classDef error fill:#fee2e2,stroke:#ef4444",
            "    classDef start fill:#dbeafe,stroke:#3b82f6",
            "",
        ])

        # Add nodes with shapes
        for node in self.graph.nodes:
            node_id = node.signature[:8]
            shape = self._get_node_shape(node)
            lines.append(f"    {node_id}{shape}")

        lines.append("")

        # Add edges
        for transition in self.graph.transitions:
            from_id = transition.from_state[:8]
            to_id = transition.to_state[:8]
            label = f"{transition.method}"
            arrow = "-->|" + label + "|" if not transition.is_error else "-.->|" + label + "|"
            lines.append(f"    {from_id} {arrow} {to_id}")

        # Apply styles
        for node in self.graph.nodes:
            node_id = node.signature[:8]
            style_class = self._get_style_class(node)
            lines.append(f"    class {node_id} {style_class}")

        lines.append("```")

        return '\n'.join(lines)

    def _get_node_shape(self, node: StateNode) -> str:
        label = f"State: {node.signature[:8]}"
        if node.signature == self.graph.root_state:
            return f"([{label}])"  # Stadium shape for start
        if node.is_terminal:
            return f"[/{label}/]"  # Parallelogram for terminal
        return f"[{label}]"  # Rectangle for normal

    def _get_style_class(self, node: StateNode) -> str:
        if node.signature == self.graph.root_state:
            return "start"
        if node.is_error_state:
            return "error"
        return "success"
```

### 7.3 Interactive HTML (vis.js)

```python
class HTMLVisualizationExporter:
    """Exports interactive HTML visualization using vis.js."""

    def __init__(self, graph: StateGraph, metrics: CoverageMetrics):
        self.graph = graph
        self.metrics = metrics

    def to_html(self, title: str = "State Explorer Visualization") -> str:
        """Generate self-contained interactive HTML."""

        # Prepare node data
        nodes_data = []
        for node in self.graph.nodes:
            nodes_data.append({
                "id": node.signature,
                "label": f"{node.signature[:8]}\\nDepth: {node.depth}",
                "color": self._get_node_color(node),
                "shape": "box",
                "title": self._get_node_tooltip(node),
            })

        # Prepare edge data
        edges_data = []
        for i, transition in enumerate(self.graph.transitions):
            edges_data.append({
                "id": i,
                "from": transition.from_state,
                "to": transition.to_state,
                "label": transition.action,
                "color": {"color": self._get_edge_color(transition)},
                "arrows": "to",
                "title": self._get_edge_tooltip(transition),
            })

        return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f3f4f6;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        .header {{
            background: linear-gradient(135deg, #6366f1, #4f46e5);
            color: white;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
        }}
        .metrics {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .metric-card {{
            background: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .metric-value {{
            font-size: 2rem;
            font-weight: bold;
            color: #6366f1;
        }}
        .metric-label {{
            color: #6b7280;
            font-size: 0.875rem;
        }}
        #graph-container {{
            width: 100%;
            height: 600px;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .legend {{
            display: flex;
            gap: 20px;
            margin-top: 15px;
            justify-content: center;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .legend-color {{
            width: 16px;
            height: 16px;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>

        <div class="metrics">
            <div class="metric-card">
                <div class="metric-value">{self.metrics.states_discovered}</div>
                <div class="metric-label">States Discovered</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{self.metrics.transitions_executed}</div>
                <div class="metric-label">Transitions</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{self.metrics.endpoint_coverage_pct:.1f}%</div>
                <div class="metric-label">Endpoint Coverage</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{self.metrics.error_rate:.1f}%</div>
                <div class="metric-label">Error Rate</div>
            </div>
        </div>

        <div id="graph-container"></div>

        <div class="legend">
            <div class="legend-item">
                <div class="legend-color" style="background: #3b82f6;"></div>
                <span>Start State</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #22c55e;"></div>
                <span>Normal State</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #ef4444;"></div>
                <span>Error State</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #6b7280;"></div>
                <span>Terminal State</span>
            </div>
        </div>
    </div>

    <script>
        var nodes = new vis.DataSet({json.dumps(nodes_data)});
        var edges = new vis.DataSet({json.dumps(edges_data)});

        var container = document.getElementById('graph-container');
        var data = {{ nodes: nodes, edges: edges }};
        var options = {{
            layout: {{
                hierarchical: {{
                    direction: 'UD',
                    sortMethod: 'directed',
                    nodeSpacing: 150,
                    levelSeparation: 100,
                }}
            }},
            physics: false,
            interaction: {{
                hover: true,
                tooltipDelay: 100,
            }},
            nodes: {{
                font: {{ size: 12 }},
                borderWidth: 2,
            }},
            edges: {{
                font: {{ size: 10, align: 'middle' }},
                width: 2,
            }},
        }};

        var network = new vis.Network(container, data, options);
    </script>
</body>
</html>'''

    def _get_node_color(self, node: StateNode) -> str:
        if node.signature == self.graph.root_state:
            return "#3b82f6"
        if node.is_error_state:
            return "#ef4444"
        if node.is_terminal:
            return "#6b7280"
        return "#22c55e"

    def _get_edge_color(self, transition: StateTransition) -> str:
        if transition.is_error:
            return "#ef4444"
        return "#6b7280"

    def _get_node_tooltip(self, node: StateNode) -> str:
        return f"""
State: {node.signature}
Depth: {node.depth}
Visits: {node.visit_count}
Path: {' -> '.join(node.discovery_path[:3])}{'...' if len(node.discovery_path) > 3 else ''}
        """.strip()

    def _get_edge_tooltip(self, transition: StateTransition) -> str:
        return f"""
Action: {transition.action}
Method: {transition.method}
URL: {transition.url}
Status: {transition.status_code}
Duration: {transition.duration_ms:.0f}ms
        """.strip()
```

---

## 8. Integration Points

### 8.1 Integration with VenomQA Client

```python
from venomqa.clients.base import BaseClient

class StateExplorerClient:
    """Wrapper around VenomQA client for state exploration."""

    def __init__(self, client: BaseClient):
        self.client = client
        self._ensure_connected()

    def _ensure_connected(self) -> None:
        """Ensure client is connected."""
        if not self.client.is_connected():
            self.client.connect()

    def execute_action(
        self,
        action: GeneratedAction,
    ) -> tuple[dict[str, Any], int, float]:
        """Execute an action and return response data.

        Returns:
            Tuple of (response_json, status_code, duration_ms)
        """
        import time

        start = time.time()

        # Build headers
        headers = {**self.client.default_headers, **action.headers}

        # Execute request using VenomQA client internals
        response = self.client._session.request(
            method=action.method,
            url=action.url,
            json=action.body,
            headers=headers,
            timeout=self.client.timeout,
        )

        duration_ms = (time.time() - start) * 1000

        # Record in history
        self.client._record_request(
            operation=f"{action.method} {action.url}",
            request_data=action.body,
            response_data=response.json() if response.content else None,
            duration_ms=duration_ms,
        )

        return response.json(), response.status_code, duration_ms
```

### 8.2 Integration with StateManager for Rollbacks

```python
from venomqa.state import StateManager

class ExplorationStateIntegration:
    """Integration between State Explorer and VenomQA StateManager."""

    def __init__(self, state_manager: StateManager):
        self.state_manager = state_manager
        self.exploration_checkpoints: dict[str, str] = {}

    def initialize(self) -> str:
        """Initialize exploration with base checkpoint.

        Returns:
            Name of the base checkpoint.
        """
        self.state_manager.connect()
        checkpoint_name = "exploration_base"
        self.state_manager.checkpoint(checkpoint_name)
        self.exploration_checkpoints["base"] = checkpoint_name
        return checkpoint_name

    def create_state_checkpoint(self, state_signature: str) -> str:
        """Create checkpoint for a specific state.

        Args:
            state_signature: State signature to checkpoint.

        Returns:
            Checkpoint name.
        """
        checkpoint_name = f"state_{state_signature[:16]}"
        self.state_manager.checkpoint(checkpoint_name)
        self.exploration_checkpoints[state_signature] = checkpoint_name
        return checkpoint_name

    def rollback_to_state(self, state_signature: str) -> bool:
        """Rollback to a previously checkpointed state.

        Args:
            state_signature: State to rollback to.

        Returns:
            True if rollback successful, False if checkpoint not found.
        """
        checkpoint_name = self.exploration_checkpoints.get(state_signature)
        if not checkpoint_name:
            return False

        self.state_manager.rollback(checkpoint_name)
        return True

    def cleanup(self) -> None:
        """Clean up all exploration checkpoints."""
        # Rollback to base
        base = self.exploration_checkpoints.get("base")
        if base:
            self.state_manager.rollback(base)

        # Release all checkpoints
        for checkpoint_name in self.exploration_checkpoints.values():
            try:
                self.state_manager.release(checkpoint_name)
            except Exception:
                pass  # Ignore release errors

        self.state_manager.disconnect()
```

### 8.3 Integration with Reporters

```python
from venomqa.reporters.base import BaseReporter
from venomqa.core.models import JourneyResult, StepResult, Issue, Severity

class StateExplorerReporter(BaseReporter):
    """Reporter for state exploration results."""

    @property
    def file_extension(self) -> str:
        return ".html"

    def __init__(
        self,
        output_path: str | Path | None = None,
        include_graph: bool = True,
        include_coverage: bool = True,
    ):
        super().__init__(output_path)
        self.include_graph = include_graph
        self.include_coverage = include_coverage

    def generate_from_exploration(
        self,
        graph: StateGraph,
        metrics: CoverageMetrics,
        issues: list[DetectedIssue],
    ) -> str:
        """Generate HTML report from exploration results."""

        # Create HTML visualization
        visualizer = HTMLVisualizationExporter(graph, metrics)
        base_html = visualizer.to_html("State Explorer Results")

        # Inject issues section
        issues_html = self._render_issues(issues)

        # Insert before closing body tag
        return base_html.replace("</body>", f"{issues_html}</body>")

    def _render_issues(self, issues: list[DetectedIssue]) -> str:
        """Render detected issues as HTML."""

        if not issues:
            return """
            <div class="container" style="margin-top: 20px;">
                <div style="background: white; padding: 20px; border-radius: 8px; text-align: center;">
                    <span style="color: #22c55e; font-size: 1.5rem;">&#10003;</span>
                    <span style="margin-left: 10px;">No issues detected</span>
                </div>
            </div>"""

        issue_cards = []
        for issue in issues:
            color = self._get_severity_color(issue.severity)
            issue_cards.append(f"""
            <div style="border-left: 4px solid {color}; background: white; padding: 15px; margin-bottom: 10px; border-radius: 0 8px 8px 0;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                    <strong>{issue.issue_type.value.replace('_', ' ').title()}</strong>
                    <span style="background: {color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;">
                        {issue.severity.value.upper()}
                    </span>
                </div>
                <p style="color: #6b7280; margin-bottom: 10px;">{issue.message}</p>
                <div style="background: #dcfce7; color: #166534; padding: 10px; border-radius: 4px;">
                    <strong>Suggestion:</strong> {issue.suggestion}
                </div>
            </div>
            """)

        return f"""
        <div class="container" style="margin-top: 20px;">
            <h2 style="margin-bottom: 15px;">Detected Issues ({len(issues)})</h2>
            {''.join(issue_cards)}
        </div>"""

    def _get_severity_color(self, severity: Severity) -> str:
        colors = {
            Severity.CRITICAL: "#dc2626",
            Severity.HIGH: "#ea580c",
            Severity.MEDIUM: "#d97706",
            Severity.LOW: "#2563eb",
            Severity.INFO: "#6b7280",
        }
        return colors.get(severity, "#6b7280")

    def generate(self, results: list[JourneyResult]) -> str:
        """Generate standard VenomQA report format.

        Note: Use generate_from_exploration() for state exploration results.
        """
        raise NotImplementedError(
            "Use generate_from_exploration() for state exploration results"
        )
```

### 8.4 CLI Integration

```python
# In venomqa/cli/commands.py

import click

@click.command()
@click.option("--openapi", "-o", type=click.Path(exists=True), help="OpenAPI spec file")
@click.option("--base-url", "-u", required=True, help="API base URL")
@click.option("--max-depth", "-d", default=10, help="Maximum exploration depth")
@click.option("--max-states", "-s", default=1000, help="Maximum states to discover")
@click.option("--output", "-O", default="state_graph.html", help="Output file")
@click.option("--format", "-f", type=click.Choice(["html", "dot", "mermaid", "json"]), default="html")
def explore(openapi, base_url, max_depth, max_states, output, format):
    """Explore API state space automatically.

    Example:
        venomqa explore -o openapi.yaml -u http://localhost:8000 -d 5 -O report.html
    """
    from venomqa.exploration import StateExplorer, ExplorationConfig
    from venomqa.clients import HTTPClient

    # Load OpenAPI spec
    spec = load_openapi_spec(openapi) if openapi else None

    # Configure exploration
    config = ExplorationConfig(
        max_depth=max_depth,
        max_states=max_states,
    )

    # Create client and explorer
    client = HTTPClient(base_url)
    explorer = StateExplorer(
        client=client,
        action_generator=OpenAPIActionGenerator(spec, DataGenerator(), base_url),
        config=config,
    )

    # Run exploration
    click.echo("Starting state exploration...")
    with click.progressbar(length=max_states, label="Exploring") as bar:
        graph = explorer.explore(get_initial_state())
        bar.update(explorer.states_discovered)

    # Calculate metrics and detect issues
    metrics = CoverageCalculator(graph, spec).calculate()
    issues = IssueDetector(graph, IssueDetectionConfig()).detect_all()

    # Generate output
    if format == "html":
        reporter = StateExplorerReporter()
        content = reporter.generate_from_exploration(graph, metrics, issues)
    elif format == "dot":
        content = GraphvizExporter(graph).to_dot()
    elif format == "mermaid":
        content = MermaidExporter(graph).to_mermaid()
    else:  # json
        content = StateGraphSerializer.to_json(graph)

    # Write output
    with open(output, "w") as f:
        f.write(content)

    click.echo(f"\nExploration complete!")
    click.echo(f"  States discovered: {metrics.states_discovered}")
    click.echo(f"  Transitions: {metrics.transitions_executed}")
    click.echo(f"  Issues found: {len(issues)}")
    click.echo(f"  Output: {output}")
```

---

## Appendix A: Complete Usage Example

```python
from venomqa.clients import HTTPClient
from venomqa.state import PostgreSQLStateManager
from venomqa.exploration import (
    StateExplorer,
    ExplorationConfig,
    OpenAPIActionGenerator,
    DataGenerator,
    IssueDetector,
    CoverageCalculator,
    StateExplorerReporter,
)

# Load OpenAPI spec
with open("openapi.yaml") as f:
    import yaml
    spec = yaml.safe_load(f)

# Configure exploration
config = ExplorationConfig(
    strategy=ExplorationStrategy.HYBRID,
    max_depth=8,
    max_states=500,
    max_transitions=2000,
    parallel_workers=4,
    rollback_on_mutation=True,
)

# Set up components
client = HTTPClient("http://localhost:8000")
state_manager = PostgreSQLStateManager("postgresql://localhost/testdb")
action_generator = OpenAPIActionGenerator(spec, DataGenerator(), "http://localhost:8000")

# Create explorer
explorer = StateExplorer(
    client=client,
    state_manager=state_manager,
    action_generator=action_generator,
    config=config,
)

# Run exploration
with state_manager:
    # Get initial state
    initial_response = client.get("/api/health").json()

    # Explore state space
    graph = explorer.explore(initial_response)

    # Calculate coverage
    metrics = CoverageCalculator(graph, spec).calculate()

    # Detect issues
    issues = IssueDetector(graph, IssueDetectionConfig()).detect_all()

    # Generate report
    reporter = StateExplorerReporter(output_path="state_exploration_report.html")
    reporter.save_from_exploration(graph, metrics, issues)

    # Print summary
    print(f"Exploration complete!")
    print(f"  States: {metrics.states_discovered}")
    print(f"  Transitions: {metrics.transitions_executed}")
    print(f"  Endpoint Coverage: {metrics.endpoint_coverage_pct:.1f}%")
    print(f"  Issues: {len(issues)} ({len([i for i in issues if i.severity == Severity.CRITICAL])} critical)")
```

---

## Appendix B: Diagram - State Explorer Architecture

```
                    +------------------+
                    |   OpenAPI Spec   |
                    +--------+---------+
                             |
                             v
                    +------------------+
                    | ActionGenerator  |
                    +--------+---------+
                             |
                             v
+-------------+     +------------------+     +----------------+
| VenomQA     | --> | State Explorer   | --> | State Graph    |
| HTTPClient  |     |  (BFS/DFS/Hybrid)|     | (Adjacency List)|
+-------------+     +--------+---------+     +--------+-------+
                             |                        |
                             v                        v
                    +------------------+     +----------------+
                    | StateManager     |     | Issue Detector |
                    | (Rollbacks)      |     +--------+-------+
                    +------------------+              |
                                                     v
                                            +----------------+
                                            | Coverage Calc  |
                                            +--------+-------+
                                                     |
                                                     v
                                            +----------------+
                                            | Reporters      |
                                            | - HTML (vis.js)|
                                            | - DOT          |
                                            | - Mermaid      |
                                            | - JSON         |
                                            +----------------+
```

---

## Version History

| Version | Date       | Author | Changes                          |
|---------|------------|--------|----------------------------------|
| 1.0     | 2024-01-15 | VenomQA| Initial specification            |

---

*This specification is part of the VenomQA framework documentation.*
