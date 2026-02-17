"""Test data seeding module for VenomQA.

This module provides comprehensive test data seeding capabilities including:
- YAML/JSON seed file parsing with variable interpolation
- API-based seeding (POST requests)
- Database-based seeding (direct INSERT)
- Resource tracking for cleanup
- Parallel test isolation with unique prefixes

Example seed file format (YAML):
    users:
      - id: user_seller_1
        email: seller@test.com
        role: seller
      - id: user_buyer_1
        email: buyer@test.com
        role: buyer

    products:
      - id: product_1
        seller_id: ${users.user_seller_1.id}
        title: Test Product
        price: 99.99
"""

from __future__ import annotations

import copy
import functools
import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from venomqa.context import TestContext
    from venomqa.ports.client import ClientPort
    from venomqa.ports.database import DatabasePort

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


class SeedMode(Enum):
    """Mode for applying seed data."""

    API = "api"  # Use API calls (POST) to create resources
    DATABASE = "database"  # Use direct database inserts
    HYBRID = "hybrid"  # Use API for some, database for others


@dataclass
class SeedConfig:
    """Configuration for seed operations.

    Attributes:
        mode: The seeding mode (API, DATABASE, or HYBRID).
        prefix: Unique prefix for isolation (auto-generated if not provided).
        api_endpoints: Mapping of resource type to API endpoint.
        table_mapping: Mapping of resource type to database table name.
        id_field: Field name used for resource IDs (default: 'id').
        retry_on_conflict: Whether to retry on conflict errors.
        max_retries: Maximum retry attempts.
        timeout: Timeout for API calls in seconds.
        track_resources: Whether to track created resources for cleanup.
    """

    mode: SeedMode = SeedMode.API
    prefix: str = ""
    api_endpoints: dict[str, str] = field(default_factory=dict)
    table_mapping: dict[str, str] = field(default_factory=dict)
    id_field: str = "id"
    retry_on_conflict: bool = True
    max_retries: int = 3
    timeout: float = 30.0
    track_resources: bool = True

    def __post_init__(self) -> None:
        if not self.prefix:
            self.prefix = f"seed_{uuid.uuid4().hex[:8]}"


@dataclass
class SeedData:
    """Represents a single piece of seed data.

    Attributes:
        resource_type: The type of resource (e.g., 'users', 'products').
        logical_id: The logical ID from the seed file (e.g., 'user_seller_1').
        data: The actual data to seed.
        actual_id: The ID assigned after creation (may differ from logical_id).
        created_at: Timestamp when the resource was created.
        mode: The mode used to create this resource.
        endpoint: API endpoint used (if API mode).
        table: Database table used (if DATABASE mode).
    """

    resource_type: str
    logical_id: str
    data: dict[str, Any]
    actual_id: Any = None
    created_at: datetime | None = None
    mode: SeedMode | None = None
    endpoint: str | None = None
    table: str | None = None

    @property
    def fully_qualified_id(self) -> str:
        """Get the fully qualified ID for reference."""
        return f"{self.resource_type}.{self.logical_id}"


@dataclass
class SeedFile:
    """Represents a loaded seed file.

    Attributes:
        path: Path to the seed file.
        resources: Dictionary of resource type to list of SeedData.
        metadata: Optional metadata from the seed file.
        loaded_at: Timestamp when the file was loaded.
    """

    path: Path
    resources: dict[str, list[SeedData]]
    metadata: dict[str, Any] = field(default_factory=dict)
    loaded_at: datetime = field(default_factory=datetime.now)

    @property
    def resource_types(self) -> list[str]:
        """Get list of resource types in this file."""
        return list(self.resources.keys())

    @property
    def total_resources(self) -> int:
        """Get total number of resources across all types."""
        return sum(len(items) for items in self.resources.values())

    def get_resource(self, resource_type: str, logical_id: str) -> SeedData | None:
        """Get a specific resource by type and logical ID."""
        resources = self.resources.get(resource_type, [])
        for resource in resources:
            if resource.logical_id == logical_id:
                return resource
        return None


