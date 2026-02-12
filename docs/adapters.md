# Adapters Reference

This document provides detailed configuration and usage information for all available adapters in VenomQA.

## Available Adapters

| Adapter | Port | Description | Dependencies |
|---------|------|-------------|--------------|
| MailhogAdapter | MailPort | MailHog email catcher | `requests` |
| MailpitAdapter | MailPort | Mailpit email catcher | `requests` |
| SMTPMockAdapter | MailPort | In-memory SMTP server | None |
| RedisCacheAdapter | CachePort | Redis cache backend | `redis` |
| RedisQueueAdapter | QueuePort | Redis Queue (RQ) | `redis`, `rq` |
| CeleryQueueAdapter | QueuePort | Celery task queue | `celery`, `redis` |
| ElasticsearchAdapter | SearchPort | Elasticsearch search | `elasticsearch` |
| S3StorageAdapter | StoragePort | AWS S3 / MinIO | `boto3` |
| LocalStorageAdapter | StoragePort | Local filesystem | None |
| WireMockAdapter | MockPort | WireMock mock server | `requests` |
| ControllableTimeAdapter | TimePort | Deterministic time | None |
| RealTimeAdapter | TimePort | Real system time | None |
| ThreadingConcurrencyAdapter | ConcurrencyPort | Thread pool | None |
| AsyncConcurrencyAdapter | ConcurrencyPort | Asyncio | None |

---

## Email Adapters

### MailhogAdapter

