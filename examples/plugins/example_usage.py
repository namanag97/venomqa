#!/usr/bin/env python3
"""Example: Using the VenomQA Plugin System.

This example demonstrates how to:
1. Create custom plugins
2. Register and configure plugins
3. Use built-in example plugins
4. Handle lifecycle hooks
"""

from venomqa import (
    Client,
    Journey,
    JourneyResult,
    Step,
    VenomQAPlugin,
    HookPlugin,
    ReporterPlugin,
    PluginManager,
    PluginType,
    HookPriority,
    JourneyContext,
    StepContext,
    FailureContext,
    PluginsConfig,
    PluginConfig,
)
from venomqa.reporters.base import BaseReporter
from typing import Any


# =============================================================================
# Example 1: Simple Hook Plugin
# =============================================================================


class TestCounterPlugin(HookPlugin):
    """A simple plugin that counts test events.

    This demonstrates the basic structure of a hook plugin.
    """

    name = "test-counter"
    version = "1.0.0"
    description = "Count test events for metrics"
    author = "Example Author"
    priority = HookPriority.HIGH  # Run early

    def __init__(self):
        super().__init__()
        self.journey_count = 0
        self.step_count = 0
        self.pass_count = 0
        self.fail_count = 0

    def on_load(self, config: dict[str, Any]) -> None:
        """Initialize with optional config."""
        super().on_load(config)
        # Reset counters if configured
        if config.get("reset_on_load", True):
            self.journey_count = 0
            self.step_count = 0
            self.pass_count = 0
            self.fail_count = 0
        print(f"[{self.name}] Plugin loaded!")

    def on_journey_start(self, context: JourneyContext) -> None:
        """Count journey starts."""
        self.journey_count += 1
        print(f"[{self.name}] Starting journey #{self.journey_count}: {context.journey.name}")

    def on_journey_complete(self, journey, result: JourneyResult, context: JourneyContext) -> None:
        """Report journey completion."""
        status = "PASSED" if result.success else "FAILED"
        print(f"[{self.name}] Journey {journey.name} {status} in {result.duration_ms:.0f}ms")

    def on_step_complete(self, step, result, context: StepContext) -> None:
        """Count step results."""
        self.step_count += 1
        if result.success:
            self.pass_count += 1
        else:
            self.fail_count += 1

    def on_failure(self, context: FailureContext) -> None:
        """Log failures."""
        print(f"[{self.name}] FAILURE: {context.step_name} - {context.error}")

    def get_stats(self) -> dict[str, int]:
        """Get current statistics."""
        return {
            "journeys": self.journey_count,
            "steps": self.step_count,
            "passed": self.pass_count,
            "failed": self.fail_count,
        }


# =============================================================================
# Example 2: Custom Reporter Plugin
# =============================================================================


class SimpleTextReporter(BaseReporter):
    """A simple text-based reporter."""

    def __init__(self):
        super().__init__()

    @property
    def file_extension(self) -> str:
        return ".txt"

    def generate(self, results: list[JourneyResult]) -> str:
        """Generate a simple text report."""
        lines = [
            "=" * 60,
            "VenomQA Test Report",
            "=" * 60,
            "",
        ]

        total_journeys = len(results)
        passed = sum(1 for r in results if r.success)

        lines.append(f"Total Journeys: {total_journeys}")
        lines.append(f"Passed: {passed}")
        lines.append(f"Failed: {total_journeys - passed}")
        lines.append("")

        for result in results:
            status = "PASS" if result.success else "FAIL"
            lines.append(f"[{status}] {result.journey_name} ({result.duration_ms:.0f}ms)")

            for issue in result.issues:
                lines.append(f"    - {issue.step}: {issue.error}")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)


class TextReporterPlugin(ReporterPlugin):
    """Plugin that provides the simple text reporter."""

    name = "text-reporter"
    version = "1.0.0"
    description = "Simple text-based test reporter"

    def __init__(self):
        super().__init__()
        self._reporter = None

    def on_load(self, config: dict[str, Any]) -> None:
        """Initialize reporter."""
        super().on_load(config)
        self._reporter = SimpleTextReporter()

    def get_reporter(self) -> BaseReporter:
        """Return the reporter instance."""
        return self._reporter


# =============================================================================
# Example 3: Using the Plugin Manager
# =============================================================================


