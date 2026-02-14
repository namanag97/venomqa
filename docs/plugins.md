# VenomQA Plugin System

VenomQA provides a comprehensive plugin architecture that enables you to extend the framework's functionality. Plugins can add custom reporters, service adapters, data generators, reusable actions, and lifecycle hooks.

## Overview

The plugin system supports five main extension points:

1. **Reporters** - Custom output formats (Slack, DataDog, custom formats)
2. **Adapters** - Service integrations (databases, caches, queues)
3. **Generators** - Data generation (domain-specific test data)
4. **Actions** - Reusable action sets (common test patterns)
5. **Hooks** - Lifecycle callbacks (notifications, metrics, logging)

## Creating a Plugin

### Basic Plugin Structure

All plugins inherit from `VenomQAPlugin`:

```python
from venomqa.plugins import VenomQAPlugin, PluginType, HookPriority

class MyPlugin(VenomQAPlugin):
    # Required: Plugin identifier
    name = "my-plugin"
    version = "1.0.0"

    # Optional: Plugin type (default: HOOK)
    plugin_type = PluginType.HOOK
    description = "My custom plugin"
    author = "Your Name"
    priority = HookPriority.NORMAL

    def on_load(self, config: dict) -> None:
        """Called when plugin is loaded."""
        super().on_load(config)
        self.api_key = config.get("api_key")

    def on_journey_start(self, context):
        """Called before each journey."""
        print(f"Starting: {context.journey.name}")

    def on_failure(self, context):
        """Called when a test fails."""
        self.send_alert(context.error)
```

### Plugin Types

#### Hook Plugin

For plugins that only need lifecycle callbacks:

```python
from venomqa.plugins import HookPlugin, HookPriority

class NotifierPlugin(HookPlugin):
    name = "notifier"
    version = "1.0.0"
    priority = HookPriority.LOW  # Run after other plugins

    def on_failure(self, context):
        self.send_notification(context)
```

#### Reporter Plugin

For plugins that provide custom report formats:

```python
from venomqa.plugins import ReporterPlugin
from venomqa.reporters.base import BaseReporter

class MyReporter(BaseReporter):
    @property
    def file_extension(self) -> str:
        return ".html"

    def generate(self, results):
        return "<html>...</html>"

class MyReporterPlugin(ReporterPlugin):
    name = "my-reporter"
    version = "1.0.0"

    def get_reporter(self) -> BaseReporter:
        return MyReporter()
```

#### Adapter Plugin

For plugins that provide service adapters:

```python
from venomqa.plugins import AdapterPlugin

class MongoDBPlugin(AdapterPlugin):
    name = "mongodb"
    version = "1.0.0"
    provides_adapters = ["database"]

    def get_adapter(self, port_type: str):
        if port_type == "database":
            return MongoDBAdapter(self.config)
        return None
```

#### Action Plugin

For plugins that provide reusable actions:

```python
from venomqa.plugins import ActionPlugin

class AuthActionsPlugin(ActionPlugin):
    name = "auth-actions"
    version = "1.0.0"

    def get_actions(self) -> dict:
        return {
            "auth.login": self._login,
            "auth.logout": self._logout,
            "auth.refresh": self._refresh_token,
        }

    def _login(self, client, ctx, **kwargs):
        return client.post("/auth/login", json=kwargs)
```

## Available Hooks

### Plugin Lifecycle

| Hook | Method | Called When |
|------|--------|-------------|
| `ON_LOAD` | `on_load(config)` | Plugin is loaded |
| `ON_UNLOAD` | `on_unload()` | Plugin is unloaded |

### Journey Lifecycle

| Hook | Method | Called When |
|------|--------|-------------|
| `BEFORE_JOURNEY` | `on_journey_start(context)` | Before journey execution |
| `AFTER_JOURNEY` | `on_journey_complete(journey, result, context)` | After journey completes |
| `ON_JOURNEY_ERROR` | `on_journey_error(journey, error, context)` | Journey fails with exception |

### Step Lifecycle

| Hook | Method | Called When |
|------|--------|-------------|
| `BEFORE_STEP` | `on_step_start(step, context)` | Before step execution |
| `AFTER_STEP` | `on_step_complete(step, result, context)` | After step completes |
| `ON_STEP_ERROR` | `on_step_error(step, error, context)` | Step fails with exception |

### Branch Lifecycle

| Hook | Method | Called When |
|------|--------|-------------|
| `BEFORE_BRANCH` | `on_branch_start(branch, context)` | Before branch exploration |
| `AFTER_BRANCH` | `on_branch_complete(branch, result, context)` | After all paths complete |
| `BEFORE_PATH` | `on_path_start(path, context)` | Before path execution |
| `AFTER_PATH` | `on_path_complete(path, result, context)` | After path completes |

### State Lifecycle

| Hook | Method | Called When |
|------|--------|-------------|
| `ON_CHECKPOINT` | `on_checkpoint(checkpoint_name, context)` | Checkpoint created |
| `ON_ROLLBACK` | `on_rollback(checkpoint_name, context)` | Rolling back to checkpoint |

### Error Handling

| Hook | Method | Called When |
|------|--------|-------------|
| `ON_FAILURE` | `on_failure(context)` | Test failure captured |
| `ON_RETRY` | `on_retry(step, attempt, max_attempts, error, context)` | Step being retried |
| `ON_TIMEOUT` | `on_timeout(step, timeout, context)` | Step times out |

