"""Test data cleanup management for VenomQA.

This module provides comprehensive cleanup capabilities including:
- Reverse order deletion (LIFO)
- Table truncation
- Snapshot-based restoration
- Soft delete with TTL
- Automatic cleanup after journey completion or failure

Example:
    >>> cleanup = CleanupManager(
    ...     database=db,
    ...     client=http_client,
    ...     strategy=CleanupStrategy.REVERSE_DELETE
    ... )
    >>> cleanup.register_resource("users", user_id)
    >>> cleanup.register_resource("orders", order_id)
    >>> cleanup.cleanup()  # Deletes in reverse order: orders, then users
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from venomqa.ports.client import ClientPort
    from venomqa.ports.database import DatabasePort


class CleanupStrategy(Enum):
    """Strategy for cleaning up test data."""

    REVERSE_DELETE = "reverse_delete"  # Delete in reverse order of creation
    TRUNCATE = "truncate"  # Truncate tables
    SNAPSHOT_RESTORE = "snapshot_restore"  # Restore from snapshot
    SOFT_DELETE = "soft_delete"  # Soft delete with TTL
    NO_CLEANUP = "no_cleanup"  # Don't clean up (for debugging)


@dataclass
class TrackedResource:
    """Represents a tracked resource for cleanup.

    Attributes:
        resource_type: The type of resource (e.g., 'users', 'products').
        resource_id: The ID of the resource.
        created_at: When the resource was created.
        endpoint: API endpoint for deletion (if using API cleanup).
        table: Database table name (if using database cleanup).
        delete_endpoint: Custom delete endpoint override.
        cascade: Whether to cascade delete related resources.
        metadata: Additional metadata about the resource.
        priority: Cleanup priority (higher = cleaned up first).
    """

    resource_type: str
    resource_id: Any
    created_at: datetime = field(default_factory=datetime.now)
    endpoint: str | None = None
    table: str | None = None
    delete_endpoint: str | None = None
    cascade: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    priority: int = 0

    @property
    def delete_url(self) -> str:
        """Get the URL for deleting this resource via API."""
        if self.delete_endpoint:
            return self.delete_endpoint.format(id=self.resource_id)
        endpoint = self.endpoint or f"/api/{self.resource_type}"
        return f"{endpoint}/{self.resource_id}"


@dataclass
class CleanupConfig:
    """Configuration for cleanup operations.

    Attributes:
        strategy: The cleanup strategy to use.
        api_endpoints: Mapping of resource type to API delete endpoint.
        table_mapping: Mapping of resource type to database table.
        id_field: Field name used for resource IDs.
        soft_delete_field: Field name for soft delete flag.
        soft_delete_ttl: TTL for soft deleted records.
        retry_on_failure: Whether to retry failed deletes.
        max_retries: Maximum retry attempts.
        timeout: Timeout for API calls.
        on_failure: Action to take on cleanup failure ('ignore', 'warn', 'raise').
        cleanup_on_success: Whether to clean up on successful journey completion.
        cleanup_on_failure: Whether to clean up on journey failure.
        cleanup_batch_size: Number of resources to delete in each batch.
    """

    strategy: CleanupStrategy = CleanupStrategy.REVERSE_DELETE
    api_endpoints: dict[str, str] = field(default_factory=dict)
    table_mapping: dict[str, str] = field(default_factory=dict)
    id_field: str = "id"
    soft_delete_field: str = "deleted_at"
    soft_delete_ttl: timedelta = field(default_factory=lambda: timedelta(days=7))
    retry_on_failure: bool = True
    max_retries: int = 3
    timeout: float = 30.0
    on_failure: str = "warn"
    cleanup_on_success: bool = True
    cleanup_on_failure: bool = True
    cleanup_batch_size: int = 100


@dataclass
class CleanupResult:
    """Result of a cleanup operation.

    Attributes:
        success: Whether all resources were cleaned up successfully.
        deleted_count: Number of resources successfully deleted.
        failed_count: Number of resources that failed to delete.
        deleted_resources: List of successfully deleted TrackedResources.
        failed_resources: List of failed TrackedResources with error info.
        duration_ms: Total duration of the cleanup operation.
        strategy: The strategy that was used.
    """

    success: bool
    deleted_count: int = 0
    failed_count: int = 0
    deleted_resources: list[TrackedResource] = field(default_factory=list)
    failed_resources: list[tuple[TrackedResource, str]] = field(default_factory=list)
    duration_ms: float = 0.0
    strategy: CleanupStrategy = CleanupStrategy.REVERSE_DELETE

    @property
    def total_count(self) -> int:
        """Total number of resources processed."""
        return self.deleted_count + self.failed_count


class ResourceTracker:
    """Tracks created resources for later cleanup.

    This class maintains a registry of resources created during tests,
    enabling proper cleanup in the correct order.

    Example:
        >>> tracker = ResourceTracker()
        >>> tracker.track("users", 1, endpoint="/api/users")
        >>> tracker.track("orders", 100, endpoint="/api/orders")
        >>> for resource in tracker.get_cleanup_order():
        ...     print(f"Delete {resource.resource_type}/{resource.resource_id}")
    """

    def __init__(self) -> None:
        """Initialize the resource tracker."""
        self._resources: list[TrackedResource] = []
        self._by_type: dict[str, list[TrackedResource]] = {}
        self._by_journey: dict[str, list[TrackedResource]] = {}

    def track(
        self,
        resource_type: str,
        resource_id: Any,
        endpoint: str | None = None,
        table: str | None = None,
        journey: str | None = None,
        **kwargs: Any,
    ) -> TrackedResource:
        """Track a created resource.

        Args:
            resource_type: Type of the resource.
            resource_id: ID of the resource.
            endpoint: API endpoint for the resource.
            table: Database table for the resource.
            journey: Journey name this resource belongs to.
            **kwargs: Additional TrackedResource attributes.

        Returns:
            The created TrackedResource.
        """
        resource = TrackedResource(
            resource_type=resource_type,
            resource_id=resource_id,
            endpoint=endpoint,
            table=table,
            **kwargs,
        )

        self._resources.append(resource)

        # Index by type
        if resource_type not in self._by_type:
            self._by_type[resource_type] = []
        self._by_type[resource_type].append(resource)

        # Index by journey
        if journey:
            if journey not in self._by_journey:
                self._by_journey[journey] = []
            self._by_journey[journey].append(resource)

        return resource

    def track_many(
        self,
        resource_type: str,
        resource_ids: list[Any],
        **kwargs: Any,
    ) -> list[TrackedResource]:
        """Track multiple resources of the same type.

        Args:
            resource_type: Type of the resources.
            resource_ids: List of resource IDs.
            **kwargs: Additional TrackedResource attributes.

        Returns:
            List of created TrackedResources.
        """
        return [
            self.track(resource_type, rid, **kwargs) for rid in resource_ids
        ]

    def get_all(self) -> list[TrackedResource]:
        """Get all tracked resources in creation order."""
        return self._resources.copy()

    def get_by_type(self, resource_type: str) -> list[TrackedResource]:
        """Get all resources of a specific type."""
        return self._by_type.get(resource_type, []).copy()

    def get_by_journey(self, journey: str) -> list[TrackedResource]:
        """Get all resources for a specific journey."""
        return self._by_journey.get(journey, []).copy()

    def get_cleanup_order(
        self,
        journey: str | None = None,
        resource_types: list[str] | None = None,
    ) -> list[TrackedResource]:
        """Get resources in cleanup order (reverse of creation, respecting priority).

        Args:
            journey: Filter to specific journey.
            resource_types: Filter to specific resource types.

        Returns:
            List of TrackedResources in cleanup order.
        """
        if journey:
            resources = self._by_journey.get(journey, [])
        else:
            resources = self._resources

        if resource_types:
            resources = [r for r in resources if r.resource_type in resource_types]

        # Sort by priority (descending), then by creation time (descending/LIFO)
        return sorted(
            resources,
            key=lambda r: (-r.priority, -r.created_at.timestamp()),
        )

    def untrack(self, resource: TrackedResource) -> bool:
        """Remove a resource from tracking.

        Args:
            resource: The resource to untrack.

        Returns:
            True if the resource was found and removed.
        """
        if resource in self._resources:
            self._resources.remove(resource)

            if resource.resource_type in self._by_type:
                self._by_type[resource.resource_type] = [
                    r
                    for r in self._by_type[resource.resource_type]
                    if r != resource
                ]

            for journey, resources in self._by_journey.items():
                self._by_journey[journey] = [r for r in resources if r != resource]

            return True
        return False

    def clear(self, journey: str | None = None) -> None:
        """Clear tracked resources.

        Args:
            journey: If provided, only clear resources for this journey.
        """
        if journey and journey in self._by_journey:
            resources_to_remove = self._by_journey[journey]
            self._resources = [r for r in self._resources if r not in resources_to_remove]
            for resource in resources_to_remove:
                if resource.resource_type in self._by_type:
                    self._by_type[resource.resource_type] = [
                        r
                        for r in self._by_type[resource.resource_type]
                        if r not in resources_to_remove
                    ]
            del self._by_journey[journey]
        else:
            self._resources.clear()
            self._by_type.clear()
            self._by_journey.clear()

    def __len__(self) -> int:
        """Get total number of tracked resources."""
        return len(self._resources)

    def __bool__(self) -> bool:
        """Check if any resources are being tracked."""
        return bool(self._resources)


class CleanupManager:
    """Manages test data cleanup operations.

    The CleanupManager handles cleanup of test resources using various
    strategies including reverse deletion, truncation, and snapshot restoration.

    Example:
        >>> manager = CleanupManager(
        ...     client=http_client,
        ...     database=db_adapter,
        ...     config=CleanupConfig(strategy=CleanupStrategy.REVERSE_DELETE)
        ... )
        >>> manager.register_resource("users", user_id)
        >>> manager.register_resource("orders", order_id)
        >>> result = manager.cleanup()
        >>> print(f"Deleted {result.deleted_count} resources")
    """

    def __init__(
        self,
        client: ClientPort | None = None,
        database: DatabasePort | None = None,
        config: CleanupConfig | None = None,
    ) -> None:
        """Initialize the CleanupManager.

        Args:
            client: HTTP client for API-based cleanup.
            database: Database port for direct cleanup.
            config: Cleanup configuration.
        """
        self.client = client
        self.database = database
        self.config = config or CleanupConfig()
        self._tracker = ResourceTracker()
        self._snapshots: dict[str, dict[str, list[dict[str, Any]]]] = {}

    @property
    def tracker(self) -> ResourceTracker:
        """Get the resource tracker."""
        return self._tracker

    def register_resource(
        self,
        resource_type: str,
        resource_id: Any,
        journey: str | None = None,
        **kwargs: Any,
    ) -> TrackedResource:
        """Register a resource for cleanup.

        Args:
            resource_type: Type of the resource.
            resource_id: ID of the resource.
            journey: Journey name this resource belongs to.
            **kwargs: Additional TrackedResource attributes.

        Returns:
            The tracked resource.
        """
        endpoint = kwargs.pop("endpoint", None) or self.config.api_endpoints.get(
            resource_type, f"/api/{resource_type}"
        )
        table = kwargs.pop("table", None) or self.config.table_mapping.get(
            resource_type, resource_type
        )

        return self._tracker.track(
            resource_type=resource_type,
            resource_id=resource_id,
            endpoint=endpoint,
            table=table,
            journey=journey,
            **kwargs,
        )

    def register_resources(
        self,
        resources: list[Any],
        journey: str | None = None,
    ) -> list[TrackedResource]:
        """Register multiple resources for cleanup.

        Args:
            resources: List of SeedData or TrackedResource objects.
            journey: Journey name these resources belong to.

        Returns:
            List of tracked resources.
        """
        tracked = []
        for resource in resources:
            if hasattr(resource, "resource_type") and hasattr(resource, "actual_id"):
                # SeedData object
                tracked.append(
                    self.register_resource(
                        resource_type=resource.resource_type,
                        resource_id=resource.actual_id or resource.logical_id,
                        journey=journey,
                        endpoint=resource.endpoint,
                        table=resource.table,
                    )
                )
            elif isinstance(resource, TrackedResource):
                # Already a TrackedResource
                self._tracker._resources.append(resource)
                tracked.append(resource)
            elif isinstance(resource, dict):
                # Dictionary with resource info
                tracked.append(
                    self.register_resource(
                        resource_type=resource.get("type", "unknown"),
                        resource_id=resource.get("id"),
                        journey=journey,
                        **{k: v for k, v in resource.items() if k not in ("type", "id")},
                    )
                )

        return tracked

    def create_snapshot(self, name: str, tables: list[str] | None = None) -> None:
        """Create a database snapshot for later restoration.

        Args:
            name: Name for this snapshot.
            tables: Tables to snapshot (default: all tracked tables).
        """
        if self.database is None:
            raise ValueError("No database configured for snapshot")

        if tables is None:
            # Get unique tables from tracked resources
            tables = list(
                set(r.table for r in self._tracker.get_all() if r.table)
            )

        if not tables:
            tables = self.database.get_tables()

        self._snapshots[name] = self.database.dump(tables)

    def restore_snapshot(self, name: str) -> None:
        """Restore database from a snapshot.

        Args:
            name: Name of the snapshot to restore.

        Raises:
            ValueError: If snapshot doesn't exist.
        """
        if name not in self._snapshots:
            raise ValueError(f"Snapshot not found: {name}")

        if self.database is None:
            raise ValueError("No database configured for snapshot restore")

        self.database.restore(self._snapshots[name], truncate=True)

    def cleanup(
        self,
        journey: str | None = None,
        resource_types: list[str] | None = None,
        strategy: CleanupStrategy | None = None,
    ) -> CleanupResult:
        """Clean up tracked resources.

        Args:
            journey: Clean up only resources for this journey.
            resource_types: Clean up only these resource types.
            strategy: Override the configured cleanup strategy.

        Returns:
            CleanupResult with details of the operation.
        """
        start_time = datetime.now()
        strategy = strategy or self.config.strategy

        if strategy == CleanupStrategy.NO_CLEANUP:
            return CleanupResult(success=True, strategy=strategy)

        if strategy == CleanupStrategy.SNAPSHOT_RESTORE:
            return self._cleanup_via_snapshot(journey)

        if strategy == CleanupStrategy.TRUNCATE:
            return self._cleanup_via_truncate(journey, resource_types)

        # Default: REVERSE_DELETE or SOFT_DELETE
        resources = self._tracker.get_cleanup_order(journey, resource_types)

        deleted: list[TrackedResource] = []
        failed: list[tuple[TrackedResource, str]] = []

        for resource in resources:
            try:
                if strategy == CleanupStrategy.SOFT_DELETE:
                    self._soft_delete_resource(resource)
                else:
                    self._delete_resource(resource)

                deleted.append(resource)
                self._tracker.untrack(resource)

            except Exception as e:
                error_msg = str(e)
                failed.append((resource, error_msg))

                if self.config.on_failure == "raise":
                    raise
                elif self.config.on_failure == "warn":
                    import warnings

                    warnings.warn(
                        f"Failed to delete {resource.resource_type}/"
                        f"{resource.resource_id}: {error_msg}"
                    )

        end_time = datetime.now()
        duration_ms = (end_time - start_time).total_seconds() * 1000

        return CleanupResult(
            success=len(failed) == 0,
            deleted_count=len(deleted),
            failed_count=len(failed),
            deleted_resources=deleted,
            failed_resources=failed,
            duration_ms=duration_ms,
            strategy=strategy,
        )

    def _delete_resource(self, resource: TrackedResource) -> None:
        """Delete a resource via API or database."""
        # Try API first if client is available
        if self.client is not None:
            self._delete_via_api(resource)
        elif self.database is not None:
            self._delete_via_database(resource)
        else:
            raise ValueError("No client or database configured for deletion")

    def _delete_via_api(self, resource: TrackedResource) -> None:
        """Delete a resource via API call."""
        response = self.client.delete(  # type: ignore[union-attr]
            resource.delete_url,
            timeout=self.config.timeout,
        )

        # Accept 200, 204, or 404 (already deleted)
        if response.status_code not in (200, 204, 404):
            raise ValueError(
                f"Delete failed: {response.status_code} - {response.text}"
            )

    def _delete_via_database(self, resource: TrackedResource) -> None:
        """Delete a resource via direct database delete."""
        if resource.table is None:
            resource.table = self.config.table_mapping.get(
                resource.resource_type, resource.resource_type
            )

        self.database.delete(  # type: ignore[union-attr]
            resource.table,
            where=f"{self.config.id_field} = %s",
            where_params=(resource.resource_id,),
        )

    def _soft_delete_resource(self, resource: TrackedResource) -> None:
        """Soft delete a resource by setting deleted_at timestamp."""
        if self.database is None:
            raise ValueError("Database required for soft delete")

        if resource.table is None:
            resource.table = self.config.table_mapping.get(
                resource.resource_type, resource.resource_type
            )

        self.database.update(
            resource.table,
            data={self.config.soft_delete_field: datetime.now()},
            where=f"{self.config.id_field} = %s",
            where_params=(resource.resource_id,),
        )

    def _cleanup_via_truncate(
        self,
        journey: str | None,
        resource_types: list[str] | None,
    ) -> CleanupResult:
        """Clean up by truncating tables."""
        start_time = datetime.now()

        if self.database is None:
            raise ValueError("Database required for truncate cleanup")

        # Get unique tables to truncate
        resources = self._tracker.get_cleanup_order(journey, resource_types)
        tables = list(set(r.table for r in resources if r.table))

        deleted_count = 0
        failed: list[tuple[TrackedResource, str]] = []

        for table in tables:
            try:
                self.database.truncate(table, cascade=True)
                deleted_count += sum(1 for r in resources if r.table == table)
            except Exception as e:
                for r in resources:
                    if r.table == table:
                        failed.append((r, str(e)))

        # Clear tracked resources for truncated tables
        for resource in resources:
            if resource.table in tables and resource not in [f[0] for f in failed]:
                self._tracker.untrack(resource)

        end_time = datetime.now()
        duration_ms = (end_time - start_time).total_seconds() * 1000

        return CleanupResult(
            success=len(failed) == 0,
            deleted_count=deleted_count,
            failed_count=len(failed),
            failed_resources=failed,
            duration_ms=duration_ms,
            strategy=CleanupStrategy.TRUNCATE,
        )

    def _cleanup_via_snapshot(self, journey: str | None) -> CleanupResult:
        """Clean up by restoring from snapshot."""
        start_time = datetime.now()

        snapshot_name = f"journey_{journey}" if journey else "default"

        if snapshot_name not in self._snapshots:
            return CleanupResult(
                success=False,
                strategy=CleanupStrategy.SNAPSHOT_RESTORE,
                failed_resources=[
                    (TrackedResource("snapshot", snapshot_name), "Snapshot not found")
                ],
            )

        try:
            self.restore_snapshot(snapshot_name)

            # Clear tracked resources
            resources = self._tracker.get_cleanup_order(journey)
            for resource in resources:
                self._tracker.untrack(resource)

            end_time = datetime.now()
            duration_ms = (end_time - start_time).total_seconds() * 1000

            return CleanupResult(
                success=True,
                deleted_count=len(resources),
                duration_ms=duration_ms,
                strategy=CleanupStrategy.SNAPSHOT_RESTORE,
            )

        except Exception as e:
            return CleanupResult(
                success=False,
                strategy=CleanupStrategy.SNAPSHOT_RESTORE,
                failed_resources=[
                    (TrackedResource("snapshot", snapshot_name), str(e))
                ],
            )

    def cleanup_all(self) -> CleanupResult:
        """Clean up all tracked resources."""
        return self.cleanup()

    def cleanup_journey(self, journey: str) -> CleanupResult:
        """Clean up all resources for a specific journey."""
        return self.cleanup(journey=journey)

    def clear(self) -> None:
        """Clear all tracked resources without deleting them."""
        self._tracker.clear()

    def __len__(self) -> int:
        """Get number of tracked resources."""
        return len(self._tracker)

    def __bool__(self) -> bool:
        """Check if any resources are being tracked."""
        return bool(self._tracker)
