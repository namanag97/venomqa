"""VenomQA - Stateful Journey QA Framework.

VenomQA is a stateful journey testing framework for API QA with database
checkpointing and branch exploration. It allows you to test complex user
flows while automatically exploring multiple execution paths from saved
database states.

Key Features:
    - State Branching: Save database checkpoints and fork execution
    - Journey DSL: Declarative syntax for defining user flows
    - Issue Capture: Automatic failure detection with fix suggestions
    - Infrastructure Management: Docker Compose integration
    - Context Passing: Share data between steps
    - Rich Reporters: Markdown, JSON, JUnit XML, HTML output

Example:
    >>> from venomqa import Journey, Step, Checkpoint, Branch, Path, Client
    >>> from venomqa.runner import JourneyRunner
    >>>
    >>> def login(client, context):
    ...     response = client.post("/api/auth/login", json={
    ...         "email": "test@example.com",
    ...         "password": "secret"
    ...     })
    ...     context["token"] = response.json()["token"]
    ...     return response
    >>>
    >>> def create_order(client, context):
    ...     return client.post("/api/orders", json={"item_id": 1})
    >>>
    >>> journey = Journey(
    ...     name="checkout_flow",
    ...     description="Test checkout process",
    ...     steps=[
    ...         Step(name="login", action=login),
    ...         Checkpoint(name="authenticated"),
    ...         Step(name="create_order", action=create_order),
    ...         Checkpoint(name="order_created"),
    ...         Branch(
    ...             checkpoint_name="order_created",
    ...             paths=[
    ...                 Path(name="card_payment", steps=[
    ...                     Step(name="pay_card", action=lambda c, ctx: c.post("/api/pay"))
    ...                 ])
    ...             ]
    ...         )
    ...     ]
    ... )
    >>>
    >>> client = Client(base_url="http://localhost:8000")
    >>> runner = JourneyRunner(client=client)
    >>> result = runner.run(journey)
    >>> print(f"Passed: {result.success}")

Core Models:
    Journey: A complete user scenario from start to finish
    Step: A single action with assertions
    Checkpoint: A savepoint for database state
    Branch: Fork execution to explore multiple paths
    Path: A sequence of steps within a branch

Results:
    JourneyResult: Result of executing a complete journey
    StepResult: Result of executing a single step
    PathResult: Result of executing a path within a branch
    Issue: Captured failure with full context

Execution:
    JourneyRunner: Executes journeys with branching and rollback
    ExecutionContext: Typed context for sharing state between steps
    Client: HTTP client with history tracking and retry logic

Configuration:
    QAConfig: Configuration settings for VenomQA

Error Handling:
    VenomQAError: Base exception for all VenomQA errors
    ValidationError: Request/response validation errors
    ConnectionError: Network connection errors
    CircuitOpenError: Circuit breaker is open
    RetryExhaustedError: All retry attempts exhausted

Performance:
    ResponseCache: HTTP response caching
    ConnectionPool: Connection pooling for HTTP and database
    BatchExecutor: Execute multiple operations in batches

 Security:
     InputValidator: Validate and sanitize user input
     SecretsManager: Secure credential management
     Sanitizer: Data sanitization utilities

 File Handling:
     FileHandler: Upload, download, and manage files
     StorageBackend: Protocol for storage backends
     LocalStorageBackend: Local filesystem storage
     S3StorageBackend: AWS S3 storage
     GCSStorageBackend: Google Cloud Storage
     AzureBlobBackend: Azure Blob Storage
     FileGenerator: Generate test files (images, PDFs, CSVs, JSON)

 See Also:
    Documentation: https://github.com/your-org/venomqa#readme
    API Reference: docs/api.md
    CLI Usage: docs/cli.md
"""

