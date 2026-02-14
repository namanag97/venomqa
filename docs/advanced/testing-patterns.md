# Testing Patterns

Advanced testing patterns and strategies for VenomQA.

## Data-Driven Testing

### Parameterized Journeys

```python
from venomqa import Journey, Step

test_cases = [
    {"email": "valid@example.com", "password": "ValidPass123!", "expect_success": True},
    {"email": "invalid-email", "password": "ValidPass123!", "expect_success": False},
    {"email": "valid@example.com", "password": "short", "expect_success": False},
    {"email": "", "password": "ValidPass123!", "expect_success": False},
]

def make_register_action(case):
    def register(client, context):
        return client.post("/api/auth/register", json={
            "email": case["email"],
            "password": case["password"],
        })
    return register

journeys = []
for case in test_cases:
    journey = Journey(
        name=f"register_{case['email'].replace('@', '_at_').replace('.', '_')}",
        description=f"Test registration with email={case['email']}",
        tags=["registration", "data-driven"],
        steps=[
            Step(
                name="register",
                action=make_register_action(case),
                expect_failure=not case["expect_success"],
            ),
        ],
    )
    journeys.append(journey)
```

### CSV-Based Test Data

```python
import csv
from venomqa import Journey, Step


def load_test_cases(csv_path: str) -> list[dict]:
    """Load test cases from CSV file."""
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        return list(reader)


test_cases = load_test_cases("test_data/users.csv")

journeys = [
    Journey(
        name=f"user_test_{i}",
        steps=[
            Step(
                name="create_user",
                action=lambda c, ctx, tc=tc: c.post("/api/users", json=tc),
                expect_failure=tc.get("expect_failure", "false").lower() == "true",
            ),
        ],
    )
    for i, tc in enumerate(test_cases)
]
```

## Contract Testing

### Schema Validation

```python
from venomqa import Journey, Step
import jsonschema


USER_SCHEMA = {
    "type": "object",
    "required": ["id", "email", "name"],
    "properties": {
        "id": {"type": "integer"},
        "email": {"type": "string", "format": "email"},
        "name": {"type": "string", "minLength": 1},
        "created_at": {"type": "string", "format": "date-time"},
    },
}


def create_user(client, context):
    response = client.post("/api/users", json={
        "email": "test@example.com",
        "name": "Test User",
    })

    if response.status_code in [200, 201]:
        # Validate response schema
        try:
            jsonschema.validate(response.json(), USER_SCHEMA)
            context["schema_valid"] = True
        except jsonschema.ValidationError as e:
            context["schema_error"] = str(e)
            raise AssertionError(f"Schema validation failed: {e}")

    return response


def get_user(client, context):
    response = client.get(f"/api/users/{context['user_id']}")

    if response.status_code == 200:
        jsonschema.validate(response.json(), USER_SCHEMA)

    return response


journey = Journey(
    name="user_contract_test",
    description="Test user API contract",
    tags=["contract", "schema"],
    steps=[
        Step(name="create", action=create_user),
        Step(name="read", action=get_user),
    ],
)
```

## Smoke Testing

### Quick Health Checks

```python
from venomqa import Journey, Step


def health_check(client, context):
    return client.get("/health")


def api_status(client, context):
    return client.get("/api/status")


def db_ping(client, context):
    return client.get("/api/health/db")


def cache_ping(client, context):
    return client.get("/api/health/cache")


def queue_ping(client, context):
    return client.get("/api/health/queue")


smoke_journey = Journey(
    name="smoke_test",
    description="Quick health check of all services",
    tags=["smoke", "health"],
    timeout=30.0,
    steps=[
        Step(name="health", action=health_check, timeout=5.0),
        Step(name="api", action=api_status, timeout=5.0),
        Step(name="db", action=db_ping, timeout=5.0),
        Step(name="cache", action=cache_ping, timeout=5.0),
        Step(name="queue", action=queue_ping, timeout=5.0),
    ],
)
```

## Regression Testing

### Baseline Comparison

