# Ports & Adapters Architecture

VenomQA implements a **Ports and Adapters** (Hexagonal Architecture) pattern to provide clean separation between testing logic and external dependencies. This allows you to write tests that are independent of specific infrastructure implementations.

## Overview

### What are Ports?

**Ports** are abstract interfaces that define what operations your tests need, without specifying how those operations are performed. They represent the "requirements" of your testing code.

### What are Adapters?

**Adapters** are concrete implementations of Ports. They handle the actual communication with external systems (databases, caches, message queues, etc.).

### Benefits

- **Testability**: Swap real services for mocks in unit tests
- **Flexibility**: Change infrastructure without modifying test code
- **Clarity**: Clear contracts between test logic and external systems
- **Maintainability**: Each adapter can be modified independently

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      VenomQA Test Code                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │
│  │MailPort │  │CachePort│  │QueuePort│  │TimePort │  ...   │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘       │
│       │            │            │            │              │
├───────┼────────────┼────────────┼────────────┼──────────────┤
│       ▼            ▼            ▼            ▼              │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │
│  │Mailhog  │  │ Redis   │  │Celery/RQ│  │Control- │       │
│  │Adapter  │  │Adapter  │  │Adapter  │  │lableTime│       │
│  │Mailpit  │  │         │  │         │  │RealTime │       │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Available Ports

### ClientPort

HTTP client operations for making API requests.

```python
from venomqa.ports import ClientPort, Request, Response

class MyClient(ClientPort):
    def get(self, url: str, **kwargs) -> Response: ...
    def post(self, url: str, **kwargs) -> Response: ...
    def put(self, url: str, **kwargs) -> Response: ...
    def delete(self, url: str, **kwargs) -> Response: ...
```

### DatabasePort

Database operations with SQL support.

```python
from venomqa.ports import DatabasePort, QueryResult, TableInfo

class MyDatabase(DatabasePort):
    def execute(self, query: str, params=None) -> QueryResult: ...
    def insert(self, table: str, data: dict) -> QueryResult: ...
    def select(self, table: str, **kwargs) -> QueryResult: ...
    def transaction(self) -> ContextManager: ...
```

### MailPort

Email capture and verification for testing.

```python
from venomqa.ports import MailPort, Email

class MyMail(MailPort):
    def get_all_emails(self) -> list[Email]: ...
    def get_emails_to(self, recipient: str) -> list[Email]: ...
    def wait_for_email(self, to=None, from_=None, subject=None, timeout=30.0) -> Email | None: ...
    def delete_all_emails(self) -> None: ...
```

### CachePort

Caching operations with TTL support.

```python
from venomqa.ports import CachePort, CacheStats

class MyCache(CachePort):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl: int | None = None) -> bool: ...
    def delete(self, key: str) -> bool: ...
    def get_stats(self) -> CacheStats: ...
```

### QueuePort

Job queue management for async task testing.

```python
from venomqa.ports import QueuePort, JobInfo, JobResult

class MyQueue(QueuePort):
    def enqueue(self, func, *args, queue="default", **kwargs) -> str: ...
    def get_job(self, job_id: str) -> JobInfo | None: ...
    def get_job_result(self, job_id: str, timeout=30.0) -> JobResult | None: ...
```

### SearchPort

Search engine operations for full-text search testing.

```python
from venomqa.ports import SearchPort, IndexedDocument, SearchResult

class MySearch(SearchPort):
    def index_document(self, index: str, document: IndexedDocument) -> bool: ...
    def search(self, index: str, query: str | dict, **kwargs) -> tuple[list[SearchResult], int]: ...
    def create_index(self, name: str, settings=None) -> bool: ...
```

### StoragePort

Object storage operations (S3-compatible).

