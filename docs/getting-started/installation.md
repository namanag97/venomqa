# Installation

This guide covers all installation options for VenomQA.

## Requirements

- **Python 3.10 or higher**
- **pip** (Python package manager)
- **Docker** (optional, for infrastructure management)

## Basic Installation

Install VenomQA from PyPI:

```bash
pip install venomqa
```

Verify the installation:

```bash
venomqa --version
```

## Optional Dependencies

VenomQA has optional dependencies for different features:

### PostgreSQL State Management

For database checkpointing and rollback:

```bash
pip install "venomqa[postgres]"
```

This installs `psycopg[binary]` for PostgreSQL connectivity.

### Redis Adapters

For Redis cache and queue adapters:

```bash
pip install "venomqa[redis]"
```

### S3/MinIO Storage

For S3-compatible storage adapters:

```bash
pip install "venomqa[s3]"
```

### All Optional Dependencies

Install everything:

```bash
pip install "venomqa[all]"
```

### Multiple Extras

Install specific combinations:

```bash
pip install "venomqa[postgres,redis]"
```

## Installation Options Summary

| Extra | Dependencies | Purpose |
|-------|--------------|---------|
| `postgres` | `psycopg[binary]` | Database state management |
| `redis` | `redis` | Redis cache/queue adapters |
| `s3` | `boto3` | S3/MinIO storage adapter |
| `all` | All of the above | Full functionality |

## Development Installation

For contributing or development:

```bash
# Clone the repository
git clone https://github.com/venomqa/venomqa.git
cd venomqa

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install with development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check .
mypy venomqa
```

## Documentation Development

To work on documentation:

```bash
# Install docs dependencies
pip install -e ".[docs]"

# Serve documentation locally
mkdocs serve

# Build documentation
mkdocs build
```

## Troubleshooting

### PostgreSQL Installation Issues

On some systems, you may need to install build dependencies:

=== "Ubuntu/Debian"

    ```bash
    sudo apt-get install libpq-dev python3-dev
    pip install "venomqa[postgres]"
    ```

=== "macOS (Homebrew)"

    ```bash
    brew install postgresql
    pip install "venomqa[postgres]"
    ```

=== "Windows"

    Install PostgreSQL from https://www.postgresql.org/download/windows/

    Then:
    ```bash
    pip install "venomqa[postgres]"
    ```

### Virtual Environment Recommended

We strongly recommend using a virtual environment:

```bash
# Create virtual environment
python -m venv venv

# Activate it
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# Install VenomQA
pip install venomqa
```

### Upgrading VenomQA

To upgrade to the latest version:

```bash
pip install --upgrade venomqa
```

To upgrade with extras:

```bash
pip install --upgrade "venomqa[all]"
```

### Checking Installed Version

```bash
# Via CLI
venomqa --version

# Via Python
python -c "import venomqa; print(venomqa.__version__)"
```

## Next Steps

After installation, proceed to:

- [Quickstart](quickstart.md) - Create your first journey
- [Configuration](configuration.md) - Configure VenomQA for your project
