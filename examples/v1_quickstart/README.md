# VenomQA v1 Examples

These examples demonstrate the new v1 API.

## Quick Start

```python
from venomqa.v1 import Journey, Step, Checkpoint, explore

journey = Journey(
    name="simple_test",
    steps=[
        Step("login", lambda api: api.post("/login", json={"user": "test"})),
        Checkpoint("logged_in"),
        Step("action", lambda api: api.get("/data")),
    ],
)

result = explore("http://localhost:8000", journey)
print(f"Success: {result.success}")
```

## Examples

1. **simple_test.py** - Basic journey with branches
2. **with_mock_systems.py** - Using mock adapters for isolated testing

## Running

```bash
# Simple test (requires running API)
python -m examples.v1_quickstart.simple_test

# Mock systems (no external dependencies)
python -m examples.v1_quickstart.with_mock_systems
```

## Key Differences from Legacy API

| Legacy | v1 |
|--------|-----|
| `JourneyRunner` | `explore()` or `Agent` |
| `StateManager` | `Rollbackable` protocol |
| Complex setup | Simple function calls |
| 300+ exports | ~20 exports |