@dataclass
class SeedResult:
    """Result of a seeding operation.

    Attributes:
        success: Whether all seeds were applied successfully.
        created_count: Number of resources created.
        failed_count: Number of resources that failed to create.
        created_resources: List of successfully created SeedData.
        failed_resources: List of failed SeedData with error info.
        duration_ms: Total duration of the seeding operation.
        prefix: The prefix used for this seed run.
    """

    success: bool
    created_count: int = 0
    failed_count: int = 0
    created_resources: list[SeedData] = field(default_factory=list)
    failed_resources: list[tuple[SeedData, str]] = field(default_factory=list)
    duration_ms: float = 0.0
    prefix: str = ""

    @property
    def total_count(self) -> int:
        """Total number of resources processed."""
        return self.created_count + self.failed_count


class SeedManager:
    """Manages test data seeding operations.

    The SeedManager handles loading seed files, applying seed data through
    API calls or direct database inserts, and tracking created resources
    for later cleanup.

    Example:
        >>> manager = SeedManager(client=http_client, database=db_adapter)
        >>> seeds = manager.load("seeds/base.yaml")
        >>> result = manager.apply(seeds)
        >>> print(f"Created {result.created_count} resources")
        >>>
        >>> # Access created resource IDs
        >>> user_id = manager.get_actual_id("users.user_seller_1")
    """

    VARIABLE_PATTERN = re.compile(r"\$\{([^}]+)\}")

    def __init__(
        self,
        client: ClientPort | None = None,
        database: DatabasePort | None = None,
        config: SeedConfig | None = None,
    ) -> None:
        """Initialize the SeedManager.

        Args:
            client: HTTP client for API-based seeding.
            database: Database port for direct inserts.
            config: Seeding configuration.
        """
        self.client = client
        self.database = database
        self.config = config or SeedConfig()
        self._loaded_files: dict[str, SeedFile] = {}
        self._resolved_ids: dict[str, Any] = {}
        self._created_resources: list[SeedData] = []

    @property
    def created_resources(self) -> list[SeedData]:
        """Get list of all created resources."""
        return self._created_resources.copy()

    def load(self, filepath: str | Path, use_cache: bool = True) -> SeedFile:
        """Load a seed file from disk.

        Args:
            filepath: Path to the seed file (YAML or JSON).
            use_cache: Whether to use cached version if available.

        Returns:
            Loaded SeedFile instance.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the file format is unsupported.
        """
        path = Path(filepath)
        cache_key = str(path.absolute())

        if use_cache and cache_key in self._loaded_files:
            return self._loaded_files[cache_key]

        if not path.exists():
            raise FileNotFoundError(f"Seed file not found: {path}")

        data = self._load_file(path)
        seed_file = self._parse_seed_data(path, data)

        self._loaded_files[cache_key] = seed_file
        return seed_file

    def _load_file(self, path: Path) -> dict[str, Any]:
        """Load file contents as dictionary."""
        suffix = path.suffix.lower()

        if suffix == ".json":
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        elif suffix in (".yaml", ".yml"):
            if not HAS_YAML:
                raise ImportError(
                    "YAML support requires PyYAML. Install with: pip install pyyaml"
                )
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        else:
            raise ValueError(f"Unsupported seed file format: {suffix}")

    def _parse_seed_data(self, path: Path, data: dict[str, Any]) -> SeedFile:
        """Parse raw data into SeedFile structure."""
        metadata = data.pop("_metadata", {})
        resources: dict[str, list[SeedData]] = {}

        for resource_type, items in data.items():
            if not isinstance(items, list):
                continue

            resources[resource_type] = []
            for item in items:
                if not isinstance(item, dict):
                    continue

                logical_id = item.get(self.config.id_field, str(uuid.uuid4()))
                seed_data = SeedData(
                    resource_type=resource_type,
                    logical_id=str(logical_id),
                    data=copy.deepcopy(item),
                )
                resources[resource_type].append(seed_data)

        return SeedFile(path=path, resources=resources, metadata=metadata)

    def apply(
        self,
        seed_file: SeedFile,
        mode: SeedMode | None = None,
        prefix: str | None = None,
    ) -> SeedResult:
        """Apply seed data from a loaded file.

        Args:
            seed_file: The loaded SeedFile to apply.
            mode: Override the default seeding mode.
            prefix: Override the default prefix for isolation.

        Returns:
            SeedResult with details of the operation.
        """
        start_time = datetime.now()
        mode = mode or self.config.mode
        prefix = prefix or self.config.prefix

        created: list[SeedData] = []
        failed: list[tuple[SeedData, str]] = []

        # Process resources in order (important for dependencies)
        for resource_type in seed_file.resource_types:
            for seed_data in seed_file.resources[resource_type]:
                try:
                    # Resolve variable references
                    resolved_data = self._resolve_variables(seed_data.data)

                    # Apply prefix to string IDs
                    if isinstance(resolved_data.get(self.config.id_field), str):
                        original_id = resolved_data[self.config.id_field]
                        resolved_data[self.config.id_field] = f"{prefix}_{original_id}"

                    # Create the resource
                    actual_id = self._create_resource(
                        resource_type, resolved_data, mode
                    )

                    # Track the created resource
                    seed_data.actual_id = actual_id
                    seed_data.created_at = datetime.now()
                    seed_data.mode = mode

                    # Store for variable resolution
                    resolved_data[self.config.id_field] = actual_id
                    self._resolved_ids[seed_data.fully_qualified_id] = resolved_data

                    created.append(seed_data)

                    if self.config.track_resources:
                        self._created_resources.append(seed_data)

                except Exception as e:
                    failed.append((seed_data, str(e)))

        end_time = datetime.now()
        duration_ms = (end_time - start_time).total_seconds() * 1000

        return SeedResult(
            success=len(failed) == 0,
            created_count=len(created),
            failed_count=len(failed),
            created_resources=created,
            failed_resources=failed,
            duration_ms=duration_ms,
            prefix=prefix,
        )

    def _resolve_variables(self, data: dict[str, Any]) -> dict[str, Any]:
        """Resolve variable references in data.

        Variables use the format ${resource_type.logical_id.field}.
        """
        result = copy.deepcopy(data)

        def resolve_value(value: Any) -> Any:
            if isinstance(value, str):
                return self._resolve_string_variables(value)
            elif isinstance(value, dict):
                return {k: resolve_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [resolve_value(v) for v in value]
            return value

        return {k: resolve_value(v) for k, v in result.items()}

    def _resolve_string_variables(self, value: str) -> Any:
        """Resolve variable references in a string value."""
        matches = self.VARIABLE_PATTERN.findall(value)
        if not matches:
            return value

        # If the entire string is a single variable, return the resolved value directly
        if len(matches) == 1 and value == f"${{{matches[0]}}}":
            return self._resolve_reference(matches[0])

        # Otherwise, do string interpolation
        result = value
        for match in matches:
            resolved = self._resolve_reference(match)
            result = result.replace(f"${{{match}}}", str(resolved))

        return result

    def _resolve_reference(self, reference: str) -> Any:
        """Resolve a single reference like 'users.user_seller_1.id'."""
        parts = reference.split(".")
        if len(parts) < 2:
            raise ValueError(f"Invalid reference format: {reference}")

        # Get the base key (resource_type.logical_id)
        base_key = f"{parts[0]}.{parts[1]}"
        if base_key not in self._resolved_ids:
            raise ValueError(f"Reference not found: {base_key}")

        resolved_data = self._resolved_ids[base_key]

        # Navigate to the requested field
        if len(parts) > 2:
            for part in parts[2:]:
                if isinstance(resolved_data, dict):
                    resolved_data = resolved_data.get(part)
                else:
                    raise ValueError(f"Cannot access {part} on non-dict value")

        return resolved_data

    def _create_resource(
        self, resource_type: str, data: dict[str, Any], mode: SeedMode
    ) -> Any:
        """Create a resource using the specified mode."""
        if mode == SeedMode.API:
            return self._create_via_api(resource_type, data)
        elif mode == SeedMode.DATABASE:
            return self._create_via_database(resource_type, data)
        else:
            # HYBRID mode: try API first, fall back to database
            try:
                return self._create_via_api(resource_type, data)
            except Exception:
                return self._create_via_database(resource_type, data)

    def _create_via_api(self, resource_type: str, data: dict[str, Any]) -> Any:
        """Create a resource via API call."""
        if self.client is None:
            raise ValueError("No client configured for API seeding")

        endpoint = self.config.api_endpoints.get(resource_type, f"/api/{resource_type}")
        response = self.client.post(endpoint, json=data, timeout=self.config.timeout)

        if not response.ok:
            raise ValueError(f"API error: {response.status_code} - {response.text}")

        response_data = response.json()
        return response_data.get(self.config.id_field, data.get(self.config.id_field))

    def _create_via_database(self, resource_type: str, data: dict[str, Any]) -> Any:
        """Create a resource via direct database insert."""
        if self.database is None:
            raise ValueError("No database configured for database seeding")

        table = self.config.table_mapping.get(resource_type, resource_type)
        result = self.database.insert(table, data)

        return result.last_insert_id or data.get(self.config.id_field)

    def get_actual_id(self, reference: str) -> Any:
        """Get the actual ID for a logical reference.

        Args:
            reference: Reference in format 'resource_type.logical_id'.

        Returns:
            The actual ID assigned to the resource.
        """
        if reference not in self._resolved_ids:
            return None
        return self._resolved_ids[reference].get(self.config.id_field)

    def get_resource_data(self, reference: str) -> dict[str, Any] | None:
        """Get the full resolved data for a reference.

        Args:
            reference: Reference in format 'resource_type.logical_id'.

        Returns:
            The resolved data dictionary or None if not found.
        """
        return self._resolved_ids.get(reference)

    def clear_cache(self) -> None:
        """Clear the loaded file cache."""
        self._loaded_files.clear()

    def reset(self) -> None:
        """Reset all tracking state."""
        self._resolved_ids.clear()
        self._created_resources.clear()


# Type variable for fixture decorator
F = TypeVar("F", bound=Callable[..., Any])


def seed_fixture(
    seed_file: str,
    mode: SeedMode = SeedMode.API,
    cleanup: bool = True,
    prefix: str | None = None,
) -> Callable[[F], F]:
    """Decorator to seed data before a fixture runs.

    This decorator loads and applies seed data before the decorated fixture
    function runs, making the seeded IDs available in the context.

    Args:
        seed_file: Path to the seed file.
        mode: Seeding mode (API or DATABASE).
        cleanup: Whether to clean up after the journey completes.
        prefix: Optional prefix for isolation (auto-generated if not provided).

    Returns:
        Decorated fixture function.

    Example:
        >>> @seed_fixture(seed="seeds/ecommerce.yaml")
        ... def ecommerce_data(client, ctx):
        ...     # Data is seeded, IDs available in ctx.seeds
        ...     return ctx.get("seeds")
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract client and ctx from args/kwargs
            client = kwargs.get("client") or (args[0] if args else None)
            ctx: TestContext | None = kwargs.get("ctx") or (
                args[1] if len(args) > 1 else None
            )

            if ctx is None:
                # Create a minimal context if not provided
                from venomqa.context import TestContext

                ctx = TestContext()
                if "ctx" in kwargs:
                    kwargs["ctx"] = ctx
                elif len(args) > 1:
                    args = (args[0], ctx) + args[2:]  # type: ignore[assignment]

            # Get database from context if available
            database = ctx.database_port if ctx else None

            # Create seed manager
            seed_manager = SeedManager(
                client=client,
                database=database,
                config=SeedConfig(
                    mode=mode,
                    prefix=prefix or f"fixture_{uuid.uuid4().hex[:8]}",
                ),
            )

            # Load and apply seeds
            seeds = seed_manager.load(seed_file)
            result = seed_manager.apply(seeds)

            # Store in context
            ctx.set("seeds", seed_manager._resolved_ids)
            ctx.set("seed_result", result)
            ctx.set("seed_manager", seed_manager)

            if cleanup:
                ctx.set("_seed_cleanup_pending", True)

            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