```python
import json
from pathlib import Path
from venomqa import Journey, Step


BASELINE_PATH = Path("baselines")


def load_baseline(name: str) -> dict | None:
    """Load baseline response."""
    path = BASELINE_PATH / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def save_baseline(name: str, data: dict) -> None:
    """Save baseline response."""
    BASELINE_PATH.mkdir(exist_ok=True)
    path = BASELINE_PATH / f"{name}.json"
    path.write_text(json.dumps(data, indent=2))


def compare_response(name: str, actual: dict, context) -> None:
    """Compare response with baseline."""
    expected = load_baseline(name)

    if expected is None:
        # First run - save baseline
        save_baseline(name, actual)
        context[f"{name}_baseline_created"] = True
        return

    # Compare (ignoring timestamps, ids, etc.)
    def normalize(obj):
        if isinstance(obj, dict):
            return {k: normalize(v) for k, v in obj.items()
                    if k not in ["id", "created_at", "updated_at"]}
        elif isinstance(obj, list):
            return [normalize(item) for item in obj]
        return obj

    if normalize(actual) != normalize(expected):
        context[f"{name}_regression_diff"] = {
            "expected": expected,
            "actual": actual,
        }
        raise AssertionError(f"Regression detected in {name}")


def get_users_regression(client, context):
    response = client.get("/api/users")
    if response.status_code == 200:
        compare_response("get_users", response.json(), context)
    return response


journey = Journey(
    name="regression_test",
    description="Compare API responses with baselines",
    tags=["regression"],
    steps=[
        Step(name="login", action=login),
        Step(name="get_users", action=get_users_regression),
    ],
)
```

## Chaos Testing

### Random Failure Injection

```python
import random
from venomqa import Journey, Step


class ChaosConfig:
    failure_rate: float = 0.1  # 10% failure rate
    slow_rate: float = 0.2     # 20% slow rate
    slow_min: float = 0.5      # Min slow delay
    slow_max: float = 2.0      # Max slow delay


def chaos_wrapper(action, config: ChaosConfig = ChaosConfig()):
    """Wrap action with chaos injection."""
    def wrapped(client, context):
        # Random failure
        if random.random() < config.failure_rate:
            raise Exception("Chaos monkey strike!")

        # Random slowdown
        if random.random() < config.slow_rate:
            import time
            delay = random.uniform(config.slow_min, config.slow_max)
            time.sleep(delay)

        return action(client, context)

    return wrapped


def normal_action(client, context):
    return client.get("/api/data")


journey = Journey(
    name="chaos_test",
    description="Test resilience with random failures",
    tags=["chaos", "resilience"],
    steps=[
        Step(name="action_1", action=chaos_wrapper(normal_action)),
        Step(name="action_2", action=chaos_wrapper(normal_action)),
        Step(name="action_3", action=chaos_wrapper(normal_action)),
    ],
)
```

## Load Testing Patterns

### Concurrent Users

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from venomqa import Journey, Step, Client, JourneyRunner


def run_journey_for_user(user_id: int, journey: Journey, config) -> dict:
    """Run journey for a single simulated user."""
    client = Client(base_url=config.base_url)
    runner = JourneyRunner(client=client)

    # Set user-specific context
    result = runner.run(journey)

    return {
        "user_id": user_id,
        "success": result.success,
        "duration_ms": result.duration_ms,
    }


def load_test(journey: Journey, config, num_users: int = 10, max_workers: int = 5):
    """Run journey concurrently for multiple users."""
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(run_journey_for_user, i, journey, config): i
            for i in range(num_users)
        }

        for future in as_completed(futures):
            user_id = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                results.append({
                    "user_id": user_id,
                    "success": False,
                    "error": str(e),
                })

    # Analyze results
    successful = sum(1 for r in results if r.get("success"))
    avg_duration = sum(r.get("duration_ms", 0) for r in results) / len(results)

    return {
        "total_users": num_users,
        "successful": successful,
        "failed": num_users - successful,
        "avg_duration_ms": avg_duration,
        "results": results,
    }
```

## Boundary Testing

### Edge Cases

```python
from venomqa import Journey, Step, Branch, Path, Checkpoint


