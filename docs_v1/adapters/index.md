# Adapters

Adapters implement the `Rollbackable` protocol, allowing VenomQA to checkpoint and restore their state during exploration.

## Overview

| Adapter | System | Rollback Method | Install |
|---------|--------|-----------------|---------|
| `PostgresAdapter` | PostgreSQL | Savepoints | `pip install venomqa[postgres]` |
| `MySQLAdapter` | MySQL | Savepoints | `pip install venomqa[mysql]` |
| `SQLiteAdapter` | SQLite | File copy | Built-in |
| `RedisAdapter` | Redis | Dump/restore | `pip install venomqa[redis]` |
| `MockQueue` | Queue (mock) | Copy list | Built-in |
| `MockMail` | Email (mock) | Copy list | Built-in |
| `MockStorage` | Storage (mock) | Copy dict | Built-in |
| `MockTime` | Time (mock) | Save value | Built-in |
| `WireMockAdapter` | External APIs | Save mappings | Built-in |
| `HttpClient` | HTTP client | N/A (stateless) | Built-in |

---

## HttpClient

The HTTP client for making API requests. Not rollbackable (stateless).

```python
from venomqa import HttpClient

client = HttpClient(
    base_url="http://localhost:8000",
    timeout=30.0,
    headers={"Authorization": "Bearer token"},
)

# Make requests
result = client.get("/users")
result = client.post("/users", json={"name": "Alice"})
result = client.put("/users/1", json={"name": "Bob"})
result = client.patch("/users/1", json={"status": "active"})
result = client.delete("/users/1")

# Context manager
with HttpClient("http://localhost:8000") as client:
    result = client.get("/health")
```

### Constructor

```python
HttpClient(
    base_url: str,
    timeout: float = 30.0,
    headers: dict[str, str] | None = None,
)
```

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `get` | `(path, params?) -> ActionResult` | GET request |
| `post` | `(path, json?, data?, headers?) -> ActionResult` | POST request |
| `put` | `(path, json?, data?, headers?) -> ActionResult` | PUT request |
| `patch` | `(path, json?, data?, headers?) -> ActionResult` | PATCH request |
| `delete` | `(path, headers?) -> ActionResult` | DELETE request |
| `request` | `(method, path, ...) -> ActionResult` | Generic request |
| `close` | `() -> None` | Close connection |

---

## PostgresAdapter

PostgreSQL adapter using savepoints for atomic rollback.

```python
from venomqa.adapters import PostgresAdapter

db = PostgresAdapter(
    connection_string="postgresql://user:pass@localhost/testdb",
    observe_tables=["users", "orders", "products"],
)

# Use as context manager
with db:
    # Checkpoint
    cp = db.checkpoint("before_test")

    # Execute queries
    rows = db.execute("SELECT * FROM users WHERE active = true")

    # Rollback
    db.rollback(cp)
```

### Constructor

```python
PostgresAdapter(
    connection_string: str,
    observe_tables: list[str] | None = None,
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `connection_string` | `str` | PostgreSQL connection URL |
| `observe_tables` | `list[str]` | Tables to include in observations |

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `connect` | `() -> None` | Connect to database |
| `close` | `() -> None` | Close connection |
| `checkpoint` | `(name: str) -> SystemCheckpoint` | Create savepoint |
| `rollback` | `(checkpoint) -> None` | Rollback to savepoint |
| `observe` | `() -> Observation` | Query table counts |
| `execute` | `(query, params?) -> list[tuple]` | Execute SQL query |
| `commit` | `() -> None` | Commit transaction |

### Observation Data

```python
{
    "users_count": 42,
    "orders_count": 156,
    "products_count": 89,
}
```

---

## RedisAdapter

Redis adapter using dump/restore for rollback.

```python
from venomqa.adapters import RedisAdapter

cache = RedisAdapter(
    url="redis://localhost:6379",
    track_keys=["user:1", "user:2"],
    track_patterns=["session:*", "cache:*"],
)

with cache:
    cp = cache.checkpoint("before_clear")
    # ... operations ...
    cache.rollback(cp)
