# VenomQA Templates & Examples

This directory contains reusable templates and complete examples for using VenomQA in your projects.

## Directory Structure

```
├── ci/                          # CI/CD pipeline templates
│   ├── github-actions.yml       # GitHub Actions workflow
│   ├── gitlab-ci.yml            # GitLab CI configuration
│   ├── jenkins.groovy           # Jenkinsfile (declarative pipeline)
│   ├── circleci.yml             # CircleCI configuration
│   └── azure-pipelines.yml      # Azure DevOps pipeline
│
├── docker/                      # Docker templates
│   ├── Dockerfile.example       # Example Dockerfile for test APIs
│   └── docker-compose.override.yml  # Local development overrides
│
├── journeys/                    # Journey templates
│   ├── auth_flow.py             # Authentication flow patterns
│   ├── crud_flow.py             # CRUD operation patterns
│   ├── file_upload_flow.py      # File upload testing
│   └── payment_flow.py          # Payment/checkout flows
│
└── examples/
    └── full_stack_app/          # Complete example application
        ├── api/                 # Flask REST API
        ├── tests/               # pytest unit tests
        ├── journeys/            # VenomQA journeys
        ├── actions/             # Reusable actions
        └── docker-compose.yml   # Docker setup
```

## Quick Start

### 1. Copy Templates to Your Project

```bash
# Copy CI/CD templates
cp -r templates/ci/* your-project/.github/workflows/

# Copy journey templates
cp -r templates/journeys your-project/qa/

# Copy Docker templates
cp templates/docker/Dockerfile.example your-project/Dockerfile.qa
```

### 2. Using Journey Templates

```python
# journeys/my_journey.py
from templates.journeys.crud_flow import CRUDActions, crud_full_cycle_flow

# Customize for your API
my_crud_flow = crud_full_cycle_flow.with_overrides(
    base_url="https://api.myapp.com",
    resource_path="/api/products"
)
```

### 3. Run with CI/CD

```bash
# GitHub Actions - just copy the workflow file
# GitLab CI - include the template
include:
  - local: '/templates/ci/gitlab-ci.yml'

# Jenkins - use the Jenkinsfile in your pipeline
# CircleCI - reference the orb/config
```

## CI/CD Templates

### GitHub Actions

The `github-actions.yml` provides:
- Linting with Ruff and MyPy
- Unit test execution with coverage
- API integration tests
- E2E tests (on main branch)
- Performance tests (scheduled/manual)
- Slack notifications

```yaml
# .github/workflows/venomqa.yml
# Copy templates/ci/github-actions.yml here
```

### GitLab CI

Features:
- Multi-stage pipeline (lint → test → e2e → report)
- Docker-in-Docker for containerized tests
- GitLab Pages for report hosting
- Slack webhook notifications

### Jenkins

Includes:
- Kubernetes pod agent support
- Parallel test execution
- JUnit report publishing
- Email notifications on failure

### CircleCI

Features:
- Orb-based configuration
- Docker service containers
- Parallelism support
- Slack integration

### Azure Pipelines

Supports:
- Azure-hosted agents
- Service containers (PostgreSQL, Redis)
- Test results publishing
- Code coverage reports

## Journey Templates

### Authentication Flow (`auth_flow.py`)

```python
from templates.journeys.auth_flow import (
    auth_login_flow,
    auth_registration_flow,
    auth_full_flow,
)

# Use predefined flows
venomqa run --journey auth_login_flow

# Or build custom flows
from templates.journeys.auth_flow import AuthActions

auth = AuthActions("https://api.example.com")
response = auth.login("user@example.com", "password")
```

### CRUD Flow (`crud_flow.py`)

```python
from templates.journeys.crud_flow import (
    crud_create_flow,
    crud_read_flow,
    crud_update_flow,
    crud_delete_flow,
    crud_full_cycle_flow,
    CRUDActions,
)

# Test complete CRUD lifecycle
venomqa run --journey crud_full_cycle_flow

# Use CRUDActions for custom operations
crud = CRUDActions(
    base_url="https://api.example.com",
    resource_path="/api/articles"
)
crud.create({"title": "Test", "content": "..."})
```

### File Upload Flow (`file_upload_flow.py`)

