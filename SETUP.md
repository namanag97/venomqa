# VenomQA Setup Guide

Complete guide to get VenomQA running in your environment.

---

## Table of Contents

1. [Quick Setup (5 minutes)](#quick-setup-5-minutes)
2. [Full Installation](#full-installation)
3. [Project Structure](#project-structure)
4. [Configuration](#configuration)
5. [Running Your First Test](#running-your-first-test)
6. [Integration with Existing Projects](#integration-with-existing-projects)
7. [CI/CD Setup](#cicd-setup)
8. [Troubleshooting](#troubleshooting)

---

## Quick Setup (5 minutes)

### Prerequisites

- Python 3.10+ installed
- pip or pipx for package management

### Step 1: Install VenomQA

```bash
pip install venomqa
```

### Step 2: Initialize a Project

```bash
mkdir my-api-tests && cd my-api-tests
venomqa init --with-sample
```

This creates:
```
my-api-tests/
├── venomqa.yaml       # Configuration
├── journeys/          # Test journeys
│   └── sample_journey.py
├── actions/           # Reusable actions
│   └── sample_actions.py
└── .env.example       # Environment template
```

### Step 3: Configure Your API

Edit `venomqa.yaml`:
```yaml
base_url: "http://localhost:8000"  # Your API URL
timeout: 30

# Optional: Add auth
auth:
  token_env_var: "API_TOKEN"
```

### Step 4: Run Tests

```bash
# Run smoke test first
venomqa smoke-test

# Then run all journeys
venomqa run
```

---

## Full Installation

### Base Installation

```bash
pip install venomqa
```

### With Database Support

```bash
# PostgreSQL (recommended for state management)
pip install "venomqa[postgres]"

# Or with all features
pip install "venomqa[all]"
```

### Optional Dependencies

| Extra | Install Command | Features |
|-------|-----------------|----------|
| postgres | `pip install "venomqa[postgres]"` | PostgreSQL state management |
| redis | `pip install "venomqa[redis]"` | Redis caching/queues |
| graphql | `pip install "venomqa[graphql]"` | GraphQL testing |
| docker | `pip install "venomqa[docker]"` | Docker integration |
| all | `pip install "venomqa[all]"` | Everything |

### Development Installation

For contributing or local development:

```bash
git clone https://github.com/venomqa/venomqa.git
cd venomqa
pip install -e ".[dev]"
```

---

## Project Structure

### Recommended Layout

```
my-project/
├── venomqa.yaml           # Main configuration
├── .env                   # Environment variables (gitignored)
├── .env.example          # Environment template
├── journeys/              # Test journeys
│   ├── __init__.py
│   ├── auth_journey.py
│   ├── crud_journey.py
│   └── checkout_journey.py
├── actions/               # Reusable test actions
│   ├── __init__.py
│   ├── auth_actions.py
│   └── api_actions.py
├── fixtures/              # Test data
│   ├── users.json
│   └── products.json
└── reports/               # Generated reports
    └── .gitkeep
```

### Journey File Structure

```python
# journeys/my_journey.py
from venomqa import Journey, Step, Checkpoint, Branch, Path

def action_one(client, context):
    """Each action receives client and context."""
    response = client.post("/api/items", json={"name": "Test"})
    context.set("item_id", response.json()["id"])
    return response

def action_two(client, context):
    item_id = context.get("item_id")
    return client.get(f"/api/items/{item_id}")

# Required: Export a `journey` variable
journey = Journey(
    name="my_journey",
    description="Description of what this tests",
    steps=[
        Step(name="create_item", action=action_one),
        Step(name="verify_item", action=action_two),
    ],
    tags=["smoke", "api"]
)
```

---

## Configuration

### venomqa.yaml

```yaml
# Base API URL
base_url: "${API_URL:http://localhost:8000}"

# Request timeout (seconds)
timeout: 30

# Retry configuration
retry:
  max_attempts: 3
  backoff_factor: 0.5

# Authentication
auth:
  token_env_var: "API_TOKEN"
  # OR
  # username_env_var: "API_USER"
  # password_env_var: "API_PASS"

# Default headers
headers:
  Content-Type: "application/json"
  Accept: "application/json"

# State management (optional)
state:
  backend: "postgresql"
  connection_string: "${DATABASE_URL}"

# Reporting
reports:
  format: "html"
  output_dir: "./reports"

# Environment profiles
profiles:
  dev:
    base_url: "http://localhost:8000"
  staging:
    base_url: "https://staging-api.example.com"
  prod:
    base_url: "https://api.example.com"
```

### Environment Variables

Create `.env` from `.env.example`:

```bash
# .env
API_URL=http://localhost:8000
API_TOKEN=your-api-token
DATABASE_URL=postgresql://user:pass@localhost/testdb
```

---

## Running Your First Test

### 1. Verify API is Running

```bash
venomqa smoke-test
```

Expected output:
```
VenomQA Preflight Smoke Test
==================================================
  [PASS] Health check 200 (42ms)
  [PASS] Auth check 200 (18ms)

All 2 checks passed. API is ready for testing.
```

### 2. List Available Journeys

```bash
venomqa list
```

### 3. Run a Specific Journey

```bash
venomqa run my_journey
```

### 4. Run All Journeys

```bash
venomqa run
```

### 5. Generate Reports

```bash
venomqa run --format html --output ./reports/
```

---

## Integration with Existing Projects

### Adding to an Existing Python Project

```bash
cd your-project
pip install venomqa
venomqa init --skip-checks
```

### Directory Placement Options

**Option 1: Separate test directory**
```
your-project/
├── src/
├── tests/           # Unit tests
├── qa/              # VenomQA tests
│   ├── venomqa.yaml
│   └── journeys/
└── pyproject.toml
```

**Option 2: Inside tests**
```
your-project/
├── src/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── qa/          # VenomQA tests
│       ├── venomqa.yaml
│       └── journeys/
└── pyproject.toml
```

### Running from Non-Root Directory

```bash
venomqa run --config qa/venomqa.yaml
```

---

## CI/CD Setup

### GitHub Actions

```yaml
# .github/workflows/api-tests.yml
name: API Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install venomqa[postgres]

      - name: Start API server
        run: |
          # Start your API server
          python -m uvicorn app:app --host 0.0.0.0 --port 8000 &
          sleep 5

      - name: Run smoke tests
        run: venomqa smoke-test

      - name: Run journey tests
        run: venomqa run --format junit --output test-results.xml
        env:
          API_URL: http://localhost:8000
          API_TOKEN: ${{ secrets.API_TOKEN }}

      - name: Upload results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: test-results
          path: test-results.xml
```

### GitLab CI

```yaml
# .gitlab-ci.yml
api-tests:
  image: python:3.11

  services:
    - postgres:15

  variables:
    POSTGRES_PASSWORD: postgres
    DATABASE_URL: postgresql://postgres:postgres@postgres/test

  script:
    - pip install venomqa[postgres]
    - venomqa smoke-test
    - venomqa run --format junit --output test-results.xml

  artifacts:
    reports:
      junit: test-results.xml
```

### Docker

```dockerfile
# Dockerfile.tests
FROM python:3.11-slim

WORKDIR /app

# Install VenomQA
RUN pip install venomqa[all]

# Copy test files
COPY venomqa.yaml .
COPY journeys/ journeys/
COPY actions/ actions/

# Run tests
CMD ["venomqa", "run", "--format", "json"]
```

```bash
docker build -f Dockerfile.tests -t my-api-tests .
docker run --network host my-api-tests
```

---

## Troubleshooting

### Common Issues

#### "Connection refused" error

```
[E001] Connection refused: http://localhost:8000
```

**Solutions:**
1. Check if your API server is running
2. Verify the URL in `venomqa.yaml`
3. Check firewall/network settings

```bash
# Test connectivity
curl http://localhost:8000/health
```

#### "Module not found" when importing actions

```
ModuleNotFoundError: No module named 'actions'
```

**Solution:** Ensure your project root has `__init__.py` files:
```bash
touch actions/__init__.py
touch journeys/__init__.py
```

#### "Journey not found" error

```
Journey 'my_journey' not found
```

**Solutions:**
1. Check that the file exports a `journey` variable
2. Verify file is in the `journeys/` directory
3. Run `venomqa list` to see discovered journeys

#### Database connection issues

```
psycopg.OperationalError: connection refused
```

**Solutions:**
1. Verify PostgreSQL is running
2. Check `DATABASE_URL` environment variable
3. Ensure database exists

```bash
# Test database connection
psql $DATABASE_URL -c "SELECT 1"
```

#### Timeout errors

```
Request timed out after 30s
```

**Solutions:**
1. Increase timeout in `venomqa.yaml`
2. Check API server performance
3. Add retry configuration

```yaml
timeout: 60
retry:
  max_attempts: 5
  backoff_factor: 1.0
```

### Getting Help

1. **Check the docs:** https://venomqa.dev/docs
2. **Run diagnostics:** `venomqa doctor`
3. **Enable verbose mode:** `venomqa run --verbose`
4. **Check configuration:** `venomqa validate`

### Debug Mode

```bash
# Maximum verbosity
venomqa run --verbose --verbose

# Or set environment variable
VENOMQA_DEBUG=1 venomqa run
```

---

## Next Steps

1. **Read the concepts guide:** [docs/concepts/](docs/concepts/)
2. **Explore examples:** [examples/](examples/)
3. **Learn about state graphs:** [docs/concepts/state.md](docs/concepts/state.md)
4. **Set up reporting:** [docs/reference/reporters.md](docs/reference/reporters.md)

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `venomqa init` | Initialize new project |
| `venomqa run` | Run all journeys |
| `venomqa run <name>` | Run specific journey |
| `venomqa list` | List all journeys |
| `venomqa validate` | Check configuration |
| `venomqa smoke-test` | Run preflight checks |
| `venomqa doctor` | System diagnostics |
| `venomqa demo` | Run built-in demo |

| Flag | Description |
|------|-------------|
| `--verbose, -v` | Verbose output |
| `--config, -c` | Config file path |
| `--format` | Output format (html/json/junit) |
| `--output` | Output file/directory |
| `--fail-fast` | Stop on first failure |
| `--profile` | Use config profile (dev/staging/prod) |
