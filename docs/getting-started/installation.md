# Installation

Install VenomQA and set up your testing environment.

## Requirements

| Requirement | Version |
|-------------|---------|
| Python | 3.10+ |
| pip | Latest |
| OS | macOS, Linux, Windows |

## Install from PyPI

```bash
pip install venomqa
```

## Install from Source

```bash
git clone https://github.com/namanag97/venomqa.git
cd venomqa
pip install -e ".[dev]"
```

## Verify Installation

```bash
venomqa --version
# venomqa 0.6.4

venomqa doctor
# ✓ Python 3.11.5
# ✓ httpx installed
# ✓ pydantic v2
# ✓ All checks passed
```

## Optional: Database Adapters

For database rollback support, install the appropriate adapter:

### PostgreSQL

```bash
pip install "venomqa[postgres]"
# or
pip install psycopg[binary]
```

**Features:**

- `SAVEPOINT` / `ROLLBACK TO SAVEPOINT`
- Entire exploration runs in one uncommitted transaction
- True branching without test pollution

### MySQL

```bash
pip install "venomqa[mysql]"
# or
pip install mysql-connector-python
```

### SQLite

Built-in. No additional installation required.

**Features:**

- File-based copy/restore
- Works with local development databases

### Redis

```bash
pip install "venomqa[redis]"
# or
pip install redis
```

**Features:**

- `DUMP` all keys → `FLUSHALL` + `RESTORE`
- State isolation between branches

## Project Structure

VenomQA doesn't enforce a specific structure, but this works well:

```
your-project/
├── app/                    # Your application
├── qa/
│   ├── actions/           # VenomQA actions
│   │   ├── __init__.py
│   │   ├── orders.py
│   │   └── users.py
│   ├── invariants.py      # Invariant definitions
│   ├── conftest.py        # Fixtures and world setup
│   └── test_flows.py      # Test orchestration
├── pyproject.toml
└── requirements.txt
```

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `VENOMQA_API_KEY` | X-API-Key header | None |
| `VENOMQA_AUTH_TOKEN` | Bearer token | None |
| `VENOMQA_BASE_URL` | Default API URL | None |
| `VENOMQA_DB_URL` | Database connection | None |

## CLI Installation Check

```bash
# Check if CLI is available
which venomqa
# /usr/local/bin/venomqa

# Run diagnostics
venomqa doctor

# Show help
venomqa --help
```

## Common Issues

### "command not found: venomqa"

The CLI entry point wasn't installed correctly. Try:

```bash
pip install --upgrade venomqa
python -m venomqa.cli --version
```

### "ImportError: cannot import name 'HttpClient'"

Ensure you're importing from the correct module:

```python
# Correct
from venomqa.adapters.http import HttpClient

# Incorrect (old API)
from venomqa import HttpClient
```

### "psycopg.OperationalError" (PostgreSQL)

Install the binary package:

```bash
pip install "psycopg[binary]"
```

## Next Steps

- [Quickstart](quickstart.md) - Find your first bug
- [Configuration](configuration.md) - Set up authentication and timeouts
- [Concepts](../concepts/index.md) - Understand the mental model
