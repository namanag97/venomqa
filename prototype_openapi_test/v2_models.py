"""
VenomQA v2 Data Models

These are the core data structures for the new architecture.
Designed for:
1. Zero-config user experience
2. Auto-generation from OpenAPI
3. Full environment control
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal, Protocol


# =============================================================================
# Enums
# =============================================================================

class CRUDType(Enum):
    """CRUD operation types."""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LIST = "list"
    ACTION = "action"  # Non-CRUD operations


class ContainerStatus(Enum):
    """Docker container status."""
    STARTING = "starting"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STOPPED = "stopped"


class InvariantSource(Enum):
    """Where an invariant was generated from."""
    CRUD = "crud"           # From HTTP method semantics
    SCHEMA = "schema"       # From OpenAPI schema
    RELATIONSHIP = "rel"    # From resource hierarchy
    CUSTOM = "custom"       # User-defined


class Severity(Enum):
    """Bug severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class VenomQAConfig:
    """
    Main configuration.

    Design principle: Everything has sensible defaults.
    User provides docker-compose.yml, we figure out the rest.
    """

    # === Environment ===
    compose_file: Path = field(default_factory=lambda: Path("docker-compose.yml"))
    project_name: str | None = None  # Docker project name (auto-generated)

    # === Service Detection ===
    # If None, auto-detect by looking for:
    # - Service with port 8000, 8080, 3000, 5000 exposed
    # - Service named "api", "app", "web", "server"
    api_service: str | None = None
    api_port: int | None = None

    # If None, no DB rollback (API-level tracking only)
    # If set, use DB savepoints for full rollback
    db_service: str | None = None
    db_type: Literal["postgres", "mysql"] | None = None

    # === API Discovery ===
    # Paths to try for OpenAPI spec (in order)
    openapi_paths: list[str] = field(default_factory=lambda: [
        "/openapi.json",
        "/swagger.json",
        "/api/openapi.json",
        "/api/swagger.json",
        "/docs/openapi.json",
        "/v1/openapi.json",
    ])

    # === Exploration ===
    strategy: Literal["bfs", "dfs", "mcts"] = "bfs"
    max_steps: int = 1000
    max_depth: int = 10
    timeout_seconds: int = 300

    # === Invariants ===
    enable_crud_invariants: bool = True
    enable_schema_invariants: bool = True
    enable_relationship_invariants: bool = True

    # === Output ===
    output_format: Literal["console", "json", "html"] = "console"
    output_file: Path | None = None
    verbose: bool = False

    # === Advanced ===
    container_startup_timeout: int = 60
    request_timeout: int = 30
    retry_count: int = 3


# =============================================================================
# Environment
# =============================================================================

@dataclass
class Container:
    """A Docker container in our test environment."""

    id: str
    name: str
    service_name: str  # From docker-compose
    image: str
    status: ContainerStatus

    # Port mappings: container_port -> host_port
    ports: dict[int, int] = field(default_factory=dict)

    # Health check info
    health_check_cmd: str | None = None
    last_health_check: datetime | None = None

    def get_host_port(self, container_port: int) -> int | None:
        """Get the host port mapped to a container port."""
        return self.ports.get(container_port)


@dataclass
class TestEnvironment:
    """
    The isolated test environment.

    VenomQA owns this completely - we start it, we control it, we stop it.
    """

    # Compose info
    compose_file: Path
    project_name: str

    # Running containers
    containers: dict[str, Container] = field(default_factory=dict)
    network_name: str | None = None

    # Detected services
    api_container: Container | None = None
    api_base_url: str | None = None  # e.g., "http://localhost:32789"

    db_container: Container | None = None
    db_connection_string: str | None = None

    # Lifecycle
    started_at: datetime | None = None
    status: Literal["created", "starting", "ready", "exploring", "stopping", "stopped"] = "created"

    def get_container(self, service_name: str) -> Container | None:
        """Get a container by service name."""
        return self.containers.get(service_name)

    @property
    def is_ready(self) -> bool:
        """Check if environment is ready for testing."""
        return (
            self.status == "ready"
            and self.api_container is not None
            and self.api_container.status == ContainerStatus.HEALTHY
        )


# =============================================================================
# API Discovery
# =============================================================================

