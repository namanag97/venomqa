"""Core domain models for VenomQA.

This module defines the fundamental building blocks for creating test journeys:
- Step: Individual actions with assertions
- Checkpoint: Savepoints for database state rollback
- Branch: Fork execution to explore multiple paths
- Journey: Complete user scenarios combining all elements

Example:
    >>> from venomqa.core import Step, Journey, Checkpoint, Branch, Path
    >>>
    >>> # Create a simple journey
    >>> journey = Journey(
    ...     name="user_registration",
    ...     steps=[
    ...         Step(name="create_user",
    ...              action=lambda c, ctx: c.post("/users", json={"name": "test"})),
    ...         Checkpoint(name="after_create"),
    ...         Branch(
    ...             checkpoint_name="after_create",
    ...             paths=[
    ...                 Path(name="update_user", steps=[
    ...                     Step(name="update",
    ...                          action=lambda c, ctx: c.patch("/users/1"))
    ...                 ]),
    ...                 Path(name="delete_user", steps=[
    ...                     Step(name="delete",
    ...                          action=lambda c, ctx: c.delete("/users/1"))
    ...                 ]),
    ...             ]
    ...         )
    ...     ]
    ... )
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from venomqa.errors import ErrorContext, JourneyValidationError

if TYPE_CHECKING:
    pass


class Severity(Enum):
    """Issue severity levels for categorizing test failures.

    Attributes:
        CRITICAL: System-breaking issues requiring immediate attention.
        HIGH: Major functionality broken, significant impact.
        MEDIUM: Feature partially working, moderate impact.
        LOW: Minor issues, cosmetic problems.
        INFO: Informational notes, not actual failures.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    def __lt__(self, other: Severity) -> bool:
        """Compare severity levels for sorting."""
        order = [Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        return order.index(self) < order.index(other)

    def __le__(self, other: Severity) -> bool:
        """Compare severity levels for sorting."""
        return self == other or self < other


ActionCallable = Callable[..., Any]


class Step(BaseModel):
    """A single action in a journey with optional assertions.

    Steps are the fundamental unit of work in VenomQA. Each step executes
    an action (typically an HTTP request) and can have associated assertions
    to validate the response.

    Attributes:
        name: Unique identifier for this step within its journey.
        action: Callable or string reference to execute. String references
            are resolved via the plugin registry.
        description: Human-readable description of what this step does.
        expect_failure: If True, the step is expected to fail. Useful for
            testing error handling.
        timeout: Maximum execution time in seconds. None uses journey default.
        retries: Number of retry attempts on failure.
        requires_ports: List of port names required by this step.
        args: Additional keyword arguments passed to the action.

    Example:
        >>> def get_user(client, ctx):
        ...     return client.get("/users/1")
        >>>
        >>> step = Step(
        ...     name="fetch_user",
        ...     action=get_user,
        ...     description="Fetch user by ID",
        ...     timeout=10.0,
        ...     retries=2
        ... )
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        validate_assignment=True,
    )

    name: str = Field(..., min_length=1, max_length=100, description="Unique step identifier")
    action: ActionCallable | str = Field(..., description="Action callable or string reference")
    description: str = Field(default="", max_length=500, description="Human-readable description")
    expect_failure: bool = Field(default=False, description="Whether failure is expected")
    timeout: float | None = Field(
        default=None,
        ge=0.1,
        le=3600.0,
        description="Timeout in seconds",
    )
    retries: int = Field(default=0, ge=0, le=10, description="Number of retry attempts")
    requires_ports: list[str] | None = Field(
        default=None,
        description="Required port names",
    )
    args: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional action arguments",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Step name cannot be empty or whitespace")
        if not v[0].isalpha() and v[0] != "_":
            raise ValueError("Step name must start with a letter or underscore")
        return v.strip()

    @field_validator("action", mode="before")
    @classmethod
    def validate_action(cls, v: Any) -> ActionCallable | str:
        if isinstance(v, str):
            if not v.strip():
                raise ValueError("Action string reference cannot be empty")
            return v.strip()
        if callable(v):
            return v
        raise ValueError("Action must be a callable or string reference")

    def get_action_callable(self, resolver: Any = None) -> ActionCallable:
        """Resolve action to callable, handling string references.

        Args:
            resolver: Optional ActionResolver to use for string references.
                     If not provided, falls back to the global registry.

        Returns:
            The resolved callable for this step's action.

        Raises:
            PluginError: If string reference cannot be resolved.
        """
        if callable(self.action):
            return self.action

        # Use provided resolver or fall back to global registry
        if resolver is not None:
            return resolver.resolve(self.action)

        from venomqa.plugins.registry import get_registry

        registry = get_registry()
        return registry.resolve_action(self.action)

    def __hash__(self) -> int:
        return hash(self.name)


class Checkpoint(BaseModel):
    """A savepoint for database state enabling rollback.

    Checkpoints capture the database state at a specific point in the journey,
    allowing subsequent steps to be rolled back. This is essential for testing
    multiple paths from the same starting state without re-running setup.

    Attributes:
        name: Unique identifier for this checkpoint.

    Example:
        >>> checkpoint = Checkpoint(name="after_user_creation")
        >>> journey = Journey(
        ...     name="test",
        ...     steps=[
        ...         Step(name="create", action=create_user),
        ...         checkpoint,
        ...         Branch(checkpoint_name=checkpoint.name, paths=[...])
        ...     ]
        ... )
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    name: str = Field(..., min_length=1, max_length=100, description="Unique checkpoint identifier")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Checkpoint name cannot be empty or whitespace")
        return v.strip()

    def __hash__(self) -> int:
        return hash(self.name)


class Path(BaseModel):
    """A sequence of steps within a branch for parallel exploration.

    Paths allow testing multiple scenarios from a common checkpoint,
    executing independently to verify different outcomes.

    Attributes:
        name: Unique identifier for this path.
        steps: Ordered list of steps and checkpoints to execute.
        description: Human-readable description of this path's purpose.

    Example:
        >>> path = Path(
        ...     name="successful_checkout",
        ...     steps=[
        ...         Step(name="add_to_cart", action=add_item),
        ...         Step(name="checkout", action=checkout),
        ...     ],
        ...     description="Test successful checkout flow"
        ... )
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        validate_assignment=True,
    )

    name: str = Field(..., min_length=1, max_length=100, description="Unique path identifier")
    steps: list[Step | Checkpoint] = Field(
        default_factory=list,
        description="Ordered steps and checkpoints",
    )
    description: str = Field(default="", max_length=500, description="Path description")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Path name cannot be empty or whitespace")
        return v.strip()

    def get_steps_only(self) -> list[Step]:
        """Get only Step objects, excluding Checkpoints."""
        return [s for s in self.steps if isinstance(s, Step)]

    def __hash__(self) -> int:
        return hash(self.name)


class Branch(BaseModel):
    """Fork execution to explore multiple paths from a checkpoint.

    Branches enable testing multiple scenarios by rolling back to a
    checkpoint and executing different paths. Each path runs independently
    with the same starting state.

    Attributes:
        checkpoint_name: Name of the checkpoint to rollback to.
        paths: List of paths to execute from the checkpoint.

    Example:
        >>> branch = Branch(
        ...     checkpoint_name="after_order_created",
        ...     paths=[
        ...         Path(name="cancel_order", steps=[...]),
        ...         Path(name="complete_order", steps=[...]),
        ...         Path(name="refund_order", steps=[...]),
        ...     ]
        ... )
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        validate_assignment=True,
    )

    checkpoint_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Target checkpoint name",
    )
    paths: list[Path] = Field(
        default_factory=list,
        description="Paths to execute",
    )

    @field_validator("checkpoint_name")
    @classmethod
    def validate_checkpoint_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Checkpoint name cannot be empty or whitespace")
        return v.strip()

    def __hash__(self) -> int:
        return hash(self.checkpoint_name)


