"""Plugin system for VenomQA.

This module provides a comprehensive plugin architecture for extending
VenomQA's functionality. Plugins can add:
- Custom reporters (Slack, DataDog, custom formats)
- Service adapters (databases, caches, queues)
- Data generators (domain-specific test data)
- Reusable actions (common test patterns)
- Lifecycle hooks (notifications, metrics, logging)

Plugin Discovery:
    Plugins can be discovered from multiple sources:
    1. Entry points: pip install venomqa-plugin-xxx
    2. Local directory: qa/plugins/*.py
    3. Config paths: Explicit paths in venomqa.yaml

Creating a Plugin:
    ```python
    from venomqa.plugins import VenomQAPlugin, PluginType

    class MyPlugin(VenomQAPlugin):
        name = "my-plugin"
        version = "1.0.0"
        plugin_type = PluginType.HOOK

        def on_load(self, config):
            self.api_key = config.get("api_key")

        def on_journey_complete(self, journey, result, context):
            if not result.success:
                self._send_notification(result)
    ```

Configuration:
    ```yaml
    # venomqa.yaml
    plugins:
      auto_discover: true
      local_plugins_path: qa/plugins
      plugins:
        - name: venomqa-slack
          config:
            webhook_url: https://hooks.slack.com/...
        - name: ./qa/plugins/custom.py
          enabled: true
    ```

Entry Point Registration (pyproject.toml):
    ```toml
    [project.entry-points."venomqa.plugins"]
    my-plugin = "my_package.plugin:MyPlugin"
    ```

Example:
    >>> from venomqa.plugins import PluginManager, VenomQAPlugin
    >>>
    >>> # Create plugin manager
    >>> manager = PluginManager()
    >>>
    >>> # Load plugins from config
    >>> manager.load_plugins_from_config(config)
    >>>
    >>> # Or load a specific plugin
    >>> manager.load_plugin("venomqa-slack", config={"webhook_url": "..."})
    >>>
    >>> # Access plugin functionality
    >>> reporter = manager.get_reporter("slack")
"""

# Base classes
from venomqa.plugins.base import (
    ActionPlugin,
    AdapterPlugin,
    GeneratorPlugin,
    HookPlugin,
    ReporterPlugin,
    VenomQAPlugin,
)

# Discovery (existing)
from venomqa.plugins.discovery import (
    action,
    discover_actions,
    discover_all,
    discover_fixtures,
    discover_from_actions_dir,
    discover_from_fixtures_dir,
    discover_from_journeys_dir,
    discover_journeys,
    extension,
    fixture,
    journey,
)

# Hook management
from venomqa.plugins.hooks import (
    HookManager,
    HookSubscription,
    get_hook_manager,
    reset_hook_manager,
)

# Plugin loader
from venomqa.plugins.loader import (
    PluginLoader,
    PluginLoadError,
    discover_plugins,
    load_plugin,
)

# Plugin manager
from venomqa.plugins.manager import (
    PluginManager,
    get_plugin_manager,
    reset_plugin_manager,
)

# Registry (existing)
from venomqa.plugins.registry import FixtureInfo, JourneyRegistry, get_registry

# Types
from venomqa.plugins.types import (
    BranchContext,
    FailureContext,
    HookPriority,
    HookResult,
    HookType,
    JourneyContext,
    PluginConfig,
    PluginInfo,
    PluginsConfig,
    PluginType,
    StepContext,
)

__all__ = [
    # Base classes
    "VenomQAPlugin",
    "ReporterPlugin",
    "AdapterPlugin",
    "GeneratorPlugin",
    "ActionPlugin",
    "HookPlugin",
    # Types
    "PluginType",
    "HookType",
    "HookPriority",
    "PluginConfig",
    "PluginsConfig",
    "PluginInfo",
    "HookResult",
    "StepContext",
    "JourneyContext",
    "BranchContext",
    "FailureContext",
    # Plugin management
    "PluginManager",
    "get_plugin_manager",
    "reset_plugin_manager",
    # Hook management
    "HookManager",
    "HookSubscription",
    "get_hook_manager",
    "reset_hook_manager",
    # Loader
    "PluginLoader",
    "PluginLoadError",
    "discover_plugins",
    "load_plugin",
    # Existing discovery decorators
    "journey",
    "action",
    "fixture",
    "extension",
    # Existing registry
    "JourneyRegistry",
    "FixtureInfo",
    "get_registry",
    # Existing discovery functions
    "discover_journeys",
    "discover_from_journeys_dir",
    "discover_actions",
    "discover_from_actions_dir",
    "discover_fixtures",
    "discover_from_fixtures_dir",
    "discover_all",
]
