"""GraphQL action decorators for VenomQA.

Provides decorators for defining GraphQL queries, mutations, and subscriptions
as reusable, type-safe actions.

Example:
    >>> from venomqa.graphql import query, mutation
    >>>
    >>> @query("GetUser")
    >>> def get_user(client, ctx, user_id: str):
    ...     return client.graphql(
    ...         query='query GetUser($id: ID!) { user(id: $id) { id name } }',
    ...         variables={"id": user_id}
    ...     )
    >>>
    >>> @mutation("CreateUser")
    >>> def create_user(client, ctx, name: str, email: str):
    ...     return client.graphql(
    ...         query='mutation CreateUser($input: CreateUserInput!) { ... }',
    ...         variables={"input": {"name": name, "email": email}}
    ...     )
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from venomqa.http.graphql import GraphQLResponse

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class GraphQLActionMetadata:
    """Metadata for a GraphQL action.

    Attributes:
        operation_name: The GraphQL operation name.
        operation_type: Type of operation (query, mutation, subscription).
        description: Optional description of the action.
        tags: Tags for categorization.
        requires_auth: Whether the action requires authentication.
        timeout: Custom timeout for this action.
        retry_on_error: Whether to retry on transient errors.
    """

    operation_name: str
    operation_type: str = "query"
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    requires_auth: bool = False
    timeout: float | None = None
    retry_on_error: bool = True


# Registry of all GraphQL actions
_action_registry: dict[str, tuple[Callable, GraphQLActionMetadata]] = {}


def get_action_registry() -> dict[str, tuple[Callable, GraphQLActionMetadata]]:
    """Get the global action registry.

    Returns:
        Dictionary mapping action names to (function, metadata) tuples.
    """
    return _action_registry.copy()


def get_action(name: str) -> tuple[Callable, GraphQLActionMetadata] | None:
    """Get a registered action by name.

    Args:
        name: The action name (operation name or qualified name).

    Returns:
        Tuple of (function, metadata) or None if not found.
    """
    return _action_registry.get(name)


def query(
    operation_name: str | None = None,
    *,
    description: str | None = None,
    tags: list[str] | None = None,
    requires_auth: bool = False,
    timeout: float | None = None,
    retry_on_error: bool = True,
) -> Callable[[F], F]:
    """Decorator to mark a function as a GraphQL query action.

    Args:
        operation_name: The GraphQL operation name. Defaults to function name.
        description: Optional description of the query.
        tags: Tags for categorization.
        requires_auth: Whether the query requires authentication.
        timeout: Custom timeout for this query.
        retry_on_error: Whether to retry on transient errors.

    Returns:
        Decorator function.

    Example:
        >>> @query("GetProducts")
        >>> def get_products(client, ctx, first: int = 10):
        ...     return client.graphql(
        ...         query='''
        ...             query GetProducts($first: Int!) {
        ...                 products(first: $first) {
        ...                     edges { node { id title price } }
        ...                 }
        ...             }
        ...         ''',
        ...         variables={"first": first}
        ...     )
    """
    return _create_action_decorator(
        operation_type="query",
        operation_name=operation_name,
        description=description,
        tags=tags,
        requires_auth=requires_auth,
        timeout=timeout,
        retry_on_error=retry_on_error,
    )


def mutation(
    operation_name: str | None = None,
    *,
    description: str | None = None,
    tags: list[str] | None = None,
    requires_auth: bool = True,
    timeout: float | None = None,
    retry_on_error: bool = False,
) -> Callable[[F], F]:
    """Decorator to mark a function as a GraphQL mutation action.

    Args:
        operation_name: The GraphQL operation name. Defaults to function name.
        description: Optional description of the mutation.
        tags: Tags for categorization.
        requires_auth: Whether the mutation requires authentication (default True).
        timeout: Custom timeout for this mutation.
        retry_on_error: Whether to retry on transient errors (default False).

    Returns:
        Decorator function.

    Example:
        >>> @mutation("CreateProduct")
        >>> def create_product(client, ctx, title: str, price: float):
        ...     return client.graphql(
        ...         query='''
        ...             mutation CreateProduct($input: CreateProductInput!) {
        ...                 createProduct(input: $input) { id title }
        ...             }
        ...         ''',
        ...         variables={"input": {"title": title, "price": price}}
        ...     )
    """
    return _create_action_decorator(
        operation_type="mutation",
        operation_name=operation_name,
        description=description,
        tags=tags,
        requires_auth=requires_auth,
        timeout=timeout,
        retry_on_error=retry_on_error,
    )


def subscription(
    operation_name: str | None = None,
    *,
    description: str | None = None,
    tags: list[str] | None = None,
    requires_auth: bool = True,
    timeout: float | None = None,
) -> Callable[[F], F]:
    """Decorator to mark a function as a GraphQL subscription action.

    Args:
        operation_name: The GraphQL operation name. Defaults to function name.
        description: Optional description of the subscription.
        tags: Tags for categorization.
        requires_auth: Whether the subscription requires authentication.
        timeout: Timeout for subscription events.

    Returns:
        Decorator function.

    Example:
        >>> @subscription("OnProductCreated")
        >>> async def on_product_created(client, ctx):
        ...     async for event in client.subscribe(
        ...         query='subscription { productCreated { id title } }'
        ...     ):
        ...         yield event
    """
    return _create_action_decorator(
        operation_type="subscription",
        operation_name=operation_name,
        description=description,
        tags=tags,
        requires_auth=requires_auth,
        timeout=timeout,
        retry_on_error=False,
    )


def action(
    name: str | None = None,
    *,
    operation_type: str = "query",
    description: str | None = None,
    tags: list[str] | None = None,
    requires_auth: bool = False,
    timeout: float | None = None,
    retry_on_error: bool = True,
) -> Callable[[F], F]:
    """Generic decorator for GraphQL actions.

    Use this when you need more control over the action configuration.

    Args:
        name: The action name. Defaults to function name.
        operation_type: Type of operation (query, mutation, subscription).
        description: Optional description of the action.
        tags: Tags for categorization.
        requires_auth: Whether the action requires authentication.
        timeout: Custom timeout for this action.
        retry_on_error: Whether to retry on transient errors.

    Returns:
        Decorator function.
    """
    return _create_action_decorator(
        operation_type=operation_type,
        operation_name=name,
        description=description,
        tags=tags,
        requires_auth=requires_auth,
        timeout=timeout,
        retry_on_error=retry_on_error,
    )


def _create_action_decorator(
    operation_type: str,
    operation_name: str | None,
    description: str | None,
    tags: list[str] | None,
    requires_auth: bool,
    timeout: float | None,
    retry_on_error: bool,
) -> Callable[[F], F]:
    """Create a decorator for GraphQL actions.

    Args:
        operation_type: Type of GraphQL operation.
        operation_name: Name of the operation.
        description: Description of the action.
        tags: Tags for categorization.
        requires_auth: Whether authentication is required.
        timeout: Custom timeout.
        retry_on_error: Whether to retry on errors.

    Returns:
        Decorator function.
    """

    def decorator(func: F) -> F:
        op_name = operation_name or func.__name__

        metadata = GraphQLActionMetadata(
            operation_name=op_name,
            operation_type=operation_type,
            description=description or func.__doc__,
            tags=tags or [],
            requires_auth=requires_auth,
            timeout=timeout,
            retry_on_error=retry_on_error,
        )

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> GraphQLResponse:
            logger.debug(f"Executing GraphQL {operation_type}: {op_name}")

            # Extract client from args if needed for timeout/retry handling
            client = args[0] if args else kwargs.get("client")

            # Apply custom timeout if specified
            original_timeout = None
            if timeout is not None and client and hasattr(client, "timeout"):
                original_timeout = client.timeout
                client.timeout = timeout

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                if retry_on_error and _is_retryable_error(e):
                    logger.warning(f"Retrying {op_name} after error: {e}")
                    # Simple retry - more sophisticated retry is in the client
                    return func(*args, **kwargs)
                raise
            finally:
                if original_timeout is not None and client:
                    client.timeout = original_timeout

        # Attach metadata
        wrapper._graphql_metadata = metadata  # type: ignore
        wrapper._is_graphql_action = True  # type: ignore

        # Register the action
        _action_registry[op_name] = (wrapper, metadata)

        return wrapper  # type: ignore

    return decorator


def _is_retryable_error(error: Exception) -> bool:
    """Check if an error is retryable.

    Args:
        error: The exception to check.

    Returns:
        True if the error is retryable.
    """
    from venomqa.errors import ConnectionError, RequestTimeoutError

    # Network errors are retryable
    if isinstance(error, (ConnectionError, RequestTimeoutError)):
        return True

    # Check for common retryable error messages
    error_str = str(error).lower()
    retryable_patterns = [
        "timeout",
        "connection refused",
        "connection reset",
        "temporary failure",
        "service unavailable",
        "rate limit",
    ]
    return any(pattern in error_str for pattern in retryable_patterns)


def get_graphql_metadata(func: Callable) -> GraphQLActionMetadata | None:
    """Get GraphQL metadata from a decorated function.

    Args:
        func: The decorated function.

    Returns:
        GraphQLActionMetadata or None if not a GraphQL action.
    """
    return getattr(func, "_graphql_metadata", None)


def is_graphql_action(func: Callable) -> bool:
    """Check if a function is a GraphQL action.

    Args:
        func: The function to check.

    Returns:
        True if the function is a GraphQL action.
    """
    return getattr(func, "_is_graphql_action", False)


def list_actions(
    operation_type: str | None = None,
    tags: list[str] | None = None,
) -> list[tuple[str, GraphQLActionMetadata]]:
    """List registered GraphQL actions.

    Args:
        operation_type: Filter by operation type (query, mutation, subscription).
        tags: Filter by tags (any match).

    Returns:
        List of (name, metadata) tuples.
    """
    results = []

    for name, (_, metadata) in _action_registry.items():
        if operation_type and metadata.operation_type != operation_type:
            continue
        if tags and not any(tag in metadata.tags for tag in tags):
            continue
        results.append((name, metadata))

    return results


def clear_action_registry() -> None:
    """Clear the action registry. Useful for testing."""
    _action_registry.clear()
