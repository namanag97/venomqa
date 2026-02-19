# Advanced Usage

Advanced features and patterns for power users.

<div class="feature-grid" markdown>

<div class="feature-card" markdown>

### [Custom Reporters](custom-reporters.md)

Create custom reporters for your specific needs.

</div>

<div class="feature-card" markdown>

### [Custom Backends](custom-backends.md)

Implement custom state management backends.

</div>

<div class="feature-card" markdown>

### [Performance](performance.md)

Optimize test execution and reduce runtime.

</div>

<div class="feature-card" markdown>

### [Testing Patterns](testing-patterns.md)

Advanced testing patterns and strategies.

</div>

</div>

## Topics Covered

| Topic | Description |
|-------|-------------|
| [Custom Reporters](custom-reporters.md) | Create CSV, Slack, custom format reporters |
| [Custom Backends](custom-backends.md) | MySQL, Redis, custom state backends |
| [Performance](performance.md) | Parallel execution, caching, optimization |
| [Testing Patterns](testing-patterns.md) | Data-driven, chaos, regression testing |

## Quick Examples

### Custom Reporter

```python
from venomqa.reporters.base import BaseReporter

class CSVReporter(BaseReporter):
    @property
    def file_extension(self) -> str:
        return ".csv"

    def generate(self, results):
        # Generate CSV content
        return "name,status\n" + "\n".join(
            f"{r.journey_name},{r.success}" for r in results
        )
```

### Custom State Backend

```python
from venomqa.state.base import BaseStateManager

class RedisStateManager(BaseStateManager):
    def checkpoint(self, name: str) -> None:
        # Save state to Redis
        pass

    def rollback(self, name: str) -> None:
        # Restore state from Redis
        pass
```

### Parallel Execution

```yaml
# venomqa.yaml
parallel_paths: 4  # Run 4 paths concurrently
```

### Data-Driven Testing

```python
test_cases = [
    {"email": "valid@example.com", "expect_success": True},
    {"email": "invalid", "expect_success": False},
]

journeys = [
    Journey(
        name=f"test_{case['email']}",
        steps=[
            Step(
                name="register",
                action=lambda c, ctx: c.post("/register", json={"email": case["email"]}),
                expect_failure=not case["expect_success"],
            ),
        ],
    )
    for case in test_cases
]
```
