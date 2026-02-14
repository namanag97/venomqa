"""Plugin manager for VenomQA.

This module provides the central plugin management system that coordinates
plugin loading, registration, lifecycle management, and hook dispatching.

Example:
    >>> from venomqa.plugins import PluginManager
    >>>
    >>> # Create and configure manager
    >>> manager = PluginManager()
    >>> manager.load_plugins_from_config(config)
    >>>
    >>> # Get a specific plugin type
    >>> reporters = manager.get_reporters()
    >>> adapters = manager.get_adapters("cache")
    >>>
    >>> # Dispatch hooks during execution
    >>> manager.hooks.dispatch(HookType.BEFORE_JOURNEY, context=ctx)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from venomqa.plugins.base import (
    ActionPlugin,
    AdapterPlugin,
    GeneratorPlugin,
    ReporterPlugin,
    VenomQAPlugin,
)
from venomqa.plugins.hooks import HookManager, get_hook_manager
from venomqa.plugins.loader import PluginLoader, PluginLoadError
from venomqa.plugins.types import (
    BranchContext,
    FailureContext,
    HookType,
    JourneyContext,
    PluginConfig,
    PluginsConfig,
    PluginType,
    StepContext,
)

if TYPE_CHECKING:
    from venomqa.core.models import (
        Branch,
        BranchResult,
        Journey,
        JourneyResult,
        Path as JourneyPath,
        PathResult,
        Step,
        StepResult,
    )
    from venomqa.reporters.base import BaseReporter

logger = logging.getLogger(__name__)


class PluginManager:
    """Central manager for VenomQA plugins.

    The PluginManager coordinates all plugin-related functionality:
    - Loading and unloading plugins
    - Managing plugin lifecycle
    - Dispatching lifecycle hooks
    - Providing access to plugin-provided functionality

    Example:
        >>> manager = PluginManager()
        >>>
        >>> # Load plugins from config
        >>> manager.load_plugins_from_config(plugins_config)
        >>>
        >>> # Access plugin functionality
        >>> slack_reporter = manager.get_reporter("slack")
        >>> redis_cache = manager.get_adapter("cache", "redis")
        >>>
        >>> # Hook dispatch is handled automatically when using
        >>> # the PluginAwareRunner, but can be done manually:
        >>> manager.fire_journey_start(journey_context)
    """

    def __init__(
        self,
        local_plugins_path: str | Path | None = "qa/plugins",
        auto_discover: bool = True,
        fail_on_plugin_error: bool = False,
    ) -> None:
        """Initialize the plugin manager.

        Args:
            local_plugins_path: Path to local plugins directory
            auto_discover: Whether to auto-discover plugins
            fail_on_plugin_error: Whether plugin errors should propagate
        """
        self._loader = PluginLoader(
            local_path=local_plugins_path,
            auto_discover=auto_discover,
        )
        self._hooks = HookManager(fail_on_plugin_error=fail_on_plugin_error)
        self._plugins: dict[str, VenomQAPlugin] = {}
        self._reporters: dict[str, BaseReporter] = {}
        self._adapters: dict[str, dict[str, Any]] = {}
        self._generators: dict[str, Any] = {}
        self._actions: dict[str, Any] = {}
        self._assertions: dict[str, Any] = {}

    @property
    def hooks(self) -> HookManager:
        """Access the hook manager.

        Returns:
            The HookManager instance
        """
        return self._hooks

    def load_plugins_from_config(self, config: PluginsConfig) -> None:
        """Load all plugins from configuration.

        Args:
            config: Plugins configuration from venomqa.yaml
        """
        plugins = self._loader.load_all_from_config(config)

        for plugin in plugins:
            self._register_plugin(plugin)

    def load_plugin(
        self,
        name_or_path: str,
        config: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> VenomQAPlugin | None:
        """Load a single plugin by name or path.

        Args:
            name_or_path: Plugin name, module path, or file path
            config: Optional plugin configuration
            enabled: Whether the plugin should be enabled

        Returns:
            Plugin instance or None if not found
        """
        plugin_config = PluginConfig(
            name=name_or_path,
            config=config or {},
            enabled=enabled,
        )

        try:
            plugin = self._loader.load_from_config(plugin_config)
            if plugin:
                self._register_plugin(plugin)
            return plugin
        except PluginLoadError as e:
            logger.error(f"Failed to load plugin: {e}")
            return None

    def _register_plugin(self, plugin: VenomQAPlugin) -> None:
        """Register a plugin and extract its provided functionality.

        Args:
            plugin: The plugin instance to register
        """
        if plugin.name in self._plugins:
            logger.warning(f"Plugin {plugin.name} already registered, skipping")
            return

        self._plugins[plugin.name] = plugin
        self._hooks.register_plugin(plugin)

        # Extract plugin-provided functionality based on type
        self._extract_plugin_functionality(plugin)

        logger.info(
            f"Registered plugin: {plugin.name} v{plugin.version} ({plugin.plugin_type.value})"
        )

    def _extract_plugin_functionality(self, plugin: VenomQAPlugin) -> None:
        """Extract and register functionality provided by a plugin.

        Args:
            plugin: The plugin to extract functionality from
        """
        # Reporter plugins
        if plugin.plugin_type == PluginType.REPORTER or isinstance(plugin, ReporterPlugin):
            try:
                reporter = plugin.get_reporter()
                if reporter:
                    self._reporters[plugin.name] = reporter
            except NotImplementedError:
                pass

        # Adapter plugins
        if plugin.plugin_type == PluginType.ADAPTER or isinstance(plugin, AdapterPlugin):
            if hasattr(plugin, "provides_adapters"):
                for port_type in plugin.provides_adapters:
                    try:
                        adapter = plugin.get_adapter(port_type)
                        if adapter:
                            if port_type not in self._adapters:
                                self._adapters[port_type] = {}
                            self._adapters[port_type][plugin.name] = adapter
                    except NotImplementedError:
                        pass

        # Generator plugins
        if plugin.plugin_type == PluginType.GENERATOR or isinstance(plugin, GeneratorPlugin):
            if hasattr(plugin, "provides_generators"):
                for gen_name in plugin.provides_generators:
                    try:
                        generator = plugin.get_generator(gen_name)
                        if generator:
                            full_name = f"{plugin.name}.{gen_name}"
                            self._generators[full_name] = generator
                            self._generators[gen_name] = generator
                    except NotImplementedError:
                        pass

        # Action plugins
        if plugin.plugin_type == PluginType.ACTION or isinstance(plugin, ActionPlugin):
            try:
                actions = plugin.get_actions()
                self._actions.update(actions)
            except NotImplementedError:
                pass

        # Assertion plugins
        if plugin.plugin_type == PluginType.ASSERTION:
            try:
                assertions = plugin.get_assertions()
                self._assertions.update(assertions)
            except NotImplementedError:
                pass

    def unload_plugin(self, name: str) -> None:
        """Unload a plugin.

        Args:
            name: Plugin name to unload
        """
        if name not in self._plugins:
            logger.warning(f"Plugin {name} not registered")
            return

        plugin = self._plugins.pop(name)
        self._hooks.unregister_plugin(name)
        self._loader.unload(name)

        # Remove from functionality registries
        self._reporters.pop(name, None)
        for port_type in list(self._adapters.keys()):
            self._adapters[port_type].pop(name, None)

        logger.info(f"Unloaded plugin: {name}")

    # =========================================================================
    # Access Plugin Functionality
    # =========================================================================

    def get_plugin(self, name: str) -> VenomQAPlugin | None:
        """Get a registered plugin by name.

        Args:
            name: Plugin name

        Returns:
            Plugin instance or None
        """
        return self._plugins.get(name)

    def get_all_plugins(self) -> dict[str, VenomQAPlugin]:
        """Get all registered plugins.

        Returns:
            Dictionary mapping plugin names to instances
        """
        return dict(self._plugins)

    def get_plugins_by_type(self, plugin_type: PluginType) -> list[VenomQAPlugin]:
        """Get all plugins of a specific type.

        Args:
            plugin_type: The plugin type to filter by

        Returns:
            List of matching plugins
        """
        return [p for p in self._plugins.values() if p.plugin_type == plugin_type]

    def get_reporter(self, name: str) -> BaseReporter | None:
        """Get a reporter by plugin name.

        Args:
            name: Reporter plugin name

        Returns:
            BaseReporter instance or None
        """
        return self._reporters.get(name)

    def get_all_reporters(self) -> dict[str, BaseReporter]:
        """Get all registered reporters.

        Returns:
            Dictionary mapping plugin names to reporters
        """
        return dict(self._reporters)

    def get_adapter(self, port_type: str, plugin_name: str | None = None) -> Any | None:
        """Get an adapter for a port type.

        Args:
            port_type: The port type (e.g., "cache", "mail")
            plugin_name: Optional specific plugin name

        Returns:
            Adapter instance or None
        """
        adapters = self._adapters.get(port_type, {})

        if plugin_name:
            return adapters.get(plugin_name)

        # Return first available adapter
        if adapters:
            return next(iter(adapters.values()))

        return None

    def get_all_adapters(self, port_type: str) -> dict[str, Any]:
        """Get all adapters for a port type.

        Args:
            port_type: The port type

        Returns:
            Dictionary mapping plugin names to adapters
        """
        return dict(self._adapters.get(port_type, {}))

    def get_generator(self, name: str) -> Any | None:
        """Get a data generator by name.

        Args:
            name: Generator name

        Returns:
            Generator callable or None
        """
        return self._generators.get(name)

    def get_action(self, name: str) -> Any | None:
        """Get an action by name.

        Args:
            name: Action name

        Returns:
            Action callable or None
        """
        return self._actions.get(name)

    def get_all_actions(self) -> dict[str, Any]:
        """Get all registered actions.

        Returns:
            Dictionary mapping action names to callables
        """
        return dict(self._actions)

    def get_assertion(self, name: str) -> Any | None:
        """Get a custom assertion by name.

        Args:
            name: Assertion name

        Returns:
            Assertion callable or None
        """
        return self._assertions.get(name)

    # =========================================================================
    # Hook Dispatch Convenience Methods
    # =========================================================================

    def fire_journey_start(self, context: JourneyContext) -> None:
        """Fire the before_journey hook.

        Args:
            context: Journey context
        """
        self._hooks.dispatch(HookType.BEFORE_JOURNEY, context)

    def fire_journey_complete(
        self,
        journey: Journey,
        result: JourneyResult,
        context: JourneyContext,
    ) -> None:
        """Fire the after_journey hook.

        Args:
            journey: The completed journey
            result: Journey result
            context: Journey context
        """
        self._hooks.dispatch(HookType.AFTER_JOURNEY, journey, result, context)

    def fire_journey_error(
        self,
        journey: Journey,
        error: Exception,
        context: JourneyContext,
    ) -> None:
        """Fire the on_journey_error hook.

        Args:
            journey: The failed journey
            error: The exception
            context: Journey context
        """
        self._hooks.dispatch(HookType.ON_JOURNEY_ERROR, journey, error, context)

    def fire_step_start(self, step: Step, context: StepContext) -> None:
        """Fire the before_step hook.

        Args:
            step: The step about to execute
            context: Step context
        """
        self._hooks.dispatch(HookType.BEFORE_STEP, step, context)

    def fire_step_complete(
        self,
        step: Step,
        result: StepResult,
        context: StepContext,
    ) -> None:
        """Fire the after_step hook.

        Args:
            step: The completed step
            result: Step result
            context: Step context
        """
        self._hooks.dispatch(HookType.AFTER_STEP, step, result, context)

    def fire_step_error(
        self,
        step: Step,
        error: Exception,
        context: StepContext,
    ) -> None:
        """Fire the on_step_error hook.

        Args:
            step: The failed step
            error: The exception
            context: Step context
        """
        self._hooks.dispatch(HookType.ON_STEP_ERROR, step, error, context)

    def fire_branch_start(self, branch: Branch, context: BranchContext) -> None:
        """Fire the before_branch hook.

        Args:
            branch: The branch about to execute
            context: Branch context
        """
        self._hooks.dispatch(HookType.BEFORE_BRANCH, branch, context)

    def fire_branch_complete(
        self,
        branch: Branch,
        result: BranchResult,
        context: BranchContext,
    ) -> None:
        """Fire the after_branch hook.

        Args:
            branch: The completed branch
            result: Branch result
            context: Branch context
        """
        self._hooks.dispatch(HookType.AFTER_BRANCH, branch, result, context)

    def fire_path_start(self, path: JourneyPath, context: BranchContext) -> None:
        """Fire the before_path hook.

        Args:
            path: The path about to execute
            context: Branch context
        """
        self._hooks.dispatch(HookType.BEFORE_PATH, path, context)

    def fire_path_complete(
        self,
        path: JourneyPath,
        result: PathResult,
        context: BranchContext,
    ) -> None:
        """Fire the after_path hook.

        Args:
            path: The completed path
            result: Path result
            context: Branch context
        """
        self._hooks.dispatch(HookType.AFTER_PATH, path, result, context)

    def fire_checkpoint(self, checkpoint_name: str, context: JourneyContext) -> None:
        """Fire the on_checkpoint hook.

        Args:
            checkpoint_name: Name of the checkpoint
            context: Journey context
        """
        self._hooks.dispatch(HookType.ON_CHECKPOINT, checkpoint_name, context)

    def fire_rollback(self, checkpoint_name: str, context: JourneyContext) -> None:
        """Fire the on_rollback hook.

        Args:
            checkpoint_name: Name of the checkpoint
            context: Journey context
        """
        self._hooks.dispatch(HookType.ON_ROLLBACK, checkpoint_name, context)

    def fire_failure(self, context: FailureContext) -> None:
        """Fire the on_failure hook.

        Args:
            context: Failure context
        """
        self._hooks.dispatch(HookType.ON_FAILURE, context)

    def fire_retry(
        self,
        step: Step,
        attempt: int,
        max_attempts: int,
        error: Exception,
        context: StepContext,
    ) -> None:
        """Fire the on_retry hook.

        Args:
            step: The step being retried
            attempt: Current attempt number
            max_attempts: Maximum attempts
            error: The error
            context: Step context
        """
        self._hooks.dispatch(HookType.ON_RETRY, step, attempt, max_attempts, error, context)

    def fire_timeout(self, step: Step, timeout: float, context: StepContext) -> None:
        """Fire the on_timeout hook.

        Args:
            step: The timed out step
            timeout: Timeout value
            context: Step context
        """
        self._hooks.dispatch(HookType.ON_TIMEOUT, step, timeout, context)

    # =========================================================================
    # Lifecycle Management
    # =========================================================================

    def get_stats(self) -> dict[str, Any]:
        """Get plugin statistics.

        Returns:
            Dictionary with plugin statistics
        """
        return {
            "plugin_count": len(self._plugins),
            "reporter_count": len(self._reporters),
            "adapter_types": list(self._adapters.keys()),
            "generator_count": len(self._generators),
            "action_count": len(self._actions),
            "hook_stats": self._hooks.get_stats(),
        }

    def close(self) -> None:
        """Shutdown the plugin manager and clean up resources."""
        for name in list(self._plugins.keys()):
            self.unload_plugin(name)

        self._hooks.close()
        self._loader.clear()

        self._reporters.clear()
        self._adapters.clear()
        self._generators.clear()
        self._actions.clear()
        self._assertions.clear()


# Global plugin manager instance
_global_manager: PluginManager | None = None


def get_plugin_manager() -> PluginManager:
    """Get the global plugin manager instance.

    Returns:
        The global PluginManager instance
    """
    global _global_manager
    if _global_manager is None:
        _global_manager = PluginManager()
    return _global_manager


def reset_plugin_manager() -> None:
    """Reset the global plugin manager (mainly for testing)."""
    global _global_manager
    if _global_manager is not None:
        _global_manager.close()
    _global_manager = None
