# CLI Reference

VenomQA provides a command-line interface for running explorations, validating journeys, and managing projects.

## Installation

```bash
pip install venomqa
```

The `venomqa` command becomes available after installation.

## Commands

### venomqa (no arguments)

Running `venomqa` with no arguments prints the help message listing all available commands.

```bash
venomqa
venomqa --help
```

---

### demo

See VenomQA find a real bug that unit tests miss. Runs a mock Order API with a planted bug — double refunds are allowed. Unit tests pass because they test refund in isolation. VenomQA finds the bug by testing the sequence `create_order → refund → refund`.

```bash
venomqa demo [options]
```

#### Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--port` | `-p` | `8000` | Port for demo server |
| `--verbose` | `-v` | False | Show HTTP requests |

#### Example

```bash
venomqa demo
venomqa demo --port 9000 --verbose
```

After the demo, try it on your own API:

```bash
venomqa init --with-sample
```

---

### init

Initialize a new VenomQA project. Creates a `venomqa/` directory with config, action stubs, and fixture directories.

```bash
venomqa init [options]
```

Created layout:

```
venomqa/
├── venomqa.yaml        API URL and settings
├── llm-context.md      Paste into any AI assistant for help
├── actions/            Your action functions (api, context) -> response
├── fixtures/           Shared test data
├── journeys/           Exploration scripts using Agent.explore()
└── reports/            Generated HTML/JSON reports
```

File preservation: your files (`actions/`, `journeys/`, `fixtures/`) are never overwritten without `--force`. Framework files (`llm-context.md`, `README.md`) are safe to update.

#### Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--force` | `-f` | False | Overwrite ALL files including your actions/journeys |
| `--path` | `-p` | `venomqa` | Base path for QA directory |
| `--with-sample` | `-s` | False | Include a sample journey and actions |
| `--skip-checks` | | False | Skip preflight checks |
| `--update` | `-u` | False | Update framework files only — preserves your actions/journeys |
| `--yes` | `-y` | False | Skip interactive setup, use defaults |

#### Examples

```bash
venomqa init                    # Minimal scaffold (creates venomqa/)
venomqa init --with-sample      # Scaffold + working sample exploration
venomqa init -p myproject       # Use a different directory name
venomqa init --update           # Update framework files, preserve your code
```

---

### doctor

Run system health checks and diagnostics. Checks that all required dependencies are installed and properly configured.

```bash
venomqa doctor [options]
```

#### Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--verbose` | `-v` | False | Show additional diagnostic information |
| `--json` | | False | Output results as JSON |
| `--skip-connectivity` | | False | Skip database connectivity checks (faster) |
| `--fix` | | False | Show fix suggestions for failed checks |

#### Examples

```bash
venomqa doctor                      # Full health check
venomqa doctor --fix                # Show fix suggestions
venomqa doctor --skip-connectivity  # Skip DB checks (faster)
venomqa doctor --json               # Machine-readable output
```

#### Exit codes

| Code | Meaning |
|------|---------|
| `0` | All required checks passed |
| `1` | One or more required checks failed |

---

### explore

Run stateful exploration against an API using a journey file.

```bash
venomqa explore <journey_file> --base-url <url> [options]
```

A journey file defines actions (API calls) and invariants (rules to check). VenomQA tests every reachable sequence of actions and reports violations.

#### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `journey_file` | Yes | Path to Python file containing Journey definition |

#### Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--base-url` | `-u` | (required) | Base URL of the API to test |
| `--db-url` | | None | PostgreSQL connection string |
| `--redis-url` | | None | Redis connection string |
| `--strategy` | | `bfs` | Exploration strategy: `bfs`, `dfs`, `random` |
| `--max-steps` | | `1000` | Maximum exploration steps |
| `--format` | `-f` | `console` | Output format: `console`, `json`, `markdown`, `junit` |
| `--output` | `-o` | stdout | Output file path |

#### Examples

Basic exploration:
```bash
venomqa explore journeys/checkout.py --base-url http://localhost:8000
```

With database and JUnit output:
```bash
venomqa explore journeys/checkout.py \
  --base-url http://localhost:8000 \
  --db-url postgresql://user:pass@localhost/testdb \
  --format junit \
  --output reports/results.xml
```

Different strategies:
```bash
# Breadth-first (default) — explores all actions at each depth level
venomqa explore journey.py -u http://localhost:8000 --strategy bfs

# Depth-first — follows one path deeply before backtracking
venomqa explore journey.py -u http://localhost:8000 --strategy dfs

# Random — random exploration (good for fuzzing)
venomqa explore journey.py -u http://localhost:8000 --strategy random
```

Don't have a journey file yet?
```bash
venomqa init --with-sample
# then run the generated sample journey
```

---

### validate

Validate journey syntax without running exploration. Works with DSL-style Journey files. Files using the flat `Action`/`Agent` API don't need validation — run them directly with `venomqa explore`.

```bash
venomqa validate <journey_file>
```

#### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `journey_file` | Yes | Path to Python file containing Journey definition |

#### Example

```bash
venomqa validate journeys/checkout.py
```

