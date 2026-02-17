"""Tests for VenomQA GraphQL module.

Tests GraphQL-specific features including:
- Action decorators (query, mutation, subscription)
- GraphQL assertions
- Schema validation
- Fragment support
- Subscription handling
- Code generation
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from venomqa.http.graphql import GraphQLError, GraphQLResponse


# Test data
@pytest.fixture
def successful_response() -> GraphQLResponse:
    """Create a successful GraphQL response."""
    return GraphQLResponse(
        data={
            "users": [
                {"id": "1", "name": "Alice", "email": "alice@example.com"},
                {"id": "2", "name": "Bob", "email": "bob@example.com"},
            ],
            "products": {
                "edges": [
                    {"node": {"id": "p1", "title": "Product 1", "price": 99.99}},
                    {"node": {"id": "p2", "title": "Product 2", "price": 149.99}},
                ]
            },
        },
        errors=[],
        status_code=200,
        duration_ms=45.0,
    )


@pytest.fixture
def error_response() -> GraphQLResponse:
    """Create a GraphQL response with errors."""
    return GraphQLResponse(
        data=None,
        errors=[
            GraphQLError(
                message="Cannot query field 'invalid' on type 'Query'",
                locations=[{"line": 1, "column": 3}],
            ),
            GraphQLError(
                message="Field 'user' is missing required argument 'id'",
                extensions={"code": "VALIDATION_ERROR"},
            ),
        ],
        status_code=200,
        duration_ms=10.0,
    )


@pytest.fixture
def partial_response() -> GraphQLResponse:
    """Create a GraphQL response with partial data and errors."""
    return GraphQLResponse(
        data={"user": {"id": "1", "name": "Alice"}},
        errors=[
            GraphQLError(
                message="Permission denied for field 'email'",
                path=["user", "email"],
            )
        ],
        status_code=200,
        duration_ms=30.0,
    )


class TestGraphQLActions:
    """Tests for GraphQL action decorators."""

    def test_query_decorator_registers_action(self) -> None:
        """Test that @query decorator registers the action."""
        from venomqa.graphql.actions import (
            clear_action_registry,
            get_action,
            query,
        )

        clear_action_registry()

        @query("GetUsers")
        def get_users(client: Any, ctx: Any) -> GraphQLResponse:
            """Get all users."""
            return GraphQLResponse(data={"users": []})

        action_tuple = get_action("GetUsers")
        assert action_tuple is not None
        func, metadata = action_tuple
        assert metadata.operation_name == "GetUsers"
        assert metadata.operation_type == "query"

    def test_mutation_decorator_sets_requires_auth(self) -> None:
        """Test that @mutation decorator sets requires_auth by default."""
        from venomqa.graphql.actions import (
            clear_action_registry,
            get_action,
            mutation,
        )

        clear_action_registry()

        @mutation("CreateUser")
        def create_user(client: Any, ctx: Any, name: str) -> GraphQLResponse:
            """Create a user."""
            return GraphQLResponse(data={"createUser": {"id": "1"}})

        action_tuple = get_action("CreateUser")
        assert action_tuple is not None
        _, metadata = action_tuple
        assert metadata.requires_auth is True
        assert metadata.retry_on_error is False

    def test_subscription_decorator(self) -> None:
        """Test that @subscription decorator works correctly."""
        from venomqa.graphql.actions import (
            clear_action_registry,
            get_action,
            subscription,
        )

        clear_action_registry()

        @subscription("OnUserCreated")
        async def on_user_created(client: Any, ctx: Any):
            """Subscribe to user creation events."""
            yield GraphQLResponse(data={"userCreated": {"id": "1"}})

        action_tuple = get_action("OnUserCreated")
        assert action_tuple is not None
        _, metadata = action_tuple
        assert metadata.operation_type == "subscription"

    def test_action_with_tags(self) -> None:
        """Test action with tags for filtering."""
        from venomqa.graphql.actions import (
            clear_action_registry,
            list_actions,
            query,
        )

        clear_action_registry()

        @query("GetProducts", tags=["products", "catalog"])
        def get_products(client: Any, ctx: Any) -> GraphQLResponse:
            return GraphQLResponse(data={"products": []})

        @query("GetOrders", tags=["orders"])
        def get_orders(client: Any, ctx: Any) -> GraphQLResponse:
            return GraphQLResponse(data={"orders": []})

        product_actions = list_actions(tags=["products"])
        assert len(product_actions) == 1
        assert product_actions[0][0] == "GetProducts"

    def test_is_graphql_action(self) -> None:
        """Test checking if a function is a GraphQL action."""
        from venomqa.graphql.actions import (
            clear_action_registry,
            is_graphql_action,
            query,
        )

        clear_action_registry()

        @query("Test")
        def test_action(client: Any, ctx: Any) -> GraphQLResponse:
            return GraphQLResponse(data={})

        def regular_function() -> None:
            pass

        assert is_graphql_action(test_action) is True
        assert is_graphql_action(regular_function) is False


class TestGraphQLAssertions:
    """Tests for GraphQL assertions."""

    def test_to_have_no_errors_passes(self, successful_response: GraphQLResponse) -> None:
        """Test that to_have_no_errors passes for successful response."""
        from venomqa.graphql.assertions import expect_graphql

        expect_graphql(successful_response).to_have_no_errors()

    def test_to_have_no_errors_fails(self, error_response: GraphQLResponse) -> None:
        """Test that to_have_no_errors fails for error response."""
        from venomqa.graphql.assertions import GraphQLAssertionError, expect_graphql

        with pytest.raises(GraphQLAssertionError) as exc_info:
            expect_graphql(error_response).to_have_no_errors()

        assert "to have no errors" in str(exc_info.value)

    def test_to_have_errors(self, error_response: GraphQLResponse) -> None:
        """Test that to_have_errors passes for error response."""
        from venomqa.graphql.assertions import expect_graphql

        expect_graphql(error_response).to_have_errors()

    def test_to_have_error_count(self, error_response: GraphQLResponse) -> None:
        """Test that to_have_error_count works correctly."""
        from venomqa.graphql.assertions import expect_graphql

        expect_graphql(error_response).to_have_error_count(2)

    def test_to_have_error_containing(self, error_response: GraphQLResponse) -> None:
        """Test that to_have_error_containing works correctly."""
        from venomqa.graphql.assertions import expect_graphql

        expect_graphql(error_response).to_have_error_containing("Cannot query field")

    def test_to_have_error_code(self, error_response: GraphQLResponse) -> None:
        """Test that to_have_error_code works correctly."""
        from venomqa.graphql.assertions import expect_graphql

        expect_graphql(error_response).to_have_error_code("VALIDATION_ERROR")

    def test_to_have_data_at_simple_path(self, successful_response: GraphQLResponse) -> None:
        """Test that to_have_data_at works for simple paths."""
        from venomqa.graphql.assertions import expect_graphql

        expect_graphql(successful_response).to_have_data_at("users")

    def test_to_have_data_at_nested_path(self, successful_response: GraphQLResponse) -> None:
        """Test that to_have_data_at works for nested paths."""
        from venomqa.graphql.assertions import expect_graphql

        expect_graphql(successful_response).to_have_data_at("products.edges")

    def test_to_have_data_at_array_index(self, successful_response: GraphQLResponse) -> None:
        """Test that to_have_data_at works with array indices."""
        from venomqa.graphql.assertions import expect_graphql

        expect_graphql(successful_response).to_have_data_at("users[0].name")
        expect_graphql(successful_response).to_have_data_at("products.edges[1].node.title")

    def test_to_have_data_equal(self, successful_response: GraphQLResponse) -> None:
        """Test that to_have_data_equal works correctly."""
        from venomqa.graphql.assertions import expect_graphql

        expect_graphql(successful_response).to_have_data_equal("users[0].name", "Alice")

    def test_to_have_data_length(self, successful_response: GraphQLResponse) -> None:
        """Test that to_have_data_length works correctly."""
        from venomqa.graphql.assertions import expect_graphql

        expect_graphql(successful_response).to_have_data_length("users", 2)

    def test_to_have_data_type(self, successful_response: GraphQLResponse) -> None:
        """Test that to_have_data_type works correctly."""
        from venomqa.graphql.assertions import expect_graphql

        expect_graphql(successful_response).to_have_data_type("users", list)
        expect_graphql(successful_response).to_have_data_type("products.edges[0].node", dict)

    def test_to_be_successful(self, successful_response: GraphQLResponse) -> None:
        """Test that to_be_successful works correctly."""
        from venomqa.graphql.assertions import expect_graphql

        expect_graphql(successful_response).to_be_successful()

    def test_to_have_response_time_under(self, successful_response: GraphQLResponse) -> None:
        """Test that to_have_response_time_under works correctly."""
        from venomqa.graphql.assertions import expect_graphql

        expect_graphql(successful_response).to_have_response_time_under(100.0)

    def test_negation_with_not(self, successful_response: GraphQLResponse) -> None:
        """Test that negation with not_ works."""
        from venomqa.graphql.assertions import expect_graphql

        expect_graphql(successful_response).not_.to_have_errors()

    def test_chained_assertions(self, successful_response: GraphQLResponse) -> None:
        """Test that assertions can be chained."""
        from venomqa.graphql.assertions import expect_graphql

        expect_graphql(successful_response).to_have_no_errors().to_have_data().to_have_data_at("users")

    def test_functional_api(self, successful_response: GraphQLResponse, error_response: GraphQLResponse) -> None:
        """Test the functional assertion API."""
        from venomqa.graphql.assertions import (
            assert_graphql_data_at,
            assert_graphql_error_contains,
            assert_graphql_no_errors,
        )

        assert_graphql_no_errors(successful_response)

        data = assert_graphql_data_at(successful_response, "users[0].name")
        assert data == "Alice"

        assert_graphql_error_contains(error_response, "Cannot query field")


class TestGraphQLSchema:
    """Tests for GraphQL schema validation."""

    @pytest.fixture
    def sample_sdl(self) -> str:
        """Sample GraphQL SDL."""
        return """
            type Query {
                user(id: ID!): User
                users(first: Int): [User!]!
            }

            type Mutation {
                createUser(input: CreateUserInput!): User!
            }

            type User {
                id: ID!
                name: String!
                email: String!
            }

            input CreateUserInput {
                name: String!
                email: String!
            }

            enum UserRole {
                ADMIN
                USER
                GUEST
            }
        """

    def test_load_schema_from_sdl(self, sample_sdl: str, tmp_path) -> None:
        """Test loading schema from SDL file."""
        from venomqa.graphql.schema import load_schema_from_file

        schema_file = tmp_path / "schema.graphql"
        schema_file.write_text(sample_sdl)

        schema = load_schema_from_file(schema_file)

        assert schema.query_type == "Query"
        assert schema.mutation_type == "Mutation"
        assert "User" in schema.types
        assert "CreateUserInput" in schema.inputs
        assert "UserRole" in schema.enums

    def test_schema_validator_valid_query(self, sample_sdl: str, tmp_path) -> None:
        """Test schema validator with valid query."""
        from venomqa.graphql.schema import SchemaValidator, load_schema_from_file

        schema_file = tmp_path / "schema.graphql"
        schema_file.write_text(sample_sdl)
        schema = load_schema_from_file(schema_file)
        validator = SchemaValidator(schema)

        errors = validator.validate_query(
            """
            query GetUser($id: ID!) {
                user(id: $id) {
                    id
                    name
                    email
                }
            }
            """,
            variables={"id": "123"},
        )

        assert len(errors) == 0

    def test_schema_validator_variable_type_checking(self, sample_sdl: str, tmp_path) -> None:
        """Test schema validator checks variable types."""
        from venomqa.graphql.schema import SchemaValidator, load_schema_from_file

        schema_file = tmp_path / "schema.graphql"
        schema_file.write_text(sample_sdl)
        schema = load_schema_from_file(schema_file)
        validator = SchemaValidator(schema)

        # Wrong type for variable
        errors = validator.validate_query(
            """
            query GetUser($id: ID!) {
                user(id: $id) { id }
            }
            """,
            variables={"id": 123.5},  # Float instead of ID (string/int)
        )

        # The validator should catch this
        assert any("ID" in e for e in errors)

    def test_schema_get_query_fields(self, sample_sdl: str, tmp_path) -> None:
        """Test getting query fields from schema."""
        from venomqa.graphql.schema import load_schema_from_file

        schema_file = tmp_path / "schema.graphql"
        schema_file.write_text(sample_sdl)
        schema = load_schema_from_file(schema_file)

        query_fields = schema.get_query_fields()
        assert "user" in query_fields
        assert "users" in query_fields


class TestGraphQLFragments:
    """Tests for GraphQL fragment support."""

    def test_fragment_registration(self) -> None:
        """Test fragment registration with decorator."""
        from venomqa.graphql.fragments import (
            FragmentRegistry,
            fragment,
        )

        registry = FragmentRegistry()

        @fragment("UserFields", on="User", registry=registry)
        def user_fields():
            return """
                id
                name
                email
            """

        frag = registry.get("UserFields")
        assert frag is not None
        assert frag.name == "UserFields"
        assert frag.on_type == "User"
        assert "id" in frag.fields

    def test_fragment_to_graphql(self) -> None:
        """Test converting fragment to GraphQL string."""
        from venomqa.graphql.fragments import Fragment

        frag = Fragment(
            name="ProductFields",
            on_type="Product",
            fields="id\ntitle\nprice",
        )

        graphql_str = frag.to_graphql()

        assert "fragment ProductFields on Product" in graphql_str
        assert "id" in graphql_str
        assert "title" in graphql_str

    def test_compose_query_with_fragments(self) -> None:
        """Test composing query with fragments."""
        from venomqa.graphql.fragments import (
            FragmentRegistry,
            compose_query,
            fragment,
        )

        registry = FragmentRegistry()

        @fragment("UserFields", on="User", registry=registry)
        def user_fields():
            return "id\nname"

        query = """
            query GetUsers {
                users {
                    ...UserFields
                }
            }
        """

        composed = compose_query(query, registry=registry)

        assert "fragment UserFields on User" in composed
        assert "...UserFields" in composed

    def test_fragment_dependency_resolution(self) -> None:
        """Test fragment dependency resolution."""
        from venomqa.graphql.fragments import Fragment, FragmentRegistry

        registry = FragmentRegistry()

        # Register fragments with dependencies
        registry.register(Fragment(
            name="AddressFields",
            on_type="Address",
            fields="street city country",
        ))

        registry.register(Fragment(
            name="UserFields",
            on_type="User",
            fields="id name\naddress { ...AddressFields }",
            dependencies=["AddressFields"],
        ))

        resolved = registry.resolve_dependencies(["UserFields"])

        # AddressFields should come before UserFields
        assert len(resolved) == 2
        assert resolved[0].name == "AddressFields"
        assert resolved[1].name == "UserFields"

    def test_query_builder(self) -> None:
        """Test the QueryBuilder fluent interface."""
        from venomqa.graphql.fragments import FragmentRegistry, QueryBuilder

        registry = FragmentRegistry()

        builder = QueryBuilder("GetProducts", registry=registry)
        query = (
            builder.add_variable("first", "Int!")
            .add_variable("after", "String")
            .add_field("products", args={"first": "$first", "after": "$after"}, subfields=["id", "title"])
            .build()
        )

        assert "query GetProducts" in query
        assert "$first: Int!" in query
        assert "$after: String" in query
        assert "products(first: $first, after: $after)" in query


class TestGraphQLSubscriptions:
    """Tests for GraphQL subscription support."""

    @pytest.fixture
    def subscription_options(self):
        """Create subscription options."""
        from venomqa.graphql.subscriptions import SubscriptionOptions

        return SubscriptionOptions(
            timeout=10.0,
            max_events=5,
            event_timeout=5.0,
        )

    def test_subscription_event_data_access(self) -> None:
        """Test accessing data from subscription events."""
        from venomqa.graphql.subscriptions import SubscriptionEvent

        event = SubscriptionEvent(
            id="event-1",
            subscription_id="sub-1",
            data={
                "userCreated": {
                    "id": "user-1",
                    "name": "Alice",
                }
            },
        )

        assert event.successful is True
        assert event.get_data("userCreated.id") == "user-1"
        assert event.get_data("userCreated.name") == "Alice"

    def test_subscription_event_with_errors(self) -> None:
        """Test subscription event with errors."""
        from venomqa.graphql.subscriptions import SubscriptionEvent

        event = SubscriptionEvent(
            id="event-1",
            subscription_id="sub-1",
            data=None,
            errors=[{"message": "Subscription error"}],
        )

        assert event.has_errors is True
        assert event.successful is False

    @pytest.mark.asyncio
    async def test_subscription_handler_receives_events(self) -> None:
        """Test subscription handler receives events correctly."""
        from venomqa.graphql.subscriptions import SubscriptionHandler

        handler = SubscriptionHandler(
            subscription_id="sub-1",
            query="subscription { userCreated { id } }",
        )
        handler.start()

        # Simulate receiving an event
        event = await handler.receive_event({
            "data": {"userCreated": {"id": "1"}}
        })

        assert event.data == {"userCreated": {"id": "1"}}
        assert handler.event_count == 1

    def test_subscription_options_filter(self) -> None:
        """Test subscription options with filter function."""
        from venomqa.graphql.subscriptions import SubscriptionEvent, SubscriptionOptions

        def filter_admin_events(event: SubscriptionEvent) -> bool:
            return event.get_data("userCreated.role") == "admin"

        options = SubscriptionOptions(
            filter_fn=filter_admin_events,
        )

        # Create events
        admin_event = SubscriptionEvent(
            id="1",
            subscription_id="sub-1",
            data={"userCreated": {"role": "admin"}},
        )
        user_event = SubscriptionEvent(
            id="2",
            subscription_id="sub-1",
            data={"userCreated": {"role": "user"}},
        )

        # Filter should accept admin, reject user
        assert options.filter_fn(admin_event) is True
        assert options.filter_fn(user_event) is False


class TestGraphQLCodeGen:
    """Tests for GraphQL code generation."""

    @pytest.fixture
    def sample_schema(self, tmp_path) -> str:
        """Create a sample schema file."""
        sdl = """
            type Query {
                user(id: ID!): User
                users(first: Int, after: String): UserConnection!
                product(id: ID!): Product
            }

            type Mutation {
                createUser(input: CreateUserInput!): User!
                updateUser(id: ID!, input: UpdateUserInput!): User
                deleteUser(id: ID!): Boolean!
            }

            type Subscription {
                userCreated: User!
                productUpdated(productId: ID!): Product!
            }

            type User {
                id: ID!
                name: String!
                email: String!
            }

            type Product {
                id: ID!
                title: String!
                price: Float!
            }

            type UserConnection {
                edges: [UserEdge!]!
                pageInfo: PageInfo!
            }

            type UserEdge {
                node: User!
                cursor: String!
            }

            type PageInfo {
                hasNextPage: Boolean!
            }

            input CreateUserInput {
                name: String!
                email: String!
            }

            input UpdateUserInput {
                name: String
                email: String
            }
        """
        schema_file = tmp_path / "schema.graphql"
        schema_file.write_text(sdl)
        return str(schema_file)

    def test_generate_actions_from_schema(self, sample_schema: str, tmp_path) -> None:
        """Test generating actions from schema."""
        from venomqa.graphql.codegen import generate_actions_from_schema

        output_dir = tmp_path / "generated"

        code = generate_actions_from_schema(
            schema_source=sample_schema,
            output_dir=str(output_dir),
            module_name="actions",
        )

        # Check generated code structure
        assert "@query(" in code
        assert "@mutation(" in code
        assert "def user(" in code or "def get_user(" in code
        assert "def create_user(" in code

        # Check files were created
        assert (output_dir / "actions.py").exists()
        assert (output_dir / "__init__.py").exists()

    def test_action_generator_creates_valid_python(self, sample_schema: str) -> None:
        """Test that generated code is valid Python."""
        from venomqa.graphql.codegen import generate_actions_from_schema

        code = generate_actions_from_schema(
            schema_source=sample_schema,
        )

        # Compile the generated code to check syntax
        compile(code, "<generated>", "exec")

    def test_action_generator_includes_docstrings(self, sample_schema: str) -> None:
        """Test that generated code includes docstrings."""
        from venomqa.graphql.codegen import generate_actions_from_schema

        code = generate_actions_from_schema(
            schema_source=sample_schema,
            include_docstrings=True,
        )

        assert '"""' in code
        assert "Returns:" in code

    def test_action_generator_without_type_hints(self, sample_schema: str) -> None:
        """Test generating code without type hints."""
        from venomqa.graphql.codegen import generate_actions_from_schema

        code = generate_actions_from_schema(
            schema_source=sample_schema,
            include_type_hints=False,
        )

        # Should still have valid Python code
        compile(code, "<generated>", "exec")

    def test_schema_parser_extracts_operations(self, sample_schema: str) -> None:
        """Test that schema parser extracts all operations."""
        from venomqa.graphql.codegen import SchemaParser
        from venomqa.graphql.schema import load_schema_from_file

        schema = load_schema_from_file(sample_schema)
        parser = SchemaParser(schema)

        queries = parser.get_query_operations()
        mutations = parser.get_mutation_operations()
        subscriptions = parser.get_subscription_operations()

        assert len(queries) == 3  # user, users, product
        assert len(mutations) == 3  # createUser, updateUser, deleteUser
        assert len(subscriptions) == 2  # userCreated, productUpdated


