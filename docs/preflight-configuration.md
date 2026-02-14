# Preflight Configuration

VenomQA's preflight system runs quick smoke tests against your API before
executing a full test suite. This guide explains how to configure those tests
using a YAML file so you can reuse the same checks across environments.

## Quick Start

Generate a starter config:

```bash
venomqa smoke-test --init > preflight.yaml
```

Run smoke tests from the config:

```bash
venomqa smoke-test --config preflight.yaml
```

## Configuration File Format

A preflight config is a single YAML file with the following top-level keys:

```yaml
base_url: "http://localhost:8000"
timeout: 10.0

auth:
  token_env_var: "API_TOKEN"
  header: "Authorization"
  prefix: "Bearer"

health_checks: [...]
auth_checks: [...]
crud_checks: [...]
list_checks: [...]
custom_checks: [...]
```

### Base Settings

| Field      | Type    | Default                   | Description                     |
|------------|---------|---------------------------|---------------------------------|
| `base_url` | string  | `http://localhost:8000`   | Root URL of the API under test  |
| `timeout`  | float   | `10.0`                    | HTTP timeout in seconds         |

### Authentication

```yaml
auth:
  token_env_var: "API_TOKEN"   # Read token from this env var
  # token: "eyJ..."           # Or hardcode a token
  header: "Authorization"      # HTTP header name
  prefix: "Bearer"             # Prefix before the token value
```

| Field           | Type   | Default          | Description                          |
|-----------------|--------|------------------|--------------------------------------|
| `token`         | string | -                | Hardcoded auth token                 |
| `token_env_var` | string | -                | Env var name containing the token    |
| `header`        | string | `Authorization`  | HTTP header to set                   |
| `prefix`        | string | `Bearer`         | Prefix before the token value        |

If both `token` and `token_env_var` are set, the explicit `token` takes precedence.

### Health Checks

Verify the API is running and healthy.

```yaml
health_checks:
  - path: /health
    expected_status: [200]
    expected_json:
      status: "healthy"
    timeout: 5.0  # Override global timeout

  - path: /health/ready
    expected_status: [200]
```

| Field             | Type       | Default  | Description                          |
|-------------------|------------|----------|--------------------------------------|
| `path`            | string     | `/health`| Endpoint path                        |
| `expected_status` | list[int]  | `[200]`  | HTTP status codes treated as success |
| `expected_json`   | dict       | -        | Response body must be a superset     |
| `timeout`         | float      | -        | Per-check timeout override           |

### Auth Checks

Verify that authenticated requests succeed.

```yaml
auth_checks:
  - path: /api/v1/me
    expected_status: [200]

  - path: /api/v1/workspaces
    method: GET
    expected_status: [200]
```

| Field             | Type       | Default       | Description              |
|-------------------|------------|---------------|--------------------------|
| `path`            | string     | `/api/v1/me`  | Auth-protected endpoint  |
| `method`          | string     | `GET`         | HTTP method              |
| `expected_status` | list[int]  | `[200]`       | Success status codes     |

### CRUD Checks

Verify resource creation works.

```yaml
crud_checks:
  - name: "Create workspace"
    path: /api/v1/workspaces
    method: POST
    payload:
      name: "Preflight Test ${RANDOM}"
    expected_status: [201, 409]
    cleanup_path: /api/v1/workspaces/${id}
```

| Field             | Type       | Default             | Description                    |
|-------------------|------------|---------------------|--------------------------------|
| `name`            | string     | -                   | Human-readable label           |
| `path`            | string     | `/api/v1/resources` | POST endpoint path             |
| `method`          | string     | `POST`              | HTTP method                    |
| `payload`         | dict       | `{}`                | JSON body to send              |
| `expected_status` | list[int]  | `[200, 201, 409]`   | Success status codes           |
| `cleanup_path`    | string     | -                   | DELETE path template (future)  |

### List Checks

Verify list/pagination endpoints return data.