```python
from templates.journeys.file_upload_flow import (
    single_file_upload_flow,
    multiple_file_upload_flow,
    chunked_upload_flow,
    FileUploadActions,
)

# Test file uploads
venomqa run --journey single_file_upload_flow

# Use FileUploadActions
uploader = FileUploadActions("https://api.example.com")
uploader.upload_single("/path/to/file.pdf")
uploader.upload_chunked("/path/to/large_file.zip", chunk_size=5*1024*1024)
```

### Payment Flow (`payment_flow.py`)

```python
from templates.journeys.payment_flow import (
    shopping_cart_flow,
    checkout_success_flow,
    refund_flow,
    full_purchase_flow,
    PaymentActions,
)

# Test payment flows
venomqa run --journey full_purchase_flow

# Use PaymentActions
payment = PaymentActions("https://api.example.com")
payment.create_cart()
payment.add_to_cart(cart_id, product_id, quantity=2)
payment.process_checkout(cart_id, payment_method_id, shipping_address)
```

## Full Stack Example

The `examples/full_stack_app/` directory contains a complete working example:

### Running the Example

```bash
cd examples/full_stack_app

# Option 1: Run API locally
pip install -r api/requirements.txt
python -m api.main &
venomqa run --config venomqa.yaml

# Option 2: Use Docker Compose
docker-compose up -d
docker-compose exec venomqa venomqa run

# Option 3: Run tests
pytest tests/ -v
```

### Example Structure

```
full_stack_app/
├── api/
│   ├── main.py              # Flask REST API
│   └── requirements.txt     # Python dependencies
├── tests/
│   └── test_api.py          # pytest unit tests
├── journeys/
│   └── __init__.py          # VenomQA journey definitions
├── actions/
│   └── __init__.py          # Reusable action functions
├── docker-compose.yml       # Docker orchestration
└── venomqa.yaml             # VenomQA configuration
```

## Docker Templates

### Dockerfile.example

Multi-stage build for test APIs:
- Builder stage for compilation
- Runtime stage with minimal dependencies
- Non-root user for security
- Health check support

### docker-compose.override.yml

Local development overrides including:
- Hot-reload for API
- Database and cache services
- Admin UIs (Adminer, Redis Commander)
- Mock server for external APIs
- MailHog for email testing

## Best Practices

### 1. Journey Organization

```python
# journeys/__init__.py
from .auth import auth_flows
from .products import product_flows
from .orders import order_flows

ALL_JOURNEYS = [
    *auth_flows,
    *product_flows,
    *order_flows,
]
```

### 2. Action Reusability

```python
# actions/common.py
def with_auth(action):
    def wrapped(client, context):
        if not context.get("token"):
            login(client, context)
        return action(client, context)
    return wrapped

# Use in journeys
Step(name="protected_action", action=with_auth(my_action))
```

### 3. Environment Configuration

```yaml
# venomqa.yaml
base_url: "${API_BASE_URL:-http://localhost:8000}"
timeout: ${TIMEOUT:-30}

environments:
  dev:
    base_url: "http://localhost:8000"
  staging:
    base_url: "https://staging-api.example.com"
  prod:
    base_url: "https://api.example.com"
    timeout: 60
```

### 4. CI/CD Integration

```yaml
# .github/workflows/test.yml
- name: Run VenomQA
  run: |
    venomqa run \
      --config venomqa.yaml \
      --env ${{ matrix.environment }} \
      --tags ${{ matrix.tags }} \
      --parallel 4 \
      --output-dir reports
```

## Troubleshooting

### Common Issues

1. **Connection refused**: Ensure the API is running and accessible
2. **Auth token expired**: Check token refresh logic in journeys
3. **Timeout errors**: Increase `timeout` in venomqa.yaml
4. **Flaky tests**: Add retry configuration for unstable operations

### Debug Mode

```bash
# Enable verbose output
venomqa run --verbose --debug

# Run single journey
venomqa run --journey auth_login_flow --debug

# Dry run (validate without executing)
venomqa run --dry-run
```

## Contributing

To contribute new templates:

1. Follow the existing structure
2. Include docstrings and comments
3. Add type hints for Python code
4. Test with the full_stack_app example
5. Update this README

## License

MIT License - See LICENSE file for details.