class TestGraphQLTester:
    """Tests for the GraphQL tester high-level interface."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock GraphQL client."""
        client = MagicMock()
        client.query.return_value = GraphQLResponse(
            data={"users": []},
            status_code=200,
        )
        client.mutate.return_value = GraphQLResponse(
            data={"createUser": {"id": "1"}},
            status_code=200,
        )
        return client

    def test_tester_query_with_validation(self) -> None:
        """Test tester validates queries against schema."""
        from venomqa.graphql.tester import GraphQLTester

        with patch("venomqa.graphql.tester.GraphQLClient") as MockClient:
            mock_client = MagicMock()
            mock_client.query.return_value = GraphQLResponse(data={"users": []})
            MockClient.return_value = mock_client

            tester = GraphQLTester("http://localhost:4000/graphql")

            # Query without schema loaded should work (validation disabled implicitly)
            response = tester.query("{ users { id } }", validate=False)
            assert response.data == {"users": []}

    def test_tester_expect_creates_graphql_expectation(self) -> None:
        """Test that tester.expect creates GraphQL expectation."""
        from venomqa.graphql.assertions import GraphQLExpectation
        from venomqa.graphql.tester import GraphQLTester

        with patch("venomqa.graphql.tester.GraphQLClient"):
            tester = GraphQLTester("http://localhost:4000/graphql")
            response = GraphQLResponse(data={"test": "value"})

            expectation = tester.expect(response)

            assert isinstance(expectation, GraphQLExpectation)

    def test_tester_context_manager(self) -> None:
        """Test tester works as context manager."""
        from venomqa.graphql.tester import GraphQLTester

        with patch("venomqa.graphql.tester.GraphQLClient") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client

            with GraphQLTester("http://localhost:4000/graphql") as tester:
                # Access client to trigger lazy creation
                _ = tester.client
                assert tester is not None

            # Should call disconnect on exit
            mock_client.disconnect.assert_called_once()


