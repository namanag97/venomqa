# API Reference

This document provides a comprehensive reference for all public classes and functions in VenomQA.

> **Quick Start**: New to VenomQA? See the [Getting Started Guide](getting-started.md) first.

## Table of Contents

- [Core Models](#core-models)
  - [Journey](#journey)
  - [Step](#step)
  - [Checkpoint](#checkpoint)
  - [Branch](#branch)
  - [Path](#path)
- [Result Models](#result-models)
  - [JourneyResult](#journeyresult)
  - [StepResult](#stepresult)
  - [PathResult](#pathresult)
  - [Issue](#issue)
  - [Severity](#severity)
- [Execution](#execution)
  - [JourneyRunner](#journeyrunner)
  - [ExecutionContext](#executioncontext)
- [Client](#client)
  - [Client](#client-class)
  - [AsyncClient](#asyncclient)
  - [RequestRecord](#requestrecord)
- [Configuration](#configuration)
  - [QAConfig](#qaconfig)
  - [load_config](#load_config)
- [State Management](#state-management)
  - [StateManager Protocol](#statemanager-protocol)
  - [PostgreSQLStateManager](#postgresqlstatemanager)
- [Reporters](#reporters)
  - [BaseReporter](#basereporter)
  - [MarkdownReporter](#markdownreporter)
  - [JSONReporter](#jsonreporter)
  - [JUnitReporter](#junitreporter)
- [Infrastructure](#infrastructure)
  - [InfrastructureManager Protocol](#infrastructuremanager-protocol)
  - [DockerInfrastructureManager](#dockerinfrastructuremanager)

## Related Documentation

| Topic | Document |
|-------|----------|
| Writing Journeys | [journeys.md](journeys.md) |
| Database Backends | [backends.md](backends.md) |
| CLI Reference | [cli.md](cli.md) |
| Ports & Adapters | [ports.md](ports.md) |
| Advanced Usage | [advanced.md](advanced.md) |
| FAQ | [FAQ.md](FAQ.md) |

---

## Core Models

### Journey

A complete user scenario from start to finish. Contains a sequence of Steps, Checkpoints, and Branches.

```python
from venomqa import Journey, Step, Checkpoint, Branch

journey = Journey(
    name="user_registration",
    description="Complete user registration flow",
    tags=["auth", "critical"],
    timeout=120.0,
    steps=[
        Step(name="register", action=register_user),
        Checkpoint(name="user_created"),
        Step(name="verify_email", action=verify_email),
    ],
)
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | Required | Unique identifier for the journey |
| `steps` | `list[Step \| Checkpoint \| Branch]` | Required | Sequence of steps to execute |
| `description` | `str` | `""` | Human-readable description |
| `tags` | `list[str]` | `[]` | Tags for filtering/categorization |
| `timeout` | `float \| None` | `None` | Maximum execution time in seconds |

#### Methods

| Method | Return Type | Description |
|--------|-------------|-------------|
| `_validate_checkpoints()` | `None` | Validates that all Branch references point to existing Checkpoints |

#### Raises

- `ValueError`: If a Branch references a non-existent checkpoint

---

### Step

A single action in a journey with optional assertions.

```python
from venomqa import Step

def login_action(client, context):
    response = client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "secret",
    })
    context["token"] = response.json()["token"]
    return response

step = Step(
    name="login",
    action=login_action,
    description="Authenticate user",
    timeout=10.0,
    retries=3,
    expect_failure=False,
)
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | Required | Unique identifier for the step |
| `action` | `Callable[[Client, ExecutionContext], Any]` | Required | Function to execute |
| `description` | `str` | `""` | Human-readable description |
| `expect_failure` | `bool` | `False` | If True, step passes when action fails |
| `timeout` | `float \| None` | `None` | Maximum execution time in seconds |
| `retries` | `int` | `0` | Number of retry attempts on failure |

#### Action Function Signature

```python
def action(client: Client, context: ExecutionContext) -> Any:
    """
    Args:
        client: HTTP client for making requests
        context: Execution context for sharing data between steps
    
    Returns:
        Any: Typically an httpx.Response object
    """
    pass
```

---

### Checkpoint

A savepoint for database state that enables rollback.

```python
from venomqa import Checkpoint

checkpoint = Checkpoint(name="user_created")
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | Required | Unique identifier for the checkpoint |

---

### Branch

Forks execution to explore multiple paths from a checkpoint.

```python
from venomqa import Branch, Path, Step

branch = Branch(
    checkpoint_name="order_created",
    paths=[
        Path(name="card_payment", steps=[
            Step(name="pay_card", action=pay_with_card),
        ]),
        Path(name="wallet_payment", steps=[
            Step(name="pay_wallet", action=pay_with_wallet),
        ]),
    ],
)
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `checkpoint_name` | `str` | Required | Name of the checkpoint to rollback to |
| `paths` | `list[Path]` | Required | List of paths to explore |

---

### Path

A sequence of steps within a branch.

```python
from venomqa import Path, Step

path = Path(
    name="successful_payment",
    description="Happy path for payment processing",
    steps=[
        Step(name="submit_payment", action=submit_payment),
        Step(name="verify_receipt", action=verify_receipt),
    ],
)
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | Required | Unique identifier for the path |
| `steps` | `list[Step \| Checkpoint]` | Required | Sequence of steps to execute |
| `description` | `str` | `""` | Human-readable description |

---

## Result Models

### JourneyResult

Result of executing a complete journey.

```python
@dataclass
class JourneyResult:
    journey_name: str
    success: bool
    started_at: datetime
    finished_at: datetime
    step_results: list[StepResult]
    branch_results: list[BranchResult]
    issues: list[Issue]
    duration_ms: float
```

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `total_steps` | `int` | Total number of steps executed |
| `passed_steps` | `int` | Number of successful steps |
| `total_paths` | `int` | Total number of branch paths executed |
| `passed_paths` | `int` | Number of successful paths |

---

### StepResult

Result of executing a single step.

```python
@dataclass
class StepResult:
    step_name: str
    success: bool
    started_at: datetime
    finished_at: datetime
    response: dict[str, Any] | None
    error: str | None
    request: dict[str, Any] | None
    duration_ms: float
```

---

### PathResult

Result of executing a path within a branch.

```python
@dataclass
class PathResult:
    path_name: str
    success: bool
    step_results: list[StepResult]
    error: str | None
```

---

### Issue

Captured failure with full context.

```python
@dataclass
class Issue:
    journey: str
    path: str
    step: str
    error: str
    severity: Severity
    request: dict[str, Any] | None
    response: dict[str, Any] | None
    logs: list[str]
    suggestion: str
    timestamp: datetime
```

#### Auto-Generated Suggestions

The `Issue` class automatically generates fix suggestions based on error patterns:

| Error Pattern | Suggestion |
|---------------|------------|
| `401` | Check authentication - token may be invalid or expired |
| `403` | Permission denied - check user roles and permissions |
| `404` | Endpoint not found - verify route registration and URL path |
| `422` | Validation error - check request body schema |
| `500` | Server error - check backend logs for exception traceback |
| `timeout` | Operation timed out - check if service is healthy |
| `connection refused` | Service not running - check Docker or network |

---

### Severity

Issue severity levels.

```python
from venomqa import Severity

class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"
```

---

## Execution

### JourneyRunner

Executes journeys with state branching and rollback support.

```python
from venomqa import JourneyRunner, Client
from venomqa.state import PostgreSQLStateManager

client = Client(base_url="http://localhost:8000")
state_manager = PostgreSQLStateManager("postgresql://qa:secret@localhost/qa_test")

runner = JourneyRunner(
    client=client,
    state_manager=state_manager,
    parallel_paths=4,
    fail_fast=False,
    capture_logs=True,
    log_lines=50,
)

result = runner.run(journey)
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `client` | `Client` | Required | HTTP client for requests |
| `state_manager` | `StateManager \| None` | `None` | State manager for checkpoints |
| `parallel_paths` | `int` | `1` | Max concurrent branch paths |
| `fail_fast` | `bool` | `False` | Stop on first failure |
| `capture_logs` | `bool` | `True` | Capture infrastructure logs |
| `log_lines` | `int` | `50` | Number of log lines to capture |

#### Methods

| Method | Return Type | Description |
|--------|-------------|-------------|
| `run(journey: Journey)` | `JourneyResult` | Execute a complete journey |
| `get_issues()` | `list[Issue]` | Get all captured issues |

---

### ExecutionContext

Typed context for sharing state between steps.

```python
from venomqa.core.context import ExecutionContext

context = ExecutionContext()

# Store values
context["user_id"] = 123
context.set("token", "abc123")

# Retrieve values
user_id = context["user_id"]
token = context.get("token")
required_value = context.get_required("user_id")  # Raises KeyError if missing

# Store step results
context.store_step_result("login", response.json())

# Get previous step result
login_result = context.get_step_result("login")

# Snapshot and restore
snapshot = context.snapshot()
context.restore(snapshot)
```

#### Methods

| Method | Return Type | Description |
|--------|-------------|-------------|
| `set(key, value)` | `None` | Store a value |
| `get(key, default=None)` | `Any` | Retrieve a value |
| `get_required(key)` | `Any` | Retrieve value or raise KeyError |
| `store_step_result(name, result)` | `None` | Store step result |
| `get_step_result(name)` | `Any` | Get previous step result |
| `clear()` | `None` | Clear all data |
| `snapshot()` | `dict` | Create context snapshot |
| `restore(snapshot)` | `None` | Restore from snapshot |
| `to_dict()` | `dict` | Export as dictionary |

---

## Client

### Client Class

HTTP client with history tracking and retry logic.

```python
from venomqa import Client

client = Client(
    base_url="http://localhost:8000",
    timeout=30.0,
    retry_count=3,
    retry_delay=1.0,
    default_headers={"X-API-Key": "secret"},
)

# Connect (optional - auto-connects on first request)
client.connect()

# Set authentication
client.set_auth_token("my-jwt-token")
client.set_auth_token("my-api-key", scheme="ApiKey")

# Make requests
response = client.get("/api/users")
response = client.post("/api/users", json={"name": "John"})
response = client.put("/api/users/1", json={"name": "Jane"})
response = client.patch("/api/users/1", json={"active": False})
response = client.delete("/api/users/1")

# Access history
history = client.get_history()
last = client.last_request()

# Clear history
client.clear_history()

# Disconnect
client.disconnect()
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_url` | `str` | Required | Base URL for all requests |
| `timeout` | `float` | `30.0` | Request timeout in seconds |
| `retry_count` | `int` | `3` | Number of retry attempts |
| `retry_delay` | `float` | `1.0` | Base delay between retries |
| `default_headers` | `dict \| None` | `None` | Headers for all requests |

#### Methods

| Method | Description |
|--------|-------------|
| `connect()` | Initialize the HTTP client |
| `disconnect()` | Close the HTTP client |
| `set_auth_token(token, scheme="Bearer")` | Set authentication header |
| `clear_auth()` | Clear authentication |
| `request(method, path, **kwargs)` | Make HTTP request |
| `get(path, **kwargs)` | GET request |
| `post(path, **kwargs)` | POST request |
| `put(path, **kwargs)` | PUT request |
| `patch(path, **kwargs)` | PATCH request |
| `delete(path, **kwargs)` | DELETE request |
| `get_history()` | Get all request records |
| `clear_history()` | Clear request history |
| `last_request()` | Get most recent request |

---

### AsyncClient

Async HTTP client with the same interface as `Client`.

```python
from venomqa.client import AsyncClient

async def run_tests():
    client = AsyncClient(base_url="http://localhost:8000")
    await client.connect()
    
    response = await client.get("/api/users")
    
    await client.disconnect()
```

---

### RequestRecord

Record of an HTTP request/response.

```python
@dataclass
class RequestRecord:
    method: str
    url: str
    request_body: Any | None
    response_status: int
    response_body: Any | None
    headers: dict[str, str]
    duration_ms: float
    timestamp: datetime
    error: str | None
```

---

## Configuration

### QAConfig

Configuration settings for VenomQA.

```python
from venomqa import QAConfig

config = QAConfig(
    base_url="http://localhost:8000",
    db_url="postgresql://qa:secret@localhost:5432/qa_test",
    db_backend="postgresql",
    docker_compose_file="docker-compose.qa.yml",
    timeout=30,
    retry_count=3,
    retry_delay=1.0,
    capture_logs=True,
    log_lines=50,
    parallel_paths=1,
    report_dir="reports",
    report_formats=["markdown", "junit"],
    verbose=False,
    fail_fast=False,
)
```

#### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `base_url` | `str` | `"http://localhost:8000"` | API base URL |
| `db_url` | `str \| None` | `None` | Database connection URL |
| `db_backend` | `str` | `"postgresql"` | Database backend type |
| `docker_compose_file` | `str` | `"docker-compose.qa.yml"` | Docker compose file path |
| `timeout` | `int` | `30` | Request timeout in seconds |
| `retry_count` | `int` | `3` | Number of retry attempts |
| `retry_delay` | `float` | `1.0` | Delay between retries |
| `capture_logs` | `bool` | `True` | Capture infrastructure logs |
| `log_lines` | `int` | `50` | Number of log lines to capture |
| `parallel_paths` | `int` | `1` | Max concurrent branch paths |
| `report_dir` | `str` | `"reports"` | Output directory for reports |
| `report_formats` | `list[str]` | `["markdown"]` | Report formats to generate |
| `verbose` | `bool` | `False` | Enable verbose logging |
| `fail_fast` | `bool` | `False` | Stop on first failure |

#### Environment Variables

All options can be overridden with `VENOMQA_` prefixed environment variables:

```bash
export VENOMQA_BASE_URL="http://api.example.com"
export VENOMQA_DB_URL="postgresql://user:pass@host/db"
export VENOMQA_TIMEOUT=60
export VENOMQA_VERBOSE=true
```

---

### load_config

Load configuration from file and environment.

```python
from venomqa.config import load_config

# Load from default venomqa.yaml
config = load_config()

# Load from specific path
config = load_config("path/to/config.yaml")
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config_path` | `str \| Path \| None` | `None` | Path to config file |

#### Priority Order

1. CLI arguments (highest)
2. Environment variables
3. Config file
4. Defaults (lowest)

---

## State Management

### StateManager Protocol

Protocol defining the state manager interface.

```python
class StateManager(Protocol):
    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def checkpoint(self, name: str) -> None: ...
    def rollback(self, name: str) -> None: ...
    def release(self, name: str) -> None: ...
    def reset(self) -> None: ...
    def is_connected(self) -> bool: ...
```

---

### PostgreSQLStateManager

PostgreSQL state manager using SQL SAVEPOINT.

```python
from venomqa.state import PostgreSQLStateManager

state_manager = PostgreSQLStateManager(
    connection_url="postgresql://qa:secret@localhost:5432/qa_test",
    tables_to_reset=["users", "orders", "items"],
    exclude_tables=["migrations", "schema_versions"],
)

state_manager.connect()
state_manager.checkpoint("before_test")
# ... run tests ...
state_manager.rollback("before_test")
state_manager.disconnect()
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `connection_url` | `str` | Required | PostgreSQL connection string |
| `tables_to_reset` | `list[str] \| None` | `None` | Tables to truncate on reset |
| `exclude_tables` | `list[str] \| None` | `None` | Tables to exclude from reset |

#### Methods

| Method | Description |
|--------|-------------|
| `connect()` | Establish database connection |
| `disconnect()` | Close database connection |
| `checkpoint(name)` | Create SQL SAVEPOINT |
| `rollback(name)` | Rollback to SAVEPOINT |
| `release(name)` | Release SAVEPOINT |
| `reset()` | Truncate all tables |
| `commit()` | Commit current transaction |

---

## Reporters

### BaseReporter

Abstract base class for all reporters.

```python
from venomqa.reporters.base import BaseReporter

class CustomReporter(BaseReporter):
    @property
    def file_extension(self) -> str:
        return ".custom"
    
    def generate(self, results: list[JourneyResult]) -> str:
        # Generate report
        return "report content"
```

#### Methods

| Method | Return Type | Description |
|--------|-------------|-------------|
| `generate(results)` | `str \| dict \| bytes` | Generate report content |
| `save(results, path)` | `Path` | Save report to file |

---

### MarkdownReporter

Generate human-readable Markdown reports.

```python
from venomqa.reporters import MarkdownReporter

reporter = MarkdownReporter(output_path="reports/test.md")
reporter.save([result1, result2])
```

---

### JSONReporter

Generate JSON reports for programmatic consumption.

```python
from venomqa.reporters import JSONReporter

reporter = JSONReporter(output_path="reports/test.json", indent=2)
reporter.save([result1, result2])
```

---

### JUnitReporter

Generate JUnit XML for CI/CD integration.

```python
from venomqa.reporters import JUnitReporter

reporter = JUnitReporter(output_path="reports/junit.xml")
reporter.save([result1, result2])
```

---

## Infrastructure

### InfrastructureManager Protocol

Protocol defining the infrastructure manager interface.

```python
class InfrastructureManager(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def wait_healthy(self, timeout: float = 60.0) -> bool: ...
    def logs(self, service_name: str) -> str: ...
    def is_running(self) -> bool: ...
```

---

### DockerInfrastructureManager

Docker Compose infrastructure manager.

```python
from venomqa.infra import DockerInfrastructureManager

infra = DockerInfrastructureManager(
    compose_file="docker-compose.qa.yml",
    project_name="venomqa_test",
    services=["api", "db"],
)

infra.start()
if infra.wait_healthy(timeout=60):
    # Run tests
    pass
infra.stop()
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `compose_file` | `str \| Path \| None` | `None` | Docker compose file path |
| `project_name` | `str \| None` | `None` | Docker compose project name |
| `services` | `list[str] \| None` | `None` | Specific services to start |

#### Methods

| Method | Description |
|--------|-------------|
| `start()` | Start services with `docker compose up -d` |
| `stop()` | Stop services with `docker compose down` |
| `wait_healthy(timeout)` | Wait for services to be healthy |
| `logs(service_name)` | Get logs from a service |
| `is_running()` | Check if services are running |
| `restart()` | Restart all services |
| `pull()` | Pull images |
| `build()` | Build images |

---

## Ports

Ports are abstract interfaces that define contracts for external system interactions. See [Ports Documentation](ports.md) for detailed information.

### Importing Ports

```python
from venomqa.ports import (
    ClientPort,
    DatabasePort,
    MailPort,
    CachePort,
    QueuePort,
    SearchPort,
    StoragePort,
    FilePort,
    TimePort,
    ConcurrencyPort,
    MockPort,
    StatePort,
    WebSocketPort,
    WebhookPort,
    NotificationPort,
)
```

### Port Data Classes

Each port has associated data classes for structured data:

```python
from venomqa.ports import (
    Request, Response, RequestBuilder,     # ClientPort
    QueryResult, TableInfo, ColumnInfo,    # DatabasePort
    Email, EmailAttachment,                 # MailPort
    CacheEntry, CacheStats,                 # CachePort
    JobInfo, JobResult, JobStatus,         # QueuePort
    IndexedDocument, SearchIndex, SearchResult,  # SearchPort
    StorageObject, FileInfo,                # StoragePort, FilePort
    TimeInfo, ScheduledTask,                # TimePort
    TaskInfo, TaskResult,                   # ConcurrencyPort
    MockResponse, MockEndpoint, RecordedRequest,  # MockPort
    StateEntry, StateQuery,                 # StatePort
    WSMessage, WSConnection,                # WebSocketPort
    WebhookRequest, WebhookResponse, WebhookSubscription,  # WebhookPort
    PushNotification, SMSMessage,           # NotificationPort
)
```

### Creating Custom Port Implementations

```python
from abc import ABC
from venomqa.ports import CachePort, CacheStats

class CustomCacheAdapter(CachePort):
    def get(self, key: str) -> Any | None:
        # Implementation
        pass
    
    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        # Implementation
        pass
    
    # ... implement all abstract methods
```

---

## Adapters

Adapters are concrete implementations of Ports. See [Adapters Documentation](adapters.md) for detailed configuration.

### Importing Adapters

```python
from venomqa.adapters import (
    MailhogAdapter,
    MailpitAdapter,
    SMTPMockAdapter,
    RedisCacheAdapter,
    RedisQueueAdapter,
    CeleryQueueAdapter,
    ElasticsearchAdapter,
    S3StorageAdapter,
    LocalStorageAdapter,
    WireMockAdapter,
    ControllableTimeAdapter,
    RealTimeAdapter,
    ThreadingConcurrencyAdapter,
    AsyncConcurrencyAdapter,
    register_adapter,
    get_adapter,
    list_adapters,
)
```

### Adapter Registration

```python
from venomqa.adapters import register_adapter, register_adapter_class, get_adapter

# Decorator registration
@register_adapter("my_adapter")
class MyAdapter(CachePort):
    pass

# Direct registration
register_adapter_class("another_adapter", AnotherAdapter)

# Retrieval
adapter_class = get_adapter("my_adapter")
all_adapters = list_adapters()
```