@dataclass
class SchemaSpec:
    """
    A JSON Schema specification (fully resolved, no $refs).

    This is what we use for:
    - Generating request bodies
    - Validating responses
    - Creating invariants
    """

    type: str | None = None  # "object", "array", "string", "integer", etc.

    # For objects
    properties: dict[str, SchemaSpec] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    additional_properties: bool | SchemaSpec = True

    # For arrays
    items: SchemaSpec | None = None
    min_items: int | None = None
    max_items: int | None = None

    # For strings
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    format: str | None = None  # "email", "uri", "date-time", etc.

    # For numbers
    minimum: float | None = None
    maximum: float | None = None
    exclusive_minimum: float | None = None
    exclusive_maximum: float | None = None

    # For enums
    enum: list[Any] | None = None

    # Composition (resolved)
    one_of: list[SchemaSpec] | None = None
    any_of: list[SchemaSpec] | None = None
    all_of: list[SchemaSpec] | None = None

    # Original raw schema (for debugging)
    _raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict, resolver: Callable[[str], dict] | None = None) -> SchemaSpec:
        """Parse a JSON Schema dict into SchemaSpec, resolving $refs."""
        # Handle $ref
        if "$ref" in data and resolver:
            resolved = resolver(data["$ref"])
            return cls.from_dict(resolved, resolver)

        spec = cls(_raw=data)
        spec.type = data.get("type")
        spec.required = data.get("required", [])
        spec.enum = data.get("enum")

        # Object properties
        if "properties" in data:
            spec.properties = {
                k: cls.from_dict(v, resolver)
                for k, v in data["properties"].items()
            }

        # Array items
        if "items" in data:
            spec.items = cls.from_dict(data["items"], resolver)

        # String constraints
        spec.min_length = data.get("minLength")
        spec.max_length = data.get("maxLength")
        spec.pattern = data.get("pattern")
        spec.format = data.get("format")

        # Number constraints
        spec.minimum = data.get("minimum")
        spec.maximum = data.get("maximum")

        return spec


@dataclass
class ParamSpec:
    """An API parameter (path, query, header, cookie)."""

    name: str
    location: Literal["path", "query", "header", "cookie"]
    required: bool = False
    schema: SchemaSpec | None = None
    description: str | None = None

    # For path params, this is the context key to look up
    context_key: str | None = None


@dataclass
class DiscoveredEndpoint:
    """
    An endpoint discovered from OpenAPI.

    This is the intermediate representation between OpenAPI and VenomQA actions.
    """

    # Identity
    path: str                        # "/users/{user_id}"
    method: str                      # "GET", "POST", etc.
    operation_id: str | None = None  # "getUser"

    # Inferred semantics
    resource_type: str | None = None  # "user"
    crud_type: CRUDType = CRUDType.ACTION

    # Parameters
    path_params: list[ParamSpec] = field(default_factory=list)
    query_params: list[ParamSpec] = field(default_factory=list)
    header_params: list[ParamSpec] = field(default_factory=list)

    # Request body
    request_body_required: bool = False
    request_body_schema: SchemaSpec | None = None

    # Responses
    success_responses: dict[int, SchemaSpec] = field(default_factory=dict)  # 200 -> schema
    error_responses: dict[int, SchemaSpec] = field(default_factory=dict)    # 400 -> schema

    # Dependencies (inferred from path)
    requires_resources: list[str] = field(default_factory=list)  # ["organization"]

    # Security
    requires_auth: bool = False
    security_schemes: list[str] = field(default_factory=list)

    # Metadata
    summary: str | None = None
    description: str | None = None
    tags: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        """Generate a name for this endpoint."""
        if self.operation_id:
            return self.operation_id
        # Fallback: method_resource
        resource = self.resource_type or "unknown"
        return f"{self.method.lower()}_{resource}"

    @property
    def path_param_names(self) -> list[str]:
        """Get list of path parameter names."""
        return [p.name for p in self.path_params]


@dataclass
class ResourceType:
    """A resource type inferred from the API."""

    name: str                    # "user"
    plural: str                  # "users"
    parent: str | None = None   # "organization" (if nested)

    # Endpoints that operate on this resource
    create_endpoint: str | None = None
    read_endpoint: str | None = None
    update_endpoint: str | None = None
    delete_endpoint: str | None = None
    list_endpoint: str | None = None