Integration with [MailHog](https://github.com/mailhog/MailHog), a popular email testing tool.

```python
from venomqa.adapters import MailhogAdapter

adapter = MailhogAdapter(
    host="localhost",
    smtp_port=1025,
    api_port=8025,
    timeout=10.0,
)
```

#### Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | `str` | `"localhost"` | MailHog server hostname |
| `smtp_port` | `int` | `1025` | SMTP server port |
| `api_port` | `int` | `8025` | API server port |
| `timeout` | `float` | `10.0` | Request timeout in seconds |

#### Environment Variables

```bash
MAILHOG_HOST=localhost
MAILHOG_SMTP_PORT=1025
MAILHOG_API_PORT=8025
```

#### Docker Setup

```bash
docker run -d -p 1025:1025 -p 8025:8025 mailhog/mailhog
```

#### Usage Example

```python
adapter = MailhogAdapter()

# Wait for email
email = adapter.wait_for_email(
    to="user@example.com",
    subject="Welcome",
    timeout=30.0,
)

assert email is not None
assert "Welcome" in email.subject

# Clean up
adapter.delete_all_emails()
```

---

### MailpitAdapter

Integration with [Mailpit](https://github.com/axllent/mailpit), a modern email testing tool.

```python
from venomqa.adapters import MailpitAdapter

adapter = MailpitAdapter(
    host="localhost",
    smtp_port=1025,
    api_port=8025,
    timeout=10.0,
    use_tls=False,
)
```

#### Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | `str` | `"localhost"` | Mailpit server hostname |
| `smtp_port` | `int` | `1025` | SMTP server port |
| `api_port` | `int` | `8025` | API server port |
| `timeout` | `float` | `10.0` | Request timeout in seconds |
| `use_tls` | `bool` | `False` | Use TLS for SMTP |

#### Docker Setup

```bash
docker run -d -p 1025:1025 -p 8025:8025 axllent/mailpit
```

#### Additional Methods

```python
# Search emails using Mailpit's search syntax
emails = adapter.search("from:admin@example.com")

# Get specific email by ID
email = adapter.get_message("msg_123")

# Mark email as read
adapter.set_read("msg_123", read=True)
```

---

### SMTPMockAdapter

In-memory SMTP mock server for isolated testing.

```python
from venomqa.adapters import SMTPMockAdapter

adapter = SMTPMockAdapter(
    host="localhost",
    port=2500,
    timeout=10.0,
)

# Start the mock server
adapter.start()

# Use it...

# Stop when done
adapter.stop()
```

#### Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | `str` | `"localhost"` | Hostname to bind to |
| `port` | `int` | `2500` | Port to listen on |
| `timeout` | `float` | `10.0` | Operation timeout |

#### Context Manager Usage

```python
import smtplib
from email.message import EmailMessage

def test_with_smtp_mock():
    mock = SMTPMockAdapter(port=2500)
    mock.start()
    
    try:
        # Send email to mock
        msg = EmailMessage()
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg["Subject"] = "Test"
        msg.set_content("Hello")
        
        with smtplib.SMTP("localhost", 2500) as server:
            server.send_message(msg)
        
        # Verify email was captured
        emails = mock.get_emails_to("recipient@example.com")
        assert len(emails) == 1
    finally:
        mock.stop()
```

---

## Cache Adapters

### RedisCacheAdapter

Redis cache backend with full TTL and statistics support.

```python
from venomqa.adapters import RedisCacheAdapter

adapter = RedisCacheAdapter(
    host="localhost",
    port=6379,
    db=0,
    password=None,
    prefix="venomqa:",
    default_ttl=3600,
)
```

#### Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | `str` | `"localhost"` | Redis server hostname |
| `port` | `int` | `6379` | Redis server port |
| `db` | `int` | `0` | Redis database number |
| `password` | `str \| None` | `None` | Redis password |
| `prefix` | `str` | `"venomqa:"` | Key prefix for namespacing |
| `default_ttl` | `int` | `3600` | Default TTL in seconds |

#### Environment Variables

```bash
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=secret
REDIS_DB=0
```

#### Additional Methods

```python
# Increment/decrement counters
adapter.increment("counter", 1)
adapter.decrement("counter", 1)

# Get or set default
value = adapter.get_or_set("key", default="default_value", ttl=60)

# Set operations
adapter.add_to_set("tags", "python", "testing")
tags = adapter.get_set("tags")

# List operations
adapter.push_to_list("queue", "item1", "item2")
items = adapter.get_list("queue")

# Hash operations
adapter.set_hash("user:1", "name", "John")
name = adapter.get_hash("user:1", "name")
user_data = adapter.get_all_hash("user:1")
```

---

## Queue Adapters

### RedisQueueAdapter

Redis Queue (RQ) integration for job queue testing.

```python
from venomqa.adapters import RedisQueueAdapter

adapter = RedisQueueAdapter(
    host="localhost",
    port=6379,
    db=0,
    password=None,
    default_queue="default",
)
```

#### Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | `str` | `"localhost"` | Redis server hostname |
| `port` | `int` | `6379` | Redis server port |
| `db` | `int` | `0` | Redis database number |
| `password` | `str \| None` | `None` | Redis password |
| `default_queue` | `str` | `"default"` | Default queue name |

#### Installation

```bash
pip install redis rq
```

#### Usage Example

```python
def process_data(data):
    return data * 2

# Enqueue job
job_id = adapter.enqueue(process_data, {"key": "value"}, queue="processing")

# Wait for result
result = adapter.get_job_result(job_id, timeout=60.0)
if result and result.success:
    print(f"Result: {result.result}")

# Check queue length
queue_length = adapter.get_queue_length("processing")

# Get failed jobs
failed = adapter.get_failed_jobs()

# Get worker info
workers = adapter.get_workers()
```

---

### CeleryQueueAdapter

Celery task queue integration for distributed task testing.

```python
from venomqa.adapters import CeleryQueueAdapter

adapter = CeleryQueueAdapter(
    broker_url="redis://localhost:6379/0",
    result_backend="redis://localhost:6379/1",
    default_queue="celery",
)
```

#### Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `broker_url` | `str` | `"redis://localhost:6379/0"` | Celery broker URL |
| `result_backend` | `str` | `"redis://localhost:6379/1"` | Result backend URL |
| `default_queue` | `str` | `"celery"` | Default queue name |

#### Installation

```bash
pip install celery redis
```

#### Usage Example

```python
# Enqueue task by name
job_id = adapter.enqueue("myapp.tasks.send_email", to="user@example.com")

# Wait for result
result = adapter.get_job_result(job_id, timeout=30.0)

# Advanced scheduling
job_id = adapter.apply_async(
    "myapp.tasks.process",
    args=("data",),
    kwargs={"option": True},
    queue="priority",
    countdown=10,  # Delay 10 seconds
)

# Get registered tasks
tasks = adapter.get_registered_tasks()

# Get worker info
workers = adapter.get_workers()
```

---

## Search Adapters

### ElasticsearchAdapter

Elasticsearch integration for full-text search testing.

```python
from venomqa.adapters import ElasticsearchAdapter

adapter = ElasticsearchAdapter(
    hosts=["http://localhost:9200"],
    cloud_id=None,
    api_key=None,
    basic_auth=None,
    timeout=30,
    verify_certs=True,
)
```

#### Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hosts` | `list[str] \| None` | `None` | List of Elasticsearch hosts |
| `cloud_id` | `str \| None` | `None` | Elastic Cloud ID |
| `api_key` | `str \| None` | `None` | API key for authentication |
| `basic_auth` | `tuple \| None` | `None` | (username, password) tuple |
| `timeout` | `int` | `30` | Request timeout in seconds |
| `verify_certs` | `bool` | `True` | Verify SSL certificates |

#### Installation

```bash
pip install elasticsearch
```

#### Usage Example

```python
from venomqa.ports import IndexedDocument

# Create index
adapter.create_index("products", settings={
    "number_of_shards": 1,
    "number_of_replicas": 0,
})

# Index document
doc = IndexedDocument(
    id="prod_1",
    content="Ergonomic office chair with lumbar support",
    title="Office Chair",
    fields={"price": 299.99, "category": "furniture"},
    tags=["office", "furniture"],
)
adapter.index_document("products", doc, refresh=True)

# Search
results, total = adapter.search(
    "products",
    query="chair",
    fields=["title", "content"],
    limit=10,
)

# Bulk index
documents = [IndexedDocument(id=f"prod_{i}", content=f"Product {i}") for i in range(100)]
count = adapter.index_documents("products", documents)

# Get document
doc = adapter.get_document("products", "prod_1")

# Scroll through all results
for batch in adapter.scroll_search("products", "chair", size=100):
    for result in batch:
        print(result.id, result.score)

# Cluster health
health = adapter.get_cluster_health()
```

---

## Storage Adapters

### S3StorageAdapter

AWS S3 and S3-compatible storage (MinIO, DigitalOcean Spaces, etc.).

```python
from venomqa.adapters import S3StorageAdapter

adapter = S3StorageAdapter(
    endpoint_url=None,  # Use AWS S3
    region_name="us-east-1",
    aws_access_key_id=None,
    aws_secret_access_key=None,
)
```

#### Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `endpoint_url` | `str \| None` | `None` | S3 endpoint (for MinIO, etc.) |
| `region_name` | `str` | `"us-east-1"` | AWS region |
| `aws_access_key_id` | `str \| None` | `None` | AWS access key |
| `aws_secret_access_key` | `str \| None` | `None` | AWS secret key |

#### Environment Variables

```bash
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
S3_ENDPOINT=http://localhost:9000  # For MinIO
```

#### Installation

```bash
pip install boto3
```

#### Usage Example

```python
# Create bucket
adapter.create_bucket("test-bucket")

# Upload
adapter.upload("test-bucket", "file.txt", b"Hello World", content_type="text/plain")

# Download
data = adapter.download("test-bucket", "file.txt")
print(data.decode())

# Check existence
exists = adapter.exists("test-bucket", "file.txt")

# List objects
for obj in adapter.list_objects("test-bucket", prefix="files/"):
    print(obj.key, obj.size)

# Presigned URL
url = adapter.get_presigned_url("test-bucket", "file.txt", expires_in=3600)

# Copy/move
adapter.copy("test-bucket", "file.txt", "backup-bucket", "backup.txt")
adapter.move("test-bucket", "old.txt", "test-bucket", "new.txt")

# Tags
adapter.set_object_tags("test-bucket", "file.txt", {"env": "test", "type": "data"})
tags = adapter.get_object_tags("test-bucket", "file.txt")

# Cleanup
adapter.delete("test-bucket", "file.txt")
adapter.delete_bucket("test-bucket", force=True)
```

#### MinIO Example

```python
adapter = S3StorageAdapter(
    endpoint_url="http://localhost:9000",
    region_name="us-east-1",
    aws_access_key_id="minioadmin",
    aws_secret_access_key="minioadmin",
)
```

---

### LocalStorageAdapter

Local filesystem storage for testing without external dependencies.

```python
from venomqa.adapters import LocalStorageAdapter

adapter = LocalStorageAdapter(
    base_path="./storage",
    create_dirs=True,
    hash_key_paths=False,
)
```

#### Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_path` | `str` | `"./storage"` | Base directory for storage |
| `create_dirs` | `bool` | `True` | Create directories automatically |
| `hash_key_paths` | `bool` | `False` | Hash keys for file paths |

#### Usage Example

```python
adapter = LocalStorageAdapter(base_path="/tmp/test-storage")

# Create bucket (directory)
adapter.create_bucket("test")

# Upload
adapter.upload("test", "data.json", b'{"key": "value"}')

# Download
data = adapter.download("test", "data.json")

# List buckets
buckets = adapter.list_buckets()

# Get bucket size
size = adapter.get_bucket_size("test")

# Clear bucket
count = adapter.clear_bucket("test")
```

---

## Mock Adapters

### WireMockAdapter

[WireMock](https://wiremock.org/) integration for HTTP mocking.

```python
from venomqa.adapters import WireMockAdapter

adapter = WireMockAdapter(
    host="localhost",
    port=8080,
    timeout=10.0,
)
```

#### Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | `str` | `"localhost"` | WireMock server hostname |
| `port` | `int` | `8080` | WireMock server port |
| `timeout` | `float` | `10.0` | Request timeout in seconds |

#### Docker Setup

```bash
docker run -d -p 8080:8080 wiremock/wiremock
```

#### Usage Example

```python
from venomqa.ports import MockResponse

adapter = WireMockAdapter()

# Simple stub
adapter.stub("GET", "/api/users", body={"users": []}, status_code=200)

# Stub with delay
adapter.stub("GET", "/api/slow", body={"data": "..."}, delay=2.0)

# Stub with custom headers
adapter.stub(
    "POST", "/api/auth",
    body={"token": "abc123"},
    headers={"X-Request-Id": "test-123"},
)

# Sequential responses
adapter.stub_sequence("GET", "/api/status", responses=[
    MockResponse(status_code=503, body={"status": "starting"}),
    MockResponse(status_code=200, body={"status": "ready"}),
])

# Verify requests
assert adapter.verify("GET", "/api/users", count=1)
assert adapter.verify("GET", "/api/users", at_least=1)

# Get recorded requests
requests = adapter.get_requests(method="GET", path="/api/users")
for req in requests:
    print(f"{req.method} {req.path}")

# Global delay
adapter.set_global_delay(0.5)

# Reset
adapter.reset()

# Get base URL for making requests
base_url = adapter.get_base_url()  # http://localhost:8080
```

---

## Time Adapters

### ControllableTimeAdapter

Deterministic time for testing time-dependent functionality.

```python
from datetime import timedelta
from venomqa.adapters import ControllableTimeAdapter

adapter = ControllableTimeAdapter(
    initial_time=None,
    timezone_name="UTC",
)
```

#### Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `initial_time` | `datetime \| None` | `None` | Starting time (defaults to now) |
| `timezone_name` | `str` | `"UTC"` | Timezone name |

#### Usage Example

```python
from datetime import datetime, timedelta

adapter = ControllableTimeAdapter()

# Freeze time
adapter.freeze()
now = adapter.now()
adapter.advance(timedelta(hours=1))
assert adapter.now() > now

# Set specific time
adapter.set_time(datetime(2024, 1, 1, 12, 0, 0))

# Sleep advances time instantly when frozen
adapter.sleep(60)  # Advances 60 seconds instantly

# Schedule tasks
def callback():
    print("Task executed!")

task_id = adapter.schedule_after(30.0, callback)
adapter.advance(timedelta(seconds=30))  # Triggers callback

# Unfreeze to use real time
adapter.unfreeze()

# Reset everything
adapter.reset()
```

---

### RealTimeAdapter

Real system time for production use.

```python
from venomqa.adapters import RealTimeAdapter

adapter = RealTimeAdapter(timezone_name="UTC")
```

#### Usage Example

```python
adapter = RealTimeAdapter()

# Get current time
now = adapter.now()
timestamp = adapter.timestamp()

# Real sleep
adapter.sleep(1.0)  # Actually sleeps 1 second

# Schedule real tasks
def callback():
    print("Executed after delay!")

task_id = adapter.schedule_after(5.0, callback)
# ... 5 seconds later, callback runs

# Cancel scheduled task
adapter.cancel_schedule(task_id)
```

---

## Concurrency Adapters

### ThreadingConcurrencyAdapter

Thread-based parallel execution.

```python
from venomqa.adapters import ThreadingConcurrencyAdapter

adapter = ThreadingConcurrencyAdapter(
    max_workers=4,
    thread_name_prefix="venomqa-",
)
```

#### Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_workers` | `int` | `4` | Maximum worker threads |
| `thread_name_prefix` | `str` | `"venomqa-"` | Thread name prefix |

#### Usage Example

```python
def process_item(item):
    return item * 2

adapter = ThreadingConcurrencyAdapter(max_workers=4)

# Spawn task
task_id = adapter.spawn(process_item, 21)

# Wait for result
result = adapter.join(task_id, timeout=10.0)
print(result.result)  # 42

# Spawn multiple tasks
task_ids = adapter.spawn_many([process_item] * 10)

# Wait for all
results = adapter.join_all(task_ids)

# Map in parallel
results = adapter.map_parallel(process_item, range(10), max_workers=4)

# Check task status
if adapter.is_completed(task_id):
    result = adapter.get_result(task_id)

# Shutdown
adapter.shutdown(wait=True)
```

---

### AsyncConcurrencyAdapter

Asyncio-based parallel execution for async functions.

```python
from venomqa.adapters import AsyncConcurrencyAdapter

adapter = AsyncConcurrencyAdapter(max_concurrent=10)
```

#### Usage Example

```python
import asyncio

async def async_process(item):
    await asyncio.sleep(0.1)
    return item * 2

async def main():
    adapter = AsyncConcurrencyAdapter(max_concurrent=10)
    
    # Spawn async task
    task_id = await adapter.spawn_async(async_process, 21)
    
    # Wait for result
    result = await adapter.join_async(task_id)
    print(result.result)  # 42
    
    # Parallel map
    results = await adapter.map_parallel_async(async_process, range(10))

asyncio.run(main())
```

---

## Adapter Registry

You can register and retrieve adapters by name:

```python
from venomqa.adapters import register_adapter, get_adapter, list_adapters

# Register adapter
@register_adapter("my_custom")
class MyCustomAdapter(CachePort):
    pass

# Or register directly
register_adapter_class("another", AnotherAdapter)

# Get adapter class
adapter_class = get_adapter("my_custom")

# List all adapters
names = list_adapters()
```