def example_manual_plugin_registration():
    """Example of manually registering plugins."""
    print("\n" + "=" * 60)
    print("Example: Manual Plugin Registration")
    print("=" * 60 + "\n")

    # Create plugin manager
    manager = PluginManager(auto_discover=False)

    # Create and register plugins
    counter_plugin = TestCounterPlugin()
    reporter_plugin = TextReporterPlugin()

    # Register with manager
    manager._register_plugin(counter_plugin)
    manager._register_plugin(reporter_plugin)

    # Initialize plugins
    counter_plugin.on_load({"reset_on_load": True})
    reporter_plugin.on_load({})

    # List registered plugins
    print("Registered plugins:")
    for name, plugin in manager.get_all_plugins().items():
        print(f"  - {name} v{plugin.version} ({plugin.plugin_type.value})")

    # Get specific functionality
    reporter = manager.get_reporter("text-reporter")
    print(f"\nText reporter available: {reporter is not None}")

    return manager


def example_config_based_loading():
    """Example of loading plugins from configuration."""
    print("\n" + "=" * 60)
    print("Example: Config-Based Plugin Loading")
    print("=" * 60 + "\n")

    # Define plugin configuration (as would be in venomqa.yaml)
    config = PluginsConfig(
        auto_discover=False,  # Don't auto-discover entry points
        local_plugins_path=None,  # No local plugins directory
        plugins=[
            # Reference built-in example plugins
            PluginConfig(
                name="venomqa.plugins.examples.console_logger",
                enabled=True,
                config={
                    "level": "debug",
                    "color": True,
                    "show_timestamps": True,
                },
            ),
            PluginConfig(
                name="venomqa.plugins.examples.timing_analyzer",
                enabled=True,
                config={
                    "threshold_warning_ms": 500,
                    "threshold_critical_ms": 2000,
                },
            ),
        ],
    )

    # Create manager and load plugins
    manager = PluginManager(auto_discover=False)
    manager.load_plugins_from_config(config)

    print("Plugins loaded from config:")
    for name, plugin in manager.get_all_plugins().items():
        print(f"  - {name} (enabled: {plugin.enabled})")

    return manager


def example_hook_dispatch():
    """Example of manually dispatching hooks."""
    print("\n" + "=" * 60)
    print("Example: Hook Dispatch")
    print("=" * 60 + "\n")

    # Create manager and register counter plugin
    manager = PluginManager(auto_discover=False)
    counter = TestCounterPlugin()
    manager._register_plugin(counter)
    counter.on_load({})

    # Create test journey and context
    journey = Journey(
        name="example_journey",
        description="An example journey",
        steps=[
            Step(name="step1", action=lambda c, ctx: None),
            Step(name="step2", action=lambda c, ctx: None),
        ],
    )

    # Create context
    context = JourneyContext(
        journey=journey,
        client=None,
    )

    # Manually fire hooks (normally done by JourneyRunner)
    manager.fire_journey_start(context)

    # Simulate step execution
    step_context = StepContext(
        journey_name=journey.name,
        path_name="main",
        step_name="step1",
        step_number=1,
        step=journey.steps[0],
        context=None,
    )
    manager.fire_step_start(journey.steps[0], step_context)

    # Simulate failure
    failure_context = FailureContext(
        journey_name=journey.name,
        path_name="main",
        step_name="step1",
        error="Connection refused",
    )
    manager.fire_failure(failure_context)

    print(f"\nPlugin stats: {counter.get_stats()}")

    return manager


# =============================================================================
# Example 4: Creating a Complete Custom Plugin
# =============================================================================


