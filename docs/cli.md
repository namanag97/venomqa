# CLI Documentation

VenomQA provides a command-line interface for running journeys, listing available tests, and generating reports.

## Installation

```bash
pip install venomqa
```

The CLI is installed as the `venomqa` command.

## Global Options

| Option | Short | Description |
|--------|-------|-------------|
| `--verbose` | `-v` | Enable verbose/debug output |
| `--config` | `-c` | Path to configuration file |
| `--help` | `-h` | Show help message |

## Commands

### `venomqa run`

Run one or more journeys.

```bash
# Run all discovered journeys
venomqa run

# Run specific journeys
venomqa run checkout_flow payment_flow

# Run with options
venomqa run checkout_flow --fail-fast --format json

# Skip infrastructure setup
venomqa run --no-infra
```

#### Arguments

| Argument | Description |
|----------|-------------|
| `JOURNEY_NAMES` | One or more journey names to run (optional) |

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--no-infra` | flag | - | Skip Docker setup/teardown |
| `--format`, `-f` | choice | `text` | Output format (`text` or `json`) |
| `--fail-fast` | flag | - | Stop on first failure |
| `--verbose`, `-v` | flag | - | Enable debug logging |
| `--config`, `-c` | path | - | Path to config file |

#### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All journeys passed |
| `1` | One or more journeys failed |

#### Examples

**Run all journeys:**
```bash
venomqa run
```

**Run specific journeys:**
```bash
venomqa run user_registration checkout_flow
```

**Run with JSON output:**
```bash
venomqa run --format json
```

**Run with fail-fast mode:**
```bash
venomqa run --fail-fast
```

**Run without infrastructure management:**
```bash
# Use when services are already running
venomqa run --no-infra
```

**Run with verbose logging:**
```bash
venomqa run -v
```

**Run with custom config:**
```bash
venomqa run -c /path/to/venomqa.yaml
```

**Combine options:**
```bash
venomqa run checkout_flow --fail-fast --format json --verbose
```

---

### `venomqa list`

List all discovered journeys.

```bash
# List journeys in text format
venomqa list

# List in JSON format
venomqa list --format json
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--format`, `-f` | choice | `text` | Output format (`text` or `json`) |

#### Examples

**Text output:**
```bash
$ venomqa list
Found 3 journey(s):

  • checkout_flow (journeys/checkout_flow.py)
  • user_registration (journeys/user_registration.py)
  • admin_flow (journeys/admin_flow.py)
```

**JSON output:**
```bash
$ venomqa list --format json
{
  "checkout_flow": {
    "name": "checkout_flow",
    "path": "journeys/checkout_flow.py"
  },
  "user_registration": {
    "name": "user_registration",
    "path": "journeys/user_registration.py"
  },
  "admin_flow": {
    "name": "admin_flow",
    "path": "journeys/admin_flow.py"
  }
}
```

---

### `venomqa report`

Generate a report from the last run.

```bash
# Generate markdown report (default)
venomqa report

# Generate specific format
venomqa report --format junit --output reports/junit.xml

# Generate HTML report
venomqa report --format html --output reports/test.html
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--format`, `-f` | choice | `markdown` | Report format (`markdown`, `json`, `junit`, `html`) |
| `--output`, `-o` | path | `reports/report.{ext}` | Output file path |

#### Supported Formats

| Format | Extension | Description |
|--------|-----------|-------------|
| `markdown` | `.md` | Human-readable Markdown report |
| `json` | `.json` | Structured JSON for programmatic use |
| `junit` | `.xml` | JUnit XML for CI/CD integration |
| `html` | `.html` | Standalone HTML report |

#### Examples

**Generate markdown report:**
```bash
venomqa report --format markdown --output reports/test.md
```

**Generate JUnit XML for CI:**
```bash
venomqa report --format junit --output reports/junit.xml
```

**Generate JSON for processing:**
```bash
venomqa report --format json --output reports/results.json
```

**Generate HTML for sharing:**
```bash
venomqa report --format html --output reports/test.html
```

---

## Configuration File

Create a `venomqa.yaml` file in your project root:

```yaml
# API Configuration
base_url: "http://localhost:8000"

# Database Configuration
db_url: "postgresql://qa:secret@localhost:5432/qa_test"
db_backend: "postgresql"

# Infrastructure
docker_compose_file: "docker-compose.qa.yml"

# Request Settings
timeout: 30
retry_count: 3
retry_delay: 1.0

# Logging
capture_logs: true
log_lines: 50
verbose: false

# Execution
parallel_paths: 1
fail_fast: false

# Reporting
report_dir: "reports"
report_formats:
  - markdown
  - junit
```

## Environment Variables

All configuration options can be overridden with environment variables prefixed with `VENOMQA_`:

```bash
# API Configuration
export VENOMQA_BASE_URL="http://api.example.com"