class StepResult(BaseModel):
    """Result of executing a single step.

    Captures the outcome of step execution including timing, response data,
    and any errors encountered.

    Attributes:
        step_name: Name of the executed step.
        success: Whether the step completed successfully.
        started_at: Timestamp when execution began.
        finished_at: Timestamp when execution completed.
        response: Response data from the action (e.g., HTTP response).
        error: Error message if the step failed.
        request: Request data sent to the action.
        duration_ms: Execution duration in milliseconds.

    Example:
        >>> result = StepResult(
        ...     step_name="get_user",
        ...     success=True,
        ...     started_at=datetime.now(),
        ...     finished_at=datetime.now(),
        ...     response={"status_code": 200, "body": {"id": 1}},
        ...     duration_ms=45.2
        ... )
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    step_name: str = Field(..., description="Name of the executed step")
    success: bool = Field(..., description="Whether step succeeded")
    started_at: datetime = Field(..., description="Execution start timestamp")
    finished_at: datetime = Field(..., description="Execution end timestamp")
    response: dict[str, Any] | None = Field(default=None, description="Response data")
    error: str | None = Field(default=None, description="Error message if failed")
    request: dict[str, Any] | None = Field(default=None, description="Request data")
    duration_ms: float = Field(default=0.0, ge=0, description="Duration in milliseconds")

    @model_validator(mode="after")
    def validate_consistency(self) -> StepResult:
        if self.success and self.error:
            raise ValueError("Successful step should not have an error message")
        if not self.success and not self.error:
            raise ValueError("Failed step must have an error message")
        if self.finished_at < self.started_at:
            raise ValueError("finished_at cannot be before started_at")
        return self

    @property
    def duration_seconds(self) -> float:
        """Duration in seconds."""
        return self.duration_ms / 1000.0


class PathResult(BaseModel):
    """Result of executing a path within a branch.

    Aggregates step results for a complete path execution.

    Attributes:
        path_name: Name of the executed path.
        success: Whether all steps in the path succeeded.
        step_results: Results for each step in the path.
        error: Error message if the path failed.

    Example:
        >>> result = PathResult(
        ...     path_name="checkout_flow",
        ...     success=True,
        ...     step_results=[step_result1, step_result2]
        ... )
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        validate_assignment=True,
    )

    path_name: str = Field(..., description="Name of the executed path")
    success: bool = Field(..., description="Whether path succeeded")
    step_results: list[StepResult] = Field(
        default_factory=list,
        description="Results for each step",
    )
    error: str | None = Field(default=None, description="Error message if failed")

    @property
    def total_duration_ms(self) -> float:
        """Total duration of all steps in milliseconds."""
        return sum(r.duration_ms for r in self.step_results)

    @property
    def passed_steps(self) -> int:
        """Number of passed steps."""
        return sum(1 for r in self.step_results if r.success)

    @property
    def failed_steps(self) -> int:
        """Number of failed steps."""
        return sum(1 for r in self.step_results if not r.success)