class MetricsCollectorPlugin(VenomQAPlugin):
    """A more complete plugin that collects metrics.

    This demonstrates:
    - Multiple hook implementations
    - Configuration handling
    - State management across hooks
    - Providing multiple features
    """

    name = "metrics-collector"
    version = "1.0.0"
    plugin_type = PluginType.HOOK
    description = "Collect and report test execution metrics"
    author = "VenomQA Examples"
    priority = HookPriority.NORMAL
    requires = []  # No special requirements

    def __init__(self):
        super().__init__()
        self._metrics: dict[str, Any] = {}
        self._current_journey: str | None = None

    def on_load(self, config: dict[str, Any]) -> None:
        """Initialize metrics collection."""
        super().on_load(config)
        self._metrics = {
            "total_journeys": 0,
            "passed_journeys": 0,
            "failed_journeys": 0,
            "total_steps": 0,
            "passed_steps": 0,
            "failed_steps": 0,
            "total_duration_ms": 0,
            "step_durations": [],
            "failures": [],
        }
        self._logger.info("Metrics collector initialized")

    def on_journey_start(self, context: JourneyContext) -> None:
        """Track journey start."""
        self._current_journey = context.journey.name
        self._metrics["total_journeys"] += 1

    def on_journey_complete(self, journey, result, context: JourneyContext) -> None:
        """Record journey metrics."""
        if result.success:
            self._metrics["passed_journeys"] += 1
        else:
            self._metrics["failed_journeys"] += 1

        self._metrics["total_duration_ms"] += result.duration_ms
        self._current_journey = None

    def on_step_complete(self, step, result, context: StepContext) -> None:
        """Record step metrics."""
        self._metrics["total_steps"] += 1

        if result.success:
            self._metrics["passed_steps"] += 1
        else:
            self._metrics["failed_steps"] += 1

        self._metrics["step_durations"].append({
            "journey": context.journey_name,
            "step": step.name,
            "duration_ms": result.duration_ms,
            "success": result.success,
        })

    def on_failure(self, context: FailureContext) -> None:
        """Record failure details."""
        self._metrics["failures"].append({
            "journey": context.journey_name,
            "step": context.step_name,
            "error": str(context.error),
        })

    def get_metrics(self) -> dict[str, Any]:
        """Get collected metrics."""
        metrics = dict(self._metrics)

        # Calculate derived metrics
        durations = [d["duration_ms"] for d in metrics["step_durations"]]
        if durations:
            metrics["avg_step_duration_ms"] = sum(durations) / len(durations)
            metrics["max_step_duration_ms"] = max(durations)
            metrics["min_step_duration_ms"] = min(durations)

        if metrics["total_journeys"] > 0:
            metrics["pass_rate"] = metrics["passed_journeys"] / metrics["total_journeys"]

        return metrics

    def print_report(self) -> None:
        """Print a metrics report."""
        metrics = self.get_metrics()

        print("\n" + "=" * 60)
        print("METRICS REPORT")
        print("=" * 60)
        print(f"Journeys: {metrics['passed_journeys']}/{metrics['total_journeys']} passed")
        print(f"Steps: {metrics['passed_steps']}/{metrics['total_steps']} passed")
        print(f"Total Duration: {metrics['total_duration_ms']:.0f}ms")

        if "avg_step_duration_ms" in metrics:
            print(f"Avg Step Duration: {metrics['avg_step_duration_ms']:.2f}ms")

        if metrics["failures"]:
            print(f"\nFailures ({len(metrics['failures'])}):")
            for failure in metrics["failures"]:
                print(f"  - {failure['journey']}/{failure['step']}: {failure['error']}")

        print("=" * 60 + "\n")


# =============================================================================
# Main Example Runner
# =============================================================================


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("VenomQA Plugin System Examples")
    print("=" * 60)

    # Example 1: Manual registration
    manager1 = example_manual_plugin_registration()
    manager1.close()

    # Example 2: Config-based loading
    try:
        manager2 = example_config_based_loading()
        manager2.close()
    except Exception as e:
        print(f"Note: Config loading example failed: {e}")

    # Example 3: Hook dispatch
    manager3 = example_hook_dispatch()
    manager3.close()

    # Example 4: Complete custom plugin
    print("\n" + "=" * 60)
    print("Example: Complete Custom Plugin")
    print("=" * 60 + "\n")

    collector = MetricsCollectorPlugin()
    collector.on_load({})

    # Simulate some activity
    from datetime import datetime
    journey = Journey(name="test", steps=[])
    context = JourneyContext(journey=journey, client=None)
    collector.on_journey_start(context)

    # Simulate step
    from venomqa.core.models import StepResult
    step = Step(name="test_step", action=lambda c, ctx: None)
    step_ctx = StepContext(
        journey_name="test",
        path_name="main",
        step_name="test_step",
        step_number=1,
        step=step,
        context=None,
    )
    now = datetime.now()
    result = StepResult(
        step_name="test_step",
        success=True,
        started_at=now,
        finished_at=now,
        duration_ms=42.5,
    )
    collector.on_step_complete(step, result, step_ctx)

    # Simulate failure
    failure_ctx = FailureContext(
        journey_name="test",
        path_name="main",
        step_name="failing_step",
        error="Timeout",
    )
    collector.on_failure(failure_ctx)

    collector.print_report()

    print("\nAll examples completed!")


if __name__ == "__main__":
    main()
