# Advanced Usage

This guide covers advanced features and patterns in VenomQA.

> **Prerequisites**: Familiarity with [Journeys](journeys.md) and [Configuration](backends.md).

## Table of Contents

- [Caching](#caching)
- [Parallel Execution](#parallel-execution)
- [Custom Reporters](#custom-reporters)
- [Custom State Backends](#custom-state-backends)
- [Hooks and Extensions](#hooks-and-extensions)
- [Performance Optimization](#performance-optimization)
- [Error Handling Strategies](#error-handling-strategies)
- [Testing Patterns](#testing-patterns)

## Related Documentation

| Topic | Document |
|-------|----------|
| API Reference | [api.md](api.md) |
| Adapters | [adapters.md](adapters.md) |
| Examples | [examples.md](examples.md) |
| FAQ | [FAQ.md](FAQ.md) |

---

## Caching

### Response Caching

Cache responses to speed up repeated requests:

```python
from functools import lru_cache
from venomqa import Client

class CachedClient(Client):
    """HTTP client with response caching for GET requests."""
    
    def __init__(self, *args, cache_size: int = 100, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache_size = cache_size
        self._get_cached = lru_cache(maxsize=cache_size)(self._get_uncached)
    
    def _get_uncached(self, path: str, cache_key: str) -> dict:
        """Uncached GET implementation."""
        return super().get(path)
    
    def get(self, path: str, **kwargs) -> dict:
        # Create cache key from path and params
        import json
        cache_key = json.dumps({"path": path, "kwargs": kwargs}, sort_keys=True)
        return self._get_cached(path, cache_key)
    
    def clear_cache(self):
        """Clear the response cache."""
        self._get_cached.cache_clear()
```

### Authentication Token Caching

Cache auth tokens across steps:

```python
from venomqa.core.context import ExecutionContext

def login_with_cache(client, context: ExecutionContext):
    """Login with token caching to avoid repeated auth."""
    cached_token = context.get("_cached_auth_token")
    
    if cached_token:
        client.set_auth_token(cached_token)
        # Verify token still works
        response = client.get("/api/auth/verify")
        if response.status_code == 200:
            return response
    
    # Perform fresh login
    response = client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "secret",
    })
    
    if response.status_code == 200:
        token = response.json()["token"]
        context["_cached_auth_token"] = token
        client.set_auth_token(token)
    
    return response
```

### Fixture Data Caching

Cache expensive setup operations:

```python
import hashlib
import pickle
from pathlib import Path

class FixtureCache:
    """Cache fixture data to disk."""
    
    def __init__(self, cache_dir: str = ".venomqa_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
    
    def _cache_key(self, data: dict) -> str:
        return hashlib.md5(pickle.dumps(data)).hexdigest()
    
    def get(self, key: str) -> dict | None:
        cache_file = self.cache_dir / f"{key}.pkl"
        if cache_file.exists():
            return pickle.loads(cache_file.read_bytes())
        return None
    
    def set(self, key: str, data: dict) -> None:
        cache_file = self.cache_dir / f"{key}.pkl"
        cache_file.write_bytes(pickle.dumps(data))
    
    def cached_setup(self, setup_func, *args, **kwargs):
        """Run setup function with caching."""
        cache_key = self._cache_key({"func": setup_func.__name__, "args": args, "kwargs": kwargs})
        
        cached = self.get(cache_key)
        if cached is not None:
            return cached
        
        result = setup_func(*args, **kwargs)
        self.set(cache_key, result)
        return result
```

---

## Parallel Execution

### Enabling Parallel Paths

Run branch paths in parallel:

```python
from venomqa import JourneyRunner

runner = JourneyRunner(
    client=client,
    state_manager=state_manager,
    parallel_paths=4,  # Run up to 4 paths concurrently
)

result = runner.run(journey)
```

### Configuration

```yaml
# venomqa.yaml
parallel_paths: 4
```

### Considerations for Parallel Execution

1. **State Isolation**: Each parallel path needs isolated state
2. **Resource Limits**: Don't exceed database connection limits
3. **Rate Limiting**: APIs may have rate limits

### Isolating State for Parallel Paths

When running in parallel, each path needs its own context:

```python
# The runner automatically handles this by:
# 1. Creating a context snapshot before the branch
# 2. Restoring the snapshot for each path
# 3. Each path gets its own isolated context

# For database state, ensure:
# 1. Each path uses different record IDs
# 2. Or use database-level transactions with SAVEPOINT
```

### Parallel Journey Execution

Run multiple journeys in parallel:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from venomqa import JourneyRunner, Client

def run_journey(journey, config):
    client = Client(base_url=config.base_url)
    runner = JourneyRunner(client=client)
    return runner.run(journey)

def run_all_parallel(journeys, config, max_workers=4):
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(run_journey, j, config): j
            for j in journeys
        }
        
        for future in as_completed(futures):
            journey = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                print(f"Journey {journey.name} failed: {e}")
    
    return results
```

---

## Custom Reporters

### Creating a Custom Reporter

```python
from pathlib import Path
from typing import Any
from venomqa.reporters.base import BaseReporter
from venomqa.core.models import JourneyResult

class CSVReporter(BaseReporter):
    """Generate CSV reports for spreadsheet analysis."""
    
    @property
    def file_extension(self) -> str:
        return ".csv"
    
    def generate(self, results: list[JourneyResult]) -> str:
        lines = [
            "journey_name,success,duration_ms,total_steps,passed_steps,issue_count"
        ]
        
        for result in results:
            lines.append(
                f"{result.journey_name},"
                f"{result.success},"
                f"{result.duration_ms:.0f},"
                f"{result.total_steps},"
                f"{result.passed_steps},"
                f"{len(result.issues)}"
            )
        
        return "\n".join(lines)


class SlackReporter(BaseReporter):
    """Send test results to Slack."""
    
    def __init__(self, webhook_url: str, output_path: str | Path | None = None):
        super().__init__(output_path)
        self.webhook_url = webhook_url
    
    @property
    def file_extension(self) -> str:
        return ".json"
    
    def generate(self, results: list[JourneyResult]) -> dict[str, Any]:
        passed = sum(1 for r in results if r.success)
        failed = len(results) - passed
        
        color = "good" if failed == 0 else "danger"
        status = "All tests passed!" if failed == 0 else f"{failed} test(s) failed"
        
        return {
            "attachments": [{
                "color": color,
                "title": "VenomQA Test Results",
                "text": status,
                "fields": [
                    {"title": "Passed", "value": str(passed), "short": True},
                    {"title": "Failed", "value": str(failed), "short": True},
                ],
            }]
        }
    
    def send_to_slack(self, results: list[JourneyResult]) -> None:
        import httpx
        
        payload = self.generate(results)
        httpx.post(self.webhook_url, json=payload)


class HTMLDashboardReporter(BaseReporter):
    """Generate interactive HTML dashboard."""
    
    @property
    def file_extension(self) -> str:
        return ".html"
    
    def generate(self, results: list[JourneyResult]) -> str:
        return f"""<!DOCTYPE html>
<html>
<head>
    <title>VenomQA Dashboard</title>
    <style>
        body {{ font-family: system-ui, sans-serif; margin: 40px; }}
        .card {{ border: 1px solid #e5e5e5; border-radius: 8px; padding: 16px; margin: 16px 0; }}
        .passed {{ border-left: 4px solid #22c55e; }}
        .failed {{ border-left: 4px solid #ef4444; }}
        .metrics {{ display: flex; gap: 24px; }}
        .metric {{ text-align: center; }}
        .metric-value {{ font-size: 2em; font-weight: bold; }}
        .metric-label {{ color: #666; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #e5e5e5; }}
    </style>
</head>
<body>
    <h1>VenomQA Dashboard</h1>
    
    <div class="card">
        <div class="metrics">
            {self._generate_metrics(results)}
        </div>
    </div>
    
    <div class="card">
        <h2>Journey Results</h2>
        <table>
            <tr>
                <th>Journey</th>
                <th>Status</th>
                <th>Duration</th>
                <th>Steps</th>
                <th>Issues</th>
            </tr>
            {self._generate_rows(results)}
        </table>
    </div>
</body>
</html>"""
    
    def _generate_metrics(self, results: list[JourneyResult]) -> str:
        passed = sum(1 for r in results if r.success)
        failed = len(results) - passed
        total_duration = sum(r.duration_ms for r in results)
        
        return f"""
            <div class="metric">
                <div class="metric-value" style="color: #22c55e;">{passed}</div>
                <div class="metric-label">Passed</div>
            </div>
            <div class="metric">
                <div class="metric-value" style="color: #ef4444;">{failed}</div>
                <div class="metric-label">Failed</div>
            </div>
            <div class="metric">
                <div class="metric-value">{total_duration/1000:.1f}s</div>
                <div class="metric-label">Duration</div>
            </div>
        """
    
    def _generate_rows(self, results: list[JourneyResult]) -> str:
        rows = []
        for r in results:
            status_class = "passed" if r.success else "failed"
            status_icon = "✓" if r.success else "✗"
            rows.append(f"""
                <tr class="{status_class}">
                    <td>{r.journey_name}</td>
                    <td>{status_icon}</td>
                    <td>{r.duration_ms:.0f}ms</td>
                    <td>{r.passed_steps}/{r.total_steps}</td>
                    <td>{len(r.issues)}</td>
                </tr>
            """)
        return "\n".join(rows)
```

### Using Custom Reporters

```python
from venomqa.reporters import MarkdownReporter

# Use built-in reporter
reporter = MarkdownReporter(output_path="reports/test.md")
reporter.save([result1, result2])

# Use custom reporter
csv_reporter = CSVReporter(output_path="reports/results.csv")
csv_reporter.save([result1, result2])

slack_reporter = SlackReporter(webhook_url="https://hooks.slack.com/...")
slack_reporter.send_to_slack([result1, result2])
```

---

## Custom State Backends

See [Database Backends](backends.md#custom-backends) for implementing custom state backends.

---

## Hooks and Extensions

### Pre/Post Step Hooks

```python
from venomqa import JourneyRunner, Step
from venomqa.core.models import StepResult
from typing import Callable

class HookedJourneyRunner(JourneyRunner):
    """Runner with pre/post step hooks."""
    
    def __init__(self, *args, 
                 pre_step_hook: Callable | None = None,
                 post_step_hook: Callable | None = None,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.pre_step_hook = pre_step_hook
        self.post_step_hook = post_step_hook
    
    def _run_step(self, step: Step, journey_name: str, path_name: str, context) -> StepResult:
        # Pre-step hook
        if self.pre_step_hook:
            self.pre_step_hook(step=step, journey=journey_name, path=path_name, context=context)
        
        # Run the step
        result = super()._run_step(step, journey_name, path_name, context)
        
        # Post-step hook
        if self.post_step_hook:
            self.post_step_hook(step=step, result=result, context=context)
        
        return result


# Usage
def log_step(step, journey, path, context):
    print(f"Running: {journey}/{path}/{step.name}")

def capture_screenshot_on_failure(step, result, context):
    if not result.success:
        # Take screenshot, save logs, etc.
        print(f"Step {step.name} failed, capturing diagnostics...")

runner = HookedJourneyRunner(
    client=client,
    pre_step_hook=log_step,
    post_step_hook=capture_screenshot_on_failure,
)
```

### Journey Lifecycle Hooks

```python
class LifecycleRunner(JourneyRunner):
    """Runner with full lifecycle hooks."""
    
    def __init__(self, *args,
                 on_journey_start: Callable | None = None,
                 on_journey_end: Callable | None = None,
                 on_branch_start: Callable | None = None,
                 on_branch_end: Callable | None = None,
                 on_path_start: Callable | None = None,
                 on_path_end: Callable | None = None,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.on_journey_start = on_journey_start
        self.on_journey_end = on_journey_end
        self.on_branch_start = on_branch_start
        self.on_branch_end = on_branch_end
        self.on_path_start = on_path_start
        self.on_path_end = on_path_end
    
    def run(self, journey):
        if self.on_journey_start:
            self.on_journey_start(journey=journey)
        
        result = super().run(journey)
        
        if self.on_journey_end:
            self.on_journey_end(journey=journey, result=result)
        
        return result
```

---

## Performance Optimization

### Reduce Request Overhead

```python
# Reuse client across journeys
client = Client(base_url="http://localhost:8000")
client.connect()  # Keep connection open

for journey in journeys:
    runner = JourneyRunner(client=client)
    result = runner.run(journey)

client.disconnect()
```

### Batch Operations

```python
def create_items_batch(client, context):
    """Create multiple items in one request."""
    items = [{"name": f"Item {i}"} for i in range(10)]
    return client.post("/api/items/batch", json={"items": items})
```

### Skip Unnecessary Steps

```python
def conditional_step(client, context):
    # Skip if already done
    if context.get("setup_complete"):
        return {"status": "skipped"}
    
    # Do expensive setup
    result = client.post("/api/setup", json={...})
    context["setup_complete"] = True
    return result
```

### Parallel Data Setup

```python
from concurrent.futures import ThreadPoolExecutor

def setup_test_data_parallel(client, context):
    """Setup test data in parallel."""
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(client.post, "/api/users", json={"name": f"User {i}"})
            for i in range(10)
        ]
        results = [f.result() for f in futures]
    
    context["user_ids"] = [r.json()["id"] for r in results]
    return results
```

---

## Error Handling Strategies

### Graceful Degradation

```python
def resilient_step(client, context):
    """Step that degrades gracefully on failure."""
    try:
        response = client.get("/api/features")
        context["features"] = response.json()
    except Exception:
        # Use defaults if features API is down
        context["features"] = {"default_feature": True}
    
    return response
```

### Retry with Exponential Backoff

```python
import time
import random

def retry_with_backoff(func, max_retries=3, base_delay=1.0):
    """Execute function with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            time.sleep(delay)

def flaky_api_call(client, context):
    return retry_with_backoff(
        lambda: client.get("/api/flaky-endpoint"),
        max_retries=5,
        base_delay=0.5,
    )
```

### Circuit Breaker Pattern

```python
from datetime import datetime, timedelta
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    """Circuit breaker for unreliable services."""
    
    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.state = CircuitState.CLOSED
        self.last_failure_time: datetime | None = None
    
    def execute(self, func):
        if self.state == CircuitState.OPEN:
            if self._should_try_recovery():
                self.state = CircuitState.HALF_OPEN
            else:
                raise Exception("Circuit breaker is open")
        
        try:
            result = func()
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e
    
    def _should_try_recovery(self) -> bool:
        if self.last_failure_time is None:
            return True
        return datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout)
    
    def _on_success(self):
        self.failures = 0
        self.state = CircuitState.CLOSED
    
    def _on_failure(self):
        self.failures += 1
        self.last_failure_time = datetime.now()
        if self.failures >= self.failure_threshold:
            self.state = CircuitState.OPEN

# Usage
circuit = CircuitBreaker(failure_threshold=3, recovery_timeout=30)

def protected_api_call(client, context):
    return circuit.execute(lambda: client.get("/api/unreliable"))
```

---

## Known Limitations

### Parallel Path Execution with State Management

When using `parallel_paths > 1` (parallel branch execution), database state isolation is not guaranteed. Each path should start from the checkpoint state, but with parallel execution:

- All threads share the same database connection
- Rollback doesn't happen between parallel paths
- Paths may interfere with each other's database state

**Recommendation**: Use `parallel_paths=1` (sequential execution) when:
- Your journeys use database checkpoints and rollback
- Your paths modify database state
- State isolation between paths is important

Parallel execution is safe when:
- You're only testing read operations
- Paths are independent and don't rely on specific database state
- You're using the MockStateManager (in-memory)

---

## Testing Patterns

### Data-Driven Testing

```python
from venomqa import Journey, Step

# Test with multiple data sets
test_cases = [
    {"name": "valid_user", "email": "test@example.com", "expect_success": True},
    {"name": "invalid_email", "email": "invalid", "expect_success": False},
    {"name": "missing_email", "email": None, "expect_success": False},
]

journeys = []
for case in test_cases:
    def register_test(client, context, case=case):
        return client.post("/api/register", json={"email": case["email"]})
    
    journey = Journey(
        name=f"register_{case['name']}",
        steps=[
            Step(
                name="register",
                action=register_test,
                expect_failure=not case["expect_success"],
            ),
        ],
    )
    journeys.append(journey)
```

### Smoke Tests

```python
smoke_journey = Journey(
    name="smoke_test",
    description="Quick health check of critical endpoints",
    timeout=30.0,
    steps=[
        Step(name="health", action=lambda c, ctx: c.get("/health")),
        Step(name="api_status", action=lambda c, ctx: c.get("/api/status")),
        Step(name="db_ping", action=lambda c, ctx: c.get("/api/ping/db")),
    ],
)
```

### Regression Tests

```python
# Capture expected responses for regression testing
expected_responses = {
    "get_user": {"id": 1, "name": "Test User"},
}

def regression_test_step(client, context):
    response = client.get("/api/users/1")
    actual = response.json()
    expected = expected_responses["get_user"]
    
    if actual != expected:
        context["regression_diff"] = {
            "expected": expected,
            "actual": actual,
        }
        raise AssertionError("Response differs from expected")
    
    return response
```

### Chaos Testing

```python
import random

def chaos_step(client, context):
    """Introduce random failures for resilience testing."""
    # Randomly fail 10% of the time
    if random.random() < 0.1:
        raise Exception("Chaos monkey strike!")
    
    return client.get("/api/data")

def slow_network_step(client, context):
    """Simulate slow network conditions."""
    import time
    time.sleep(random.uniform(0.5, 2.0))  # Random delay
    return client.get("/api/data")
```

---

## Ports & Adapters

The Ports and Adapters architecture enables clean separation between test logic and external dependencies.

### Dependency Injection Pattern

Inject adapters through constructor or fixtures:

```python
import pytest
from venomqa.ports import CachePort, MailPort
from venomqa.adapters import RedisCacheAdapter, MailhogAdapter

class TestUserRegistration:
    def __init__(self, cache: CachePort, mail: MailPort):
        self.cache = cache
        self.mail = mail
    
    def test_registration_sends_email(self):
        # Register user
        self.register_user("test@example.com")
        
        # Verify email was sent
        email = self.mail.wait_for_email(
            to="test@example.com",
            subject="Welcome",
            timeout=30.0,
        )
        assert email is not None
        
        # Verify cache was updated
        assert self.cache.exists("user:test@example.com")

# Using with pytest fixtures
@pytest.fixture
def cache():
    return RedisCacheAdapter(host="localhost")

@pytest.fixture
def mail():
    return MailhogAdapter(host="localhost")

def test_with_adapters(cache, mail):
    tester = TestUserRegistration(cache, mail)
    tester.test_registration_sends_email()
```

### Swapping Adapters for Testing

Use different adapters for different test environments:

```python
from venomqa.ports import CachePort
from venomqa.adapters import RedisCacheAdapter, LocalStorageAdapter

def get_cache_adapter(env: str) -> CachePort:
    if env == "production":
        return RedisCacheAdapter(
            host="redis.production.internal",
            password=os.environ["REDIS_PASSWORD"],
        )
    elif env == "staging":
        return RedisCacheAdapter(host="localhost")
    else:
        # In-memory adapter for unit tests
        return LocalStorageAdapter(base_path="/tmp/test-cache")
```

### Time Travel Testing

Test time-dependent logic without waiting:

```python
from datetime import timedelta
from venomqa.adapters import ControllableTimeAdapter

def test_token_expiration():
    time = ControllableTimeAdapter()
    time.freeze()
    
    # Create token that expires in 1 hour
    token = create_token(expires_in=3600)
    assert token.is_valid()
    
    # Fast forward 59 minutes
    time.advance(timedelta(minutes=59))
    assert token.is_valid()
    
    # Fast forward 1 more minute - token should expire
    time.advance(timedelta(minutes=1))
    assert not token.is_valid()

def test_scheduled_task():
    time = ControllableTimeAdapter()
    results = []
    
    def callback():
        results.append("executed")
    
    # Schedule task for 5 seconds
    time.schedule_after(5.0, callback)
    
    # Time hasn't advanced yet
    assert len(results) == 0
    
    # Advance past scheduled time
    time.advance(timedelta(seconds=5))
    assert len(results) == 1
```

### Mock Server Integration

Use WireMock for API stubbing in tests:

```python
import pytest
from venomqa.adapters import WireMockAdapter
from venomqa import Client

@pytest.fixture
def mock_server():
    mock = WireMockAdapter(port=8080)
    yield mock
    mock.reset()

def test_api_with_mock(mock_server):
    # Stub API response
    mock_server.stub(
        "GET",
        "/api/users/1",
        body={"id": 1, "name": "John Doe"},
        status_code=200,
    )
    
    # Stub error response
    mock_server.stub(
        "GET",
        "/api/users/999",
        body={"error": "Not found"},
        status_code=404,
    )
    
    # Use mocked API
    client = Client(base_url=mock_server.get_base_url())
    
    response = client.get("/api/users/1")
    assert response.status_code == 200
    assert response.json()["name"] == "John Doe"
    
    # Verify request was made
    assert mock_server.verify("GET", "/api/users/1", count=1)

def test_sequential_responses(mock_server):
    # Return different responses on each call
    mock_server.stub_sequence("POST", "/api/orders", responses=[
        MockResponse(status_code=201, body={"id": 1}),
        MockResponse(status_code=201, body={"id": 2}),
        MockResponse(status_code=429, body={"error": "Rate limited"}),
    ])
    
    client = Client(base_url=mock_server.get_base_url())
    
    # First call
    r1 = client.post("/api/orders")
    assert r1.status_code == 201
    
    # Second call
    r2 = client.post("/api/orders")
    assert r2.status_code == 201
    
    # Third call - rate limited
    r3 = client.post("/api/orders")
    assert r3.status_code == 429
```

### Parallel Task Execution

Test concurrent operations:

```python
from venomqa.adapters import ThreadingConcurrencyAdapter

def test_concurrent_requests():
    concurrency = ThreadingConcurrencyAdapter(max_workers=10)
    
    def make_request(user_id):
        # Simulate API call
        return client.get(f"/api/users/{user_id}")
    
    # Spawn 100 concurrent tasks
    task_ids = concurrency.map_async(make_request, range(100))
    
    # Wait for all to complete
    results = concurrency.join_all(task_ids, timeout=30.0)
    
    # Verify all succeeded
    successful = [r for r in results if r.success]
    assert len(successful) == 100
```

### Email Testing Workflow

Complete email testing with cleanup:

```python
import pytest
from venomqa.adapters import MailhogAdapter

@pytest.fixture
def mail():
    adapter = MailhogAdapter(host="localhost")
    adapter.delete_all_emails()  # Clean slate
    yield adapter
    adapter.delete_all_emails()  # Cleanup

def test_password_reset_email(mail):
    # Request password reset
    response = client.post("/api/auth/forgot-password", json={
        "email": "user@example.com",
    })
    assert response.status_code == 200
    
    # Wait for and verify email
    email = mail.wait_for_email(
        to="user@example.com",
        subject="Password Reset",
        timeout=30.0,
    )
    
    assert email is not None
    assert "reset" in email.body.lower()
    
    # Extract reset link from email
    import re
    match = re.search(r'https://\S+/reset/\S+', email.body)
    assert match
    reset_link = match.group(0)
    
    # Use reset link
    response = client.post(reset_link, json={"password": "newpass123"})
    assert response.status_code == 200
```

### Cache Testing Patterns

Test cache behavior:

```python
from venomqa.adapters import RedisCacheAdapter

def test_cache_expiration():
    cache = RedisCacheAdapter()
    
    # Set with TTL
    cache.set("session:abc123", {"user_id": 1}, ttl=60)
    
    # Verify exists
    assert cache.exists("session:abc123")
    
    # Check TTL
    ttl = cache.get_ttl("session:abc123")
    assert 0 < ttl <= 60
    
    # Get stats
    stats = cache.get_stats()
    print(f"Hit rate: {stats.hit_rate}%")

def test_cache_invalidation():
    cache = RedisCacheAdapter()
    
    # Cache user data
    cache.set("user:1", {"name": "John", "role": "user"})
    
    # Update user
    update_user(1, role="admin")
    
    # Invalidate cache
    cache.delete("user:1")
    
    # Next read will fetch fresh data
    user = cache.get("user:1")
    assert user is None
```

### Queue Testing Patterns

Test async job processing:

```python
from venomqa.adapters import RedisQueueAdapter

def test_job_queue():
    queue = RedisQueueAdapter(host="localhost")
    
    # Clear queue
    queue.clear_queue("test")
    
    # Enqueue job
    job_id = queue.enqueue(
        "myapp.tasks.send_notification",
        user_id=123,
        message="Hello!",
        queue="test",
    )
    
    # Check job status
    job = queue.get_job(job_id)
    assert job.status == "pending"
    
    # Wait for completion (requires worker running)
    result = queue.get_job_result(job_id, timeout=60.0)
    
    if result:
        assert result.success
        print(f"Job result: {result.result}")
    
    # Check for failed jobs
    failed = queue.get_failed_jobs(queue="test")
    assert len(failed) == 0
```

### Creating Test Fixtures with Ports

Create reusable test fixtures:

```python
import pytest
from typing import TypeVar, Protocol
from venomqa.ports import CachePort, MailPort, QueuePort

T = TypeVar('T')

class TestFixtures:
    """Collection of test fixtures using ports."""
    
    def __init__(
        self,
        cache: CachePort,
        mail: MailPort,
        queue: QueuePort,
    ):
        self.cache = cache
        self.mail = mail
        self.queue = queue
    
    def reset(self):
        """Reset all fixtures to clean state."""
        self.cache.clear()
        self.mail.delete_all_emails()
        self.queue.clear_queue()
    
    def cached_user(self, user_id: int) -> dict:
        """Get or create cached user."""
        key = f"test:user:{user_id}"
        user = self.cache.get(key)
        if user is None:
            user = {"id": user_id, "name": f"User {user_id}"}
            self.cache.set(key, user, ttl=300)
        return user

@pytest.fixture
def fixtures():
    from venomqa.adapters import (
        RedisCacheAdapter,
        MailhogAdapter,
        RedisQueueAdapter,
    )
    
    fx = TestFixtures(
        cache=RedisCacheAdapter(),
        mail=MailhogAdapter(),
        queue=RedisQueueAdapter(),
    )
    fx.reset()
    yield fx
    fx.reset()
```

### Health Check Pattern

Verify external services before tests:

```python
import pytest
from venomqa.adapters import (
    RedisCacheAdapter,
    MailhogAdapter,
    ElasticsearchAdapter,
)

@pytest.fixture(scope="session", autouse=True)
def verify_services():
    """Verify all required services are healthy."""
    services = [
        ("Redis", RedisCacheAdapter()),
        ("MailHog", MailhogAdapter()),
        ("Elasticsearch", ElasticsearchAdapter()),
    ]
    
    unhealthy = []
    for name, adapter in services:
        if not adapter.health_check():
            unhealthy.append(name)
    
    if unhealthy:
        pytest.skip(f"Services not available: {', '.join(unhealthy)}")
```

### Multi-Environment Configuration

Configure adapters for different environments:

```python
from dataclasses import dataclass
from venomqa.ports import CachePort, MailPort
from venomqa.adapters import RedisCacheAdapter, MailhogAdapter, MailpitAdapter

@dataclass
class Environment:
    name: str
    cache: CachePort
    mail: MailPort

def get_environment() -> Environment:
    env_name = os.environ.get("ENV", "local")
    
    if env_name == "production":
        return Environment(
            name="production",
            cache=RedisCacheAdapter(
                host="redis.prod.internal",
                password=os.environ["REDIS_PASSWORD"],
            ),
            mail=MailpitAdapter(
                host="mail.prod.internal",
                use_tls=True,
            ),
        )
    elif env_name == "staging":
        return Environment(
            name="staging",
            cache=RedisCacheAdapter(host="localhost"),
            mail=MailhogAdapter(host="localhost"),
        )
    else:
        return Environment(
            name="local",
            cache=RedisCacheAdapter(host="localhost"),
            mail=MailhogAdapter(host="localhost"),
        )
```