```python
from venomqa.ports import StoragePort, StorageObject

class MyStorage(StoragePort):
    def get(self, bucket: str, key: str) -> StorageObject | None: ...
    def put(self, bucket: str, key: str, content: bytes, **kwargs) -> bool: ...
    def delete(self, bucket: str, key: str) -> bool: ...
```

### FilePort

Local filesystem operations.

```python
from venomqa.ports import FilePort, FileInfo

class MyFiles(FilePort):
    def read(self, path: str, binary=False) -> str | bytes: ...
    def write(self, path: str, content: str | bytes) -> int: ...
    def list_dir(self, path: str, recursive=False) -> list[FileInfo]: ...
```

### TimePort

Time operations with controllable time for testing.

```python
from venomqa.ports import TimePort, ScheduledTask

class MyTime(TimePort):
    def now(self) -> datetime: ...
    def sleep(self, seconds: float) -> None: ...
    def schedule(self, task: ScheduledTask) -> str: ...
```

### ConcurrencyPort

Parallel task execution.

```python
from venomqa.ports import ConcurrencyPort, TaskResult

class MyConcurrency(ConcurrencyPort):
    def spawn(self, func, *args, **kwargs) -> str: ...
    def join(self, task_id: str, timeout=None) -> TaskResult: ...
    def map_parallel(self, func, items, max_workers=4) -> list: ...
```

### MockPort

HTTP mock server for API stubbing.

```python
from venomqa.ports import MockPort, MockResponse, RecordedRequest

class MyMock(MockPort):
    def stub(self, method: str, path: str, response: MockResponse = None, **kwargs) -> str: ...
    def get_requests(self, method=None, path=None) -> list[RecordedRequest]: ...
    def verify(self, method: str, path: str, count=None) -> bool: ...
```

### StatePort

Key-value state management with TTL and data structures.

```python
from venomqa.ports import StatePort, StateEntry

class MyState(StatePort):
    def get(self, key: str) -> StateEntry | None: ...
    def set(self, key: str, value: Any, ttl_seconds=None) -> StateEntry: ...
    def watch(self, key: str, callback) -> str: ...
```

### WebSocketPort

WebSocket client for real-time communication testing.

```python
from venomqa.ports import WebSocketPort, WSMessage, WSConnection

class MyWebSocket(WebSocketPort):
    def connect(self, url: str, headers=None) -> WSConnection: ...
    def send(self, connection_id: str, message: str | bytes) -> bool: ...
    def receive(self, connection_id: str, timeout=10.0) -> WSMessage | None: ...
```

### WebhookPort

Webhook receiver for external callback testing.

```python
from venomqa.ports import WebhookPort, WebhookRequest

class MyWebhook(WebhookPort):
    def receive(self, timeout=30.0) -> WebhookRequest | None: ...
    def subscribe(self, subscription: WebhookSubscription) -> str: ...
```

### NotificationPort

Push notification and SMS testing.

```python
from venomqa.ports import NotificationPort, PushNotification, SMSMessage

class MyNotification(NotificationPort):
    def send_push(self, notification: PushNotification) -> str: ...
    def send_sms(self, message: SMSMessage) -> str: ...
```

## Creating Custom Adapters

### Step 1: Choose a Port to Implement

Identify which Port interface your adapter should implement:

```python
from venomqa.ports import CachePort, CacheStats
```

### Step 2: Create the Adapter Class