```yaml
list_checks:
  - path: /api/v1/items
    expected_type: array

  - path: /api/v1/orders
    expected_type: paginated
```

| Field             | Type       | Default             | Description                   |
|-------------------|------------|---------------------|-------------------------------|
| `path`            | string     | `/api/v1/resources` | GET endpoint path             |
| `expected_status` | list[int]  | `[200]`             | Success status codes          |
| `expected_type`   | string     | `array`             | `"array"` or `"paginated"`   |

### Custom Checks

Run any arbitrary HTTP request with validation.

```yaml
custom_checks:
  - name: "OpenAPI spec available"
    method: GET
    path: /openapi.json
    expected_status: [200]
    expected_json:
      openapi: "3.0.0"

  - name: "Create via PUT"
    method: PUT
    path: /api/v1/settings
    payload:
      theme: "dark"
    headers:
      X-Custom: "value"
    expected_status: [200, 204]
```

| Field             | Type       | Default          | Description                    |
|-------------------|------------|------------------|--------------------------------|
| `name`            | string     | `Custom check`   | Human-readable label           |
| `method`          | string     | `GET`            | HTTP method                    |
| `path`            | string     | `/`              | Endpoint path                  |
| `payload`         | dict       | -                | JSON body (for POST/PUT/PATCH) |
| `headers`         | dict       | -                | Extra HTTP headers             |
| `expected_status` | list[int]  | `[200]`          | Success status codes           |
| `expected_json`   | dict       | -                | Response must be a superset    |

## Environment Variable Substitution

All string values in the YAML support `${VAR}` substitution.

| Syntax               | Behavior                                         |
|----------------------|--------------------------------------------------|
| `${VAR}`             | Replaced with env var value; **error** if not set |
| `${VAR:default}`     | Replaced with env var value or `default`          |
| `${RANDOM}`          | Random 8-character hex string                    |
| `${UUID}`            | Random UUID4 string                              |
| `${TIMESTAMP}`       | Current UNIX timestamp                           |

Example:

```yaml
base_url: "${API_URL:http://localhost:8000}"
crud_checks:
  - path: /api/v1/items
    payload:
      name: "test-${RANDOM}"
      id: "${UUID}"
```

## CLI Usage

```bash
# Run from config file
venomqa smoke-test --config preflight.yaml

# Override base URL (e.g., for staging)
venomqa smoke-test --config preflight.yaml --base-url http://staging:8000

# Override token
venomqa smoke-test --config preflight.yaml --token $STAGING_TOKEN

# JSON output (for CI)
venomqa smoke-test --config preflight.yaml --json

# Generate example config
venomqa smoke-test --init > preflight.yaml
```

## Programmatic Usage

```python
from venomqa.preflight import SmokeTest, PreflightConfig

# From YAML file
smoke = SmokeTest.from_yaml("preflight.yaml")
report = smoke.run_all()
report.print_report()

# From config object
config = PreflightConfig(
    base_url="http://localhost:8000",
    health_checks=[HealthCheckConfig(path="/health")],
    crud_checks=[CRUDCheckConfig(path="/items", payload={"name": "test"})],
)
smoke = SmokeTest.from_config(config)
report = smoke.run_all()

# From dict (e.g., loaded from another source)
config = PreflightConfig.from_dict({
    "base_url": "http://localhost:8000",
    "health_checks": [{"path": "/health"}],
})
smoke = SmokeTest.from_config(config)
```

## Example Configs

VenomQA includes pre-built configs for common frameworks in
`examples/preflight_configs/`:

- **`generic_rest_api.yaml`** -- Minimal config for any REST API
- **`fastapi_app.yaml`** -- FastAPI with OpenAPI docs
- **`django_app.yaml`** -- Django REST Framework
- **`dip_api.yaml`** -- DIP API (the original use case)

Copy one as a starting point:

```bash
cp examples/preflight_configs/fastapi_app.yaml preflight.yaml
# Edit to match your API
venomqa smoke-test --config preflight.yaml
```
