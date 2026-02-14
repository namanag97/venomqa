# Configuration Reference

Complete reference for all VenomQA configuration options.

## Configuration File

VenomQA reads configuration from `venomqa.yaml` in the project root.

```yaml
# venomqa.yaml - Complete configuration reference

# ====================
# API Configuration
# ====================
base_url: "http://localhost:8000"    # Base URL for all API requests
timeout: 30                          # Request timeout in seconds
retry_count: 3                       # Number of retry attempts
retry_delay: 1.0                     # Base delay between retries (seconds)

# ====================
# Database Configuration
# ====================
db_url: "postgresql://qa:secret@localhost:5432/qa_test"
db_backend: "postgresql"             # postgresql, sqlite, mysql

# ====================
# Infrastructure
# ====================
docker_compose_file: "docker-compose.qa.yml"

# ====================
# Execution
# ====================
parallel_paths: 1                    # Max concurrent branch paths
fail_fast: false                     # Stop on first failure

# ====================
# Logging
# ====================
verbose: false                       # Enable verbose/debug output
capture_logs: true                   # Capture infrastructure logs
log_lines: 50                        # Number of log lines to capture

# ====================
# Reporting
# ====================
report_dir: "reports"                # Output directory for reports
report_formats:                      # Report formats to generate
  - markdown
  - junit
```

## Configuration Options

### API Configuration

| Option | Type | Default | Environment Variable | Description |
|--------|------|---------|---------------------|-------------|
| `base_url` | string | `"http://localhost:8000"` | `VENOMQA_BASE_URL` | Base URL for API requests |
| `timeout` | integer | `30` | `VENOMQA_TIMEOUT` | Request timeout (seconds) |
| `retry_count` | integer | `3` | `VENOMQA_RETRY_COUNT` | Retry attempts on failure |
| `retry_delay` | float | `1.0` | `VENOMQA_RETRY_DELAY` | Base delay between retries |

### Database Configuration

| Option | Type | Default | Environment Variable | Description |
|--------|------|---------|---------------------|-------------|
| `db_url` | string | `null` | `VENOMQA_DB_URL` | Database connection URL |
| `db_backend` | string | `"postgresql"` | `VENOMQA_DB_BACKEND` | Database backend type |

**Supported backends:**

- `postgresql` - PostgreSQL with SAVEPOINT support (recommended)
- `sqlite` - SQLite with limited checkpoint support
- `mysql` - MySQL with SAVEPOINT support

**Connection URL formats:**

```bash
# PostgreSQL
postgresql://user:password@host:5432/database
postgresql://user:password@host:5432/database?sslmode=require

# SQLite
sqlite:///path/to/database.db
sqlite:///:memory:

# MySQL
mysql://user:password@host:3306/database
```

### Infrastructure Configuration

| Option | Type | Default | Environment Variable | Description |
|--------|------|---------|---------------------|-------------|
| `docker_compose_file` | string | `"docker-compose.qa.yml"` | `VENOMQA_DOCKER_COMPOSE_FILE` | Docker Compose file path |

### Execution Configuration

| Option | Type | Default | Environment Variable | Description |
|--------|------|---------|---------------------|-------------|
| `parallel_paths` | integer | `1` | `VENOMQA_PARALLEL_PATHS` | Max concurrent paths |
| `fail_fast` | boolean | `false` | `VENOMQA_FAIL_FAST` | Stop on first failure |

!!! warning "Parallel Execution"
    Using `parallel_paths > 1` with database state management may cause isolation issues. Use sequential execution (`parallel_paths=1`) when state isolation is critical.

### Logging Configuration

| Option | Type | Default | Environment Variable | Description |
|--------|------|---------|---------------------|-------------|
| `verbose` | boolean | `false` | `VENOMQA_VERBOSE` | Enable debug output |
| `capture_logs` | boolean | `true` | `VENOMQA_CAPTURE_LOGS` | Capture infra logs |
| `log_lines` | integer | `50` | `VENOMQA_LOG_LINES` | Log lines to capture |

### Reporting Configuration

| Option | Type | Default | Environment Variable | Description |
|--------|------|---------|---------------------|-------------|
| `report_dir` | string | `"reports"` | `VENOMQA_REPORT_DIR` | Report output directory |
| `report_formats` | list | `["markdown"]` | `VENOMQA_REPORT_FORMATS` | Formats to generate |

**Available formats:**

- `markdown` - Human-readable Markdown
- `json` - Structured JSON
- `junit` - JUnit XML for CI/CD
- `html` - Standalone HTML report
- `sarif` - SARIF for security tools

