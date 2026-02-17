"""Base plugin class for VenomQA.

This module provides the abstract base class that all VenomQA plugins
must inherit from. Plugins extend VenomQA's functionality through
a well-defined interface with lifecycle hooks.

Example:
    >>> from venomqa.plugins import VenomQAPlugin, PluginType
    >>>
    >>> class MyPlugin(VenomQAPlugin):
    ...     name = "my-plugin"
    ...     version = "1.0.0"
    ...     plugin_type = PluginType.HOOK
    ...
    ...     def on_journey_start(self, context):
    ...         print(f"Starting journey: {context.journey.name}")
    ...
    ...     def on_step_complete(self, step, result, context):
    ...         print(f"Step {step.name}: {'PASS' if result.success else 'FAIL'}")

Plugin Types:
    - REPORTER: Custom output formats
    - ADAPTER: Service integrations
    - GENERATOR: Data generation
    - ACTION: Reusable actions
    - HOOK: Lifecycle callbacks
"""

from __future__ import annotations

import logging
from abc import ABC
from typing import TYPE_CHECKING, Any

from venomqa.plugins.types import (
    BranchContext,
    FailureContext,
    HookPriority,
    HookType,
    JourneyContext,
    PluginInfo,
    PluginType,
    StepContext,
)

if TYPE_CHECKING:
    from venomqa.core.models import (
        Branch,
        BranchResult,
        Journey,
        JourneyResult,
        Path,
        PathResult,
        Step,
        StepResult,
    )
    from venomqa.reporters.base import BaseReporter

logger = logging.getLogger(__name__)


