# VenomQA Examples

This directory contains working examples demonstrating VenomQA's capabilities.

## Quick Start

### Fastest Way to See VenomQA

```bash
# No setup required - uses mock servers
venomqa demo
```

This runs a self-contained demo that finds a real bug in 30 seconds.

### Run a Working Example

```bash
# Self-contained, no external dependencies
python3 examples/v1_quickstart/with_mock_systems.py

# Or run the full github_stripe_qa suite
pytest examples/github_stripe_qa/
```

## Examples Overview

| Example | Works Out of Box | Description |
|---------|-----------------|-------------|
| **v1_quickstart/** | YES | Basic VenomQA patterns with mock systems |
| **github_stripe_qa/** | YES | Full example with 2 planted bugs |
| **v1/** | YES | Tests against real GitHub API |
| **subscriptions_qa/** | Needs Docker | PostgreSQL + Redis, 3 planted bugs |
| **full_featured_app/** | Needs Docker | Enterprise patterns, all adapters |

## v1_quickstart/ (Start Here)

Two files demonstrating core concepts:

```bash
# Works immediately - uses mock adapters
python3 examples/v1_quickstart/with_mock_systems.py

# Requires running API server
python3 examples/v1_quickstart/simple_test.py
```

**`with_mock_systems.py`** shows:
- Actions with `(api, context)` signature
- Invariants that check state
- MockMail, MockStorage, MockTime adapters
- BFS exploration

## github_stripe_qa/ (Best Full Example)

Complete QA setup with planted bugs that VenomQA finds:

```bash
# Run all 15 tests
pytest examples/github_stripe_qa/

# Or run the main exploration script
python3 examples/github_stripe_qa/main.py
```

**Planted Bugs:**
1. GitHub open-issues endpoint leaks closed issues
2. Stripe allows over-refunds (refund > original amount)

**Demonstrates:**
- MockHTTPServer pattern for in-process mock APIs
- Real checkpoint/rollback for state exploration
- Focused sub-explorations for efficiency
- Bug detection through BFS

## v1/ (Real API Testing)

Tests against the real GitHub public API:

```bash
python3 examples/v1/test_github_api.py
```

**Demonstrates:**
- Custom Rollbackable adapter for read-only APIs
- Data structure validation invariants
- Mermaid diagram generation

## subscriptions_qa/ (Requires Docker)

SaaS subscription management with 3 planted bugs:

```bash
# Start services
docker compose -f examples/subscriptions_qa/docker-compose.yml up -d

# Run tests
pytest examples/subscriptions_qa/
```

**Requires:** PostgreSQL, Redis

**Demonstrates:**
- PostgresAdapter for database rollback
- RedisAdapter for cache rollback
- MockMail, MockQueue, MockStorage, MockTime
- All adapter types working together

## full_featured_app/ (Requires Docker)

Enterprise patterns with all VenomQA features:

```bash
# Start services
docker compose -f examples/full_featured_app/docker/docker-compose.yml up -d

# Run tests
python3 examples/full_featured_app/qa/test_full_app_v1.py
```

**Demonstrates:**
- Full stack testing (API + PostgreSQL)
- Multiple system adapters
- Production-like patterns

## Writing Your Own Tests

### Basic Pattern

```python
from venomqa import Action, Invariant, Agent, World, BFS, Severity
from venomqa.adapters import HttpClient

# 1. Define actions
def create_user(api, context):
    return api.post("/users", json={"name": "Test"})

def get_user(api, context):
    user_id = context.get("user_id")
    return api.get(f"/users/{user_id}")

# 2. Define invariants
def no_500_errors(world):
    return True  # Check something meaningful

# 3. Set up world and agent
api = HttpClient("http://localhost:8000")
world = World(api=api, state_from_context=["user_id"])

agent = Agent(
    world=world,
    actions=[
        Action(name="create_user", execute=create_user),
        Action(name="get_user", execute=get_user),
    ],
    invariants=[
        Invariant(name="no_500", check=no_500_errors, severity=Severity.CRITICAL)
    ],
    strategy=BFS(),
    max_steps=50,
)

result = agent.explore()
print(f"Violations: {len(result.violations)}")
```

### With Database Rollback

```python
from venomqa.adapters.postgres import PostgresAdapter

db = PostgresAdapter("postgresql://user:pass@localhost/dbname")
world = World(api=api, systems={"db": db})
```

## Troubleshooting

### Import Errors

```bash
pip install -e .
python3 -c "import venomqa; print(venomqa.__version__)"
```

### Docker Services

```bash
docker compose logs
docker compose down -v && docker compose up -d
```

### Tests Timing Out

```bash
curl http://localhost:PORT/health  # Check API is running
```

## Next Steps

1. Run `venomqa demo` to see bug detection in action
2. Study `github_stripe_qa/` for the best complete example
3. Read `docs_v1/guides/quickstart.md` for detailed guides
4. Check `src/venomqa/v1/` for the framework implementation