```

### Constructor

```python
RedisAdapter(
    url: str = "redis://localhost:6379",
    track_keys: list[str] | None = None,
    track_patterns: list[str] | None = None,
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `url` | `str` | Redis connection URL |
| `track_keys` | `list[str]` | Specific keys to track |
| `track_patterns` | `list[str]` | Key patterns to track (default: `["*"]`) |

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `connect` | `() -> None` | Connect to Redis |
| `close` | `() -> None` | Close connection |
| `checkpoint` | `(name: str) -> SystemCheckpoint` | Dump tracked keys |
| `rollback` | `(checkpoint) -> None` | Restore from dump |
| `observe` | `() -> Observation` | Get tracked key values |

### Observation Data

```python
{
    "user:1": b"...",
    "session:abc": ["item1", "item2"],
    "cache:products": {"id": "123", "name": "Widget"},
}
```

---

## MockQueue

In-memory queue for testing asynchronous workflows.

```python
from venomqa.adapters import MockQueue

queue = MockQueue(name="tasks")

# Push messages
msg = queue.push({"task": "send_email", "to": "user@example.com"})
print(msg.id)  # "msg_1"

# Pop messages
next_msg = queue.pop()
print(next_msg.payload)  # {"task": "send_email", ...}

# Check counts
print(queue.pending_count)   # 0
print(queue.processed_count) # 1

# Checkpoint and rollback
cp = queue.checkpoint("before_test")
queue.push({"task": "other"})
queue.rollback(cp)  # Queue restored
```

### Constructor

```python
MockQueue(name: str = "default")
```

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `push` | `(payload: Any) -> Message` | Add message to queue |
| `pop` | `() -> Message \| None` | Get and mark processed |
| `peek` | `() -> Message \| None` | Get without processing |
| `clear` | `() -> None` | Clear all messages |
| `checkpoint` | `(name: str) -> SystemCheckpoint` | Save queue state |
| `rollback` | `(checkpoint) -> None` | Restore queue state |
| `observe` | `() -> Observation` | Get queue stats |

### Message Class

```python
@dataclass
class Message:
    id: str
    payload: Any
    created_at: datetime
    processed: bool
```

### Observation Data

```python
{
    "pending": 5,
    "processed": 3,
    "total": 8,
}
```

---

## MockMail

In-memory email capture for testing email sending.

```python
from venomqa.adapters import MockMail

mail = MockMail()

# Send email (captured, not really sent)
mail.send(
    to="user@example.com",
    subject="Welcome!",
    body="Thanks for signing up.",
)

# Check sent emails
print(mail.sent_count)  # 1
print(mail.get_sent()[0].to)  # ["user@example.com"]

# Filter by recipient
user_emails = mail.get_sent(to="user@example.com")

# Checkpoint/rollback
cp = mail.checkpoint("before_test")
mail.send(to="other@example.com", subject="Test", body="...")
mail.rollback(cp)  # Email removed
```

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `send` | `(to, subject, body, from_addr?, cc?, bcc?) -> Email` | Capture an email |
| `get_sent` | `(to?: str) -> list[Email]` | Get sent emails, optionally filtered by recipient |
| `get_by_subject` | `(subject: str) -> list[Email]` | Get emails by subject (contains match) |
| `clear` | `() -> None` | Clear all sent emails |
| `checkpoint` | `(name: str) -> SystemCheckpoint` | Save mail state |
| `rollback` | `(checkpoint) -> None` | Restore mail state |
| `observe` | `() -> Observation` | Get mail stats |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `sent_count` | `int` | Number of emails sent |

### Email Class

```python
@dataclass
class Email:
    id: str
    to: list[str]
    subject: str
    body: str
    from_addr: str
    cc: list[str]
    bcc: list[str]
    sent_at: datetime
```

### Observation Data

```python
{
    "sent_count": 3,
    "recipients": ["user1@example.com", "user2@example.com", "user3@example.com"],
}
```

---

## MockStorage

In-memory file storage for testing uploads/downloads.

```python
from venomqa.adapters import MockStorage

storage = MockStorage()

# Store files
storage.put("images/logo.png", b"PNG data...")
storage.put("docs/readme.txt", b"Hello world")

# Retrieve
data = storage.get("images/logo.png")

# Delete
storage.delete("docs/readme.txt")

# List
files = storage.list("images/")  # ["images/logo.png"]
```

### StoredFile Class

```python
@dataclass
class StoredFile:
    path: str
    data: bytes
    content_type: str
    created_at: datetime
```

---

## MockTime

Mock time source for testing time-dependent logic.

```python
from venomqa.adapters import MockTime
from datetime import datetime, timedelta

time = MockTime()

# Set specific time
time.set(datetime(2024, 1, 15, 10, 30, 0))

# Advance time
time.advance(timedelta(hours=1))

# Get current time
now = time.now()  # 2024-01-15 11:30:00

# Checkpoint/rollback
cp = time.checkpoint("before_advance")
time.advance(timedelta(days=1))
time.rollback(cp)  # Back to original time
```

---

## WireMockAdapter

Adapter for WireMock (external API mocking).

```python
from venomqa.adapters import WireMockAdapter

wiremock = WireMockAdapter(url="http://localhost:8080")

# Checkpoint saves current stub mappings
cp = wiremock.checkpoint("before_test")

# ... modify stubs ...

# Rollback restores original stubs
wiremock.rollback(cp)
```

---

## Creating Custom Adapters

Implement the `Rollbackable` protocol:

```python
from venomqa.world.rollbackable import Rollbackable, SystemCheckpoint
from venomqa.core.state import Observation

class MyAdapter(Rollbackable):
    def checkpoint(self, name: str) -> SystemCheckpoint:
        """Save current state."""
        return {"data": self._internal_state.copy()}

    def rollback(self, checkpoint: SystemCheckpoint) -> None:
        """Restore state from checkpoint."""
        self._internal_state = checkpoint["data"].copy()

    def observe(self) -> Observation:
        """Return current observable state."""
        return Observation(
            system="my_system",
            data={"key": "value"},
        )
```

### Guidelines

1. **Checkpoint must be complete**: All state needed for rollback must be saved
2. **Rollback must be exact**: After rollback, system must be indistinguishable from checkpoint time
3. **Observe should be cheap**: Called frequently, avoid expensive operations
4. **Use deep copies**: Prevent mutation of checkpoint data