class TestIntegrationScenarios:
    """Integration tests for common GraphQL testing scenarios."""

    def test_ecommerce_query_flow(self) -> None:
        """Test a typical e-commerce query flow."""
        from venomqa.graphql.assertions import expect_graphql

        # Simulate product query response
        response = GraphQLResponse(
            data={
                "products": {
                    "edges": [
                        {"node": {"id": "1", "title": "Widget", "price": 29.99}},
                        {"node": {"id": "2", "title": "Gadget", "price": 49.99}},
                    ],
                    "pageInfo": {"hasNextPage": True},
                }
            },
            status_code=200,
        )

        # Assertions
        (
            expect_graphql(response)
            .to_have_no_errors()
            .to_have_data_at("products.edges")
            .to_have_data_length("products.edges", 2)
            .to_have_data_equal("products.edges[0].node.title", "Widget")
            .to_have_data_type("products.edges[0].node.price", float)
        )

    def test_authentication_mutation_flow(self) -> None:
        """Test an authentication mutation flow."""
        from venomqa.graphql.assertions import expect_graphql

        # Simulate login response
        response = GraphQLResponse(
            data={
                "login": {
                    "user": {"id": "1", "email": "test@example.com"},
                    "token": "jwt-token-here",
                    "expiresAt": "2024-12-31T23:59:59Z",
                }
            },
            status_code=200,
        )

        (
            expect_graphql(response)
            .to_be_successful()
            .to_have_data_at("login.token")
            .to_have_data_matching("login.token", r"^jwt-")
            .to_have_data_at("login.user.id")
        )

    def test_error_handling_flow(self) -> None:
        """Test error handling assertions."""
        from venomqa.graphql.assertions import expect_graphql

        # Simulate validation error response
        response = GraphQLResponse(
            data=None,
            errors=[
                GraphQLError(
                    message="Email is required",
                    path=["createUser", "input", "email"],
                    extensions={"code": "VALIDATION_ERROR", "field": "email"},
                ),
                GraphQLError(
                    message="Password must be at least 8 characters",
                    path=["createUser", "input", "password"],
                    extensions={"code": "VALIDATION_ERROR", "field": "password"},
                ),
            ],
            status_code=200,
        )

        (
            expect_graphql(response)
            .to_have_errors()
            .to_have_error_count(2)
            .to_have_error_code("VALIDATION_ERROR")
            .to_have_error_containing("Email is required")
        )