class BranchResult(BaseModel):
    """Result of executing all paths in a branch.

    Aggregates path results for a complete branch execution.

    Attributes:
        checkpoint_name: Name of the checkpoint this branch started from.
        path_results: Results for each path in the branch.

    Example:
        >>> result = BranchResult(
        ...     checkpoint_name="after_setup",
        ...     path_results=[path_result1, path_result2]
        ... )
        >>> print(result.all_passed)
        True
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        validate_assignment=True,
    )

    checkpoint_name: str = Field(..., description="Starting checkpoint name")
    path_results: list[PathResult] = Field(
        default_factory=list,
        description="Results for each path",
    )

    @property
    def all_passed(self) -> bool:
        """Whether all paths in the branch succeeded."""
        if not self.path_results:
            return True
        return all(r.success for r in self.path_results)

    @property
    def passed_paths(self) -> int:
        """Number of passed paths."""
        return sum(1 for r in self.path_results if r.success)

    @property
    def failed_paths(self) -> int:
        """Number of failed paths."""
        return sum(1 for r in self.path_results if not r.success)


class Issue(BaseModel):
    """Captured failure with full context for debugging.

    Issues represent test failures with rich context to aid debugging,
    including automatic suggestion generation based on error patterns.

    Attributes:
        journey: Name of the journey where the issue occurred.
        path: Name of the path where the issue occurred.
        step: Name of the step that failed.
        error: The error message or description.
        severity: Severity level of the issue.
        request: Request data that caused the failure.
        response: Response data received before failure.
        logs: Relevant log entries for debugging.
        suggestion: Auto-generated or custom fix suggestion.
        timestamp: When the issue was captured.

    Example:
        >>> issue = Issue(
        ...     journey="user_auth",
        ...     path="main",
        ...     step="login",
        ...     error="HTTP 401: Invalid credentials",
        ...     severity=Severity.HIGH
        ... )
        >>> print(issue.suggestion)
        "Check authentication - token may be invalid or expired"
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    journey: str = Field(..., min_length=1, description="Journey name")
    path: str = Field(..., min_length=1, description="Path name")
    step: str = Field(..., min_length=1, description="Step name")
    error: str = Field(..., min_length=1, description="Error message")
    severity: Severity = Field(default=Severity.HIGH, description="Issue severity")
    request: dict[str, Any] | None = Field(default=None, description="Request data")
    response: dict[str, Any] | None = Field(default=None, description="Response data")
    logs: list[str] = Field(default_factory=list, description="Debug logs")
    suggestion: str = Field(default="", description="Fix suggestion")
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Issue timestamp",
    )

    @model_validator(mode="after")
    def generate_suggestion_if_needed(self) -> Issue:
        if not self.suggestion:
            self.suggestion = self._generate_suggestion()
        return self

    def _generate_suggestion(self) -> str:
        """Auto-generate fix suggestion based on error patterns."""
        error_lower = self.error.lower()
        suggestions: dict[str, str] = {
            "401": "Check authentication - token may be invalid or expired",
            "403": "Permission denied - check user roles and permissions",
            "404": "Endpoint not found - verify route registration and URL path",
            "409": "Conflict - resource already exists or state mismatch",
            "422": "Validation error - check request body schema",
            "429": "Rate limited - reduce request frequency or add delays",
            "500": "Server error - check backend logs for exception traceback",
            "502": "Bad gateway - check upstream service availability",
            "503": "Service unavailable - check service health and capacity",
            "504": "Gateway timeout - check upstream service response time",
            "timeout": "Operation timed out - check if service is healthy",
            "timed out": "Operation timed out - check if service is healthy",
            "connection refused": "Service not running - check Docker or network",
            "connection reset": "Connection closed - check service stability",
            "connection timeout": "Cannot reach service - check network/firewall",
            "ssl": "SSL/TLS error - check certificates and protocol settings",
            "dns": "DNS resolution failed - check hostname and DNS configuration",
            "auth": "Authentication failed - verify credentials and auth config",
            "permission": "Permission denied - check file/directory permissions",
            "not found": "Resource not found - verify the resource exists",
            "invalid": "Invalid input - check data format and constraints",
            "duplicate": "Duplicate entry - check for unique constraint violations",
            "foreign key": "Foreign key constraint - ensure referenced entities exist",
            "null": "Null value not allowed - provide required fields",
            "json": "JSON parsing error - check request/response format",
            "schema": "Schema validation failed - check data structure",
        }

        for pattern, suggestion in suggestions.items():
            if pattern in error_lower:
                return suggestion

        return "Review the error details and check system logs"

    def to_dict(self) -> dict[str, Any]:
        """Convert issue to dictionary for serialization."""
        return {
            "journey": self.journey,
            "path": self.path,
            "step": self.step,
            "error": self.error,
            "severity": self.severity.value,
            "request": self.request,
            "response": self.response,
            "logs": self.logs,
            "suggestion": self.suggestion,
            "timestamp": self.timestamp.isoformat(),
        }


