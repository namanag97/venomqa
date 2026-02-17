"""Load fixtures from JSON/YAML files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


class FixtureLoadError(Exception):
    """Error loading fixture file."""

    pass


class FixtureLoader:
    """Load test fixtures from JSON or YAML files."""

    def __init__(self, base_path: str | Path | None = None):
        self.base_path = Path(base_path) if base_path else Path.cwd()
        self._cache: dict[str, Any] = {}

    def load(self, filepath: str | Path, use_cache: bool = True) -> Any:
        """Load fixture from file path."""
        path = self._resolve_path(filepath)

        cache_key = str(path)
        if use_cache and cache_key in self._cache:
            return copy.deepcopy(self._cache[cache_key])

        if not path.exists():
            raise FixtureLoadError(f"Fixture file not found: {path}")

        suffix = path.suffix.lower()
        if suffix == ".json":
            data = self._load_json(path)
        elif suffix in (".yaml", ".yml"):
            data = self._load_yaml(path)
        else:
            raise FixtureLoadError(f"Unsupported fixture format: {suffix}")

        if use_cache:
            self._cache[cache_key] = data

        return copy.deepcopy(data)

    def _resolve_path(self, filepath: str | Path) -> Path:
        path = Path(filepath)
        if path.is_absolute():
            return path
        return self.base_path / path

    def _load_json(self, path: Path) -> Any:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise FixtureLoadError(f"Invalid JSON in {path}: {e}") from e

    def _load_yaml(self, path: Path) -> Any:
        if not HAS_YAML:
            raise FixtureLoadError("YAML support requires PyYAML. Install with: pip install pyyaml")
        try:
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise FixtureLoadError(f"Invalid YAML in {path}: {e}") from e

    def load_json(self, filepath: str | Path) -> Any:
        """Load fixture from JSON file."""
        path = self._resolve_path(filepath)
        return self._load_json(path)

    def load_yaml(self, filepath: str | Path) -> Any:
        """Load fixture from YAML file."""
        path = self._resolve_path(filepath)
        return self._load_yaml(path)

    def load_all(self, directory: str | Path, pattern: str = "*.json") -> dict[str, Any]:
        """Load all matching fixtures from directory."""
        dir_path = self._resolve_path(directory)
        if not dir_path.is_dir():
            raise FixtureLoadError(f"Directory not found: {dir_path}")

        results = {}
        for filepath in sorted(dir_path.glob(pattern)):
            name = filepath.stem
            results[name] = self.load(filepath)
        return results

    def clear_cache(self) -> None:
        """Clear the fixture cache."""
        self._cache.clear()

    def preload(self, filepaths: list[str | Path]) -> None:
        """Preload multiple fixtures into cache."""
        for filepath in filepaths:
            self.load(filepath, use_cache=True)


class FixtureSet:
    """A collection of related fixtures."""

    def __init__(self, name: str, loader: FixtureLoader | None = None):
        self.name = name
        self.loader = loader or FixtureLoader()
        self._fixtures: dict[str, Any] = {}

    def load(self, filepath: str | Path) -> None:
        """Load fixtures from file into this set."""
        data = self.loader.load(filepath)
        if isinstance(data, dict):
            self._fixtures.update(data)
        else:
            self._fixtures[self._get_name(filepath)] = data

    def _get_name(self, filepath: str | Path) -> str:
        return Path(filepath).stem

    def get(self, key: str, default: Any = None) -> Any:
        """Get fixture by key."""
        return self._fixtures.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self._fixtures[key]

    def __contains__(self, key: str) -> bool:
        return key in self._fixtures

    def keys(self) -> list[str]:
        return list(self._fixtures.keys())

    def values(self) -> list[Any]:
        return list(self._fixtures.values())

    def items(self) -> list[tuple[str, Any]]:
        return list(self._fixtures.items())

    def to_dict(self) -> dict[str, Any]:
        return self._fixtures.copy()


def load_fixture(filepath: str | Path, base_path: str | Path | None = None) -> Any:
    """Convenience function to load a single fixture."""
    loader = FixtureLoader(base_path)
    return loader.load(filepath)


def load_fixtures(
    directory: str | Path, pattern: str = "*.json", base_path: str | Path | None = None
) -> dict[str, Any]:
    """Convenience function to load all fixtures from directory."""
    loader = FixtureLoader(base_path)
    return loader.load_all(directory, pattern)


import copy  # noqa: E402