from venomqa.adapters import get_adapter, list_adapters, register_adapter, register_adapter_class
from venomqa.client import Client, SecureCredentials
from venomqa.config import QAConfig
from venomqa.context import (
    ContextBuilder,
    PortConfig,
    PortsConfiguration,
    TestContext,
    create_context,
)
from venomqa.core.context import ExecutionContext
from venomqa.core.models import (
    Branch,
    Checkpoint,
    Issue,
    Journey,
    JourneyResult,
    Path,
    PathResult,
    Severity,
    Step,
    StepResult,
)
from venomqa.errors import (
    BackoffStrategy,
    CircuitBreaker,
    CircuitOpenError,
    ConnectionError,
    ConnectionTimeoutError,
    ErrorCode,
    ErrorContext,
    GlobalErrorHandler,
    JourneyError,
    RateLimitedError,
    RecoveryStrategy,
    RetryExhaustedError,
    RetryPolicy,
    StateError,
    ValidationError,
    VenomQAError,
    handle_errors,
    with_circuit_breaker,
    with_retry,
)
from venomqa.files import (
    AzureBlobBackend,
    BinaryGenerator,
    CSVGenerator,
    FileGenerator,
    FileHandler,
    FileUploadResult,
    GCSStorageBackend,
    ImageGenerator,
    JSONGenerator,
    LocalStorageBackend,
    PDFGenerator,
    S3StorageBackend,
    StorageBackend,
    StorageConfig,
)
from venomqa.performance import (
    BatchExecutor,
    BatchProgress,
    BatchResult,
    CachedResponse,
    CacheStats,
    ConnectionPool,
    DBConnectionPool,
    HTTPConnectionPool,
    PoolStats,
    ResponseCache,
    aggregate_results,
    default_progress_callback,
)
from venomqa.ports import (
    CacheEntry,
    CachePort,
    ClientPort,
    ColumnInfo,
    ConcurrencyPort,
    DatabasePort,
    Email,
    EmailAttachment,
    FileInfo,
    FilePort,
    IndexedDocument,
    JobInfo,
    JobResult,
    JobStatus,
    MailPort,
    MockEndpoint,
    MockPort,
    MockResponse,
    NotificationPort,
    PushNotification,
    QueuePort,
    RecordedRequest,
    Request,
    RequestBuilder,
    Response,
    ScheduledTask,
    SearchIndex,
    SearchPort,
    SearchResult,
    SMSMessage,
    StateEntry,
    StatePort,
    StateQuery,
    StorageObject,
    StoragePort,
    TableInfo,
    TaskInfo,
    TaskResult,
    TimeInfo,
    TimePort,
    WebhookPort,
    WebhookRequest,
    WebhookResponse,
    WebhookSubscription,
    WebSocketPort,
    WSConnection,
    WSMessage,
)
from venomqa.runner import JourneyRunner
from venomqa.security import (
    EnvironmentBackend,
    InputValidator,
    Sanitizer,
    SecretsManager,
    SensitiveDataFilter,
    VaultBackend,
)

__version__ = "0.2.0"
__author__ = "Naman Agarwal"
__license__ = "MIT"

__all__ = [
    "Journey",
    "JourneyResult",
    "Step",
    "StepResult",
    "Branch",
    "Path",
    "PathResult",
    "Checkpoint",
    "Issue",
    "Severity",
    "ExecutionContext",
    "TestContext",
    "ContextBuilder",
    "PortConfig",
    "PortsConfiguration",
    "create_context",
    "JourneyRunner",
    "Client",
    "SecureCredentials",
    "QAConfig",
    "VenomQAError",
    "ErrorCode",
    "ErrorContext",
    "ConnectionError",
    "ConnectionTimeoutError",
    "ValidationError",
    "StateError",
    "JourneyError",
    "CircuitOpenError",
    "RetryExhaustedError",
    "RateLimitedError",
    "BackoffStrategy",
    "RetryPolicy",
    "CircuitBreaker",
    "RecoveryStrategy",
    "GlobalErrorHandler",
    "handle_errors",
    "with_retry",
    "with_circuit_breaker",
    "ResponseCache",
    "CachedResponse",
    "CacheStats",
    "ConnectionPool",
    "HTTPConnectionPool",
    "DBConnectionPool",
    "PoolStats",
    "BatchExecutor",
    "BatchProgress",
    "BatchResult",
    "aggregate_results",
    "default_progress_callback",
    "InputValidator",
    "SecretsManager",
    "VaultBackend",
    "EnvironmentBackend",
    "Sanitizer",
    "SensitiveDataFilter",
    "FileHandler",
    "FileUploadResult",
    "StorageBackend",
    "StorageConfig",
    "LocalStorageBackend",
    "S3StorageBackend",
    "GCSStorageBackend",
    "AzureBlobBackend",
    "FileGenerator",
    "ImageGenerator",
    "PDFGenerator",
    "CSVGenerator",
    "JSONGenerator",
    "BinaryGenerator",
    "ClientPort",
    "Request",
    "Response",
    "RequestBuilder",
    "StatePort",
    "StateEntry",
    "StateQuery",
    "DatabasePort",
    "QueryResult",
    "TableInfo",
    "ColumnInfo",
    "TimePort",
    "TimeInfo",
    "ScheduledTask",
    "FilePort",
    "StoragePort",
    "FileInfo",
    "StorageObject",
    "WebSocketPort",
    "WSMessage",
    "WSConnection",
    "QueuePort",
    "JobInfo",
    "JobResult",
    "JobStatus",
    "MailPort",
    "Email",
    "EmailAttachment",
    "ConcurrencyPort",
    "TaskInfo",
    "TaskResult",
    "CachePort",
    "CacheEntry",
    "SearchPort",
    "SearchIndex",
    "SearchResult",
    "IndexedDocument",
    "NotificationPort",
    "PushNotification",
    "SMSMessage",
    "WebhookPort",
    "WebhookRequest",
    "WebhookResponse",
    "WebhookSubscription",
    "MockPort",
    "MockEndpoint",
    "MockResponse",
    "RecordedRequest",
    "get_adapter",
    "list_adapters",
    "register_adapter",
    "register_adapter_class",
]
