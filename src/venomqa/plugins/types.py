"""Plugin type definitions and enums for VenomQA.

This module defines the type system for the VenomQA plugin architecture,
including plugin types, hook priorities, and configuration schemas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PluginType(str, Enum):
    """Types of plugins supported by VenomQA.

    Each plugin type provides a different extension point:
    - REPORTER: Custom output formats (e.g., Slack, DataDog)
    - ADAPTER: New service integrations (e.g., custom databases)
    - GENERATOR: Custom data generation (e.g., domain-specific fixtures)
    - ACTION: Reusable action sets (e.g., common auth flows)
    - HOOK: Lifecycle callbacks (e.g., notifications, metrics)
    """

    REPORTER = "reporter"
    ADAPTER = "adapter"
    GENERATOR = "generator"
    ACTION = "action"
    HOOK = "hook"
    MIDDLEWARE = "middleware"
    ASSERTION = "assertion"


class HookPriority(int, Enum):
    """Priority levels for hook execution order.

    Lower numbers execute first. Use these to control the order
    in which plugins receive lifecycle events.
    """

    HIGHEST = 0
    HIGH = 25
    NORMAL = 50
    LOW = 75
    LOWEST = 100


class HookType(str, Enum):
    """Available lifecycle hooks in VenomQA.

    Plugins can subscribe to these hooks to receive callbacks
    during journey execution.
    """

    # Plugin lifecycle
    ON_LOAD = "on_load"
    ON_UNLOAD = "on_unload"

    # Journey lifecycle
    BEFORE_JOURNEY = "before_journey"
    AFTER_JOURNEY = "after_journey"
    ON_JOURNEY_ERROR = "on_journey_error"

    # Step lifecycle
    BEFORE_STEP = "before_step"
    AFTER_STEP = "after_step"
    ON_STEP_ERROR = "on_step_error"

    # Branch lifecycle
    BEFORE_BRANCH = "before_branch"
    AFTER_BRANCH = "after_branch"
    BEFORE_PATH = "before_path"
    AFTER_PATH = "after_path"

    # State lifecycle
    ON_CHECKPOINT = "on_checkpoint"
    ON_ROLLBACK = "on_rollback"

    # Error handling
    ON_FAILURE = "on_failure"
    ON_RETRY = "on_retry"
    ON_TIMEOUT = "on_timeout"

    # Reporting
    BEFORE_REPORT = "before_report"
    AFTER_REPORT = "after_report"


class PluginConfig(BaseModel):
    """Configuration for a single plugin.

    Plugins are configured in venomqa.yaml:

    ```yaml
    plugins:
      - name: venomqa-slack
        enabled: true
        config:
          webhook_url: https://hooks.slack.com/...
      - name: ./qa/plugins/custom.py
        enabled: true
    ```

    Attributes:
        name: Plugin name or path. Can be:
            - Entry point name: "venomqa-slack"
            - Package name: "venomqa_custom_reporter"
            - Local path: "./qa/plugins/custom.py"
        enabled: Whether the plugin is active
        priority: Hook execution priority
        config: Plugin-specific configuration
    """

    model_config = {"use_enum_values": True}

    name: str = Field(..., min_length=1, description="Plugin name or path")
    enabled: bool = Field(default=True, description="Whether plugin is enabled")
    priority: HookPriority = Field(default=HookPriority.NORMAL, description="Hook priority")
    config: dict[str, Any] = Field(default_factory=dict, description="Plugin configuration")


class PluginsConfig(BaseModel):
    """Configuration for all plugins.

    Attributes:
        plugins: List of plugin configurations
        auto_discover: Auto-discover plugins from entry points
        local_plugins_path: Path to local plugins directory
    """

    plugins: list[PluginConfig] = Field(default_factory=list)
    auto_discover: bool = Field(default=True, description="Auto-discover from entry points")
    local_plugins_path: str | None = Field(
        default="qa/plugins",
        description="Path to local plugins directory",
    )


@dataclass
class PluginInfo:
    """Runtime information about a loaded plugin.

    Attributes:
        name: Plugin name
        version: Plugin version
        plugin_type: Type of plugin
        description: Human-readable description
        author: Plugin author
        hooks: List of hooks this plugin subscribes to
        provides: What the plugin provides (reporter name, adapter type, etc.)
        requires: Required dependencies or capabilities
        config_schema: JSON schema for plugin configuration
    """

    name: str
    version: str = "0.0.0"
    plugin_type: PluginType = PluginType.HOOK
    description: str = ""
    author: str = ""
    hooks: list[HookType] = field(default_factory=list)
    provides: dict[str, Any] = field(default_factory=dict)
    requires: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] | None = None


@dataclass
class HookResult:
    """Result from executing a hook.

    Attributes:
        plugin_name: Name of the plugin that produced this result
        hook_type: The hook that was executed
        success: Whether the hook executed successfully
        data: Any data returned by the hook
        error: Error message if hook failed
        duration_ms: Execution time in milliseconds
    """

    plugin_name: str
    hook_type: HookType
    success: bool = True
    data: Any = None
    error: str | None = None
    duration_ms: float = 0.0


@dataclass
class StepContext:
    """Context passed to step hooks.

    Attributes:
        journey_name: Name of the current journey
        path_name: Name of the current path (or "main")
        step_name: Name of the current step
        step_number: Step index (1-based)
        step: The Step object
        context: Execution context with shared state
    """

    journey_name: str
    path_name: str
    step_name: str
    step_number: int
    step: Any  # Step object
    context: Any  # ExecutionContext


@dataclass
class JourneyContext:
    """Context passed to journey hooks.

    Attributes:
        journey: The Journey object
        client: HTTP client
        state_manager: State manager if available
        context: Execution context with shared state
    """

    journey: Any  # Journey object
    client: Any  # Client object
    state_manager: Any | None = None
    context: Any = None  # ExecutionContext


@dataclass
class BranchContext:
    """Context passed to branch hooks.

    Attributes:
        journey_name: Name of the current journey
        checkpoint_name: Name of the checkpoint being branched from
        paths: List of path names in this branch
        context: Execution context with shared state
    """

    journey_name: str
    checkpoint_name: str
    paths: list[str]
    context: Any  # ExecutionContext


@dataclass
class FailureContext:
    """Context passed to failure hooks.

    Attributes:
        journey_name: Name of the journey where failure occurred
        path_name: Name of the path where failure occurred
        step_name: Name of the step that failed
        error: The error that occurred
        request: Request data if available
        response: Response data if available
        traceback: Full traceback string
    """

    journey_name: str
    path_name: str
    step_name: str
    error: Exception | str
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    traceback: str | None = None
