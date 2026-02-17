"""Plugin loader and discovery for VenomQA.

This module handles plugin discovery and loading from multiple sources:
- Python entry points (pip-installed plugins)
- Local plugin files (./qa/plugins/)
- Explicit module paths

Example:
    >>> from venomqa.plugins.loader import PluginLoader
    >>>
    >>> loader = PluginLoader()
    >>> plugins = loader.discover_all()
    >>> for plugin in plugins:
    ...     print(f"Found: {plugin.name} v{plugin.version}")

Plugin Discovery:
    1. Entry points: "venomqa.plugins" group in pyproject.toml
    2. Local directory: qa/plugins/*.py files
    3. Config paths: Explicit paths in venomqa.yaml
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from venomqa.plugins.base import VenomQAPlugin
from venomqa.plugins.types import PluginConfig, PluginsConfig

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Entry point group for VenomQA plugins
ENTRY_POINT_GROUP = "venomqa.plugins"


class PluginLoadError(Exception):
    """Raised when a plugin fails to load."""

    def __init__(self, plugin_name: str, reason: str, cause: Exception | None = None) -> None:
        self.plugin_name = plugin_name
        self.reason = reason
        self.cause = cause
        message = f"Failed to load plugin '{plugin_name}': {reason}"
        if cause:
            message += f" (caused by: {cause})"
        super().__init__(message)


class PluginLoader:
    """Discovers and loads VenomQA plugins from various sources.

    The loader supports multiple plugin sources:
    - Entry points (pip install venomqa-plugin-xxx)
    - Local files (./qa/plugins/my_plugin.py)
    - Module paths (venomqa_custom.reporter)

    Example:
        >>> loader = PluginLoader(local_path="qa/plugins")
        >>> plugins = loader.discover_all()
        >>>
        >>> # Load specific plugin by name
        >>> plugin = loader.load_from_entry_point("venomqa-slack")
        >>>
        >>> # Load from local file
        >>> plugin = loader.load_from_file("./qa/plugins/custom.py")
    """

    def __init__(
        self,
        local_path: str | Path | None = "qa/plugins",
        auto_discover: bool = True,
    ) -> None:
        """Initialize the plugin loader.

        Args:
            local_path: Path to local plugins directory
            auto_discover: Whether to auto-discover from entry points
        """
        self.local_path = Path(local_path) if local_path else None
        self.auto_discover = auto_discover
        self._loaded: dict[str, VenomQAPlugin] = {}
        self._entry_points: dict[str, Any] = {}

    def discover_all(self) -> list[VenomQAPlugin]:
        """Discover all available plugins from all sources.

        Returns:
            List of discovered plugin instances
        """
        plugins: list[VenomQAPlugin] = []

        # Discover from entry points
        if self.auto_discover:
            plugins.extend(self.discover_entry_points())

        # Discover from local directory
        if self.local_path and self.local_path.exists():
            plugins.extend(self.discover_local())

        return plugins

    def discover_entry_points(self) -> list[VenomQAPlugin]:
        """Discover plugins from Python entry points.

        Searches for plugins registered under the "venomqa.plugins"
        entry point group in pyproject.toml.

        Returns:
            List of discovered plugin instances
        """
        plugins: list[VenomQAPlugin] = []

        try:
            # Python 3.10+ importlib.metadata
            from importlib.metadata import entry_points

            eps = entry_points(group=ENTRY_POINT_GROUP)

            for ep in eps:
                try:
                    plugin = self._load_entry_point(ep)
                    if plugin:
                        plugins.append(plugin)
                        self._entry_points[ep.name] = ep
                except Exception as e:
                    logger.error(f"Failed to load entry point {ep.name}: {e}")

        except Exception as e:
            logger.warning(f"Error discovering entry points: {e}")

        return plugins

    def _load_entry_point(self, ep: Any) -> VenomQAPlugin | None:
        """Load a plugin from an entry point.

        Args:
            ep: Entry point object

        Returns:
            Plugin instance or None
        """
        try:
            plugin_class = ep.load()

            # Validate it's a VenomQAPlugin
            if not isinstance(plugin_class, type) or not issubclass(plugin_class, VenomQAPlugin):
                logger.warning(f"Entry point {ep.name} is not a VenomQAPlugin subclass")
                return None

            # Instantiate the plugin
            plugin = plugin_class()
            self._loaded[plugin.name] = plugin

            logger.info(f"Loaded plugin from entry point: {plugin.name} v{plugin.version}")
            return plugin

        except Exception as e:
            raise PluginLoadError(ep.name, "Failed to load entry point", e) from e

    def discover_local(self) -> list[VenomQAPlugin]:
        """Discover plugins from the local plugins directory.

        Returns:
            List of discovered plugin instances
        """
        if not self.local_path or not self.local_path.exists():
            return []

        plugins: list[VenomQAPlugin] = []

        for file_path in self.local_path.glob("*.py"):
            if file_path.name.startswith("_"):
                continue

            try:
                plugin = self.load_from_file(file_path)
                if plugin:
                    plugins.append(plugin)
            except Exception as e:
                logger.error(f"Failed to load local plugin {file_path}: {e}")

        return plugins

    def load_from_file(self, file_path: str | Path) -> VenomQAPlugin | None:
        """Load a plugin from a Python file.

        Args:
            file_path: Path to the plugin file

        Returns:
            Plugin instance or None if no plugin found
        """
        file_path = Path(file_path).resolve()

        if not file_path.exists():
            raise PluginLoadError(str(file_path), "File not found")

        if not file_path.suffix == ".py":
            raise PluginLoadError(str(file_path), "Not a Python file")

        try:
            # Generate unique module name
            module_name = f"venomqa_plugin_{file_path.stem}_{id(file_path)}"

            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                raise PluginLoadError(str(file_path), "Cannot create module spec")

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Find VenomQAPlugin subclasses in the module
            plugin = self._find_plugin_in_module(module)

            if plugin:
                self._loaded[plugin.name] = plugin
                logger.info(f"Loaded plugin from file: {plugin.name} v{plugin.version}")

            return plugin

        except PluginLoadError:
            raise
        except Exception as e:
            raise PluginLoadError(str(file_path), "Failed to load module", e) from e

    def load_from_module(self, module_path: str) -> VenomQAPlugin | None:
        """Load a plugin from a module path.

        Args:
            module_path: Dotted module path (e.g., "venomqa_slack.plugin")

        Returns:
            Plugin instance or None if no plugin found
        """
        try:
            module = importlib.import_module(module_path)
            plugin = self._find_plugin_in_module(module)

            if plugin:
                self._loaded[plugin.name] = plugin
                logger.info(f"Loaded plugin from module: {plugin.name} v{plugin.version}")

            return plugin

        except ImportError as e:
            raise PluginLoadError(module_path, "Module not found", e) from e
        except Exception as e:
            raise PluginLoadError(module_path, "Failed to load module", e) from e

    def _find_plugin_in_module(self, module: Any) -> VenomQAPlugin | None:
        """Find and instantiate a VenomQAPlugin subclass in a module.

        Args:
            module: The loaded module

        Returns:
            Plugin instance or None
        """
        # Look for explicit plugin export
        if hasattr(module, "plugin"):
            plugin_obj = module.plugin
            if isinstance(plugin_obj, VenomQAPlugin):
                return plugin_obj
            if isinstance(plugin_obj, type) and issubclass(plugin_obj, VenomQAPlugin):
                return plugin_obj()

        # Look for Plugin class
        if hasattr(module, "Plugin"):
            plugin_class = module.Plugin
            if isinstance(plugin_class, type) and issubclass(plugin_class, VenomQAPlugin):
                return plugin_class()

        # Search for any VenomQAPlugin subclass
        for name in dir(module):
            if name.startswith("_"):
                continue

            obj = getattr(module, name)

            if not isinstance(obj, type):
                continue

            if obj is VenomQAPlugin:
                continue

            if issubclass(obj, VenomQAPlugin) and obj.__module__ == module.__name__:
                return obj()

        return None

    def load_from_config(
        self,
        config: PluginConfig,
    ) -> VenomQAPlugin | None:
        """Load a plugin from configuration.

        Args:
            config: Plugin configuration

        Returns:
            Plugin instance or None
        """
        name = config.name

        # Check if already loaded
        if name in self._loaded:
            plugin = self._loaded[name]
            plugin.on_load(config.config)
            return plugin

        # Try as local file path
        if name.startswith("./") or name.startswith("/") or name.endswith(".py"):
            plugin = self.load_from_file(name)
        # Try as entry point name
        elif name in self._entry_points:
            plugin = self._load_entry_point(self._entry_points[name])
        # Try as module path
        else:
            # First try entry points
            self.discover_entry_points()
            if name in self._loaded:
                plugin = self._loaded[name]
            else:
                # Try as module path
                try:
                    plugin = self.load_from_module(name)
                except PluginLoadError:
                    plugin = None

        if plugin:
            plugin.priority = config.priority
            plugin.enabled = config.enabled
            plugin.on_load(config.config)

        return plugin

    def load_all_from_config(
        self,
        config: PluginsConfig,
    ) -> list[VenomQAPlugin]:
        """Load all plugins from configuration.

        Args:
            config: Plugins configuration

        Returns:
            List of loaded plugin instances
        """
        # Update loader settings from config
        if config.local_plugins_path:
            self.local_path = Path(config.local_plugins_path)
        self.auto_discover = config.auto_discover

        plugins: list[VenomQAPlugin] = []

        # Auto-discover first
        if config.auto_discover:
            discovered = self.discover_all()
            plugins.extend(discovered)

        # Load explicitly configured plugins
        for plugin_config in config.plugins:
            try:
                plugin = self.load_from_config(plugin_config)
                if plugin and plugin not in plugins:
                    plugins.append(plugin)
            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_config.name}: {e}")

        return plugins

    def get_loaded(self) -> dict[str, VenomQAPlugin]:
        """Get all loaded plugins.

        Returns:
            Dictionary mapping plugin names to instances
        """
        return dict(self._loaded)

    def is_loaded(self, name: str) -> bool:
        """Check if a plugin is loaded.

        Args:
            name: Plugin name

        Returns:
            True if plugin is loaded
        """
        return name in self._loaded

    def unload(self, name: str) -> None:
        """Unload a plugin.

        Args:
            name: Plugin name to unload
        """
        if name in self._loaded:
            plugin = self._loaded.pop(name)
            try:
                plugin.on_unload()
            except Exception as e:
                logger.error(f"Error unloading plugin {name}: {e}")

    def clear(self) -> None:
        """Unload all plugins."""
        for name in list(self._loaded.keys()):
            self.unload(name)


def discover_plugins(
    config: PluginsConfig | None = None,
    local_path: str | Path | None = "qa/plugins",
) -> list[VenomQAPlugin]:
    """Convenience function to discover all plugins.

    Args:
        config: Optional plugins configuration
        local_path: Path to local plugins directory

    Returns:
        List of discovered plugin instances
    """
    loader = PluginLoader(local_path=local_path)

    if config:
        return loader.load_all_from_config(config)
    else:
        return loader.discover_all()


def load_plugin(
    name_or_path: str,
    config: dict[str, Any] | None = None,
) -> VenomQAPlugin:
    """Convenience function to load a single plugin.

    Args:
        name_or_path: Plugin name, module path, or file path
        config: Optional plugin configuration

    Returns:
        Plugin instance

    Raises:
        PluginLoadError: If plugin cannot be loaded
    """
    loader = PluginLoader(auto_discover=False)

    plugin_config = PluginConfig(name=name_or_path, config=config or {})
    plugin = loader.load_from_config(plugin_config)

    if plugin is None:
        raise PluginLoadError(name_or_path, "No plugin found")

    return plugin
