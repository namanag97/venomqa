# Adapters

HTTP and system adapters for VenomQA.

## HTTP Adapters

### HttpClient

The primary adapter for making HTTP requests.

```python
from venomqa.adapters.http import HttpClient

api = HttpClient(
    base_url="http://localhost:8000",
    headers={"X-API-Key": "secret"},
    timeout=30.0,
    verify_ssl=True,
    follow_redirects=True,
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_url` | `str` | Required | Base URL for all requests |
| `headers` | `dict` | `{}` | Default headers |
| `timeout` | `float` | `30.0` | Request timeout in seconds |
| `verify_ssl` | `bool` | `True` | Verify SSL certificates |
| `follow_redirects` | `bool` | `True` | Follow HTTP redirects |

**Methods:**

```python
# GET request
resp = api.get("/users/123")
resp = api.get("/users", params={"page": 1})

# POST request
resp = api.post("/users", json={"name": "Alice"})
resp = api.post("/upload", files={"file": open("data.txt", "rb")})

# PUT request
resp = api.put("/users/123", json={"name": "Alice Updated"})

# PATCH request
resp = api.patch("/users/123", json={"name": "Alice"})

# DELETE request
resp = api.delete("/users/123")

# Custom request
resp = api.request("OPTIONS", "/users")
```

**Response Object:**

```python
resp.status_code      # HTTP status code
resp.headers          # Response headers
resp.json()           # Parse JSON body
resp.text             # Raw text body
resp.content          # Raw bytes
resp.elapsed          # Time taken (timedelta)
```

**Context Integration:**

```python
def create_user(api, context):
    resp = api.post("/users", json={"name": "Alice"})
    context.set("last_status", resp.status_code)
    context.set("user_id", resp.json()["id"])
    return resp
```

---

### AuthenticatedHttpClient

Extends HttpClient with automatic authentication.

```python
from venomqa.adapters.http import AuthenticatedHttpClient

api = AuthenticatedHttpClient(
    base_url="http://localhost:8000",
    auth_type="bearer",
    token="your-jwt-token",
)
```

**Auth Types:**

```python
# Bearer token
api = AuthenticatedHttpClient(
    base_url="...",
    auth_type="bearer",
    token="jwt-token-here",
)

# API Key header
api = AuthenticatedHttpClient(
    base_url="...",
    auth_type="api_key",
    api_key="your-api-key",
    api_key_header="X-API-Key",  # Default
)

# Basic auth
api = AuthenticatedHttpClient(
    base_url="...",
    auth_type="basic",
    username="user",
    password="pass",
)
```

---

## Database Adapters

### PostgresAdapter

```python
from venomqa.adapters.postgres import PostgresAdapter

db = PostgresAdapter(
    connection_string="postgresql://user:pass@host:5432/db",
    schema="public",
)

# Query
rows = db.query("SELECT * FROM orders WHERE status = %s", ["pending"])

# Execute
db.execute("UPDATE orders SET status = %s WHERE id = %s", ["shipped", "123"])

# Transaction (managed by VenomQA)
# Do not use explicitly
```

### MySQLAdapter

```python
from venomqa.adapters.mysql import MySQLAdapter

db = MySQLAdapter(
    host="localhost",
    port=3306,
    user="root",
    password="secret",
    database="testdb",
)

# Query
rows = db.query("SELECT * FROM orders WHERE status = %s", ["pending"])

# Execute
db.execute("UPDATE orders SET status = %s", ["shipped"])
```

### SQLiteAdapter

```python
from venomqa.adapters.sqlite import SQLiteAdapter

db = SQLiteAdapter(
    path="/path/to/database.db",
    copy_on_checkpoint=True,
)

# In-memory mode
db = SQLiteAdapter(path=":memory:")
```

---

## Cache Adapters

### RedisAdapter

```python
from venomqa.adapters.redis_adapter import RedisAdapter

redis = RedisAdapter(
    host="localhost",
    port=6379,
    db=0,
    password=None,
)

# Get/Set
value = redis.get("key")
redis.set("key", "value", ttl=3600)

# Delete
redis.delete("key")

# Clear all
redis.flush()

# Get all keys
keys = redis.keys()
```

---

## Mock Adapters

### MockSystem

In-memory mock for unit testing.

```python
from venomqa.adapters.mock import MockSystem

mock = MockSystem(initial_state={
    "users": [{"id": 1, "name": "Alice"}],
    "orders": [],
})

# Query
users = mock.query("users")

# Modify
mock.execute("INSERT INTO users VALUES (?)", [{"id": 2, "name": "Bob"}])

# Clear
mock.clear()
```

---

## Custom Adapters

Create custom adapters by implementing the SystemAdapter protocol.

```python
from typing import Any, Dict
from venomqa.adapters.base import SystemAdapter

class ElasticsearchAdapter(SystemAdapter):
    """Adapter for Elasticsearch."""
    
    def __init__(self, hosts: list):
        self.client = Elasticsearch(hosts)
        self._checkpoint_data = None
    
    def checkpoint(self) -> str:
        """Save current state."""
        # Dump all indices
        self._checkpoint_data = {}
        for index in self.client.indices.get("*"):
            self._checkpoint_data[index] = self.client.search(
                index=index,
                body={"query": {"match_all": {}}}
            )
        return "es_checkpoint"
    
    def rollback(self, checkpoint_id: str) -> None:
        """Restore to checkpoint."""
        # Clear and restore
        for index in self.client.indices.get("*"):
            self.client.indices.delete(index=index)
        
        for index, data in self._checkpoint_data.items():
            self.client.indices.create(index=index)
            for doc in data["hits"]["hits"]:
                self.client.index(
                    index=index,
                    id=doc["_id"],
                    body=doc["_source"]
                )
    
    def get_state(self) -> Dict[str, Any]:
        """Extract current state for comparison."""
        return {
            "doc_count": self.client.count()["count"]
        }
```

**Using Custom Adapters:**

```python
world = World(
    api=api,
    systems={
        "db": PostgresAdapter(...),
        "search": ElasticsearchAdapter(["localhost:9200"]),
    },
)
```

---

## Adapter Protocol

All adapters must implement:

```python
class SystemAdapter(Protocol):
    def checkpoint(self) -> str:
        """Create a checkpoint. Returns checkpoint ID."""
        ...
    
    def rollback(self, checkpoint_id: str) -> None:
        """Restore to a checkpoint."""
        ...
    
    def get_state(self) -> Dict[str, Any]:
        """Get current state for comparison."""
        ...
```

---

## Best Practices

### 1. Use Connection Pooling

```python
# HttpClient reuses connections automatically
api = HttpClient(base_url="http://localhost:8000")
```

### 2. Handle Timeouts

```python
try:
    resp = api.get("/slow-endpoint", timeout=60.0)
except httpx.TimeoutException:
    context.set("timeout_occurred", True)
    return None
```

### 3. Retry Transient Errors

```python
import tenacity

@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    retry=tenacity.retry_if_exception_type(httpx.NetworkError),
)
def create_with_retry(api, context):
    return api.post("/orders", json={...})
```

### 4. Validate Responses

```python
def create_order(api, context):
    resp = api.post("/orders", json={"amount": 100})
    
    if resp.status_code not in (200, 201):
        context.set("error", resp.json().get("error"))
        return None
    
    data = resp.json()
    if "id" not in data:
        raise ValueError("Response missing 'id' field")
    
    context.set("order_id", data["id"])
    return resp
```

## Next Steps

- [Database Backends](backends.md) - Database-specific docs
- [API Reference](api.md) - Core API
- [Configuration](config.md) - Setup options