class JourneyResult(BaseModel):
    """Result of executing a complete journey.

    Aggregates all results from journey execution including step results,
    branch results, and captured issues.

    Attributes:
        journey_name: Name of the executed journey.
        success: Whether the journey completed successfully.
        started_at: Timestamp when journey execution began.
        finished_at: Timestamp when journey execution completed.
        step_results: Results for main-line steps (not in branches).
        branch_results: Results for all branch executions.
        issues: All issues captured during execution.
        duration_ms: Total execution duration in milliseconds.

    Example:
        >>> result = journey(client)
        >>> print(f"Journey {result.journey_name}: {'PASSED' if result.success else 'FAILED'}")
        >>> print(f"Steps: {result.passed_steps}/{result.total_steps} passed")
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        validate_assignment=True,
    )

    journey_name: str = Field(..., description="Journey name")
    success: bool = Field(..., description="Whether journey succeeded")
    started_at: datetime = Field(..., description="Execution start timestamp")
    finished_at: datetime = Field(..., description="Execution end timestamp")
    step_results: list[StepResult] = Field(
        default_factory=list,
        description="Main path step results",
    )
    branch_results: list[BranchResult] = Field(
        default_factory=list,
        description="Branch execution results",
    )
    issues: list[Issue] = Field(default_factory=list, description="Captured issues")
    duration_ms: float = Field(default=0.0, ge=0, description="Duration in milliseconds")

    @property
    def total_steps(self) -> int:
        """Total number of steps executed."""
        return len(self.step_results)

    @property
    def passed_steps(self) -> int:
        """Number of passed steps."""
        return sum(1 for r in self.step_results if r.success)

    @property
    def failed_steps(self) -> int:
        """Number of failed steps."""
        return sum(1 for r in self.step_results if not r.success)

    @property
    def total_paths(self) -> int:
        """Total number of branch paths executed."""
        return sum(len(b.path_results) for b in self.branch_results)

    @property
    def passed_paths(self) -> int:
        """Number of passed branch paths."""
        return sum(1 for b in self.branch_results for p in b.path_results if p.success)

    @property
    def failed_paths(self) -> int:
        """Number of failed branch paths."""
        return sum(1 for b in self.branch_results for p in b.path_results if not p.success)

    @property
    def duration_seconds(self) -> float:
        """Duration in seconds."""
        return self.duration_ms / 1000.0

    @property
    def critical_issues(self) -> list[Issue]:
        """Issues with CRITICAL severity."""
        return [i for i in self.issues if i.severity == Severity.CRITICAL]

    @property
    def high_severity_issues(self) -> list[Issue]:
        """Issues with HIGH or CRITICAL severity."""
        return [i for i in self.issues if i.severity in (Severity.CRITICAL, Severity.HIGH)]

    def get_issues_by_severity(self, severity: Severity) -> list[Issue]:
        """Get issues filtered by severity level."""
        return [i for i in self.issues if i.severity == severity]

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary for serialization."""
        return {
            "journey_name": self.journey_name,
            "success": self.success,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration_ms": self.duration_ms,
            "total_steps": self.total_steps,
            "passed_steps": self.passed_steps,
            "failed_steps": self.failed_steps,
            "total_paths": self.total_paths,
            "passed_paths": self.passed_paths,
            "failed_paths": self.failed_paths,
            "issues_count": len(self.issues),
            "critical_issues_count": len(self.critical_issues),
        }