@dataclass
class DiscoveredAPI:
    """
    Everything we learn from the OpenAPI spec.

    This is the complete parsed representation used for generation.
    """

    # Metadata
    title: str = ""
    version: str = ""
    description: str = ""
    openapi_version: str = ""

    # Endpoints
    endpoints: list[DiscoveredEndpoint] = field(default_factory=list)

    # Schemas (resolved)
    schemas: dict[str, SchemaSpec] = field(default_factory=dict)

    # Inferred structure
    resource_types: dict[str, ResourceType] = field(default_factory=dict)

    # Security
    security_schemes: dict[str, dict] = field(default_factory=dict)

    @property
    def endpoint_count(self) -> int:
        return len(self.endpoints)

    def get_endpoint(self, operation_id: str) -> DiscoveredEndpoint | None:
        """Get endpoint by operation ID."""
        for ep in self.endpoints:
            if ep.operation_id == operation_id:
                return ep
        return None


# =============================================================================
# Generated Artifacts
# =============================================================================

@dataclass
class GeneratedAction:
    """
    An action generated from an endpoint.

    This wraps a DiscoveredEndpoint with execution logic.
    """

    name: str
    endpoint: DiscoveredEndpoint

    # Preconditions (auto-generated from path params and resources)
    required_context_keys: list[str] = field(default_factory=list)
    required_resources: list[str] = field(default_factory=list)

    # Expected responses
    expected_success_codes: list[int] = field(default_factory=lambda: [200, 201, 204])
    expected_error_codes: list[int] = field(default_factory=lambda: [400, 401, 403, 404])

    # Generated at runtime
    _execute: Callable | None = field(default=None, repr=False)
    _body_generator: Callable | None = field(default=None, repr=False)


@dataclass
class GeneratedInvariant:
    """
    An invariant generated from the API spec.

    Invariants are the heart of VenomQA - they define what "correct" means.
    """

    name: str
    description: str
    source: InvariantSource
    severity: Severity = Severity.MEDIUM

    # What generated this invariant
    endpoint: DiscoveredEndpoint | None = None
    schema: SchemaSpec | None = None

    # The check function (set at runtime)
    _check: Callable | None = field(default=None, repr=False)

    @property
    def source_description(self) -> str:
        """Human-readable description of where this came from."""
        if self.endpoint:
            return f"{self.endpoint.method} {self.endpoint.path}"
        if self.source == InvariantSource.SCHEMA:
            return "response schema"
        return str(self.source.value)


@dataclass
class GeneratedArtifacts:
    """All generated test artifacts."""

    actions: list[GeneratedAction] = field(default_factory=list)
    invariants: list[GeneratedInvariant] = field(default_factory=list)
    resource_types: dict[str, ResourceType] = field(default_factory=dict)

    @property
    def action_count(self) -> int:
        return len(self.actions)

    @property
    def invariant_count(self) -> int:
        return len(self.invariants)

    def invariants_by_source(self) -> dict[str, int]:
        """Count invariants by source type."""
        counts: dict[str, int] = {}
        for inv in self.invariants:
            key = inv.source.value
            counts[key] = counts.get(key, 0) + 1
        return counts


# =============================================================================
# Exploration & Results
# =============================================================================

@dataclass
class ActionResult:
    """Result of executing an action."""

    success: bool
    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    error: str | None = None
    duration_ms: float = 0.0

    # Request info (for reproduction)
    request_method: str = ""
    request_url: str = ""
    request_headers: dict[str, str] = field(default_factory=dict)
    request_body: Any = None

    @property
    def is_success(self) -> bool:
        """Check if response indicates success (2xx)."""
        return 200 <= self.status_code < 300

    def to_curl(self) -> str:
        """Generate curl command to reproduce this request."""
        parts = ["curl", "-X", self.request_method]

        for k, v in self.request_headers.items():
            if k.lower() not in ("host", "content-length"):
                parts.extend(["-H", f'"{k}: {v}"'])

        if self.request_body:
            import json
            body_str = json.dumps(self.request_body)
            parts.extend(["-d", f"'{body_str}'"])

        parts.append(f'"{self.request_url}"')
        return " ".join(parts)


@dataclass
class ExplorationState:
    """A state in the exploration graph."""

    id: str

    # What we observed
    resources: dict[str, list[str]] = field(default_factory=dict)  # type -> [ids]
    context: dict[str, Any] = field(default_factory=dict)

    # For rollback
    checkpoint_id: str | None = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Transition:
    """A transition in the exploration graph."""

    from_state_id: str
    action_name: str
    to_state_id: str

    result: ActionResult
    duration_ms: float = 0.0

    # Violations found during this transition
    violations: list[str] = field(default_factory=list)