```python
from dataclasses import dataclass
from typing import Any
from venomqa.ports import CachePort, CacheStats

@dataclass
class MyCacheConfig:
    """Configuration for custom cache adapter."""
    host: str = "localhost"
    port: int = 11211
    timeout: float = 10.0

class MyCacheAdapter(CachePort):
    """Custom cache adapter for Memcached."""
    
    def __init__(self, host: str = "localhost", port: int = 11211):
        self.config = MyCacheConfig(host=host, port=port)
        self._client = self._connect()
    
    def _connect(self):
        import pymemcache
        return pymemcache.Client((self.config.host, self.config.port))
    
    def get(self, key: str) -> Any | None:
        value = self._client.get(key)
        return value.decode() if value else None
    
    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        return self._client.set(key, str(value), expire=ttl or 0)
    
    def delete(self, key: str) -> bool:
        return self._client.delete(key)
    
    def exists(self, key: str) -> bool:
        return self._client.get(key) is not None
    
    def clear(self) -> bool:
        self._client.flush_all()
        return True
    
    def get_stats(self) -> CacheStats:
        stats = self._client.stats()
        return CacheStats(
            hits=stats.get(b'get_hits', 0),
            misses=stats.get(b'get_misses', 0),
            keys_count=stats.get(b'curr_items', 0),
        )
    
    def health_check(self) -> bool:
        try:
            self._client.stats()
            return True
        except Exception:
            return False
```

### Step 3: Register the Adapter (Optional)

```python
from venomqa.adapters import register_adapter_class

register_adapter_class("my_cache", MyCacheAdapter)
```

### Step 4: Use in Tests

```python
from myapp.testing import MyCacheAdapter

def test_with_custom_cache():
    cache = MyCacheAdapter(host="localhost", port=11211)
    
    cache.set("user:123", {"name": "John"})
    user = cache.get("user:123")
    
    assert user is not None
```

## Port Configuration

### Environment Variables

Each adapter typically supports configuration via environment variables:

| Adapter | Environment Variables |
|---------|----------------------|
| RedisCacheAdapter | `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD` |
| ElasticsearchAdapter | `ELASTICSEARCH_HOSTS`, `ELASTICSEARCH_API_KEY` |
| S3StorageAdapter | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_ENDPOINT` |
| MailhogAdapter | `MAILHOG_HOST`, `MAILHOG_API_PORT` |

### Configuration Classes

Adapters use dataclasses for configuration:

```python
@dataclass
class RedisCacheConfig:
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    prefix: str = "venomqa:"
    default_ttl: int = 3600
```

### Using with Dependency Injection

```python
from venomqa.ports import CachePort
from venomqa.adapters import RedisCacheAdapter

class TestContext:
    def __init__(self, cache: CachePort):
        self.cache = cache

def test_with_cache():
    cache = RedisCacheAdapter(host="localhost")
    ctx = TestContext(cache)
    
    ctx.cache.set("key", "value")
    assert ctx.cache.get("key") == "value"
```

## Best Practices

### 1. Depend on Ports, Not Adapters

```python
# Good - depends on abstraction
def test_user_cache(cache: CachePort):
    cache.set("user:1", {"name": "John"})
    assert cache.exists("user:1")

# Bad - depends on concrete implementation
def test_user_cache(cache: RedisCacheAdapter):
    ...
```

### 2. Use Health Checks

```python
def test_with_mail(mail: MailPort):
    if not mail.health_check():
        pytest.skip("Mail service not available")
    
    # Run tests...
```

### 3. Clean Up After Tests

```python
@pytest.fixture
def cache():
    adapter = RedisCacheAdapter()
    yield adapter
    adapter.clear()  # Clean up
```

### 4. Use Controllable Time for Deterministic Tests

```python
from venomqa.adapters import ControllableTimeAdapter

def test_scheduled_task():
    time = ControllableTimeAdapter()
    time.freeze()
    
    task_ran = False
    def callback():
        nonlocal task_ran
        task_ran = True
    
    time.schedule_after(60.0, callback)
    time.advance(timedelta(seconds=60))
    
    assert task_ran
```

### 5. Mock External Services

```python
from venomqa.adapters import WireMockAdapter

def test_api_with_mock():
    mock = WireMockAdapter()
    mock.stub("GET", "/api/users", body={"users": []})
    
    # Test code uses mock.get_base_url()
    response = client.get(f"{mock.get_base_url()}/api/users")
    assert response.json() == {"users": []}
    
    mock.verify("GET", "/api/users", count=1)
```