StepOrCheckpointOrBranch = Step | Checkpoint | Branch


class Journey(BaseModel):
    """A complete user scenario from start to finish.

    Journeys are the top-level container for test scenarios, combining
    steps, checkpoints, and branches to model complex user flows.

    Attributes:
        name: Unique identifier for this journey.
        steps: Ordered list of steps, checkpoints, and branches.
        description: Human-readable description of the journey.
        tags: Tags for categorization and filtering.
        timeout: Default timeout for steps (seconds). None = no limit.
        requires: List of required services/capabilities.

    Example:
        >>> class UserJourney(Journey):
        ...     def invariants(self):
        ...         return [
        ...             SQLInvariant(
        ...                 query="SELECT COUNT(*) FROM users",
        ...                 expected=1,
        ...                 message="Should have exactly 1 user"
        ...             )
        ...         ]
        >>>
        >>> journey = UserJourney(
        ...     name="user_crud",
        ...     steps=[
        ...         Step(name="create", action=create_user),
        ...         Checkpoint(name="after_create"),
        ...         Step(name="read", action=get_user),
        ...     ],
        ...     tags=["user", "crud", "smoke"]
        ... )
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        validate_assignment=True,
    )

    name: str = Field(..., min_length=1, max_length=100, description="Journey identifier")
    steps: list[StepOrCheckpointOrBranch] = Field(
        default_factory=list,
        description="Ordered steps, checkpoints, and branches",
    )
    description: str = Field(default="", max_length=1000, description="Journey description")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")
    timeout: float | None = Field(
        default=None,
        ge=0.1,
        le=86400.0,
        description="Default step timeout in seconds",
    )
    requires: list[str] = Field(
        default_factory=list,
        description="Required services/capabilities",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Journey name cannot be empty or whitespace")
        if not v[0].isalpha() and v[0] != "_":
            raise ValueError("Journey name must start with a letter or underscore")
        return v.strip()

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        return [tag.strip().lower() for tag in v if tag.strip()]

    @model_validator(mode="after")
    def validate_checkpoints(self) -> Journey:
        """Ensure Branch checkpoint_names reference existing Checkpoints."""
        checkpoint_names: set[str] = set()
        branch_refs: set[str] = set()

        for step in self.steps:
            if isinstance(step, Checkpoint):
                checkpoint_names.add(step.name)
            elif isinstance(step, Branch):
                branch_refs.add(step.checkpoint_name)

        missing = branch_refs - checkpoint_names
        if missing:
            raise JourneyValidationError(
                message=f"Branch references undefined checkpoint(s): {missing}",
                field="steps",
                context=ErrorContext(
                    extra={
                        "missing_checkpoints": list(missing),
                        "available_checkpoints": list(checkpoint_names),
                    }
                ),
            )
        return self

    def get_steps(self) -> list[Step]:
        """Get all Step objects (not Checkpoints or Branches) from main path."""
        result: list[Step] = []
        for step in self.steps:
            if isinstance(step, Step):
                result.append(step)
        return result

    def get_checkpoints(self) -> list[Checkpoint]:
        """Get all Checkpoint objects from the journey."""
        return [s for s in self.steps if isinstance(s, Checkpoint)]

    def get_branches(self) -> list[Branch]:
        """Get all Branch objects from the journey."""
        return [s for s in self.steps if isinstance(s, Branch)]

    def has_tag(self, tag: str) -> bool:
        """Check if journey has a specific tag."""
        return tag.strip().lower() in self.tags

    def validate(self) -> list[str]:
        """Validate journey structure and return list of issues found.

        This method performs comprehensive validation including:
        - Step names are unique across the journey
        - Actions are callable or valid string references
        - Branches have at least one path
        - Paths have at least one step
        - No empty journey

        Returns:
            List of validation issue descriptions. Empty list if valid.

        Example:
            >>> issues = journey.validate()
            >>> if issues:
            ...     for issue in issues:
            ...         print(f"  - {issue}")
            ...     raise ValueError("Journey validation failed")
        """
        issues: list[str] = []

        # Check journey has steps
        if not self.steps:
            issues.append("Journey has no steps defined")
            return issues  # Can't validate further without steps

        # Collect all step names for uniqueness check
        step_names: dict[str, list[str]] = {}  # name -> [locations]

        def collect_step_names(steps: list, location: str) -> None:
            for item in steps:
                if isinstance(item, Step):
                    if item.name not in step_names:
                        step_names[item.name] = []
                    step_names[item.name].append(location)
                elif isinstance(item, Branch):
                    for path in item.paths:
                        collect_step_names(path.steps, f"{location} > {path.name}")

        collect_step_names(self.steps, "main")

        # Check for duplicate step names
        for name, locations in step_names.items():
            if len(locations) > 1:
                issues.append(
                    f"Duplicate step name '{name}' found in: {', '.join(locations)}"
                )

        # Check branches have paths and paths have steps
        for item in self.steps:
            if isinstance(item, Branch):
                if not item.paths:
                    issues.append(
                        f"Branch at checkpoint '{item.checkpoint_name}' has no paths"
                    )
                for path in item.paths:
                    if not path.steps:
                        issues.append(
                            f"Path '{path.name}' in branch '{item.checkpoint_name}' has no steps"
                        )

        # Check actions are callable or valid string references
        def check_actions(steps: list, location: str) -> None:
            for item in steps:
                if isinstance(item, Step):
                    if not callable(item.action) and not isinstance(item.action, str):
                        issues.append(
                            f"Step '{item.name}' in {location}: action must be callable or string reference"
                        )
                elif isinstance(item, Branch):
                    for path in item.paths:
                        check_actions(path.steps, f"{location} > {path.name}")

        check_actions(self.steps, "main")

        return issues

    def validate_or_raise(self) -> None:
        """Validate journey and raise JourneyValidationError if invalid.

        Raises:
            JourneyValidationError: If journey has structural issues.

        Example:
            >>> journey.validate_or_raise()  # Raises if invalid
            >>> runner.run(journey)  # Safe to run
        """
        issues = self.validate()
        if issues:
            raise JourneyValidationError(
                message=f"Journey '{self.name}' has {len(issues)} validation issue(s)",
                field="journey",
                context=ErrorContext(
                    journey_name=self.name,
                    extra={"issues": issues},
                ),
            )

    def __call__(self, client: Any, context: Any = None) -> JourneyResult:
        """Execute the journey with a client and optional context.

        Args:
            client: HTTP client for making requests.
            context: Optional execution context for sharing state.

        Returns:
            JourneyResult from executing the journey.
        """
        from venomqa.runner import JourneyRunner

        runner = JourneyRunner(client=client)
        return runner.run(self)

    def invariants(self) -> list[Any]:
        """Return list of invariants to check after journey execution.

        Override this method in subclasses to define custom invariants
        that verify system state after journey completion.

        Returns:
            List of invariant objects (e.g., SQLInvariant instances).

        Example:
            >>> class OrderJourney(Journey):
            ...     def invariants(self):
            ...         return [
            ...             SQLInvariant(
            ...                 query="SELECT status FROM orders WHERE id = 1",
            ...                 expected="completed",
            ...             )
            ...         ]
        """
        return []

    def __hash__(self) -> int:
        return hash(self.name)
