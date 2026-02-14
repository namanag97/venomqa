# Contributing

We love contributions! Here's how to get started with VenomQA development.

## Quick Start

```bash
# Clone the repository
git clone https://github.com/venomqa/venomqa.git
cd venomqa

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install with development dependencies
pip install -e ".[dev,docs]"

# Install pre-commit hooks
pre-commit install

# Run tests
pytest

# Run linting
ruff check .
mypy venomqa
```

## Ways to Contribute

### Report Bugs

Found a bug? [Open an issue](https://github.com/venomqa/venomqa/issues/new?template=bug_report.md) with:

- VenomQA version
- Python version
- Minimal reproduction steps
- Expected vs actual behavior

### Suggest Features

Have an idea? [Start a discussion](https://github.com/venomqa/venomqa/discussions) to:

- Describe the use case
- Explain the proposed solution
- Discuss alternatives

### Improve Documentation

Documentation improvements are always welcome:

- Fix typos
- Add examples
- Clarify explanations
- Translate documentation

### Submit Code

Ready to code? Look for issues labeled [`good first issue`](https://github.com/venomqa/venomqa/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).

## Development Workflow

### 1. Fork and Clone

```bash
# Fork on GitHub, then clone
git clone https://github.com/YOUR_USERNAME/venomqa.git
cd venomqa
git remote add upstream https://github.com/venomqa/venomqa.git
```

### 2. Create Branch

```bash
git checkout -b feature/my-feature
# or
git checkout -b fix/my-fix
```

### 3. Make Changes

- Write code
- Add tests
- Update documentation

### 4. Test Changes

```bash
# Run all tests
pytest

# Run specific tests
pytest tests/test_models.py

# Run with coverage
pytest --cov=venomqa

# Run linting
ruff check .
ruff format --check .

# Run type checking
mypy venomqa
```

### 5. Commit Changes

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```bash
git commit -m "feat: add support for MySQL backend"
git commit -m "fix: resolve checkpoint naming conflict"
git commit -m "docs: add MySQL configuration example"
git commit -m "test: add tests for branch rollback"
```

### 6. Push and Create PR

```bash
git push origin feature/my-feature
```

Then create a Pull Request on GitHub.

## Code Style

### Python Style

We use:

- [Ruff](https://github.com/astral-sh/ruff) for linting and formatting
- [mypy](https://mypy.readthedocs.io/) for type checking
- Line length: 100 characters

```bash
# Format code
ruff format .

# Check linting
ruff check .

# Fix linting issues
ruff check --fix .
```

### Type Hints

Use type hints for all public APIs:

```python
def create_journey(
    name: str,
    steps: list[Step],
    description: str = "",
    tags: list[str] | None = None,
) -> Journey:
    """Create a new journey.

    Args:
        name: Unique journey identifier
        steps: List of steps to execute
        description: Human-readable description
        tags: Optional tags for filtering

    Returns:
        A new Journey instance
    """
    pass
```

### Docstrings

Use Google-style docstrings:

```python
def process_result(
    result: StepResult,
    context: ExecutionContext,
) -> dict[str, Any]:
    """Process a step result and update context.

    Args:
        result: The step execution result
        context: The execution context to update

    Returns:
        A dictionary containing processed result data

    Raises:
        ValueError: If result is invalid
        StateError: If context cannot be updated
    """
    pass
```

## Testing

### Test Structure

```
tests/
├── test_models.py          # Core model tests
├── test_runner.py          # Runner tests
├── test_client.py          # HTTP client tests
├── test_state.py           # State manager tests
├── test_reporters.py       # Reporter tests
└── conftest.py             # Shared fixtures
```

### Writing Tests

```python
import pytest
from venomqa import Journey, Step, Client


class TestJourney:
    def test_journey_creation(self):
        """Test basic journey creation."""
        journey = Journey(
            name="test",
            steps=[
                Step(name="step1", action=lambda c, ctx: c.get("/"))
            ],
        )
        assert journey.name == "test"
        assert len(journey.steps) == 1

    def test_journey_validation(self):
        """Test journey validates checkpoint references."""
        with pytest.raises(ValueError):
            Journey(
                name="test",
                steps=[
                    Branch(checkpoint_name="nonexistent", paths=[])
                ],
            )


@pytest.fixture
def client():
    """Create test client."""
    return Client(base_url="http://localhost:8000")


@pytest.fixture
def mock_response(respx_mock):
    """Mock HTTP responses."""
    respx_mock.get("/health").respond(200, json={"status": "ok"})
    return respx_mock
```

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=venomqa --cov-report=html

# Specific file
pytest tests/test_models.py

# Specific test
pytest tests/test_models.py::TestJourney::test_journey_creation

# Verbose output
pytest -v

# Stop on first failure
pytest -x
```

## Documentation

### Building Docs

```bash
# Install docs dependencies
pip install -e ".[docs]"

# Serve locally
mkdocs serve

# Build
mkdocs build
```

### Documentation Structure

```
docs/
├── index.md                  # Home page
├── getting-started/          # Getting started guides
├── concepts/                 # Core concepts
├── tutorials/                # Step-by-step tutorials
├── reference/                # API reference
├── examples/                 # Code examples
└── advanced/                 # Advanced topics
```

## Release Process

1. Update version in `venomqa/__init__.py` and `pyproject.toml`
2. Update CHANGELOG.md
3. Create release PR
4. After merge, tag release: `git tag v0.x.0`
5. Push tag: `git push --tags`
6. GitHub Actions builds and publishes to PyPI

## Code of Conduct

Please read our [Code of Conduct](CODE_OF_CONDUCT.md) before contributing.

## Questions?

- [GitHub Discussions](https://github.com/venomqa/venomqa/discussions)
- [Discord](https://discord.gg/venomqa)
