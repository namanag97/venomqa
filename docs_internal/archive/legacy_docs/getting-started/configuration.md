# Configuration

VenomQA can be configured through a YAML file, environment variables, or programmatically.

## Configuration File

Create a `venomqa.yaml` file in your project root:

```yaml
# API Configuration
base_url: "http://localhost:8000"

# Database Configuration (for state management)
db_url: "postgresql://qa:secret@localhost:5432/qa_test"
db_backend: "postgresql"

# Infrastructure
docker_compose_file: "docker-compose.qa.yml"

# Request Settings
timeout: 30
retry_count: 3
retry_delay: 1.0

# Execution
parallel_paths: 1
fail_fast: false

# Logging
verbose: false
capture_logs: true
log_lines: 50

# Reporting
report_dir: "reports"
report_formats:
  - markdown
  - junit
```

## Configuration Options

### API Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `base_url` | string | `"http://localhost:8000"` | Base URL for all API requests |
| `timeout` | integer | `30` | Request timeout in seconds |
| `retry_count` | integer | `3` | Number of retry attempts on failure |
| `retry_delay` | float | `1.0` | Base delay between retries in seconds |

### Database Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `db_url` | string | `null` | Database connection URL |
| `db_backend` | string | `"postgresql"` | Database backend type |

Supported backends:

- `postgresql` - PostgreSQL with SAVEPOINT support
- `sqlite` - SQLite (limited checkpoint support)
- `mysql` - MySQL (community contributed)

### Infrastructure Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `docker_compose_file` | string | `"docker-compose.qa.yml"` | Path to Docker Compose file |

### Execution Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `parallel_paths` | integer | `1` | Max concurrent branch paths |
| `fail_fast` | boolean | `false` | Stop on first failure |

!!! warning "Parallel Execution with State"
    When using `parallel_paths > 1` with database state management, ensure your paths are isolated or use separate database connections.

### Logging Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `verbose` | boolean | `false` | Enable verbose/debug output |
| `capture_logs` | boolean | `true` | Capture infrastructure logs |
| `log_lines` | integer | `50` | Number of log lines to capture |

### Reporting Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `report_dir` | string | `"reports"` | Output directory for reports |
| `report_formats` | list | `["markdown"]` | Report formats to generate |

Available formats: `markdown`, `json`, `junit`, `html`, `sarif`

## Environment Variables

All configuration options can be overridden with environment variables prefixed with `VENOMQA_`:

```bash
# API Configuration
export VENOMQA_BASE_URL="http://api.staging.example.com"
export VENOMQA_TIMEOUT=60

# Database
export VENOMQA_DB_URL="postgresql://user:pass@host:5432/db"
export VENOMQA_DB_BACKEND="postgresql"

# Execution
export VENOMQA_VERBOSE=true
export VENOMQA_FAIL_FAST=true
export VENOMQA_PARALLEL_PATHS=4
```

## Configuration Priority

Configuration is loaded in this order (later sources override earlier):

1. **Default values** (lowest priority)
2. **Configuration file** (`venomqa.yaml`)
3. **Environment variables** (`VENOMQA_*`)
4. **CLI arguments** (highest priority)

## Multiple Environments

Use different configuration files for different environments:

```bash
# Development
venomqa run -c venomqa.dev.yaml

# Staging
venomqa run -c venomqa.staging.yaml

# Production (read-only tests)
venomqa run -c venomqa.prod.yaml
```

Or use environment variables in CI/CD:

```yaml
# .github/workflows/test.yml
jobs:
  test:
    runs-on: ubuntu-latest
    env:
      VENOMQA_BASE_URL: ${{ secrets.API_URL }}
      VENOMQA_DB_URL: ${{ secrets.DATABASE_URL }}
    steps:
      - uses: actions/checkout@v4
      - run: pip install venomqa
      - run: venomqa run
```

## Programmatic Configuration

Configure VenomQA in Python:

```python
from venomqa import QAConfig, Client, JourneyRunner

# Create configuration
config = QAConfig(
    base_url="http://localhost:8000",
    db_url="postgresql://qa:secret@localhost:5432/qa_test",
    db_backend="postgresql",
    timeout=30,
    retry_count=3,
    parallel_paths=2,
    capture_logs=True,
)

# Create client with config
client = Client(
    base_url=config.base_url,
    timeout=config.timeout,
    retry_count=config.retry_count,
)

# Create runner
runner = JourneyRunner(
    client=client,
    parallel_paths=config.parallel_paths,
    fail_fast=config.fail_fast,
)

# Run journey
result = runner.run(journey)
```

### Loading Configuration from File

```python
from venomqa.config import load_config

# Load from default location (venomqa.yaml)
config = load_config()

# Load from specific path
config = load_config("path/to/config.yaml")

# Access values
print(config.base_url)
print(config.db_url)
```

## Docker Compose Integration

VenomQA can manage test infrastructure via Docker Compose.

### Example docker-compose.qa.yml

```yaml
version: "3.8"

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://qa:secret@db:5432/qa_test
    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:15
    environment:
      POSTGRES_DB: qa_test
      POSTGRES_USER: qa
      POSTGRES_PASSWORD: secret
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U qa -d qa_test"]
      interval: 5s
      timeout: 5s
      retries: 5
    # Use tmpfs for faster tests
    tmpfs:
      - /var/lib/postgresql/data

  redis:
    image: redis:7
    ports:
      - "6379:6379"

  mailhog:
    image: mailhog/mailhog
    ports:
      - "1025:1025"
      - "8025:8025"
```

### Running with Infrastructure

```bash
# Run with Docker management (starts, runs, stops)
venomqa run

# Skip Docker management (services already running)
venomqa run --no-infra
```

## Best Practices

### 1. Use Environment-Specific Configs

```
project/
├── venomqa.yaml              # Default/development
├── venomqa.staging.yaml      # Staging environment
├── venomqa.prod.yaml         # Production (read-only)
└── journeys/
```

### 2. Never Commit Secrets

Use environment variables for sensitive data:

```yaml
# venomqa.yaml (safe to commit)
base_url: "http://localhost:8000"

# In CI/CD or shell (secrets)
export VENOMQA_DB_URL="postgresql://..."
```

### 3. Use Sensible Timeouts

```yaml
# Short for local development
timeout: 10

# Longer for CI/CD (network latency)
timeout: 60
```

### 4. Enable Verbose Mode for Debugging

```bash
venomqa run my_journey -v
```

Or in config:

```yaml
verbose: true  # Temporary for debugging
```

## Configuration Schema Reference

For IDE autocompletion, here's the full schema:

```yaml
# venomqa.yaml
---
# Required
base_url: string  # e.g., "http://localhost:8000"

# Optional - Database
db_url: string | null  # e.g., "postgresql://user:pass@host:5432/db"
db_backend: string  # default: "postgresql"

# Optional - Infrastructure
docker_compose_file: string  # default: "docker-compose.qa.yml"

# Optional - Request
timeout: integer  # default: 30 (seconds)
retry_count: integer  # default: 3
retry_delay: float  # default: 1.0 (seconds)

# Optional - Execution
parallel_paths: integer  # default: 1
fail_fast: boolean  # default: false

# Optional - Logging
verbose: boolean  # default: false
capture_logs: boolean  # default: true
log_lines: integer  # default: 50

# Optional - Reporting
report_dir: string  # default: "reports"
report_formats: list[string]  # default: ["markdown"]
```

## Next Steps

- [Quickstart](quickstart.md) - Create your first journey
- [Core Concepts](../concepts/index.md) - Understand Journeys and Checkpoints
- [CLI Reference](../reference/cli.md) - Command-line options
