"""Console logging plugin for VenomQA.

This plugin provides detailed console output during test execution,
useful for debugging and local development.

Configuration:
    ```yaml
    plugins:
      - name: venomqa.plugins.examples.console_logger
        config:
          level: debug
          show_timestamps: true
          show_request_body: false
          show_response_body: false
          color: true
    ```

Example:
    >>> from venomqa.plugins.examples import ConsoleLoggerPlugin
    >>>
    >>> plugin = ConsoleLoggerPlugin()
    >>> plugin.on_load({"level": "debug", "color": True})
"""

from __future__ import annotations

import sys
from datetime import datetime
from typing import TYPE_CHECKING, Any

from venomqa.plugins.base import HookPlugin
from venomqa.plugins.types import (
    BranchContext,
    FailureContext,
    HookPriority,
    JourneyContext,
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


class ConsoleLoggerPlugin(HookPlugin):
    """Log test events to console with formatting.

    This plugin provides rich console output during test execution,
    with optional colors and timestamps.

    Configuration Options:
        level: Log level (debug, info, warning, error)
        show_timestamps: Show timestamps in output
        show_request_body: Show request bodies
        show_response_body: Show response bodies
        color: Use ANSI colors
        indent: Indentation for nested output
    """

    name = "console-logger"
    version = "1.0.0"
    plugin_type = PluginType.HOOK
    description = "Log test events to console"
    author = "VenomQA Team"
    priority = HookPriority.HIGHEST  # Run first to log before other plugins

    # ANSI color codes
    COLORS = {
        "reset": "\033[0m",
        "bold": "\033[1m",
        "dim": "\033[2m",
        "red": "\033[31m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "blue": "\033[34m",
        "magenta": "\033[35m",
        "cyan": "\033[36m",
        "white": "\033[37m",
    }

    def __init__(self) -> None:
        super().__init__()
        self.level: str = "info"
        self.show_timestamps: bool = True
        self.show_request_body: bool = False
        self.show_response_body: bool = False
        self.use_color: bool = True
        self.indent: str = "  "
        self._depth: int = 0

    def on_load(self, config: dict[str, Any]) -> None:
        """Load plugin configuration.

        Args:
            config: Plugin configuration
        """
        super().on_load(config)

        self.level = config.get("level", "info")
        self.show_timestamps = config.get("show_timestamps", True)
        self.show_request_body = config.get("show_request_body", False)
        self.show_response_body = config.get("show_response_body", False)
        self.use_color = config.get("color", True)
        self.indent = config.get("indent", "  ")

        # Disable colors if not a TTY
        if not sys.stdout.isatty():
            self.use_color = False

    def _color(self, text: str, color: str) -> str:
        """Apply color to text.

        Args:
            text: Text to color
            color: Color name

        Returns:
            Colored text
        """
        if not self.use_color:
            return text
        return f"{self.COLORS.get(color, '')}{text}{self.COLORS['reset']}"

    def _timestamp(self) -> str:
        """Get current timestamp string.

        Returns:
            Formatted timestamp or empty string
        """
        if not self.show_timestamps:
            return ""
        return self._color(
            f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] ",
            "dim",
        )

    def _indent(self) -> str:
        """Get indentation for current depth.

        Returns:
            Indentation string
        """
        return self.indent * self._depth

    def _log(self, message: str, color: str = "white") -> None:
        """Log a message to console.

        Args:
            message: Message to log
            color: Color for the message
        """
        prefix = self._timestamp()
        indent = self._indent()
        colored_message = self._color(message, color)
        print(f"{prefix}{indent}{colored_message}")

    def on_journey_start(self, context: JourneyContext) -> None:
        """Log journey start.

        Args:
            context: Journey context
        """
        journey = context.journey
        self._log(
            f"{'=' * 60}",
            "blue",
        )
        self._log(
            f"JOURNEY: {journey.name}",
            "bold",
        )
        if journey.description:
            self._log(
                f"Description: {journey.description}",
                "dim",
            )
        self._log(
            f"{'=' * 60}",
            "blue",
        )
        self._depth = 1

    def on_journey_complete(
        self,
        journey: Journey,
        result: JourneyResult,
        context: JourneyContext,
    ) -> None:
        """Log journey completion.

        Args:
            journey: The completed journey
            result: Journey result
            context: Journey context
        """
        self._depth = 0
        self._log(
            f"{'=' * 60}",
            "blue",
        )

        if result.success:
            status = self._color("PASSED", "green")
        else:
            status = self._color("FAILED", "red")

        self._log(f"JOURNEY {status}: {journey.name}")
        self._log(
            f"Duration: {result.duration_ms / 1000:.2f}s | "
            f"Steps: {result.passed_steps}/{result.total_steps} | "
            f"Issues: {len(result.issues)}",
            "dim",
        )
        self._log(
            f"{'=' * 60}",
            "blue",
        )

    def on_step_start(self, step: Step, context: StepContext) -> None:
        """Log step start.

        Args:
            step: The step about to execute
            context: Step context
        """
        if self.level == "debug":
            self._log(
                f"Step {context.step_number}: {step.name}...",
                "cyan",
            )

    def on_step_complete(
        self,
        step: Step,
        result: StepResult,
        context: StepContext,
    ) -> None:
        """Log step completion.

        Args:
            step: The completed step
            result: Step result
            context: Step context
        """
        duration = f"({result.duration_ms:.0f}ms)"

        if result.success:
            status = self._color("[PASS]", "green")
        else:
            status = self._color("[FAIL]", "red")

        self._log(f"{status} Step {context.step_number}: {step.name} {duration}")

        if not result.success and result.error:
            self._depth += 1
            self._log(f"Error: {result.error}", "red")
            self._depth -= 1

        if self.show_request_body and result.request:
            self._depth += 1
            self._log(f"Request: {result.request}", "dim")
            self._depth -= 1

        if self.show_response_body and result.response:
            self._depth += 1
            self._log(f"Response: {result.response}", "dim")
            self._depth -= 1

    def on_branch_start(self, branch: Branch, context: BranchContext) -> None:
        """Log branch start.

        Args:
            branch: The branch about to execute
            context: Branch context
        """
        self._log(
            f"BRANCH from checkpoint '{branch.checkpoint_name}' "
            f"({len(branch.paths)} paths)",
            "magenta",
        )
        self._depth += 1

    def on_branch_complete(
        self,
        branch: Branch,
        result: BranchResult,
        context: BranchContext,
    ) -> None:
        """Log branch completion.

        Args:
            branch: The completed branch
            result: Branch result
            context: Branch context
        """
        self._depth -= 1

        if result.all_passed:
            status = self._color("PASSED", "green")
        else:
            status = self._color("FAILED", "red")

        self._log(
            f"BRANCH {status}: {result.passed_paths}/{len(result.path_results)} paths passed",
            "magenta",
        )

    def on_path_start(self, path: Path, context: BranchContext) -> None:
        """Log path start.

        Args:
            path: The path about to execute
            context: Branch context
        """
        self._log(f"PATH: {path.name}", "yellow")
        self._depth += 1

    def on_path_complete(
        self,
        path: Path,
        result: PathResult,
        context: BranchContext,
    ) -> None:
        """Log path completion.

        Args:
            path: The completed path
            result: Path result
            context: Branch context
        """
        self._depth -= 1

        if result.success:
            status = self._color("[PASS]", "green")
        else:
            status = self._color("[FAIL]", "red")

        duration = f"({result.total_duration_ms:.0f}ms)"
        self._log(f"{status} PATH: {path.name} {duration}", "yellow")

    def on_checkpoint(self, checkpoint_name: str, context: JourneyContext) -> None:
        """Log checkpoint creation.

        Args:
            checkpoint_name: Checkpoint name
            context: Journey context
        """
        self._log(f"CHECKPOINT: {checkpoint_name}", "blue")

    def on_rollback(self, checkpoint_name: str, context: JourneyContext) -> None:
        """Log rollback.

        Args:
            checkpoint_name: Checkpoint name
            context: Journey context
        """
        self._log(f"ROLLBACK to: {checkpoint_name}", "yellow")

    def on_failure(self, context: FailureContext) -> None:
        """Log failure details.

        Args:
            context: Failure context
        """
        if self.level in ("debug", "info"):
            self._log(
                f"FAILURE: {context.journey_name}/{context.path_name}/{context.step_name}",
                "red",
            )
            self._depth += 1
            self._log(f"Error: {context.error}", "red")
            self._depth -= 1


# Allow direct import as plugin
Plugin = ConsoleLoggerPlugin
plugin = ConsoleLoggerPlugin()