Output:
```
Journey 'checkout_flow' is valid
  Steps: 5
  Checkpoints: 2
  Invariants: 3
```

---

### record

Proxy HTTP calls from a journey replay and generate a new Journey skeleton. Captures real traffic from a journey run and produces a scaffold you can edit.

```bash
venomqa record <journey_file> --base-url <url> [options]
```

Pass `-` as `journey_file` to skip replaying an existing journey and only capture live traffic.

#### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `journey_file` | Yes | Path to existing journey to replay, or `-` to skip |

#### Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--base-url` | `-u` | (required) | Base URL of the API to record |
| `--output` | `-o` | stdout | Output file for generated code |
| `--name` | | `recorded_journey` | Journey name in generated code |

#### Examples

```bash
# Replay an existing journey and capture the traffic
venomqa record journeys/checkout.py -u http://localhost:8000 -o journeys/recorded.py

# Just capture traffic without replaying a journey
venomqa record - -u http://localhost:8000 -o journeys/recorded.py
```

---

### llm-docs

Print a complete LLM context document for VenomQA. Paste the output into ChatGPT, Claude, Cursor, or any AI assistant so it knows the exact API signatures and can help you write tests without hallucinating wrong code.

```bash
venomqa llm-docs [options]
```

#### Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--output` | `-o` | stdout | Write to a file instead of stdout |

#### Examples

```bash
venomqa llm-docs                     # Print to terminal
venomqa llm-docs | pbcopy            # Copy to clipboard (macOS)
venomqa llm-docs -o context.txt      # Save to file
```

---

## Journey File Format

Journey files are Python modules that export a `Journey` object or define `Action` and `Invariant` objects directly.

### Basic Structure

```python
# journeys/checkout.py
from venomqa import Action, Invariant, Agent, World

def create_order(api, context):
    resp = api.post("/orders", json={"amount": 100})
    context.set("order_id", resp.json()["id"])
    return resp

def refund_order(api, context):
    order_id = context.get("order_id")
    return api.post(f"/orders/{order_id}/refund")

def check_refund_limit(world):
    order_id = world.context.get("order_id")
    if order_id is None:
        return True
    resp = world.api.get(f"/orders/{order_id}")
    order = resp.json()
    return order["refunded"] <= order["amount"]

actions = [Action("create_order", create_order), Action("refund_order", refund_order)]
invariants = [Invariant("refund_limit", check_refund_limit, "Refunded amount must not exceed order amount")]
```

---

## Output Formats

### Console (default)

Human-readable output to terminal:

```
============================================================
EXPLORATION RESULTS
============================================================

States visited: 15
Transitions taken: 20
Coverage: 85.3%
Duration: 1234ms
Success: True

Violations: 0
  (no violations - all invariants passed)
```

### JSON

Machine-readable JSON:

```bash
venomqa explore journey.py -u http://localhost:8000 -f json -o results.json
```

```json
{
  "success": true,
  "states_visited": 15,
  "transitions_taken": 20,
  "coverage_percent": 85.3,
  "duration_ms": 1234,
  "violations": [],
  "unique_violations": []
}
```

### Markdown

Report suitable for documentation:

```bash
venomqa explore journey.py -u http://localhost:8000 -f markdown -o report.md
```

### JUnit XML

For CI integration:

```bash
venomqa explore journey.py -u http://localhost:8000 -f junit -o results.xml
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success — no violations found |
| `1` | Failure — violations found or error occurred |

---

## CI/CD Integration

### GitHub Actions

```yaml
- name: Run VenomQA
  run: |
    venomqa explore journeys/main.py \
      --base-url ${{ secrets.API_URL }} \
      --db-url ${{ secrets.DB_URL }} \
      --format junit \
      --output results.xml

- name: Publish Results
  uses: EnricoMi/publish-unit-test-result-action@v2
  if: always()
  with:
    files: results.xml
```

### GitLab CI

```yaml
test:
  script:
    - venomqa explore journeys/main.py -u $API_URL -f junit -o results.xml
  artifacts:
    reports:
      junit: results.xml
```

---

## Troubleshooting

### Journey not found

```
Error: Could not load journey from journeys/test.py
```

Ensure your file:
1. Exists at the specified path
2. Contains a `journey` variable or `Journey` instance
3. Has no syntax errors (try `python3 -c "import journeys.test"`)

### validate only works with DSL-style journeys

```
Error: No Journey found in my_journey.py.
  venomqa validate only works with DSL-style Journey files.
  Files using the flat Action/Agent API don't need validation —
  run them directly with: venomqa explore <file> --base-url <url>
```

Use `venomqa explore` directly for files that use the flat `Action`/`Agent` API.

### Connection errors

```
Error: Connection refused
```

Check:
1. API is running at the specified URL
2. Database/Redis URLs are correct
3. Network access is available

Run `venomqa doctor` to diagnose connectivity issues.

### Too many steps

```
Warning: Reached max_steps limit (1000)
```

Either:
1. Increase `--max-steps` for more complete exploration
2. Or your state space is very large (expected for complex APIs)