## Plugin Configuration

### YAML Configuration

Configure plugins in `venomqa.yaml`:

```yaml
plugins:
  # Auto-discover plugins from entry points
  auto_discover: true

  # Local plugins directory
  local_plugins_path: qa/plugins

  # Plugin configurations
  plugins:
    # Reference by entry point name
    - name: venomqa-slack
      enabled: true
      priority: low
      config:
        webhook_url: https://hooks.slack.com/services/...
        channel: "#qa-alerts"

    # Reference by module path
    - name: venomqa.plugins.examples.timing_analyzer
      config:
        threshold_warning_ms: 1000

    # Reference local file
    - name: ./qa/plugins/custom.py
      enabled: true
```

### Programmatic Configuration

```python
from venomqa.plugins import (
    PluginManager,
    PluginsConfig,
    PluginConfig,
    HookPriority,
)

config = PluginsConfig(
    auto_discover=True,
    local_plugins_path="qa/plugins",
    plugins=[
        PluginConfig(
            name="my-plugin",
            enabled=True,
            priority=HookPriority.HIGH,
            config={"api_key": "xxx"},
        ),
    ],
)

manager = PluginManager()
manager.load_plugins_from_config(config)
```

## Plugin Discovery

Plugins are discovered from multiple sources:

### 1. Entry Points (Recommended)

Register plugins in `pyproject.toml`:

```toml
[project.entry-points."venomqa.plugins"]
my-plugin = "my_package.plugin:MyPlugin"
```

Install the package and VenomQA will auto-discover it.

### 2. Local Directory

Place Python files in `qa/plugins/`:

```python
# qa/plugins/custom.py
from venomqa.plugins import VenomQAPlugin

class CustomPlugin(VenomQAPlugin):
    name = "custom"
    version = "1.0.0"
    ...

# Either export directly:
plugin = CustomPlugin()

# Or use 'Plugin' class name:
Plugin = CustomPlugin
```

### 3. Module Import

Load by module path:

```python
manager.load_plugin("my_package.plugins.custom")
```

## Built-in Example Plugins

VenomQA includes several example plugins:

### Console Logger

Rich console output during test execution:

```yaml
plugins:
  - name: venomqa.plugins.examples.console_logger
    config:
      level: debug
      color: true
      show_timestamps: true
```

### Timing Analyzer

Analyze step execution times:

```yaml
plugins:
  - name: venomqa.plugins.examples.timing_analyzer
    config:
      threshold_warning_ms: 1000
      threshold_critical_ms: 5000
      track_percentiles: [50, 90, 95, 99]
```

### Slack Notifier

Send Slack notifications:

```yaml
plugins:
  - name: venomqa.plugins.examples.slack_notifier
    config:
      webhook_url: ${SLACK_WEBHOOK_URL}
      channel: "#qa-alerts"
      notify_on_failure: true
      mention_on_failure: "@qa-team"
```

### DataDog Metrics

Report metrics to DataDog:

```yaml
plugins:
  - name: venomqa.plugins.examples.datadog_metrics
    config:
      api_key: ${DATADOG_API_KEY}
      prefix: venomqa
      tags:
        - env:production
        - team:qa
```

### Custom Assertions

Additional assertion helpers:

```yaml
plugins:
  - name: venomqa.plugins.examples.custom_assertions
    config:
      strict_mode: false
```

Use in steps:

```python
from venomqa.plugins import get_plugin_manager

manager = get_plugin_manager()
assertions = manager.get_assertion("assert_json_path")

def my_step(client, ctx):
    response = client.get("/api/users")
    assertions["assert_json_path"](response, "data.users.0.name", "John")
```

## Hook Priority

Control hook execution order with priorities:

```python
from venomqa.plugins import HookPriority

class EarlyPlugin(VenomQAPlugin):
    priority = HookPriority.HIGHEST  # Run first (0)

class LatePlugin(VenomQAPlugin):
    priority = HookPriority.LOWEST   # Run last (100)
```

Priority levels:
- `HIGHEST` (0)
- `HIGH` (25)
- `NORMAL` (50) - default
- `LOW` (75)
- `LOWEST` (100)

## Error Handling

Plugin errors are isolated by default:

```python
# In PluginManager
manager = PluginManager(fail_on_plugin_error=False)  # Default

# If True, plugin errors propagate and abort test execution
manager = PluginManager(fail_on_plugin_error=True)
```

## Context Objects

### JourneyContext

```python
@dataclass
class JourneyContext:
    journey: Journey          # The Journey object
    client: Client           # HTTP client
    state_manager: Any       # State manager (optional)
    context: ExecutionContext  # Shared state
```

### StepContext

```python
@dataclass
class StepContext:
    journey_name: str
    path_name: str
    step_name: str
    step_number: int
    step: Step
    context: ExecutionContext
```

### FailureContext

```python
@dataclass
class FailureContext:
    journey_name: str
    path_name: str
    step_name: str
    error: Exception | str
    request: dict | None
    response: dict | None
    traceback: str | None
```

## Best Practices

1. **Keep plugins focused** - Each plugin should do one thing well
2. **Use appropriate priority** - Logging plugins should run early, notifications late
3. **Handle errors gracefully** - Don't let plugin failures break tests
4. **Document configuration** - Clearly document required and optional config
5. **Version your plugins** - Follow semantic versioning
6. **Test your plugins** - Write unit tests for plugin logic
