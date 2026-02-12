# Contributing to VenomQA

Thank you for your interest in contributing to VenomQA! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Code Style](#code-style)
- [Pull Request Process](#pull-request-process)
- [Reporting Issues](#reporting-issues)

## Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Set up the development environment
4. Make your changes
5. Submit a pull request

## Development Setup

### Prerequisites

- Python 3.10 or higher
- pip or uv package manager
- Git
- Docker (for integration tests)

### Setup Steps

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/venomqa.git
cd venomqa

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Verify installation
venomqa --version
```

### Docker Setup (Optional)

For running integration tests with PostgreSQL:

```bash
# Start test services
docker compose -f docker-compose.test.yml up -d

# Run integration tests
pytest tests/test_integration.py

# Stop services
docker compose -f docker-compose.test.yml down
```

## Making Changes

### Branch Naming

Create a branch with a descriptive name:

- `feature/add-mysql-backend` - New features
- `fix/parallel-execution-race` - Bug fixes
- `docs/api-reference` - Documentation updates
- `refactor/reporter-interface` - Code refactoring

### Commit Messages

Follow these guidelines for commit messages:

```
<type>: <subject>

<body (optional)>

<footer (optional)>
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Example:
```
feat: add MySQL state backend support

- Implement MySQLStateManager class
- Add connection pooling support
- Update documentation with MySQL examples

Closes #123
```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=venomqa

# Run specific test file
pytest tests/test_runner.py

# Run specific test
pytest tests/test_runner.py::test_journey_execution

# Run with verbose output
pytest -v

# Run only unit tests
pytest -m "not integration"

# Run integration tests
pytest -m integration
```

### Writing Tests

Place tests in the `tests/` directory. Follow these conventions:

```python
# tests/test_example.py
import pytest
from venomqa import Journey, Step, JourneyRunner, Client

class TestJourneyExecution:
    """Tests for journey execution."""
    
    def test_simple_journey_passes(self):
        """Test that a simple journey executes successfully."""
        # Arrange
        def simple_action(client, context):
            return client.get("/health")
        
        journey = Journey(
            name="test",
            steps=[Step(name="health", action=simple_action)],
        )
        
        # Act
        runner = JourneyRunner(client=Client(base_url="http://localhost:8000"))
        result = runner.run(journey)
        
        # Assert
        assert result.success
    
    @pytest.mark.integration
    def test_with_database(self):
        """Integration test requiring database."""
        pass
```

### Test Categories

- **Unit Tests**: Fast, isolated tests with no external dependencies
- **Integration Tests**: Tests with database, API, or Docker dependencies
- **End-to-End Tests**: Full journey tests with real services

## Code Style

### Formatting

We use Ruff for linting and formatting:

```bash
# Check code style
ruff check .

# Format code
ruff format .

# Check with all rules
ruff check . --select ALL
```

### Type Hints

Use type hints for all public functions:

```python
def run_journey(
    journey: Journey,
    config: QAConfig | None = None,
) -> JourneyResult:
    """Run a journey with optional configuration.
    
    Args:
        journey: The journey to execute.
        config: Optional configuration overrides.
    
    Returns:
        The journey execution result.
    """
    pass
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
            alphanumeric with underscores.
    
    Raises:
        RuntimeError: If not connected to the database.
        ValueError: If name contains invalid characters.
    
    Example:
        >>> state_manager.checkpoint("before_order")
        >>> # ... make changes ...
        >>> state_manager.rollback("before_order")
    """
    pass
```

### Import Order

Imports should be ordered:

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

## Pull Request Process

### Before Submitting

1. **Update tests**: Ensure new code is tested
2. **Update documentation**: Update relevant docs
3. **Run linting**: `ruff check .`
4. **Run tests**: `pytest --cov=venomqa`
5. **Update changelog**: Add entry to CHANGELOG.md

### PR Checklist

- [ ] Code follows project style guidelines
- [ ] Tests pass locally
- [ ] New tests added for new functionality
- [ ] Documentation updated
- [ ] Changelog updated
- [ ] PR description is clear and complete

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Tests added/updated
- [ ] All tests pass

## Checklist
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] Changelog updated
```

### Review Process

1. Maintainers will review your PR
2. Address any feedback
3. Once approved, a maintainer will merge

## Reporting Issues

### Bug Reports

Use the bug report template and include:

- Python version
- VenomQA version
- Operating system
- Minimal reproduction code
- Expected vs actual behavior
- Error messages/stack traces

### Feature Requests

Use the feature request template and include:

- Use case description
- Proposed solution
- Alternative solutions considered
- Additional context

## Getting Help

- **GitHub Issues**: For bugs and feature requests
- **Discussions**: For questions and general discussion
- **Documentation**: Check the `docs/` directory

## Recognition

Contributors are recognized in:
- Git commit history
- Release notes
- Contributors file

Thank you for contributing to VenomQA!
