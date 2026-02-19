# Configuration

Configure VenomQA for your API and environment.

## CLI Configuration

### Authentication

```bash
# API Key header
venomqa --api-key your-api-key-here

# Bearer token
venomqa --auth-token your-bearer-token

# Basic auth
venomqa --basic-auth user:password
```

Or via environment variables:

```bash
export VENOMQA_API_KEY=your-key
export VENOMQA_AUTH_TOKEN=your-token
```

### Skip Preflight Checks

```bash
venomqa --skip-preflight
```

Skips Docker and authentication validation. Useful for CI environments.

## Programmatic Configuration

### HttpClient Options

```python
from venomqa.adapters.http import HttpClient

api = HttpClient(
    base_url="http://localhost:8000",
    headers={"X-Custom": "value"},
    timeout=30.0,
    verify_ssl=True,
    follow_redirects=True,
)
```

### World Configuration

```python
from venomqa import World
from venomqa.adapters.postgres import PostgresAdapter

# Option 1: Context-based state (simple)
world = World(
    api=api,
    state_from_context=["order_id", "user_id"],
)

# Option 2: System adapters (advanced)
world = World(
    api=api,
    systems={
        "db": PostgresAdapter("postgresql://user:pass@localhost/db"),
    },
)
```

### Agent Configuration

```python
from venomqa import Agent, BFS

agent = Agent(
    world=world,
    actions=[...],
    invariants=[...],
    strategy=BFS(),
    max_steps=100,           # Maximum actions per exploration
    max_depth=20,            # Maximum depth in state tree
    fail_fast=True,          # Stop on first violation
    seed=42,                 # Reproducible random choices
)
```

## Strategy Configuration

### BFS (Breadth-First Search)

```python
from venomqa import BFS

strategy = BFS()
```

Explores all sequences level by level. Best for finding shortest paths to bugs.

### DFS (Depth-First Search)

```python
from venomqa import DFS

strategy = DFS(max_depth=50)
```

Goes deep before backtracking. Good for finding deep state transitions.

### Coverage-Guided

```python
from venomqa import CoverageGuided

strategy = CoverageGuided(
    target_coverage=0.95,
    seed_corpus=[],
)
```

Prioritizes unexplored code paths. Requires coverage instrumentation.

## Database Configuration

### PostgreSQL

```python
from venomqa.adapters.postgres import PostgresAdapter

db = PostgresAdapter(
    connection_string="postgresql://user:pass@localhost:5432/testdb",
    schema="public",
)

world = World(api=api, systems={"db": db})
```

### MySQL

```python
from venomqa.adapters.mysql import MySQLAdapter

db = MySQLAdapter(
    host="localhost",
    port=3306,
    user="root",
    password="secret",
    database="testdb",
)
```

### SQLite

```python
from venomqa.adapters.sqlite import SQLiteAdapter

db = SQLiteAdapter(
    path="/path/to/database.db",
    copy_on_checkpoint=True,
)
```

## Reporter Configuration

### Console Reporter

```python
from venomqa.reporters import ConsoleReporter

reporter = ConsoleReporter(
    verbose=True,
    color=True,
    show_timestamps=True,
)
```

### HTML Reporter

```python
from venomqa.reporters import HTMLTraceReporter

reporter = HTMLTraceReporter(
    output_path="reports/trace.html",
    include_graph=True,
    theme="dark",
)
```

### JSON Reporter

```python
from venomqa.reporters import JSONReporter

reporter = JSONReporter(
    output_path="reports/results.json",
    pretty_print=True,
)
```

## Environment-Specific Config

### Development

```python
# qa/conftest.py
import os
from venomqa import World
from venomqa.adapters.http import HttpClient

def get_world():
    api = HttpClient(
        base_url=os.getenv("API_URL", "http://localhost:8000"),
        timeout=60.0,
    )
    return World(api=api, state_from_context=["resource_id"])
```

### CI/CD

```python
# qa/conftest_ci.py
import os
from venomqa import World
from venomqa.adapters.http import HttpClient

def get_world():
    api = HttpClient(
        base_url=os.environ["CI_API_URL"],
        headers={"Authorization": f"Bearer {os.environ['CI_API_TOKEN']}"},
        timeout=30.0,
        verify_ssl=False,  # Internal CI
    )
    return World(api=api, state_from_context=["resource_id"])
```

## Configuration File (Optional)

Create `venomqa.yaml` in your project root:

```yaml
api:
  base_url: http://localhost:8000
  timeout: 30.0
  headers:
    X-API-Version: "1.0"

database:
  type: postgres
  url: postgresql://localhost/testdb

exploration:
  strategy: bfs
  max_steps: 100
  max_depth: 20
  fail_fast: false

reporting:
  console:
    verbose: true
  html:
    output: reports/trace.html
```

Load configuration:

```bash
venomqa run --config venomqa.yaml
```

## Next Steps

- [Quickstart](quickstart.md) - Try it out
- [Concepts](../concepts/index.md) - Understand the model
- [API Reference](../reference/api.md) - Full API docs