class VenomQAPlugin(ABC):
    """Abstract base class for VenomQA plugins.

    All plugins must inherit from this class and implement the required
    properties. Plugins receive lifecycle callbacks during journey execution.

    Class Attributes:
        name: Unique plugin identifier (required)
        version: Plugin version string (required)
        plugin_type: Type of plugin (default: HOOK)
        description: Human-readable description
        author: Plugin author name
        priority: Hook execution priority (lower = earlier)

    Instance Attributes:
        config: Plugin configuration dictionary
        enabled: Whether the plugin is currently active
        _initialized: Whether on_load has been called

    Example:
        >>> class SlackNotifier(VenomQAPlugin):
        ...     name = "slack-notifier"
        ...     version = "1.0.0"
        ...     plugin_type = PluginType.HOOK
        ...     description = "Send Slack notifications on test failures"
        ...
        ...     def on_load(self, config):
        ...         self.webhook_url = config.get("webhook_url")
        ...
        ...     def on_failure(self, context):
        ...         self._send_slack_message(context.error)
    """

    # Required class attributes
    name: str = ""
    version: str = "0.0.0"

    # Optional class attributes with defaults
    plugin_type: PluginType = PluginType.HOOK
    description: str = ""
    author: str = ""
    priority: HookPriority = HookPriority.NORMAL
    requires: list[str] = []

    def __init__(self) -> None:
        """Initialize the plugin instance."""
        self.config: dict[str, Any] = {}
        self.enabled: bool = True
        self._initialized: bool = False
        self._logger = logging.getLogger(f"venomqa.plugins.{self.name or 'unknown'}")

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Validate plugin class definition."""
        super().__init_subclass__(**kwargs)
        # Only warn for concrete implementations, not base classes
        if not cls.name and not cls.__name__.endswith("Plugin"):
            logger.warning(f"Plugin class {cls.__name__} has no 'name' attribute")

    @property
    def info(self) -> PluginInfo:
        """Get plugin information.

        Returns:
            PluginInfo object with plugin metadata.
        """
        return PluginInfo(
            name=self.name,
            version=self.version,
            plugin_type=self.plugin_type,
            description=self.description,
            author=self.author,
            hooks=self._get_implemented_hooks(),
            requires=list(self.requires),
        )

    def _get_implemented_hooks(self) -> list[HookType]:
        """Detect which hooks this plugin implements.

        Returns:
            List of HookType values for implemented hooks.
        """
        hooks: list[HookType] = []
        hook_methods = {
            "on_load": HookType.ON_LOAD,
            "on_unload": HookType.ON_UNLOAD,
            "on_journey_start": HookType.BEFORE_JOURNEY,
            "on_journey_complete": HookType.AFTER_JOURNEY,
            "on_journey_error": HookType.ON_JOURNEY_ERROR,
            "on_step_start": HookType.BEFORE_STEP,
            "on_step_complete": HookType.AFTER_STEP,
            "on_step_error": HookType.ON_STEP_ERROR,
            "on_branch_start": HookType.BEFORE_BRANCH,
            "on_branch_complete": HookType.AFTER_BRANCH,
            "on_path_start": HookType.BEFORE_PATH,
            "on_path_complete": HookType.AFTER_PATH,
            "on_checkpoint": HookType.ON_CHECKPOINT,
            "on_rollback": HookType.ON_ROLLBACK,
            "on_failure": HookType.ON_FAILURE,
            "on_retry": HookType.ON_RETRY,
            "on_timeout": HookType.ON_TIMEOUT,
        }

        for method_name, hook_type in hook_methods.items():
            method = getattr(self, method_name, None)
            if method is not None:
                # Check if method is overridden (not the base class stub)
                base_method = getattr(VenomQAPlugin, method_name, None)
                if method.__func__ is not getattr(base_method, "__func__", base_method):
                    hooks.append(hook_type)

        return hooks

    # =========================================================================
    # Plugin Lifecycle Hooks
    # =========================================================================

    def on_load(self, config: dict[str, Any]) -> None:
        """Called when the plugin is loaded.

        Use this to initialize resources, validate configuration,
        and set up any required state.

        Args:
            config: Plugin-specific configuration from venomqa.yaml

        Example:
            >>> def on_load(self, config):
            ...     self.api_key = config.get("api_key")
            ...     if not self.api_key:
            ...         raise ValueError("api_key is required")
            ...     self.client = ApiClient(self.api_key)
        """
        self.config = config
        self._initialized = True

    def on_unload(self) -> None:
        """Called when the plugin is unloaded.

        Use this to clean up resources, close connections,
        and perform any necessary teardown.

        Example:
            >>> def on_unload(self):
            ...     if hasattr(self, 'client'):
            ...         self.client.close()
        """
        self._initialized = False

    # =========================================================================
    # Journey Lifecycle Hooks
    # =========================================================================

    def on_journey_start(self, context: JourneyContext) -> None:
        """Called before a journey begins execution.

        Args:
            context: Journey context with journey, client, and state manager

        Example:
            >>> def on_journey_start(self, context):
            ...     self.start_time = time.time()
            ...     print(f"Starting: {context.journey.name}")
        """
        pass

    def on_journey_complete(
        self,
        journey: Journey,
        result: JourneyResult,
        context: JourneyContext,
    ) -> None:
        """Called after a journey completes (success or failure).

        Args:
            journey: The Journey object that was executed
            result: JourneyResult with execution details
            context: Journey context

        Example:
            >>> def on_journey_complete(self, journey, result, context):
            ...     duration = result.duration_ms / 1000
            ...     status = "PASSED" if result.success else "FAILED"
            ...     print(f"{journey.name}: {status} in {duration:.2f}s")
        """
        pass

    def on_journey_error(
        self,
        journey: Journey,
        error: Exception,
        context: JourneyContext,
    ) -> None:
        """Called when a journey fails with an unhandled exception.

        This is called in addition to on_journey_complete when an
        exception causes the journey to abort.

        Args:
            journey: The Journey that failed
            error: The exception that caused the failure
            context: Journey context
        """
        pass

    # =========================================================================
    # Step Lifecycle Hooks
    # =========================================================================

    def on_step_start(self, step: Step, context: StepContext) -> None:
        """Called before a step begins execution.

        Args:
            step: The Step about to be executed
            context: Step context with journey/path/step info
        """
        pass

    def on_step_complete(
        self,
        step: Step,
        result: StepResult,
        context: StepContext,
    ) -> None:
        """Called after a step completes (success or failure).

        Args:
            step: The Step that was executed
            result: StepResult with execution details
            context: Step context
        """
        pass

    def on_step_error(
        self,
        step: Step,
        error: Exception,
        context: StepContext,
    ) -> None:
        """Called when a step fails with an exception.

        Args:
            step: The Step that failed
            error: The exception that occurred
            context: Step context
        """
        pass

    # =========================================================================
    # Branch Lifecycle Hooks
    # =========================================================================

    def on_branch_start(self, branch: Branch, context: BranchContext) -> None:
        """Called before a branch begins exploring paths.

        Args:
            branch: The Branch about to be executed
            context: Branch context
        """
        pass

    def on_branch_complete(
        self,
        branch: Branch,
        result: BranchResult,
        context: BranchContext,
    ) -> None:
        """Called after all paths in a branch complete.

        Args:
            branch: The Branch that was executed
            result: BranchResult with path results
            context: Branch context
        """
        pass

    def on_path_start(self, path: Path, context: BranchContext) -> None:
        """Called before a path begins execution.

        Args:
            path: The Path about to be executed
            context: Branch context
        """
        pass

    def on_path_complete(
        self,
        path: Path,
        result: PathResult,
        context: BranchContext,
    ) -> None:
        """Called after a path completes.

        Args:
            path: The Path that was executed
            result: PathResult with step results
            context: Branch context
        """
        pass

    # =========================================================================
    # State Lifecycle Hooks
    # =========================================================================

    def on_checkpoint(self, checkpoint_name: str, context: JourneyContext) -> None:
        """Called when a checkpoint is created.

        Args:
            checkpoint_name: Name of the checkpoint
            context: Journey context
        """
        pass

    def on_rollback(self, checkpoint_name: str, context: JourneyContext) -> None:
        """Called when rolling back to a checkpoint.

        Args:
            checkpoint_name: Name of the checkpoint being rolled back to
            context: Journey context
        """
        pass

    # =========================================================================
    # Error Handling Hooks
    # =========================================================================

    def on_failure(self, context: FailureContext) -> None:
        """Called when a test failure is captured.

        This is the primary hook for failure notifications.

        Args:
            context: Failure context with full error details

        Example:
            >>> def on_failure(self, context):
            ...     self.send_alert(
            ...         f"Test failure in {context.journey_name}",
            ...         f"Step {context.step_name} failed: {context.error}"
            ...     )
        """
        pass

    def on_retry(
        self,
        step: Step,
        attempt: int,
        max_attempts: int,
        error: Exception,
        context: StepContext,
    ) -> None:
        """Called when a step is being retried.

        Args:
            step: The Step being retried
            attempt: Current attempt number (1-based)
            max_attempts: Maximum number of attempts
            error: The error that triggered the retry
            context: Step context
        """
        pass

    def on_timeout(self, step: Step, timeout_seconds: float, context: StepContext) -> None:
        """Called when a step times out.

        Args:
            step: The Step that timed out
            timeout_seconds: The timeout value that was exceeded
            context: Step context
        """
        pass

    # =========================================================================
    # Plugin Type-Specific Methods (Override in subclasses)
    # =========================================================================

    def get_reporter(self) -> BaseReporter | None:
        """Get the reporter provided by this plugin.

        Only implement for PluginType.REPORTER plugins.

        Returns:
            BaseReporter instance or None
        """
        return None

    def get_adapter(self, port_type: str) -> Any | None:
        """Get an adapter provided by this plugin.

        Only implement for PluginType.ADAPTER plugins.

        Args:
            port_type: The port type (e.g., "cache", "mail", "queue")

        Returns:
            Adapter instance or None
        """
        return None

    def get_generator(self, generator_name: str) -> Any | None:
        """Get a data generator provided by this plugin.

        Only implement for PluginType.GENERATOR plugins.

        Args:
            generator_name: Name of the generator

        Returns:
            Generator callable or None
        """
        return None

    def get_actions(self) -> dict[str, Any]:
        """Get actions provided by this plugin.

        Only implement for PluginType.ACTION plugins.

        Returns:
            Dictionary mapping action names to callables
        """
        return {}

    def get_assertions(self) -> dict[str, Any]:
        """Get custom assertions provided by this plugin.

        Only implement for PluginType.ASSERTION plugins.

        Returns:
            Dictionary mapping assertion names to callables
        """
        return {}


class ReporterPlugin(VenomQAPlugin):
    """Base class for reporter plugins.

    Subclass this for plugins that provide custom report formats.

    Example:
        >>> class SlackReporter(ReporterPlugin):
        ...     name = "slack-reporter"
        ...     version = "1.0.0"
        ...
        ...     def get_reporter(self):
        ...         return SlackWebhookReporter(self.config["webhook_url"])
    """

    plugin_type: PluginType = PluginType.REPORTER

    def get_reporter(self) -> BaseReporter | None:
        """Return the reporter instance.

        Must be implemented by subclasses.
        """
        raise NotImplementedError("ReporterPlugin must implement get_reporter()")


class AdapterPlugin(VenomQAPlugin):
    """Base class for adapter plugins.

    Subclass this for plugins that provide service adapters.

    Example:
        >>> class MongoDBPlugin(AdapterPlugin):
        ...     name = "mongodb-adapter"
        ...     version = "1.0.0"
        ...     provides_adapters = ["database"]
        ...
        ...     def get_adapter(self, port_type):
        ...         if port_type == "database":
        ...             return MongoDBAdapter(self.config)
        ...         return None
    """

    plugin_type: PluginType = PluginType.ADAPTER
    provides_adapters: list[str] = []

    def get_adapter(self, port_type: str) -> Any | None:
        """Return an adapter for the given port type.

        Must be implemented by subclasses.
        """
        raise NotImplementedError("AdapterPlugin must implement get_adapter()")


class GeneratorPlugin(VenomQAPlugin):
    """Base class for data generator plugins.

    Subclass this for plugins that provide custom data generators.

    Example:
        >>> class FakerExtPlugin(GeneratorPlugin):
        ...     name = "faker-ext"
        ...     version = "1.0.0"
        ...     provides_generators = ["credit_card", "iban"]
        ...
        ...     def get_generator(self, name):
        ...         generators = {
        ...             "credit_card": self._gen_credit_card,
        ...             "iban": self._gen_iban,
        ...         }
        ...         return generators.get(name)
    """

    plugin_type: PluginType = PluginType.GENERATOR
    provides_generators: list[str] = []

    def get_generator(self, generator_name: str) -> Any | None:
        """Return a generator callable.

        Must be implemented by subclasses.
        """
        raise NotImplementedError("GeneratorPlugin must implement get_generator()")


class ActionPlugin(VenomQAPlugin):
    """Base class for action plugins.

    Subclass this for plugins that provide reusable actions.

    Example:
        >>> class AuthActionsPlugin(ActionPlugin):
        ...     name = "auth-actions"
        ...     version = "1.0.0"
        ...
        ...     def get_actions(self):
        ...         return {
        ...             "auth.login": self._login_action,
        ...             "auth.logout": self._logout_action,
        ...             "auth.refresh_token": self._refresh_token,
        ...         }
    """

    plugin_type: PluginType = PluginType.ACTION

    def get_actions(self) -> dict[str, Any]:
        """Return a dictionary of action callables.

        Must be implemented by subclasses.
        """
        raise NotImplementedError("ActionPlugin must implement get_actions()")


class HookPlugin(VenomQAPlugin):
    """Base class for hook-only plugins.

    Subclass this for plugins that only provide lifecycle hooks
    without any other functionality.

    This is a convenience alias for VenomQAPlugin.
    """

    plugin_type: PluginType = PluginType.HOOK
