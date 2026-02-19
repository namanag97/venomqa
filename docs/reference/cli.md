# CLI Reference

Command-line interface for VenomQA.

## Installation

```bash
pip install venomqa
venomqa --version
```

## Global Options

```bash
venomqa [OPTIONS] COMMAND [ARGS]...

Options:
  --version              Show version and exit
  --help                 Show help and exit
  --api-key TEXT         X-API-Key header for authentication
  --auth-token TEXT      Bearer token for authentication
  --basic-auth TEXT      Basic auth as user:password
  --skip-preflight       Skip Docker and auth validation
  --config PATH          Path to venomqa.yaml config file
  --verbose, -v          Enable verbose output
  --quiet, -q            Suppress non-error output
```

## Commands

### venomqa demo

Run the built-in demo to see VenomQA find a bug.

```bash
venomqa demo [OPTIONS]

Options:
  --bug-type [double_refund|stale_cache|idempotency]
                        Which bug to demonstrate
  --steps INTEGER       Maximum steps to explore (default: 50)
```

**Example:**

```bash
$ venomqa demo

  Unit Tests:  3/3 PASS ✓

  VenomQA Exploration ────────────────────────
  States visited:     8
  Transitions:        20
  Invariants checked: 40

  ╭─ CRITICAL VIOLATION ──────────────────────╮
  │ Sequence: create_order → refund → refund  │
  │ Bug:      refunded $200 on a $100 order   │
  ╰───────────────────────────────────────────╯

  Summary: 3 tests passed. 1 sequence bug found.
```

---

### venomqa doctor

Diagnose your environment and configuration.

```bash
venomqa doctor [OPTIONS]

Options:
  --fix                  Attempt to fix issues automatically
```

**Example:**

```bash
$ venomqa doctor
✓ Python 3.11.5
✓ httpx 0.25.2
✓ pydantic 2.5.0
✓ psycopg[binary] installed
✓ All checks passed
```

---

### venomqa run

Run exploration on a test suite.

```bash
venomqa run [OPTIONS] PATH

Arguments:
  PATH                   Path to qa/ directory or test file

Options:
  --strategy [bfs|dfs|coverage]
                         Exploration strategy (default: bfs)
  --max-steps INTEGER    Maximum actions to execute (default: 1000)
  --max-depth INTEGER    Maximum path depth (default: infinite)
  --fail-fast            Stop on first CRITICAL violation
  --continue-on-error    Continue even on CRITICAL violations
  --report [console|html|json|junit]
                         Report format(s), can specify multiple
  --output PATH          Output directory for reports
  --seed INTEGER         Random seed for reproducibility
```

**Examples:**

```bash
# Basic run
venomqa run qa/

# With HTML report
venomqa run qa/ --report html --output reports/

# Multiple report formats
venomqa run qa/ --report html --report json --report junit

# With limits
venomqa run qa/ --max-steps 500 --max-depth 20

# Reproducible run
venomqa run qa/ --seed 42
```

---

### venomqa init

Initialize a new VenomQA project.

```bash
venomqa init [OPTIONS] [PATH]

Arguments:
  PATH                   Where to create the project (default: current dir)

Options:
  --name TEXT            Project name
  --api-url TEXT         Base URL for API
  --with-sample          Include sample actions and invariants
  --database [postgres|mysql|sqlite|none]
                         Database adapter to configure
```

**Example:**

```bash
$ venomqa init my-project --with-sample
Creating project in my-project/
  ├── qa/
  │   ├── actions/
  │   │   └── sample.py
  │   ├── invariants.py
  │   └── test_sample.py
  ├── venomqa.yaml
  └── requirements.txt

Run with: cd my-project && venomqa run qa/
```

---

### venomqa scaffold

Generate code from OpenAPI specifications.

```bash
venomqa scaffold [OPTIONS] COMMAND

Commands:
  openapi               Generate actions from OpenAPI spec
```

#### venomqa scaffold openapi

```bash
venomqa scaffold openapi [OPTIONS] SPEC

Arguments:
  SPEC                   Path to OpenAPI spec (JSON or YAML)

Options:
  --output PATH          Output directory (default: qa/actions/)
  --prefix TEXT          Prefix for action names
  --include PATTERN      Only include paths matching pattern
  --exclude PATTERN      Exclude paths matching pattern
  --base-url TEXT        Override base URL from spec
```

**Example:**

```bash
$ venomqa scaffold openapi api-spec.yaml --output qa/actions/
Generated 24 actions:
  qa/actions/api_keys.py
  qa/actions/bookings.py
  qa/actions/users.py
```

---

### venomqa explore

Interactive exploration mode.

```bash
venomqa explore [OPTIONS] PATH

Options:
  --interactive          Enable interactive mode
  --record PATH          Record session to file
  --replay PATH          Replay recorded session
```

---

### venomqa report

Generate reports from previous runs.

```bash
venomqa report [OPTIONS] RESULTS

Arguments:
  RESULTS                Path to results.json from previous run

Options:
  --format [html|json|junit|console]
                         Output format
  --output PATH          Output directory
```

---

## Environment Variables

| Variable | Equivalent Option |
|----------|------------------|
| `VENOMQA_API_KEY` | `--api-key` |
| `VENOMQA_AUTH_TOKEN` | `--auth-token` |
| `VENOMQA_BASE_URL` | (used in config) |
| `VENOMQA_DATABASE_URL` | (used in config) |
| `VENOMQA_CONFIG` | `--config` |

## Configuration File

Create `venomqa.yaml` for persistent settings:

```yaml
api:
  base_url: http://localhost:8000
  timeout: 30.0
  headers:
    X-API-Version: "1.0"

exploration:
  strategy: bfs
  max_steps: 500
  max_depth: 25
  fail_fast: true

reporting:
  formats:
    - html
    - junit
  output_dir: reports/

database:
  type: postgres
  url: ${VENOMQA_DATABASE_URL}
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success, no violations |
| 1 | Violations found |
| 2 | Configuration error |
| 3 | Runtime error |
| 4 | Authentication error |

## Examples

### Basic Workflow

```bash
# 1. Initialize project
venomqa init my-api-tests --with-sample
cd my-api-tests

# 2. Check environment
venomqa doctor

# 3. Generate from OpenAPI
venomqa scaffold openapi ../api-spec.yaml

# 4. Run tests
venomqa run qa/ --report html

# 5. View report
open reports/trace.html
```

### CI Pipeline

```bash
# Install
pip install venomqa

# Run with limits for fast feedback
venomqa run qa/ \
  --max-steps 200 \
  --report junit \
  --output test-results/

# Exit code indicates pass/fail
```

### Debugging

```bash
# Verbose output
venomqa run qa/ -v

# Reproduce specific issue
venomqa run qa/ --seed 12345

# Interactive exploration
venomqa explore qa/ --interactive
```

## Next Steps

- [API Reference](api.md) - Python API
- [Configuration](config.md) - Configuration options
- [CI/CD Integration](../tutorials/ci-cd.md) - Automate in pipelines