def create_item_min_name(client, context):
    """Create item with minimum name length."""
    return client.post("/api/items", json={
        "name": "A",  # Minimum 1 character
        "price": 0.01,  # Minimum price
    })


def create_item_max_name(client, context):
    """Create item with maximum name length."""
    return client.post("/api/items", json={
        "name": "A" * 255,  # Maximum characters
        "price": 999999.99,  # Maximum price
    })


def create_item_boundary_exceeded(client, context):
    """Create item exceeding boundaries."""
    return client.post("/api/items", json={
        "name": "A" * 256,  # Exceeds maximum
        "price": 0,  # Below minimum
    })


journey = Journey(
    name="boundary_test",
    description="Test boundary conditions",
    tags=["boundary", "edge-case"],
    steps=[
        Checkpoint(name="start"),
        Branch(
            checkpoint_name="start",
            paths=[
                Path(name="minimum_values", steps=[
                    Step(name="create", action=create_item_min_name),
                ]),
                Path(name="maximum_values", steps=[
                    Step(name="create", action=create_item_max_name),
                ]),
                Path(name="exceeded_boundaries", steps=[
                    Step(
                        name="create",
                        action=create_item_boundary_exceeded,
                        expect_failure=True,
                    ),
                ]),
            ],
        ),
    ],
)
```

## Idempotency Testing

### Verify Idempotent Operations

```python
from venomqa import Journey, Step


def create_order(client, context):
    """Create order with idempotency key."""
    idempotency_key = "test-order-12345"
    context["idempotency_key"] = idempotency_key

    response = client.post("/api/orders", json={
        "items": [{"product_id": 1, "quantity": 1}],
    }, headers={
        "Idempotency-Key": idempotency_key,
    })

    if response.status_code in [200, 201]:
        context["order_id"] = response.json()["id"]

    return response


def retry_create_order(client, context):
    """Retry same order - should return same result."""
    response = client.post("/api/orders", json={
        "items": [{"product_id": 1, "quantity": 1}],
    }, headers={
        "Idempotency-Key": context["idempotency_key"],
    })

    # Should return same order ID, not create new one
    if response.status_code in [200, 201]:
        if response.json()["id"] != context["order_id"]:
            raise AssertionError("Idempotency failed - new order created")

    return response


journey = Journey(
    name="idempotency_test",
    description="Test idempotent operations",
    tags=["idempotency"],
    steps=[
        Step(name="create_order", action=create_order),
        Step(name="retry_order", action=retry_create_order),
        Step(name="retry_again", action=retry_create_order),
    ],
)
```

## Cleanup Patterns

### With Cleanup Steps

```python
from venomqa import Journey, Step, Checkpoint


def setup_test_data(client, context):
    """Create test data."""
    response = client.post("/api/items", json={"name": "Test"})
    context["item_id"] = response.json()["id"]
    return response


def run_tests(client, context):
    """Run actual tests."""
    return client.get(f"/api/items/{context['item_id']}")


def cleanup(client, context):
    """Clean up test data."""
    item_id = context.get("item_id")
    if item_id:
        return client.delete(f"/api/items/{item_id}")
    return {"status": "nothing to clean"}


journey = Journey(
    name="with_cleanup",
    description="Test with cleanup",
    steps=[
        Step(name="setup", action=setup_test_data),
        Checkpoint(name="after_setup"),
        Step(name="test", action=run_tests),
        Step(name="cleanup", action=cleanup),  # Always runs
    ],
)
```

### Using Context Manager

```python
class TestDataManager:
    """Manage test data with automatic cleanup."""

    def __init__(self, client):
        self.client = client
        self.created_items = []

    def create_item(self, data: dict) -> dict:
        response = self.client.post("/api/items", json=data)
        if response.status_code in [200, 201]:
            self.created_items.append(response.json()["id"])
        return response.json()

    def cleanup(self):
        for item_id in self.created_items:
            self.client.delete(f"/api/items/{item_id}")
        self.created_items.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False


# Usage in journey
def test_with_manager(client, context):
    with TestDataManager(client) as manager:
        item = manager.create_item({"name": "Test"})
        # ... run tests ...
        # Cleanup happens automatically
```
