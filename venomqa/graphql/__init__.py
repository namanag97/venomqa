"""VenomQA GraphQL Testing Module.

Provides comprehensive GraphQL testing capabilities including:
- Query and mutation decorators for defining GraphQL actions
- Schema validation from introspection or SDL files
- Fragment support and query composition
- Subscription support with WebSocket transport
- GraphQL-specific assertions
- Code generation from GraphQL schemas

Example:
    >>> from venomqa.graphql import query, mutation, GraphQLTester
    >>> from venomqa.graphql import expect_graphql
    >>>
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
    >>>
    >>> response = get_products(client, ctx, first=5)
    >>> expect_graphql(response).to_have_no_errors()
    >>> expect_graphql(response).to_have_data_at("products.edges[0].node.id")
"""

from venomqa.graphql.actions import action, mutation, query, subscription
from venomqa.graphql.assertions import (
    GraphQLAssertionError,
    GraphQLExpectation,
    assert_graphql_data_at,
    assert_graphql_error_contains,
    assert_graphql_no_errors,
    expect_graphql,
)
from venomqa.graphql.codegen import (
    ActionGenerator,
    GeneratedAction,
    SchemaParser,
    generate_actions_from_schema,
)
from venomqa.graphql.fragments import (
    Fragment,
    FragmentRegistry,
    compose_query,
    fragment,
)
from venomqa.graphql.schema import (
    GraphQLEnumType,
    GraphQLField,
    GraphQLInputType,
    GraphQLObjectType,
    GraphQLSchemaInfo,
    GraphQLTypeKind,
    SchemaValidationError,
    SchemaValidator,
    load_schema_from_file,
    load_schema_from_introspection,
)
from venomqa.graphql.subscriptions import (
    SubscriptionClient,
    SubscriptionEvent,
    SubscriptionHandler,
    SubscriptionOptions,
)
from venomqa.graphql.tester import GraphQLTester

__all__ = [
    # Actions
    "query",
    "mutation",
    "subscription",
    "action",
    # Assertions
    "expect_graphql",
    "GraphQLExpectation",
    "GraphQLAssertionError",
    "assert_graphql_no_errors",
    "assert_graphql_data_at",
    "assert_graphql_error_contains",
    # Schema
    "SchemaValidator",
    "SchemaValidationError",
    "GraphQLSchemaInfo",
    "GraphQLObjectType",
    "GraphQLField",
    "GraphQLEnumType",
    "GraphQLInputType",
    "GraphQLTypeKind",
    "load_schema_from_file",
    "load_schema_from_introspection",
    # Fragments
    "Fragment",
    "FragmentRegistry",
    "fragment",
    "compose_query",
    # Subscriptions
    "SubscriptionClient",
    "SubscriptionEvent",
    "SubscriptionHandler",
    "SubscriptionOptions",
    # Code generation
    "SchemaParser",
    "ActionGenerator",
    "GeneratedAction",
    "generate_actions_from_schema",
    # Tester
    "GraphQLTester",
]
