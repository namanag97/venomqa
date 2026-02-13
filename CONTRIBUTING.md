# Contributing to VenomQA

Thank you for your interest in contributing to VenomQA! This guide will help you get started.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Quick Start](#quick-start)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Code Style](#code-style)
- [Pull Request Process](#pull-request-process)
- [Release Process](#release-process)

---

## Code of Conduct

This project follows our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold respectful and inclusive behavior.

---

## Quick Start

```bash
# 1. Fork and clone
git clone https://github.com/YOUR_USERNAME/venomqa.git
cd venomqa

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install development dependencies
pip install -e ".[dev]"

# 4. Install pre-commit hooks
pre-commit install

# 5. Run tests
pytest

# 6. Create a branch and start coding
git checkout -b feature/your-feature
```

---

## Development Setup

### Prerequisites

- Python 3.10 or higher
- pip or uv package manager
- Git
- Docker (for integration tests)

### Installation

```bash
# Clone repository
git clone https://github.com/venomqa/venomqa.git
cd venomqa

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate

# Install all dependencies
pip install -e ".[dev,docs,postgres,redis]"

# Install pre-commit hooks
pre-commit install

# Verify setup
venomqa --version
pytest --version
```

### Docker Setup (Optional)

For running integration tests:

```bash
# Start test services
docker compose -f docker/docker-compose.ci.yml up -d

# Run integration tests
pytest -m integration

# Stop services
docker compose -f docker/docker-compose.ci.yml down
```

---

## Project Structure

```
venomqa/
├── venomqa/                  # Main package
│   ├── cli/                  # Command-line interface
│   ├── clients/              # HTTP/GraphQL/gRPC clients
│   ├── core/                 # Core models and context
│   ├── domains/              # Domain-specific test helpers
│   ├── reporters/            # Report generators
│   ├── state/                # Database state management
│   ├── adapters/             # External service adapters
│   └── tools/                # Utility tools
├── tests/                    # Test suite
│   ├── test_*.py             # Unit tests
│   └── scenarios/            # Integration test scenarios
├── docs/                     # Documentation
├── examples/                 # Example projects
│   ├── todo_app/             # Todo app example
│   ├── fastapi-example/      # FastAPI integration
│   └── quickstart/           # Quick start template
└── docker/                   # Docker configurations
```

---

## Making Changes

### Branch Naming

Use descriptive branch names:

- `feature/add-mysql-backend` - New features
- `fix/context-memory-leak` - Bug fixes
- `docs/quickstart-guide` - Documentation
- `refactor/reporter-interface` - Code refactoring
- `test/journey-edge-cases` - Test additions

### Commit Messages

Follow conventional commits:

```
<type>(<scope>): <description>

<body>

<footer>
```

**Types:**
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation
- `style` - Code style (formatting)
- `refactor` - Code refactoring
- `test` - Tests
- `chore` - Maintenance

**Examples:**

```
feat(state): add MySQL backend support

- Implement MySQLStateManager class
- Add connection pooling
- Update configuration schema

Closes #123
```

```
fix(cli): handle missing config file gracefully

Previously the CLI would crash if venomqa.yaml was missing.
Now it provides a helpful error message.

Fixes #456
```

---

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=venomqa --cov-report=html

# Run specific test file
pytest tests/test_runner.py

# Run specific test
pytest tests/test_runner.py::test_journey_execution

# Run only unit tests (fast)
pytest -m "not integration"

# Run integration tests (requires Docker)
pytest -m integration

# Run with verbose output
pytest -v
```

### Writing Tests

Place tests in the `tests/` directory:

```python
# tests/test_example.py
import pytest
from venomqa import Journey, Step
from venomqa.core.context import ExecutionContext


class TestJourneyExecution:
    """Tests for journey execution."""

    def test_simple_journey_passes(self):
        """A simple journey should execute successfully."""
        def simple_action(client, context):
            context["called"] = True
            return MockResponse(status_code=200)

        journey = Journey(
            name="test_journey",
            steps=[Step(name="step1", action=simple_action)],
        )

        # Test execution
        result = execute_journey(journey)

        assert result.success
        assert result.context["called"] is True

    @pytest.mark.integration
    def test_with_database(self, db_connection):
        """Integration test requiring database."""
        # Test with real database
        pass

    @pytest.mark.parametrize("status_code,expected", [
        (200, True),
        (201, True),
        (400, False),
        (500, False),
    ])
    def test_status_code_handling(self, status_code, expected):
        """Test various status code outcomes."""
        pass
```

### Test Markers

- `@pytest.mark.integration` - Requires external services
- `@pytest.mark.slow` - Long-running tests
- `@pytest.mark.skip` - Temporarily skipped

---

## Code Style

### Formatting

We use Ruff for linting and formatting:

```bash
# Check style
ruff check .

# Fix issues automatically
ruff check . --fix

# Format code
ruff format .

# Check types
mypy venomqa
```

### Type Hints

Use type hints for all public functions:

```python
from typing import Any

from venomqa.core.models import Journey, JourneyResult
from venomqa.config.settings import QAConfig


def run_journey(
    journey: Journey,
    config: QAConfig | None = None,
    verbose: bool = False,
) -> JourneyResult:
    """Run a journey with optional configuration.

    Args:
        journey: The journey to execute.
        config: Optional configuration overrides.
        verbose: Enable verbose logging.

    Returns:
        The journey execution result.

    Raises:
        ConfigurationError: If configuration is invalid.
    """
    ...
```

### Docstrings

Use Google-style docstrings:

```python
def checkpoint(self, name: str) -> None:
    """Create a database savepoint.

    Creates a SAVEPOINT in the current transaction that can be
    rolled back to later using the rollback() method.

    Args:
        name: Unique identifier for the checkpoint. Must be
            alphanumeric with underscores only.

    Raises:
        RuntimeError: If not connected to the database.
        ValueError: If name contains invalid characters.

    Example:
        >>> state_manager.checkpoint("before_payment")
        >>> # Make changes...
        >>> state_manager.rollback("before_payment")
    """
    ...
```

### Import Order

1. Standard library
2. Third-party packages
3. Local imports

```python
# Standard library
import json
from datetime import datetime
from typing import Any

# Third-party
import httpx
from pydantic import BaseModel

# Local
from venomqa.core.models import Journey
from venomqa.state.base import StateManager
```

---

## Pull Request Process

### Before Submitting

1. **Write tests** for new functionality
2. **Update documentation** if needed
3. **Run the full test suite:** `pytest`
4. **Run linting:** `ruff check .`
5. **Run type checking:** `mypy venomqa`
6. **Update CHANGELOG.md** if applicable

### PR Checklist

- [ ] Tests pass locally
- [ ] New tests added for new functionality
- [ ] Code follows project style guidelines
- [ ] Documentation updated
- [ ] Changelog updated (for user-facing changes)
- [ ] PR description explains the changes

### PR Template

```markdown
## Description

Brief description of changes.

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation

## Testing

- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] All tests pass

## Checklist

- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
```

### Review Process

1. Open a PR against `main`
2. Automated checks run (tests, linting)
3. Maintainer reviews the code
4. Address any feedback
5. Once approved, maintainer merges

---

## Release Process

Releases are handled by maintainers:

1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Create a git tag: `git tag v0.3.0`
4. Push tag: `git push --tags`
5. GitHub Actions builds and publishes to PyPI

---

## Ways to Contribute

### Good First Issues

Look for issues labeled [`good first issue`](https://github.com/venomqa/venomqa/issues?q=label%3A%22good+first+issue%22).

### Documentation

- Fix typos or unclear explanations
- Add examples
- Improve the getting started guide
- Translate documentation

### Bug Reports

Use the bug report template:

- Python version
- VenomQA version
- Operating system
- Minimal reproduction code
- Expected vs actual behavior
- Error messages/stack traces

### Feature Requests

Use the feature request template:

- Use case description
- Proposed solution
- Alternative solutions considered
- Additional context

### Code Contributions

- Fix bugs
- Add new adapters (MySQL, MongoDB, etc.)
- Add new reporters
- Improve performance
- Add CLI commands

---

## Getting Help

- **GitHub Issues:** Bug reports and feature requests
- **GitHub Discussions:** Questions and general discussion
- **Documentation:** [docs/](docs/)

---

## Recognition

Contributors are recognized in:

- Git commit history
- Release notes
- README contributors section

Thank you for contributing to VenomQA!