# Database
export VENOMQA_DB_URL="postgresql://user:pass@host/db"

# Execution
export VENOMQA_TIMEOUT=60
export VENOMQA_VERBOSE=true
export VENOMQA_FAIL_FAST=true
```

## CI/CD Integration

### GitHub Actions

```yaml
name: QA Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: qa_test
          POSTGRES_USER: qa
          POSTGRES_PASSWORD: secret
        ports:
          - 5432:5432
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
          pip install -e ".[dev]"
      
      - name: Run QA tests
        env:
          VENOMQA_BASE_URL: http://localhost:8000
          VENOMQA_DB_URL: postgresql://qa:secret@localhost:5432/qa_test
        run: |
          venomqa run --format json
      
      - name: Generate JUnit report
        if: always()
        run: |
          venomqa report --format junit --output reports/junit.xml
      
      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: qa-reports
          path: reports/
      
      - name: Publish test results
        if: always()
        uses: dorny/test-reporter@v1
        with:
          name: QA Tests
          path: reports/junit.xml
          reporter: java-junit
```

### GitLab CI

```yaml
qa-tests:
  stage: test
  image: python:3.11
  
  services:
    - name: postgres:15
      alias: postgres
  
  variables:
    POSTGRES_DB: qa_test
    POSTGRES_USER: qa
    POSTGRES_PASSWORD: secret
    VENOMQA_BASE_URL: http://localhost:8000
    VENOMQA_DB_URL: postgresql://qa:secret@postgres:5432/qa_test
  
  before_script:
    - pip install -e ".[dev]"
  
  script:
    - venomqa run --format json
    - venomqa report --format junit --output reports/junit.xml
  
  artifacts:
    when: always
    paths:
      - reports/
    reports:
      junit: reports/junit.xml
```

### CircleCI

```yaml
version: 2.1

jobs:
  qa-tests:
    docker:
      - image: python:3.11
      - image: postgres:15
        environment:
          POSTGRES_DB: qa_test
          POSTGRES_USER: qa
          POSTGRES_PASSWORD: secret
    
    environment:
      VENOMQA_BASE_URL: http://localhost:8000
      VENOMQA_DB_URL: postgresql://qa:secret@localhost:5432/qa_test
    
    steps:
      - checkout
      
      - run:
          name: Install dependencies
          command: pip install -e ".[dev]"
      
      - run:
          name: Run QA tests
          command: venomqa run
      
      - run:
          name: Generate reports
          when: always
          command: |
            venomqa report --format junit --output reports/junit.xml
            venomqa report --format html --output reports/test.html
      
      - store_test_results:
          path: reports
      
      - store_artifacts:
          path: reports

workflows:
  version: 2
  test:
    jobs:
      - qa-tests
```

### Jenkins Pipeline

```groovy
pipeline {
    agent any
    
    environment {
        VENOMQA_BASE_URL = 'http://localhost:8000'
        VENOMQA_DB_URL = 'postgresql://qa:secret@localhost:5432/qa_test'
    }
    
    stages {
        stage('Setup') {
            steps {
                sh 'pip install -e ".[dev]"'
            }
        }
        
        stage('Run Tests') {
            steps {
                sh 'venomqa run --format json'
            }
        }
        
        stage('Generate Reports') {
            steps {
                sh '''
                    venomqa report --format junit --output reports/junit.xml
                    venomqa report --format html --output reports/test.html
                '''
            }
        }
    }
    
    post {
        always {
            junit 'reports/junit.xml'
            publishHTML(target: [
                allowMissing: false,
                alwaysLinkToLastBuild: true,
                keepAll: true,
                reportDir: 'reports',
                reportFiles: 'test.html',
                reportName: 'QA Report'
            ])
        }
    }
}
```

## Exit Codes

| Code | Description |
|------|-------------|
| `0` | Success - all tests passed |
| `1` | Failure - one or more tests failed |
| `2` | Error - configuration or runtime error |

## Debugging

### Verbose Mode

Enable detailed logging to debug issues:

```bash
venomqa run -v
```

### Check Configuration

Verify configuration is loaded correctly:

```bash
# Run with debug logging to see config values
venomqa run -v 2>&1 | grep -i config
```

### Common Issues

**Journey not found:**
```bash
$ venomqa run missing_journey
Journey not found: missing_journey
```
Ensure the journey file exists in `journeys/` directory and exports a `journey` variable.

**Connection refused:**
```bash
# Check if services are running
docker compose -f docker-compose.qa.yml ps

# Start services
docker compose -f docker-compose.qa.yml up -d
```

**Database connection failed:**
```bash
# Verify database URL
echo $VENOMQA_DB_URL

# Test connection
psql "$VENOMQA_DB_URL" -c "SELECT 1"
```
