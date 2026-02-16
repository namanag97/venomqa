# CLI Reference

VenomQA v1 provides a command-line interface for running explorations and validating journeys.

## Installation

```bash
pip install venomqa
```

The `venomqa` command becomes available after installation.

## Commands

### explore

Run state exploration against an API.

```bash
venomqa explore <journey_file> --base-url <url> [options]
```

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

With database and output:
```bash
venomqa explore journeys/checkout.py \
  --base-url http://localhost:8000 \
  --db-url postgresql://user:pass@localhost/testdb \
  --format junit \
  --output reports/results.xml
```

Different strategies:
```bash
# Breadth-first (default) - explores all actions at each depth level
venomqa explore journey.py -u http://localhost:8000 --strategy bfs

# Depth-first - follows one path deeply before backtracking
venomqa explore journey.py -u http://localhost:8000 --strategy dfs

# Random - random exploration (good for fuzzing)
venomqa explore journey.py -u http://localhost:8000 --strategy random
```

---

### validate

Validate journey syntax without running exploration.

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

## Journey File Format

Journey files are Python modules that export a `Journey` object.

### Basic Structure

```python
# journeys/checkout.py
from venomqa.v1 import Journey, Step, Checkpoint, Branch, Path, Invariant

journey = Journey(
    name="checkout_flow",
    steps=[
        Step("login", lambda api: api.post("/login", json={"user": "test"})),
        Checkpoint("logged_in"),
        Step("add_to_cart", lambda api: api.post("/cart", json={"product_id": 1})),
        Checkpoint("cart_ready"),
        Branch(
            from_checkpoint="cart_ready",
            paths=[
                Path("checkout", [
                    Step("checkout", lambda api: api.post("/checkout")),
                ]),
                Path("abandon", [
                    Step("clear_cart", lambda api: api.delete("/cart")),
                ]),
            ],
        ),
    ],
    invariants=[
        Invariant(
            name="cart_consistent",
            check=lambda world: True,  # Your check here
            message="Cart must be consistent",
        ),
    ],
)
```

### With Actions Module

For larger tests, separate actions:

```python
# journeys/checkout.py
from venomqa.v1 import Journey, Step, Checkpoint
from .actions import login, add_to_cart, checkout
from .invariants import cart_consistent, order_valid

journey = Journey(
    name="checkout_flow",
    steps=[
        Step("login", login),
        Checkpoint("logged_in"),
        Step("add_to_cart", add_to_cart),
        Step("checkout", checkout),
    ],
    invariants=[cart_consistent, order_valid],
)
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
  "graph": {
    "states": [...],
    "transitions": [...]
  }
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
| `0` | Success - no violations found |
| `1` | Failure - violations found or error occurred |

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `VENOMQA_BASE_URL` | Default API base URL |
| `VENOMQA_DB_URL` | Default database URL |
| `VENOMQA_REDIS_URL` | Default Redis URL |
| `VENOMQA_MAX_STEPS` | Default max steps |

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
3. Has no syntax errors (try `python -c "import journeys.test"`)

### Connection errors

```
Error: Connection refused
```

Check:
1. API is running at the specified URL
2. Database/Redis URLs are correct
3. Network access is available

### Too many steps

```
Warning: Reached max_steps limit (1000)
```

Either:
1. Increase `--max-steps` for complete exploration
2. Or your state space is very large (expected for complex APIs)
