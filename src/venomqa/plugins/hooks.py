"""Hook management system for VenomQA plugins.

This module provides the hook registry and dispatcher that enables
plugins to subscribe to lifecycle events during test execution.

The hook system supports:
- Multiple plugins subscribing to the same hook
- Priority-based execution ordering
- Error isolation (one plugin failure doesn't break others)
- Async and sync hook handlers
- Hook result aggregation

Example:
    >>> from venomqa.plugins.hooks import HookManager
    >>>
    >>> manager = HookManager()
    >>> manager.register_plugin(my_plugin)
    >>>
    >>> # Dispatch a hook to all subscribers
    >>> results = manager.dispatch(HookType.BEFORE_JOURNEY, context=journey_context)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from venomqa.plugins.types import (
    HookPriority,
    HookResult,
    HookType,
)

if TYPE_CHECKING:
    from venomqa.plugins.base import VenomQAPlugin

# Import VenomQAPlugin at runtime to avoid circular imports
# but we need it for method comparison
_VenomQAPlugin = None


def _get_base_plugin_class():
    """Lazy import of VenomQAPlugin to avoid circular imports."""
    global _VenomQAPlugin
    if _VenomQAPlugin is None:
        from venomqa.plugins.base import VenomQAPlugin
        _VenomQAPlugin = VenomQAPlugin
    return _VenomQAPlugin

logger = logging.getLogger(__name__)


class HookSubscription:
    """Represents a plugin's subscription to a hook.

    Attributes:
        plugin: The plugin instance
        hook_type: The hook being subscribed to
        handler: The method to call
        priority: Execution priority
    """

    def __init__(
        self,
        plugin: VenomQAPlugin,
        hook_type: HookType,
        handler: Any,
        priority: HookPriority,
    ) -> None:
        self.plugin = plugin
        self.hook_type = hook_type
        self.handler = handler
        self.priority = priority

    def __lt__(self, other: HookSubscription) -> bool:
        """Sort by priority (lower number = higher priority)."""
        return self.priority.value < other.priority.value


class HookManager:
    """Manages hook subscriptions and dispatching.

    The HookManager maintains a registry of plugins and their hook
    subscriptions. When a hook is dispatched, all subscribed handlers
    are called in priority order.

    Features:
        - Thread-safe hook dispatch
        - Error isolation between plugins
        - Performance tracking
        - Hook result aggregation

    Example:
        >>> manager = HookManager()
        >>> manager.register_plugin(slack_plugin)
        >>> manager.register_plugin(metrics_plugin)
        >>>
        >>> # Dispatch hook to all subscribers
        >>> manager.dispatch(HookType.ON_FAILURE, context=failure_context)
    """

    def __init__(
        self,
        fail_on_plugin_error: bool = False,
        max_workers: int = 4,
    ) -> None:
        """Initialize the hook manager.

        Args:
            fail_on_plugin_error: If True, plugin errors propagate up
            max_workers: Thread pool size for parallel hook execution
        """
        self._subscriptions: dict[HookType, list[HookSubscription]] = defaultdict(list)
        self._plugins: dict[str, VenomQAPlugin] = {}
        self._fail_on_error = fail_on_plugin_error
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"calls": 0, "errors": 0, "total_ms": 0.0}
        )

    def register_plugin(self, plugin: VenomQAPlugin) -> None:
        """Register a plugin and subscribe its hooks.

        Args:
            plugin: The plugin instance to register

        Raises:
            ValueError: If a plugin with the same name is already registered
        """
        if plugin.name in self._plugins:
            raise ValueError(f"Plugin '{plugin.name}' is already registered")

        self._plugins[plugin.name] = plugin
        self._subscribe_plugin_hooks(plugin)
        logger.info(f"Registered plugin: {plugin.name} v{plugin.version}")

    def unregister_plugin(self, plugin_name: str) -> None:
        """Unregister a plugin and remove its hook subscriptions.

        Args:
            plugin_name: Name of the plugin to unregister
        """
        if plugin_name not in self._plugins:
            logger.warning(f"Plugin '{plugin_name}' not registered")
            return

        plugin = self._plugins.pop(plugin_name)

        # Remove all subscriptions for this plugin
        for hook_type in list(self._subscriptions.keys()):
            self._subscriptions[hook_type] = [
                sub for sub in self._subscriptions[hook_type] if sub.plugin.name != plugin_name
            ]

        # Call unload hook
        try:
            plugin.on_unload()
        except Exception as e:
            logger.error(f"Error unloading plugin {plugin_name}: {e}")

        logger.info(f"Unregistered plugin: {plugin_name}")

    def _subscribe_plugin_hooks(self, plugin: VenomQAPlugin) -> None:
        """Subscribe a plugin to its implemented hooks.

        Args:
            plugin: The plugin to subscribe
        """
        hook_mappings = {
            HookType.ON_LOAD: "on_load",
            HookType.ON_UNLOAD: "on_unload",
            HookType.BEFORE_JOURNEY: "on_journey_start",
            HookType.AFTER_JOURNEY: "on_journey_complete",
            HookType.ON_JOURNEY_ERROR: "on_journey_error",
            HookType.BEFORE_STEP: "on_step_start",
            HookType.AFTER_STEP: "on_step_complete",
            HookType.ON_STEP_ERROR: "on_step_error",
            HookType.BEFORE_BRANCH: "on_branch_start",
            HookType.AFTER_BRANCH: "on_branch_complete",
            HookType.BEFORE_PATH: "on_path_start",
            HookType.AFTER_PATH: "on_path_complete",
            HookType.ON_CHECKPOINT: "on_checkpoint",
            HookType.ON_ROLLBACK: "on_rollback",
            HookType.ON_FAILURE: "on_failure",
            HookType.ON_RETRY: "on_retry",
            HookType.ON_TIMEOUT: "on_timeout",
        }

        plugin_base_class = _get_base_plugin_class()

        for hook_type, method_name in hook_mappings.items():
            handler = getattr(plugin, method_name, None)
            if handler is None:
                continue

            # Check if method is overridden
            base_method = getattr(plugin_base_class, method_name, None)
            if base_method is not None:
                # Compare function objects (unwrap bound methods)
                if hasattr(handler, "__func__") and hasattr(base_method, "__func__"):
                    if handler.__func__ is base_method.__func__:
                        continue
                elif handler is base_method:
                    continue

            subscription = HookSubscription(
                plugin=plugin,
                hook_type=hook_type,
                handler=handler,
                priority=plugin.priority,
            )
            self._subscriptions[hook_type].append(subscription)
            self._subscriptions[hook_type].sort()

            logger.debug(f"Subscribed {plugin.name} to {hook_type.value}")

    def dispatch(
        self,
        hook_type: HookType,
        *args: Any,
        **kwargs: Any,
    ) -> list[HookResult]:
        """Dispatch a hook to all subscribed plugins.

        Handlers are called in priority order (lowest number first).
        Errors are logged but don't stop execution of other handlers
        unless fail_on_plugin_error is True.

        Args:
            hook_type: The hook to dispatch
            *args: Positional arguments for the hook handler
            **kwargs: Keyword arguments for the hook handler

        Returns:
            List of HookResult objects from each handler
        """
        subscriptions = self._subscriptions.get(hook_type, [])
        if not subscriptions:
            return []

        results: list[HookResult] = []

        for subscription in subscriptions:
            if not subscription.plugin.enabled:
                continue

            start_time = time.perf_counter()
            result = HookResult(
                plugin_name=subscription.plugin.name,
                hook_type=hook_type,
            )

            try:
                data = subscription.handler(*args, **kwargs)
                result.data = data
                result.success = True
            except Exception as e:
                result.success = False
                result.error = f"{type(e).__name__}: {e}"
                logger.error(
                    f"Plugin {subscription.plugin.name} error in {hook_type.value}: {e}",
                    exc_info=True,
                )

                if self._fail_on_error:
                    raise

            result.duration_ms = (time.perf_counter() - start_time) * 1000
            results.append(result)

            # Update stats
            stats = self._stats[subscription.plugin.name]
            stats["calls"] += 1
            stats["total_ms"] += result.duration_ms
            if not result.success:
                stats["errors"] += 1

        return results

    async def dispatch_async(
        self,
        hook_type: HookType,
        *args: Any,
        **kwargs: Any,
    ) -> list[HookResult]:
        """Dispatch a hook asynchronously to all subscribed plugins.

        Args:
            hook_type: The hook to dispatch
            *args: Positional arguments for the hook handler
            **kwargs: Keyword arguments for the hook handler

        Returns:
            List of HookResult objects from each handler
        """
        subscriptions = self._subscriptions.get(hook_type, [])
        if not subscriptions:
            return []

        async def call_handler(subscription: HookSubscription) -> HookResult:
            if not subscription.plugin.enabled:
                return HookResult(
                    plugin_name=subscription.plugin.name,
                    hook_type=hook_type,
                    success=True,
                )

            start_time = time.perf_counter()
            result = HookResult(
                plugin_name=subscription.plugin.name,
                hook_type=hook_type,
            )

            try:
                handler = subscription.handler
                if asyncio.iscoroutinefunction(handler):
                    data = await handler(*args, **kwargs)
                else:
                    # Run sync handler in thread pool
                    loop = asyncio.get_event_loop()
                    data = await loop.run_in_executor(
                        self._executor,
                        lambda: handler(*args, **kwargs),
                    )
                result.data = data
                result.success = True
            except Exception as e:
                result.success = False
                result.error = f"{type(e).__name__}: {e}"
                logger.error(
                    f"Plugin {subscription.plugin.name} error in {hook_type.value}: {e}"
                )

                if self._fail_on_error:
                    raise

            result.duration_ms = (time.perf_counter() - start_time) * 1000
            return result

        # Execute all handlers (respecting priority order)
        results = []
        for subscription in subscriptions:
            result = await call_handler(subscription)
            results.append(result)

        return results

    def dispatch_parallel(
        self,
        hook_type: HookType,
        *args: Any,
        **kwargs: Any,
    ) -> list[HookResult]:
        """Dispatch a hook to all plugins in parallel.

        Use this for hooks where order doesn't matter and you want
        maximum throughput (e.g., sending notifications).

        Args:
            hook_type: The hook to dispatch
            *args: Positional arguments for the hook handler
            **kwargs: Keyword arguments for the hook handler

        Returns:
            List of HookResult objects from each handler
        """
        subscriptions = self._subscriptions.get(hook_type, [])
        if not subscriptions:
            return []

        def call_handler(subscription: HookSubscription) -> HookResult:
            if not subscription.plugin.enabled:
                return HookResult(
                    plugin_name=subscription.plugin.name,
                    hook_type=hook_type,
                    success=True,
                )

            start_time = time.perf_counter()
            result = HookResult(
                plugin_name=subscription.plugin.name,
                hook_type=hook_type,
            )

            try:
                data = subscription.handler(*args, **kwargs)
                result.data = data
                result.success = True
            except Exception as e:
                result.success = False
                result.error = f"{type(e).__name__}: {e}"
                logger.error(
                    f"Plugin {subscription.plugin.name} error in {hook_type.value}: {e}"
                )

            result.duration_ms = (time.perf_counter() - start_time) * 1000
            return result

        # Submit all handlers to thread pool
        futures = [
            self._executor.submit(call_handler, sub)
            for sub in subscriptions
            if sub.plugin.enabled
        ]

        # Collect results
        results = [future.result() for future in futures]

        # Update stats
        for result in results:
            stats = self._stats[result.plugin_name]
            stats["calls"] += 1
            stats["total_ms"] += result.duration_ms
            if not result.success:
                stats["errors"] += 1

        return results

    def get_subscriptions(self, hook_type: HookType) -> list[HookSubscription]:
        """Get all subscriptions for a hook type.

        Args:
            hook_type: The hook type to query

        Returns:
            List of subscriptions (sorted by priority)
        """
        return list(self._subscriptions.get(hook_type, []))

    def get_stats(self) -> dict[str, dict[str, Any]]:
        """Get plugin execution statistics.

        Returns:
            Dictionary mapping plugin names to stats (calls, errors, total_ms)
        """
        return dict(self._stats)

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

    def clear(self) -> None:
        """Unregister all plugins and clear subscriptions."""
        for plugin_name in list(self._plugins.keys()):
            self.unregister_plugin(plugin_name)
        self._subscriptions.clear()
        self._stats.clear()

    def close(self) -> None:
        """Shutdown the hook manager and clean up resources."""
        self.clear()
        self._executor.shutdown(wait=True)


# Global hook manager instance
_global_hook_manager: HookManager | None = None


def get_hook_manager() -> HookManager:
    """Get the global hook manager instance.

    Returns:
        The global HookManager instance
    """
    global _global_hook_manager
    if _global_hook_manager is None:
        _global_hook_manager = HookManager()
    return _global_hook_manager


def reset_hook_manager() -> None:
    """Reset the global hook manager (mainly for testing)."""
    global _global_hook_manager
    if _global_hook_manager is not None:
        _global_hook_manager.close()
    _global_hook_manager = None
