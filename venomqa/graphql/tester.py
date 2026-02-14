"""GraphQL tester for VenomQA.

Provides a high-level testing interface for GraphQL APIs with
built-in validation, assertions, and subscription support.

Example:
    >>> from venomqa.graphql import GraphQLTester
    >>>
    >>> tester = GraphQLTester("https://api.example.com/graphql")
    >>> tester.load_schema()
    >>>
    >>> # Execute and validate
    >>> response = tester.query('''
    ...     query GetUser($id: ID!) {
    ...         user(id: $id) { id name }
    ...     }
    ... ''', variables={"id": "123"})
    >>>
    >>> tester.expect(response).to_have_no_errors()
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from venomqa.clients.graphql import AsyncGraphQLClient, GraphQLClient, GraphQLResponse
from venomqa.graphql.assertions import GraphQLExpectation, expect_graphql
from venomqa.graphql.schema import (
    GraphQLSchemaInfo,
    SchemaValidationError,
    SchemaValidator,
    load_schema_from_file,
    load_schema_from_introspection,
)
from venomqa.graphql.subscriptions import (
    SubscriptionClient,
    SubscriptionEvent,
    SubscriptionOptions,
)

logger = logging.getLogger(__name__)


class GraphQLTester:
    """High-level GraphQL testing interface.

    Combines schema validation, query execution, and assertions
    in a fluent API for comprehensive GraphQL testing.

    Example:
        >>> tester = GraphQLTester("https://api.example.com/graphql")
        >>>
        >>> # Load and validate schema
        >>> tester.load_schema()
        >>>
        >>> # Execute queries with validation
        >>> response = tester.query('''
        ...     query GetProducts($first: Int!) {
        ...         products(first: $first) {
        ...             edges { node { id title } }
        ...         }
        ...     }
        ... ''', variables={"first": 10})
        >>>
        >>> # Assert on response
        >>> tester.expect(response) \\
        ...     .to_have_no_errors() \\
        ...     .to_have_data_at("products.edges")
    """

    def __init__(
        self,
        endpoint: str,
        timeout: float = 30.0,
        default_headers: dict[str, str] | None = None,
        validate_queries: bool = True,
    ):
        """Initialize the GraphQL tester.

        Args:
            endpoint: GraphQL endpoint URL.
            timeout: Request timeout in seconds.
            default_headers: Headers for all requests.
            validate_queries: Validate queries against schema (default True).
        """
        self.endpoint = endpoint
        self.timeout = timeout
        self.default_headers = default_headers or {}
        self.validate_queries = validate_queries

        self._client: GraphQLClient | None = None
        self._async_client: AsyncGraphQLClient | None = None
        self._subscription_client: SubscriptionClient | None = None
        self._schema: GraphQLSchemaInfo | None = None
        self._validator: SchemaValidator | None = None

    @property
    def client(self) -> GraphQLClient:
        """Get or create the GraphQL client.

        Returns:
            GraphQL client instance.
        """
        if self._client is None:
            self._client = GraphQLClient(
                endpoint=self.endpoint,
                timeout=self.timeout,
                default_headers=self.default_headers,
            )
            self._client.connect()
        return self._client

    @property
    def schema(self) -> GraphQLSchemaInfo | None:
        """Get the loaded schema.

        Returns:
            The schema or None if not loaded.
        """
        return self._schema

    def set_auth_token(self, token: str, token_type: str = "Bearer") -> GraphQLTester:
        """Set authentication token.

        Args:
            token: The auth token.
            token_type: Token type (default: Bearer).

        Returns:
            Self for chaining.
        """
        self.client.set_auth_token(token, token_type)
        return self

    def load_schema(self, source: str | Path | dict[str, Any] | None = None) -> GraphQLTester:
        """Load the GraphQL schema.

        Args:
            source: Schema source (file path, introspection result, or None for introspection).

        Returns:
            Self for chaining.

        Raises:
            SchemaValidationError: If schema loading fails.
        """
        if source is None:
            # Load from introspection
            response = self.client.introspect()
            self._schema = GraphQLSchemaInfo(
                query_type=response.query_type,
                mutation_type=response.mutation_type,
                subscription_type=response.subscription_type,
            )
            # Parse types from introspection
            for name, type_info in response.types.items():
                if not name.startswith("__"):
                    self._schema.types[name] = type_info
        elif isinstance(source, dict):
            self._schema = load_schema_from_introspection(source)
        elif isinstance(source, (str, Path)):
            self._schema = load_schema_from_file(source)
        else:
            raise ValueError(f"Invalid schema source: {type(source)}")

        self._validator = SchemaValidator(self._schema)
        logger.info("Schema loaded successfully")

        return self

    def validate_query(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> list[str]:
        """Validate a query against the schema.

        Args:
            query: The GraphQL query.
            variables: Query variables.

        Returns:
            List of validation errors (empty if valid).

        Raises:
            SchemaValidationError: If schema is not loaded.
        """
        if self._validator is None:
            raise SchemaValidationError("Schema not loaded. Call load_schema() first.")

        return self._validator.validate_query(query, variables)

    def query(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
        validate: bool | None = None,
    ) -> GraphQLResponse:
        """Execute a GraphQL query.

        Args:
            query: The GraphQL query.
            variables: Query variables.
            operation_name: Operation name.
            validate: Override query validation setting.

        Returns:
            GraphQL response.

        Raises:
            SchemaValidationError: If validation fails.
        """
        should_validate = validate if validate is not None else self.validate_queries

        if should_validate and self._validator:
            errors = self._validator.validate_query(query, variables)
            if errors:
                raise SchemaValidationError(
                    f"Query validation failed: {'; '.join(errors)}",
                    errors=errors,
                )

        return self.client.query(query, variables, operation_name)

    def mutate(
        self,
        mutation: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
        validate: bool | None = None,
    ) -> GraphQLResponse:
        """Execute a GraphQL mutation.

        Args:
            mutation: The GraphQL mutation.
            variables: Mutation variables.
            operation_name: Operation name.
            validate: Override query validation setting.

        Returns:
            GraphQL response.

        Raises:
            SchemaValidationError: If validation fails.
        """
        should_validate = validate if validate is not None else self.validate_queries

        if should_validate and self._validator:
            errors = self._validator.validate_query(mutation, variables)
            if errors:
                raise SchemaValidationError(
                    f"Mutation validation failed: {'; '.join(errors)}",
                    errors=errors,
                )

        return self.client.mutate(mutation, variables, operation_name)

    async def subscribe(
        self,
        subscription: str,
        variables: dict[str, Any] | None = None,
        options: SubscriptionOptions | None = None,
    ):
        """Subscribe to a GraphQL subscription.

        Args:
            subscription: The GraphQL subscription.
            variables: Subscription variables.
            options: Subscription options.

        Yields:
            SubscriptionEvent for each received event.
        """
        if self._subscription_client is None:
            self._subscription_client = SubscriptionClient(
                endpoint=self.endpoint,
                timeout=self.timeout,
                default_headers=self.default_headers,
            )
            await self._subscription_client.connect()

        async for event in self._subscription_client.subscribe(
            subscription, variables, options=options
        ):
            yield event

    async def subscribe_once(
        self,
        subscription: str,
        variables: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> SubscriptionEvent:
        """Subscribe and wait for a single event.

        Args:
            subscription: The GraphQL subscription.
            variables: Subscription variables.
            timeout: Maximum time to wait.

        Returns:
            The first event received.
        """
        if self._subscription_client is None:
            self._subscription_client = SubscriptionClient(
                endpoint=self.endpoint,
                timeout=self.timeout,
                default_headers=self.default_headers,
            )
            await self._subscription_client.connect()

        return await self._subscription_client.subscribe_once(
            subscription, variables, timeout
        )

    def expect(self, response: GraphQLResponse) -> GraphQLExpectation:
        """Create an expectation for a GraphQL response.

        Args:
            response: The response to assert on.

        Returns:
            GraphQLExpectation for fluent assertions.

        Example:
            >>> tester.expect(response) \\
            ...     .to_have_no_errors() \\
            ...     .to_have_data_at("users")
        """
        return expect_graphql(response)

    def assert_no_errors(self, response: GraphQLResponse) -> GraphQLTester:
        """Assert that a response has no errors.

        Args:
            response: The response to check.

        Returns:
            Self for chaining.

        Raises:
            GraphQLAssertionError: If response has errors.
        """
        self.expect(response).to_have_no_errors()
        return self

    def assert_data_at(
        self,
        response: GraphQLResponse,
        path: str,
    ) -> GraphQLTester:
        """Assert that data exists at the given path.

        Args:
            response: The response to check.
            path: Path to the data.

        Returns:
            Self for chaining.

        Raises:
            GraphQLAssertionError: If data is not found.
        """
        self.expect(response).to_have_data_at(path)
        return self

    def get_data(
        self,
        response: GraphQLResponse,
        path: str | None = None,
    ) -> Any:
        """Get data from a response.

        Args:
            response: The response.
            path: Optional path to the data.

        Returns:
            The data at the path.
        """
        return response.get_data(path)

    def close(self) -> None:
        """Close all clients and clean up resources."""
        if self._client:
            self._client.disconnect()
            self._client = None

        if self._async_client:
            # Note: async cleanup should be done with async close
            self._async_client = None

    async def aclose(self) -> None:
        """Async close for all clients."""
        self.close()

        if self._subscription_client:
            await self._subscription_client.disconnect()
            self._subscription_client = None

    def __enter__(self) -> GraphQLTester:
        """Enter context manager."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager."""
        self.close()

    async def __aenter__(self) -> GraphQLTester:
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager."""
        await self.aclose()


def create_tester(
    endpoint: str,
    schema_source: str | Path | dict[str, Any] | None = None,
    **kwargs: Any,
) -> GraphQLTester:
    """Create a GraphQL tester with optional schema loading.

    Args:
        endpoint: GraphQL endpoint URL.
        schema_source: Schema source for validation.
        **kwargs: Additional arguments for GraphQLTester.

    Returns:
        Configured GraphQLTester instance.

    Example:
        >>> tester = create_tester(
        ...     "https://api.example.com/graphql",
        ...     schema_source="schema.graphql",
        ... )
    """
    tester = GraphQLTester(endpoint, **kwargs)

    if schema_source is not None:
        tester.load_schema(schema_source)

    return tester