@dataclass
class Bug:
    """A bug found during exploration."""

    id: str

    # What failed
    invariant_name: str
    invariant_description: str
    severity: Severity

    # Where it failed
    state_id: str
    action_name: str

    # How to reproduce
    reproduction_path: list[Transition] = field(default_factory=list)

    # Details
    expected: str = ""
    actual: str = ""
    result: ActionResult | None = None

    # Metadata
    found_at: datetime = field(default_factory=datetime.now)

    def to_curl_commands(self) -> list[str]:
        """Generate curl commands to reproduce this bug."""
        return [t.result.to_curl() for t in self.reproduction_path if t.result]


@dataclass
class ExplorationResult:
    """Final results of an exploration run."""

    # Environment info
    api_title: str = ""
    api_version: str = ""
    environment_name: str = ""

    # What was tested
    actions_count: int = 0
    invariants_count: int = 0

    # Exploration stats
    states_visited: int = 0
    transitions_taken: int = 0
    duration_ms: float = 0.0

    # Findings
    bugs: list[Bug] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Coverage
    actions_executed: set[str] = field(default_factory=set)
    actions_not_executed: set[str] = field(default_factory=set)

    @property
    def bug_count(self) -> int:
        return len(self.bugs)

    @property
    def has_bugs(self) -> bool:
        return len(self.bugs) > 0

    @property
    def coverage_percentage(self) -> float:
        total = len(self.actions_executed) + len(self.actions_not_executed)
        if total == 0:
            return 100.0
        return len(self.actions_executed) / total * 100

    def bugs_by_severity(self) -> dict[str, int]:
        """Count bugs by severity."""
        counts: dict[str, int] = {}
        for bug in self.bugs:
            key = bug.severity.value
            counts[key] = counts.get(key, 0) + 1
        return counts


# =============================================================================
# State Management Protocol
# =============================================================================

class StateManager(Protocol):
    """Protocol for state management backends."""

    def checkpoint(self, name: str) -> str:
        """Create a checkpoint, return checkpoint ID."""
        ...

    def rollback(self, checkpoint_id: str) -> None:
        """Rollback to a checkpoint."""
        ...

    def observe(self) -> dict[str, Any]:
        """Get current state observation."""
        ...


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Example of how these models fit together

    # 1. Config (mostly defaults)
    config = VenomQAConfig(
        compose_file=Path("docker-compose.yml"),
        # Everything else auto-detected
    )

    # 2. Environment (would be created by EnvironmentManager)
    env = TestEnvironment(
        compose_file=config.compose_file,
        project_name="venomqa_test_abc123",
        api_base_url="http://localhost:32789",
    )

    # 3. Discovered API (would be created by DiscoveryEngine)
    endpoint = DiscoveredEndpoint(
        path="/users/{user_id}",
        method="GET",
        operation_id="getUser",
        resource_type="user",
        crud_type=CRUDType.READ,
        path_params=[ParamSpec(name="user_id", location="path", required=True)],
    )

    api = DiscoveredAPI(
        title="My API",
        version="1.0",
        endpoints=[endpoint],
    )

    # 4. Generated artifacts (would be created by GeneratorEngine)
    action = GeneratedAction(
        name="getUser",
        endpoint=endpoint,
        required_context_keys=["user_id"],
    )

    invariant = GeneratedInvariant(
        name="get_user_returns_200_after_create",
        description="GET /users/{id} should return 200 after user is created",
        source=InvariantSource.CRUD,
        endpoint=endpoint,
    )

    artifacts = GeneratedArtifacts(
        actions=[action],
        invariants=[invariant],
    )

    # 5. Exploration result (would be created by ExplorationEngine)
    bug = Bug(
        id="bug_001",
        invariant_name="delete_returns_404_on_retry",
        invariant_description="Second DELETE should return 404",
        severity=Severity.MEDIUM,
        state_id="state_123",
        action_name="deleteUser",
        expected="404",
        actual="200",
    )

    result = ExplorationResult(
        api_title="My API",
        states_visited=50,
        transitions_taken=150,
        bugs=[bug],
        actions_executed={"createUser", "getUser", "deleteUser"},
    )

    print("Example data models created successfully!")
    print(f"  Config: {config.compose_file}")
    print(f"  API: {api.title} ({api.endpoint_count} endpoints)")
    print(f"  Artifacts: {artifacts.action_count} actions, {artifacts.invariant_count} invariants")
    print(f"  Result: {result.bug_count} bugs found")
