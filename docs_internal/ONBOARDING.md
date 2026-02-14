# Developer Onboarding Guide

> Getting new contributors up to speed quickly.

---

## Welcome!

Thanks for contributing to VenomQA! This guide will help you understand the codebase and start contributing.

---

## Quick Start (5 minutes)

```bash
# 1. Clone and setup
git clone https://github.com/namanag97/venomqa.git
cd venomqa
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# 2. Install in development mode
pip install -e ".[dev,docs]"

# 3. Run the demo to see it work
venomqa demo --explain

# 4. Run tests
pytest tests/ -v

# 5. Build docs locally
mkdocs serve
# Open http://127.0.0.1:8000
```

---

## Understanding the Codebase

### Directory Structure

```
venomqa/
├── __init__.py          # Public API - start here to understand exports
│
├── core/                # Core domain models
│   ├── models.py        # Journey, Step, Branch, Checkpoint
│   ├── graph.py         # StateGraph, Edge, Invariant
│   └── context.py       # ExecutionContext
│
├── runner/              # Execution engine
│   └── __init__.py      # JourneyRunner - runs journeys
│
├── client/              # HTTP client
│   └── __init__.py      # Client - makes HTTP requests
│
├── cli/                 # Command-line interface
│   ├── commands.py      # Main CLI commands
│   └── demo.py          # Demo server & command
│
├── ports/               # Abstract interfaces (what)
│   ├── database.py      # DatabasePort protocol
│   ├── cache.py         # CachePort protocol
│   └── ...
│
├── adapters/            # Concrete implementations (how)
│   ├── postgres.py
│   ├── redis_cache.py
│   └── ...
│
├── reporters/           # Output formatters
│   ├── html.py
│   ├── junit.py
│   └── ...
│
└── errors/              # Error handling
    └── base.py          # VenomQAError hierarchy
```

### Key Files to Read First

1. **`venomqa/core/models.py`** - Understand Journey, Step, Branch
2. **`venomqa/runner/__init__.py`** - How journeys are executed
3. **`venomqa/core/graph.py`** - StateGraph exploration
4. **`venomqa/cli/demo.py`** - Simple example of using the framework

---

## Architecture Overview

```
User writes journey
        │
        ▼
┌─────────────────┐
│   CLI/Python    │  ← Entry point
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  JourneyRunner  │  ← Orchestrates execution
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐ ┌───────┐
│Client │ │Context│  ← HTTP + shared state
└───────┘ └───────┘
```

**Key concepts:**
- **Journey**: A sequence of Steps
- **Step**: One API call with action function
- **Context**: Shared dict passed between steps
- **Checkpoint**: Save database state
- **Branch**: Fork execution to test multiple paths

---

## Development Workflow

### 1. Pick an Issue

- Check [GitHub Issues](https://github.com/namanag97/venomqa/issues)
- Look for `good first issue` label
- Comment to claim it

### 2. Create Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-number-description
```

### 3. Make Changes

- Write code
- Add tests
- Update docs if needed

### 4. Test Locally

```bash
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_runner.py -v

# Run with coverage
pytest tests/ --cov=venomqa --cov-report=html

# Type checking
mypy venomqa/

# Linting
ruff check venomqa/
ruff format venomqa/
```

### 5. Submit PR

```bash
git push origin feature/your-feature-name
# Then create PR on GitHub
```

---

## Coding Standards

### Style

- **Formatter**: ruff format
- **Linter**: ruff check
- **Type hints**: Required for public APIs
- **Docstrings**: Google style

```python
def my_function(param: str, count: int = 10) -> list[str]:
    """Short description.

    Longer description if needed.

    Args:
        param: Description of param.
        count: Description of count.

    Returns:
        Description of return value.

    Raises:
        ValueError: When param is empty.
    """
    pass
```

### Naming

- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`

### Imports

```python
# Standard library
import os
from pathlib import Path

# Third-party
import click
from rich.console import Console

# Local
from venomqa.core.models import Journey
from venomqa.errors import VenomQAError
```

---

## Testing

### Test Structure

```
tests/
├── test_core/
│   ├── test_models.py
│   └── test_graph.py
├── test_runner/
│   └── test_runner.py
├── test_client/
│   └── test_client.py
└── conftest.py          # Shared fixtures
```

### Writing Tests

```python
import pytest
from venomqa import Journey, Step

def test_journey_creation():
    """Test that Journey can be created with steps."""
    journey = Journey(
        name="test",
        steps=[Step(name="step1", action=lambda c, ctx: None)]
    )
    assert journey.name == "test"
    assert len(journey.steps) == 1

@pytest.fixture
def sample_journey():
    """Reusable journey fixture."""
    return Journey(name="sample", steps=[])

def test_with_fixture(sample_journey):
    assert sample_journey.name == "sample"
```

### Running Tests

```bash
# All tests
pytest

# Specific file
pytest tests/test_core/test_models.py

# Specific test
pytest tests/test_core/test_models.py::test_journey_creation

# With output
pytest -v -s

# Stop on first failure
pytest -x
```

---

## Documentation

### Building Docs

```bash
# Serve locally (hot reload)
mkdocs serve

# Build static site
mkdocs build
```

### Doc Structure

```
docs/
├── index.md              # Landing page
├── getting-started/
│   ├── quickstart.md
│   └── installation.md
├── concepts/
│   ├── theory.md
│   └── journeys.md
└── reference/
    └── api.md
```

### Writing Docs

- Use clear, simple language
- Include code examples
- Test all code examples

---

## Common Tasks

### Adding a New CLI Command

1. Add to `venomqa/cli/commands.py`:
```python
@cli.command()
@click.option("--flag", is_flag=True)
def mycommand(flag: bool):
    """Description of command."""
    pass
```

### Adding a New Adapter

1. Create `venomqa/adapters/myadapter.py`
2. Implement the relevant Port interface
3. Register in `venomqa/adapters/__init__.py`
4. Add tests in `tests/test_adapters/`

### Adding a New Reporter

1. Create `venomqa/reporters/myreporter.py`
2. Extend `BaseReporter`
3. Implement `generate()` method
4. Register in `venomqa/reporters/__init__.py`

---

## Getting Help

- **Questions**: Open a GitHub Discussion
- **Bugs**: Open a GitHub Issue
- **Chat**: Discord (coming soon)
- **Email**: [maintainer email]

---

## First Contribution Ideas

1. **Fix a typo** in docs
2. **Add a test** for uncovered code
3. **Improve error message** with "how to fix"
4. **Add docstring** to undocumented function
5. **Fix a `good first issue`**

---

## Thank You!

Every contribution helps. We're excited to have you!
