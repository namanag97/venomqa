"""Tests for VenomQA plugin system."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from venomqa.core.models import Journey, JourneyResult, Step, StepResult
from venomqa.plugins import (
    ActionPlugin,
    AdapterPlugin,
    BranchContext,
    FailureContext,
    GeneratorPlugin,
    HookManager,
    HookPriority,
    HookPlugin,
    HookType,
    JourneyContext,
    PluginConfig,
    PluginLoader,
    PluginManager,
    PluginsConfig,
    PluginType,
    ReporterPlugin,
    StepContext,
    VenomQAPlugin,
    get_hook_manager,
    get_plugin_manager,
    reset_hook_manager,
    reset_plugin_manager,
)
from datetime import datetime


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def reset_managers():
    """Reset global managers before and after each test."""
    reset_hook_manager()
    reset_plugin_manager()
    yield
    reset_hook_manager()
    reset_plugin_manager()


@pytest.fixture
def sample_journey():
    """Create a sample journey for testing."""
    return Journey(
        name="test_journey",
        description="A test journey",
        steps=[
            Step(name="step1", action=lambda c, ctx: None),
            Step(name="step2", action=lambda c, ctx: None),
        ],
    )


@pytest.fixture
def sample_journey_result():
    """Create a sample journey result for testing."""
    now = datetime.now()
    return JourneyResult(
        journey_name="test_journey",
        success=True,
        started_at=now,
        finished_at=now,
        duration_ms=100.0,
        step_results=[],
    )


@pytest.fixture
def sample_step_result():
    """Create a sample step result for testing."""
    now = datetime.now()
    return StepResult(
        step_name="test_step",
        success=True,
        started_at=now,
        finished_at=now,
        duration_ms=50.0,
    )


# =============================================================================
# Test Plugin Base Classes
# =============================================================================


class TestVenomQAPlugin:
    """Tests for VenomQAPlugin base class."""

    def test_plugin_default_values(self):
        """Test plugin has correct default values."""

        class TestPlugin(VenomQAPlugin):
            name = "test-plugin"
            version = "1.0.0"

        plugin = TestPlugin()
        assert plugin.name == "test-plugin"
        assert plugin.version == "1.0.0"
        assert plugin.plugin_type == PluginType.HOOK
        assert plugin.priority == HookPriority.NORMAL
        assert plugin.enabled is True
        assert plugin._initialized is False

    def test_plugin_on_load(self):
        """Test plugin on_load initializes config."""

        class TestPlugin(VenomQAPlugin):
            name = "test-plugin"
            version = "1.0.0"

        plugin = TestPlugin()
        config = {"key": "value"}
        plugin.on_load(config)

        assert plugin.config == config
        assert plugin._initialized is True

    def test_plugin_info(self):
        """Test plugin info property."""

        class TestPlugin(VenomQAPlugin):
            name = "test-plugin"
            version = "2.0.0"
            plugin_type = PluginType.REPORTER
            description = "A test plugin"
            author = "Test Author"

        plugin = TestPlugin()
        info = plugin.info

        assert info.name == "test-plugin"
        assert info.version == "2.0.0"
        assert info.plugin_type == PluginType.REPORTER
        assert info.description == "A test plugin"
        assert info.author == "Test Author"

    def test_plugin_detects_implemented_hooks(self):
        """Test plugin detects which hooks are implemented."""

        class TestPlugin(VenomQAPlugin):
            name = "test-plugin"
            version = "1.0.0"

            def on_journey_start(self, context):
                pass

            def on_failure(self, context):
                pass

        plugin = TestPlugin()
        hooks = plugin._get_implemented_hooks()

        assert HookType.BEFORE_JOURNEY in hooks
        assert HookType.ON_FAILURE in hooks
        assert HookType.AFTER_STEP not in hooks


class TestReporterPlugin:
    """Tests for ReporterPlugin base class."""

    def test_reporter_plugin_type(self):
        """Test reporter plugin has correct type."""

        class TestReporter(ReporterPlugin):
            name = "test-reporter"
            version = "1.0.0"

            def get_reporter(self):
                return MagicMock()

        plugin = TestReporter()
        assert plugin.plugin_type == PluginType.REPORTER

    def test_reporter_plugin_requires_get_reporter(self):
        """Test reporter plugin requires get_reporter implementation."""

        class TestReporter(ReporterPlugin):
            name = "test-reporter"
            version = "1.0.0"

        plugin = TestReporter()
        with pytest.raises(NotImplementedError):
            plugin.get_reporter()


class TestAdapterPlugin:
    """Tests for AdapterPlugin base class."""

    def test_adapter_plugin_type(self):
        """Test adapter plugin has correct type."""

        class TestAdapter(AdapterPlugin):
            name = "test-adapter"
            version = "1.0.0"
            provides_adapters = ["cache"]

            def get_adapter(self, port_type):
                return MagicMock()

        plugin = TestAdapter()
        assert plugin.plugin_type == PluginType.ADAPTER


class TestActionPlugin:
    """Tests for ActionPlugin base class."""

    def test_action_plugin_type(self):
        """Test action plugin has correct type."""

        class TestActions(ActionPlugin):
            name = "test-actions"
            version = "1.0.0"

            def get_actions(self):
                return {"my_action": lambda: None}

        plugin = TestActions()
        assert plugin.plugin_type == PluginType.ACTION


# =============================================================================
# Test Hook Manager
# =============================================================================


class TestHookManager:
    """Tests for HookManager."""

    def test_register_plugin(self, reset_managers):
        """Test registering a plugin."""

        class TestPlugin(VenomQAPlugin):
            name = "test-plugin"
            version = "1.0.0"

            def on_journey_start(self, context):
                pass

        manager = HookManager()
        plugin = TestPlugin()
        manager.register_plugin(plugin)

        assert "test-plugin" in manager.get_all_plugins()
        subscriptions = manager.get_subscriptions(HookType.BEFORE_JOURNEY)
        assert len(subscriptions) == 1
        assert subscriptions[0].plugin.name == "test-plugin"

    def test_register_duplicate_plugin_raises(self, reset_managers):
        """Test registering duplicate plugin raises error."""

        class TestPlugin(VenomQAPlugin):
            name = "test-plugin"
            version = "1.0.0"

        manager = HookManager()
        plugin = TestPlugin()
        manager.register_plugin(plugin)

        with pytest.raises(ValueError, match="already registered"):
            manager.register_plugin(TestPlugin())

    def test_unregister_plugin(self, reset_managers):
        """Test unregistering a plugin."""

        class TestPlugin(VenomQAPlugin):
            name = "test-plugin"
            version = "1.0.0"

        manager = HookManager()
        plugin = TestPlugin()
        manager.register_plugin(plugin)
        manager.unregister_plugin("test-plugin")

        assert "test-plugin" not in manager.get_all_plugins()

    def test_dispatch_hook(self, reset_managers):
        """Test dispatching a hook to subscribers."""
        call_log = []

        class TestPlugin(VenomQAPlugin):
            name = "test-plugin"
            version = "1.0.0"

            def on_failure(self, context):
                call_log.append(("test-plugin", context))

        manager = HookManager()
        plugin = TestPlugin()
        manager.register_plugin(plugin)

        context = FailureContext(
            journey_name="test",
            path_name="main",
            step_name="step1",
            error="Test error",
        )

        results = manager.dispatch(HookType.ON_FAILURE, context)

        assert len(results) == 1
        assert results[0].success is True
        assert len(call_log) == 1
        assert call_log[0][0] == "test-plugin"

    def test_dispatch_hook_with_priority(self, reset_managers):
        """Test hooks are dispatched in priority order."""
        call_order = []

        class HighPriorityPlugin(VenomQAPlugin):
            name = "high-priority"
            version = "1.0.0"
            priority = HookPriority.HIGH

            def on_failure(self, context):
                call_order.append("high")

        class LowPriorityPlugin(VenomQAPlugin):
            name = "low-priority"
            version = "1.0.0"
            priority = HookPriority.LOW

            def on_failure(self, context):
                call_order.append("low")

        manager = HookManager()
        manager.register_plugin(LowPriorityPlugin())
        manager.register_plugin(HighPriorityPlugin())

        context = FailureContext(
            journey_name="test",
            path_name="main",
            step_name="step1",
            error="Test error",
        )
        manager.dispatch(HookType.ON_FAILURE, context)

        assert call_order == ["high", "low"]

    def test_dispatch_hook_error_handling(self, reset_managers):
        """Test hook errors are isolated."""

        class FailingPlugin(VenomQAPlugin):
            name = "failing-plugin"
            version = "1.0.0"

            def on_failure(self, context):
                raise RuntimeError("Plugin error")

        class WorkingPlugin(VenomQAPlugin):
            name = "working-plugin"
            version = "1.0.0"

            def on_failure(self, context):
                return "success"

        manager = HookManager(fail_on_plugin_error=False)
        manager.register_plugin(FailingPlugin())
        manager.register_plugin(WorkingPlugin())

        context = FailureContext(
            journey_name="test",
            path_name="main",
            step_name="step1",
            error="Test error",
        )
        results = manager.dispatch(HookType.ON_FAILURE, context)

        assert len(results) == 2
        # One should fail, one should succeed
        failed = [r for r in results if not r.success]
        succeeded = [r for r in results if r.success]
        assert len(failed) == 1
        assert len(succeeded) == 1

    def test_dispatch_disabled_plugin_skipped(self, reset_managers):
        """Test disabled plugins are skipped."""
        call_count = 0

        class TestPlugin(VenomQAPlugin):
            name = "test-plugin"
            version = "1.0.0"

            def on_failure(self, context):
                nonlocal call_count
                call_count += 1

        manager = HookManager()
        plugin = TestPlugin()
        plugin.enabled = False
        manager.register_plugin(plugin)

        context = FailureContext(
            journey_name="test",
            path_name="main",
            step_name="step1",
            error="Test error",
        )
        manager.dispatch(HookType.ON_FAILURE, context)

        assert call_count == 0


# =============================================================================
# Test Plugin Manager
# =============================================================================


class TestPluginManager:
    """Tests for PluginManager."""

    def test_load_plugin(self, reset_managers):
        """Test loading a plugin by path."""

        class TestPlugin(VenomQAPlugin):
            name = "test-plugin"
            version = "1.0.0"

        manager = PluginManager(auto_discover=False)

        # Mock the loader to return our test plugin
        with patch.object(manager._loader, "load_from_config") as mock_load:
            mock_load.return_value = TestPlugin()
            plugin = manager.load_plugin("test-plugin")

        assert plugin is not None
        assert plugin.name == "test-plugin"
        assert "test-plugin" in manager.get_all_plugins()

    def test_get_plugin(self, reset_managers):
        """Test getting a plugin by name."""

        class TestPlugin(VenomQAPlugin):
            name = "test-plugin"
            version = "1.0.0"

        manager = PluginManager(auto_discover=False)
        plugin = TestPlugin()
        manager._register_plugin(plugin)

        retrieved = manager.get_plugin("test-plugin")
        assert retrieved is plugin

    def test_get_plugins_by_type(self, reset_managers):
        """Test getting plugins filtered by type."""

        class HookPluginA(VenomQAPlugin):
            name = "hook-a"
            version = "1.0.0"
            plugin_type = PluginType.HOOK

        class ReporterPluginA(ReporterPlugin):
            name = "reporter-a"
            version = "1.0.0"

            def get_reporter(self):
                return MagicMock()

        manager = PluginManager(auto_discover=False)
        manager._register_plugin(HookPluginA())
        manager._register_plugin(ReporterPluginA())

        hooks = manager.get_plugins_by_type(PluginType.HOOK)
        reporters = manager.get_plugins_by_type(PluginType.REPORTER)

        assert len(hooks) == 1
        assert len(reporters) == 1

    def test_reporter_extraction(self, reset_managers):
        """Test reporters are extracted from reporter plugins."""
        mock_reporter = MagicMock()

        class TestReporter(ReporterPlugin):
            name = "test-reporter"
            version = "1.0.0"

            def get_reporter(self):
                return mock_reporter

        manager = PluginManager(auto_discover=False)
        manager._register_plugin(TestReporter())

        reporter = manager.get_reporter("test-reporter")
        assert reporter is mock_reporter

    def test_adapter_extraction(self, reset_managers):
        """Test adapters are extracted from adapter plugins."""
        mock_adapter = MagicMock()

        class TestAdapter(AdapterPlugin):
            name = "test-adapter"
            version = "1.0.0"
            provides_adapters = ["cache"]

            def get_adapter(self, port_type):
                if port_type == "cache":
                    return mock_adapter
                return None

        manager = PluginManager(auto_discover=False)
        manager._register_plugin(TestAdapter())

        adapter = manager.get_adapter("cache")
        assert adapter is mock_adapter

    def test_action_extraction(self, reset_managers):
        """Test actions are extracted from action plugins."""
        my_action = lambda: "action result"

        class TestActions(ActionPlugin):
            name = "test-actions"
            version = "1.0.0"

            def get_actions(self):
                return {"my_action": my_action}

        manager = PluginManager(auto_discover=False)
        manager._register_plugin(TestActions())

        action = manager.get_action("my_action")
        assert action is my_action

    def test_fire_journey_hooks(self, reset_managers, sample_journey, sample_journey_result):
        """Test firing journey lifecycle hooks."""
        events = []

        class TestPlugin(VenomQAPlugin):
            name = "test-plugin"
            version = "1.0.0"

            def on_journey_start(self, context):
                events.append("start")

            def on_journey_complete(self, journey, result, context):
                events.append("complete")

        manager = PluginManager(auto_discover=False)
        manager._register_plugin(TestPlugin())

        context = JourneyContext(
            journey=sample_journey,
            client=MagicMock(),
        )

        manager.fire_journey_start(context)
        manager.fire_journey_complete(sample_journey, sample_journey_result, context)

        assert events == ["start", "complete"]

    def test_fire_step_hooks(self, reset_managers, sample_step_result):
        """Test firing step lifecycle hooks."""
        events = []

        class TestPlugin(VenomQAPlugin):
            name = "test-plugin"
            version = "1.0.0"

            def on_step_start(self, step, context):
                events.append("start")

            def on_step_complete(self, step, result, context):
                events.append("complete")

        manager = PluginManager(auto_discover=False)
        manager._register_plugin(TestPlugin())

        step = Step(name="test_step", action=lambda c, ctx: None)
        context = StepContext(
            journey_name="test",
            path_name="main",
            step_name="test_step",
            step_number=1,
            step=step,
            context=MagicMock(),
        )

        manager.fire_step_start(step, context)
        manager.fire_step_complete(step, sample_step_result, context)

        assert events == ["start", "complete"]


# =============================================================================
# Test Plugin Loader
# =============================================================================


class TestPluginLoader:
    """Tests for PluginLoader."""

    def test_discover_local_plugins(self, reset_managers, tmp_path):
        """Test discovering plugins from local directory."""
        # Create a test plugin file
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text('''
from venomqa.plugins import VenomQAPlugin

class TestPlugin(VenomQAPlugin):
    name = "local-test-plugin"
    version = "1.0.0"
''')

        loader = PluginLoader(local_path=tmp_path, auto_discover=False)
        plugins = loader.discover_local()

        assert len(plugins) == 1
        assert plugins[0].name == "local-test-plugin"

    def test_load_from_file(self, reset_managers, tmp_path):
        """Test loading a plugin from file."""
        plugin_file = tmp_path / "custom_plugin.py"
        plugin_file.write_text('''
from venomqa.plugins import VenomQAPlugin

class CustomPlugin(VenomQAPlugin):
    name = "custom-plugin"
    version = "2.0.0"
''')

        loader = PluginLoader(auto_discover=False)
        plugin = loader.load_from_file(plugin_file)

        assert plugin is not None
        assert plugin.name == "custom-plugin"
        assert plugin.version == "2.0.0"

    def test_load_from_config(self, reset_managers, tmp_path):
        """Test loading a plugin from configuration."""
        plugin_file = tmp_path / "config_plugin.py"
        plugin_file.write_text('''
from venomqa.plugins import VenomQAPlugin

class ConfigPlugin(VenomQAPlugin):
    name = "config-plugin"
    version = "1.0.0"

    def on_load(self, config):
        super().on_load(config)
        self.api_key = config.get("api_key")
''')

        loader = PluginLoader(auto_discover=False)
        config = PluginConfig(
            name=str(plugin_file),
            config={"api_key": "test-key"},
        )

        plugin = loader.load_from_config(config)

        assert plugin is not None
        assert plugin.name == "config-plugin"
        assert plugin.api_key == "test-key"


# =============================================================================
# Test Plugin Types and Context
# =============================================================================


class TestPluginTypes:
    """Tests for plugin type definitions."""

    def test_plugin_config_validation(self):
        """Test PluginConfig validation."""
        config = PluginConfig(
            name="test-plugin",
            enabled=True,
            priority=HookPriority.HIGH,
            config={"key": "value"},
        )

        assert config.name == "test-plugin"
        assert config.enabled is True
        assert config.priority == HookPriority.HIGH
        assert config.config == {"key": "value"}

    def test_plugins_config(self):
        """Test PluginsConfig validation."""
        config = PluginsConfig(
            plugins=[
                PluginConfig(name="plugin1"),
                PluginConfig(name="plugin2", enabled=False),
            ],
            auto_discover=True,
            local_plugins_path="custom/plugins",
        )

        assert len(config.plugins) == 2
        assert config.auto_discover is True
        assert config.local_plugins_path == "custom/plugins"

    def test_step_context(self):
        """Test StepContext creation."""
        step = Step(name="test", action=lambda c, ctx: None)
        context = StepContext(
            journey_name="journey1",
            path_name="main",
            step_name="test",
            step_number=1,
            step=step,
            context=None,
        )

        assert context.journey_name == "journey1"
        assert context.step_name == "test"
        assert context.step_number == 1

    def test_failure_context(self):
        """Test FailureContext creation."""
        context = FailureContext(
            journey_name="test_journey",
            path_name="main",
            step_name="failing_step",
            error="Connection refused",
            request={"method": "GET", "url": "/api/test"},
            response={"status_code": 500},
        )

        assert context.journey_name == "test_journey"
        assert context.step_name == "failing_step"
        assert context.error == "Connection refused"


# =============================================================================
# Test Example Plugins
# =============================================================================


class TestExamplePlugins:
    """Tests for example plugin implementations."""

    def test_console_logger_plugin(self, reset_managers, capsys):
        """Test console logger plugin outputs to console."""
        from venomqa.plugins.examples import ConsoleLoggerPlugin

        plugin = ConsoleLoggerPlugin()
        plugin.on_load({"color": False, "show_timestamps": False})

        context = JourneyContext(
            journey=Journey(name="test", steps=[]),
            client=MagicMock(),
        )

        plugin.on_journey_start(context)
        captured = capsys.readouterr()

        assert "JOURNEY: test" in captured.out

    def test_timing_analyzer_plugin(self, reset_managers, sample_step_result):
        """Test timing analyzer plugin tracks timings."""
        from venomqa.plugins.examples import TimingAnalyzerPlugin

        plugin = TimingAnalyzerPlugin()
        plugin.on_load({})

        step = Step(name="test_step", action=lambda c, ctx: None)
        context = StepContext(
            journey_name="test",
            path_name="main",
            step_name="test_step",
            step_number=1,
            step=step,
            context=MagicMock(),
        )

        plugin.on_step_complete(step, sample_step_result, context)

        report = plugin.get_timing_report()
        assert report["summary"]["total_steps"] == 1
        assert "test_step" in report["steps"]

    def test_custom_assertions_plugin(self, reset_managers):
        """Test custom assertions plugin provides assertions."""
        from venomqa.plugins.examples import CustomAssertionsPlugin

        plugin = CustomAssertionsPlugin()
        plugin.on_load({})

        assertions = plugin.get_assertions()

        assert "assert_json_path" in assertions
        assert "assert_response_time" in assertions
        assert "assert_contains_all" in assertions

    def test_custom_assertions_json_path(self, reset_managers):
        """Test assert_json_path assertion."""
        from venomqa.plugins.examples import CustomAssertionsPlugin

        plugin = CustomAssertionsPlugin()
        plugin.on_load({"strict_mode": False})

        # Mock response with json() method
        response = MagicMock()
        response.json.return_value = {"data": {"user": {"name": "John"}}}

        result = plugin.assert_json_path(response, "data.user.name", "John")
        assert result is True

        result = plugin.assert_json_path(response, "data.user.name", "Jane")
        assert result is False

    def test_custom_assertions_contains_all(self, reset_managers):
        """Test assert_contains_all assertion."""
        from venomqa.plugins.examples import CustomAssertionsPlugin

        plugin = CustomAssertionsPlugin()
        plugin.on_load({})

        result = plugin.assert_contains_all([1, 2, 3, 4], [1, 3])
        assert result is True

        result = plugin.assert_contains_all([1, 2, 3], [1, 5])
        assert result is False


# =============================================================================
# Test Global Functions
# =============================================================================


class TestGlobalFunctions:
    """Tests for global plugin functions."""

    def test_get_plugin_manager_singleton(self, reset_managers):
        """Test get_plugin_manager returns singleton."""
        manager1 = get_plugin_manager()
        manager2 = get_plugin_manager()

        assert manager1 is manager2

    def test_reset_plugin_manager(self, reset_managers):
        """Test reset_plugin_manager creates new instance."""
        manager1 = get_plugin_manager()
        reset_plugin_manager()
        manager2 = get_plugin_manager()

        assert manager1 is not manager2

    def test_get_hook_manager_singleton(self, reset_managers):
        """Test get_hook_manager returns singleton."""
        manager1 = get_hook_manager()
        manager2 = get_hook_manager()

        assert manager1 is manager2