## Environment Variables

All configuration options can be overridden with environment variables prefixed with `VENOMQA_`:

```bash
# API
export VENOMQA_BASE_URL="http://api.example.com"
export VENOMQA_TIMEOUT=60
export VENOMQA_RETRY_COUNT=5

# Database
export VENOMQA_DB_URL="postgresql://user:pass@host:5432/db"
export VENOMQA_DB_BACKEND="postgresql"

# Execution
export VENOMQA_PARALLEL_PATHS=4
export VENOMQA_FAIL_FAST=true
export VENOMQA_VERBOSE=true

# Reporting
export VENOMQA_REPORT_DIR="/tmp/reports"
export VENOMQA_REPORT_FORMATS="markdown,junit"
```

**Type conversion:**

| YAML Type | Environment Variable |
|-----------|---------------------|
| string | As-is |
| integer | Parsed as int |
| float | Parsed as float |
| boolean | `true`/`false`, `1`/`0`, `yes`/`no` |
| list | Comma-separated values |

## Priority Order

Configuration is loaded in this order (later sources override earlier):

1. **Default values** (lowest priority)
2. **Configuration file** (`venomqa.yaml`)
3. **Environment variables** (`VENOMQA_*`)
4. **CLI arguments** (highest priority)

## Multiple Environments

### Using Different Config Files

```bash
# Development
venomqa run -c venomqa.dev.yaml

# Staging
venomqa run -c venomqa.staging.yaml

# Production (read-only tests)
venomqa run -c venomqa.prod.yaml
```

### Example: Development Config

```yaml
# venomqa.dev.yaml
base_url: "http://localhost:8000"
db_url: "postgresql://dev:dev@localhost:5432/dev_db"
verbose: true
timeout: 10
```

### Example: Staging Config

```yaml
# venomqa.staging.yaml
base_url: "https://api.staging.example.com"
db_url: "postgresql://qa:secret@staging-db:5432/qa_test"
verbose: false
timeout: 60
```

### Example: CI/CD Config

```yaml
# venomqa.ci.yaml
base_url: "${API_URL}"  # Replaced by environment variable
timeout: 120
fail_fast: true
report_formats:
  - junit
  - html
```

## Programmatic Configuration

### QAConfig Class

```python
from venomqa import QAConfig

config = QAConfig(
    base_url="http://localhost:8000",
    db_url="postgresql://qa:secret@localhost:5432/qa_test",
    db_backend="postgresql",
    timeout=30,
    retry_count=3,
    retry_delay=1.0,
    parallel_paths=2,
    fail_fast=False,
    verbose=True,
    capture_logs=True,
    log_lines=100,
    report_dir="reports",
    report_formats=["markdown", "junit"],
)
```

### Loading from File

```python
from venomqa.config import load_config

# Load from default location
config = load_config()

# Load from specific path
config = load_config("path/to/config.yaml")

# Access values
print(config.base_url)
print(config.db_url)
print(config.timeout)
```

### Creating Client from Config

```python
from venomqa import Client, QAConfig

config = load_config()

client = Client(
    base_url=config.base_url,
    timeout=config.timeout,
    retry_count=config.retry_count,
    retry_delay=config.retry_delay,
)
```

## Validation

VenomQA validates configuration on load:

```python
from venomqa.config import load_config, ConfigValidationError

try:
    config = load_config()
except ConfigValidationError as e:
    print(f"Invalid configuration: {e}")
```

**Validation rules:**

- `base_url` must be a valid URL
- `timeout` must be positive
- `retry_count` must be non-negative
- `db_url` must be valid connection string (if provided)
- `report_formats` must contain valid format names

## Best Practices

### 1. Use Environment Variables for Secrets

```yaml
# venomqa.yaml (safe to commit)
base_url: "http://localhost:8000"
db_backend: "postgresql"

# Set secrets via environment
# export VENOMQA_DB_URL="postgresql://..."
```

### 2. Different Timeouts for Different Environments

```yaml
# Local development - fast feedback
timeout: 10

# CI/CD - allow for network latency
timeout: 60

# Production smoke tests - be patient
timeout: 120
```

### 3. Enable Verbose Only for Debugging

```yaml
# Development
verbose: true

# CI/CD - too noisy
verbose: false
```

### 4. Use Sequential Execution with Database State

```yaml
# Safe for database checkpointing
parallel_paths: 1
```

### 5. Specify Report Formats for CI/CD

```yaml
# CI/CD
report_formats:
  - junit    # For test results
  - html     # For artifacts
```
