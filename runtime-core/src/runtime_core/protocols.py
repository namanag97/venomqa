"""Protocol definitions for state-machine exploration tools.

This module defines the core abstractions that any state-machine exploration
system must implement. The separation between TypeSystem (static schema),
RuntimeContext (dynamic state), Action (transformations), and Explorer
(traversal strategy) enables flexible composition of exploration tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .type_system import ResourceType


@dataclass
class Snapshot:
    """Opaque snapshot of runtime state.

    The actual structure of data is determined by the RuntimeContext
    implementation. This dataclass serves as a type-safe wrapper.
    """
    data: Any
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class TypeSystem(Protocol):
    """Static schema: defines what resource types CAN exist.

    A TypeSystem describes the structure of resources in a system,
    including their hierarchical relationships. It does not track
    actual instances - that's the job of RuntimeContext.

    Example:
        >>> ts = MyTypeSystem()
        >>> ts.types()  # ["workspace", "upload", "user"]
        >>> ts.get_children_types("workspace")  # ["upload"]
    """

    def types(self) -> list[ResourceType]:
        """Return all registered resource types."""
        ...

    def get_type(self, name: str) -> ResourceType | None:
        """Look up a resource type by name.

        Args:
            name: The resource type name (e.g., "workspace", "upload")

        Returns:
            The ResourceType if found, None otherwise
        """
        ...

    def get_children_types(self, parent_type: str) -> list[str]:
        """Get all resource types that are children of the given parent.

        Args:
            parent_type: Name of the parent resource type

        Returns:
            List of child type names (may be empty)
        """
        ...


@runtime_checkable
class RuntimeContext(Protocol):
    """Dynamic state: tracks what resources CURRENTLY exist.

    A RuntimeContext maintains the current state of the system being
    explored, including all live resource instances. It supports
    checkpoint/rollback for branching exploration.

    Example:
        >>> ctx = MyRuntimeContext()
        >>> snap = ctx.snapshot()
        >>> # ... make changes ...
        >>> ctx.restore(snap)  # rollback to saved state
    """

    def snapshot(self) -> Snapshot:
        """Capture current state for later rollback.

        Returns:
            An opaque Snapshot that can be passed to restore()
        """
        ...

    def restore(self, snapshot: Snapshot) -> None:
        """Restore state from a previously captured snapshot.

        Args:
            snapshot: A Snapshot previously returned by snapshot()
        """
        ...


@runtime_checkable
class Action(Protocol):
    """Transformer: defines how state changes.

    An Action represents a single operation that can be performed
    on the system (e.g., create a workspace, upload a file). Actions
    declare their resource requirements and can check preconditions.

    Attributes:
        name: Human-readable identifier for the action
        requires: List of resource type names that must exist for this
                  action to be executable

    Example:
        >>> action = CreateUploadAction()
        >>> action.name  # "create_upload"
        >>> action.requires  # ["workspace"]
        >>> action.can_run(ctx)  # True if a workspace exists
    """

    name: str
    requires: list[str]

    def can_run(self, ctx: RuntimeContext) -> bool:
        """Check if this action can be executed in the current context.

        This should verify that all required resources exist and any
        other preconditions are met.

        Args:
            ctx: The current runtime context

        Returns:
            True if the action can be executed, False otherwise
        """
        ...


@runtime_checkable
class Explorer(Protocol):
    """Strategy: determines how to traverse the state space.

    An Explorer implements a traversal strategy (BFS, DFS, random, etc.)
    for exploring the state space defined by available actions.

    Example:
        >>> explorer = BFSExplorer(max_depth=10)
        >>> while not explorer.should_stop():
        ...     action = explorer.next_action(ctx, actions)
        ...     if action:
        ...         action.execute(ctx)
    """

    def next_action(
        self,
        ctx: RuntimeContext,
        actions: list[Action]
    ) -> Action | None:
        """Select the next action to execute.

        The explorer filters actions by can_run() and selects one
        according to its strategy.

        Args:
            ctx: The current runtime context
            actions: All available actions

        Returns:
            The selected action, or None if no action is available
        """
        ...

    def should_stop(self) -> bool:
        """Check if exploration should terminate.

        Returns:
            True if exploration should stop (e.g., max depth reached,
            coverage satisfied, etc.)
        """
        ...
