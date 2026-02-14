# Reference

Complete reference documentation for VenomQA.

## Quick Links

<div class="feature-grid" markdown>

<div class="feature-card" markdown>

### [API Reference](api.md)

Complete documentation for all public classes and functions.

</div>

<div class="feature-card" markdown>

### [CLI Reference](cli.md)

Command-line interface documentation.

</div>

<div class="feature-card" markdown>

### [Configuration](config.md)

All configuration options and environment variables.

</div>

<div class="feature-card" markdown>

### [Database Backends](backends.md)

Configure state management backends.

</div>

<div class="feature-card" markdown>

### [Adapters](adapters.md)

Available adapters for external services.

</div>

<div class="feature-card" markdown>

### [Reporters](reporters.md)

Report formats and custom reporters.

</div>

</div>

## API Overview

### Core Models

```python
from venomqa import (
    Journey,          # Complete user scenario
    Step,             # Single action
    Checkpoint,       # Database savepoint
    Branch,           # Multiple paths
    Path,             # Path within a branch
)
```

### Results

```python
from venomqa import (
    JourneyResult,    # Journey execution result
    StepResult,       # Step execution result
    PathResult,       # Path execution result
    Issue,            # Captured failure
    Severity,         # Issue severity level
)
```

### Execution

```python
from venomqa import (
    JourneyRunner,    # Execute journeys
    Client,           # HTTP client
    ExecutionContext, # Shared state
    QAConfig,         # Configuration
)
```

### State Management

```python
from venomqa.state import (
    PostgreSQLStateManager,  # PostgreSQL backend
    SQLiteStateManager,      # SQLite backend
    BaseStateManager,        # Base class
)
```

### Ports & Adapters

```python
from venomqa.ports import (
    CachePort,        # Cache interface
    MailPort,         # Email interface
    QueuePort,        # Queue interface
    # ... more ports
)

from venomqa.adapters import (
    RedisCacheAdapter,   # Redis cache
    MailhogAdapter,      # Mailhog email
    # ... more adapters
)
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `venomqa run [JOURNEYS]` | Run journeys |
| `venomqa list` | List available journeys |
| `venomqa report` | Generate reports |
| `venomqa --version` | Show version |
| `venomqa --help` | Show help |

## Configuration Quick Reference

```yaml
# venomqa.yaml
base_url: "http://localhost:8000"
db_url: "postgresql://user:pass@host:5432/db"
db_backend: "postgresql"
timeout: 30
retry_count: 3
parallel_paths: 1
fail_fast: false
verbose: false
report_dir: "reports"
report_formats: ["markdown", "junit"]
```

Environment variables:

```bash
VENOMQA_BASE_URL=http://api.example.com
VENOMQA_DB_URL=postgresql://...
VENOMQA_TIMEOUT=60
VENOMQA_VERBOSE=true
```
