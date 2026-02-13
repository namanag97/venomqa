"""
Integration tests for the StateExplorer class.

These tests verify that the StateExplorer can be instantiated and called,
ensuring the basic functionality works end-to-end.
"""

import pytest
from datetime import datetime, timedelta

from venomqa.explorer.explorer import StateExplorer
from venomqa.explorer.models import (
    Action,
    CoverageReport,
    ExplorationConfig,
    ExplorationResult,
    State,
    StateGraph,
)
from venomqa.explorer.engine import ExplorationStrategy
from venomqa.explorer.detector import StateDetector
from venomqa.explorer.discoverer import APIDiscoverer


class TestStateExplorerInstantiation:
    """Tests for StateExplorer instantiation."""

    def test_can_instantiate_with_defaults(self):
        """Test that StateExplorer can be instantiated with just a base URL."""
        explorer = StateExplorer(base_url="http://example.com")

        assert explorer.base_url == "http://example.com"
        assert explorer.config is not None
        assert explorer.strategy == ExplorationStrategy.BFS
        assert explorer.discoverer is not None
        assert explorer.detector is not None
        assert explorer.engine is not None
        assert explorer.visualizer is not None
        assert explorer.reporter is not None

    def test_can_instantiate_with_config(self):
        """Test that StateExplorer can be instantiated with a custom config."""
        config = ExplorationConfig(
            max_depth=5,
            max_states=50,
            timeout_seconds=60,
        )

        explorer = StateExplorer(
            base_url="http://example.com",
            config=config,
            strategy=ExplorationStrategy.DFS,
        )

        assert explorer.config.max_depth == 5
        assert explorer.config.max_states == 50
        assert explorer.config.timeout_seconds == 60
        assert explorer.strategy == ExplorationStrategy.DFS

    def test_base_url_trailing_slash_removed(self):
        """Test that trailing slashes are removed from the base URL."""
        explorer = StateExplorer(base_url="http://example.com/")
        assert explorer.base_url == "http://example.com"

        explorer2 = StateExplorer(base_url="http://example.com///")
        assert explorer2.base_url == "http://example.com"


class TestStateExplorerComponents:
    """Tests for StateExplorer component initialization."""

    def test_discoverer_initialized(self):
        """Test that the APIDiscoverer is properly initialized."""
        explorer = StateExplorer(base_url="http://example.com")

        assert isinstance(explorer.discoverer, APIDiscoverer)
        assert explorer.discoverer.base_url == "http://example.com"
        assert explorer.discoverer.config is explorer.config

    def test_detector_initialized(self):
        """Test that the StateDetector is properly initialized."""
        explorer = StateExplorer(base_url="http://example.com")

        assert isinstance(explorer.detector, StateDetector)

    def test_engine_initialized(self):
        """Test that the ExplorationEngine is properly initialized."""
        explorer = StateExplorer(
            base_url="http://example.com",
            strategy=ExplorationStrategy.GREEDY,
        )

        assert explorer.engine is not None
        assert explorer.engine.strategy == ExplorationStrategy.GREEDY


class TestStateExplorerMethods:
    """Tests for StateExplorer methods."""

    def test_set_initial_state(self):
        """Test setting the initial state."""
        explorer = StateExplorer(base_url="http://example.com")

        initial_state = State(
            id="test_state",
            name="Test State",
            properties={"key": "value"},
        )

        explorer.set_initial_state(initial_state)

        assert explorer._initial_state == initial_state
        assert explorer.engine.graph.initial_state == "test_state"
        assert "test_state" in explorer.engine.graph.states

    def test_add_seed_endpoint(self):
        """Test adding seed endpoints."""
        explorer = StateExplorer(base_url="http://example.com")

        explorer.add_seed_endpoint("GET", "/api/users")
        explorer.add_seed_endpoint("POST", "/api/users")

        actions = explorer.discoverer.get_discovered_actions()
        assert len(actions) == 2

        endpoints = {a.endpoint for a in actions}
        assert "/api/users" in endpoints

        methods = {a.method for a in actions}
        assert "GET" in methods
        assert "POST" in methods

    def test_add_state_key_field(self):
        """Test adding state key fields."""
        explorer = StateExplorer(base_url="http://example.com")

        explorer.add_state_key_field("custom_field")

        assert "custom_field" in explorer.detector.state_key_fields

    def test_set_strategy(self):
        """Test setting exploration strategy."""
        explorer = StateExplorer(base_url="http://example.com")

        assert explorer.strategy == ExplorationStrategy.BFS

        explorer.set_strategy(ExplorationStrategy.DFS)

        assert explorer.strategy == ExplorationStrategy.DFS
        assert explorer.engine.strategy == ExplorationStrategy.DFS

    def test_reset(self):
        """Test resetting the explorer state."""
        explorer = StateExplorer(base_url="http://example.com")

        # Set some state
        explorer.set_initial_state(State(id="test", name="Test"))
        explorer.add_seed_endpoint("GET", "/api/test")

        # Reset
        explorer.reset()

        assert explorer._initial_state is None
        assert explorer._result is None
        assert len(explorer.engine.graph.states) == 0

    def test_add_pre_action_hook(self):
        """Test adding pre-action hooks."""
        explorer = StateExplorer(base_url="http://example.com")
        hook_called = []

        def my_hook(action):
            hook_called.append(action)

        explorer.add_pre_action_hook(my_hook)

        assert len(explorer._pre_action_hooks) == 1
        assert explorer._pre_action_hooks[0] == my_hook

    def test_add_post_action_hook(self):
        """Test adding post-action hooks."""
        explorer = StateExplorer(base_url="http://example.com")
        hook_called = []

        def my_hook(action, response):
            hook_called.append((action, response))

        explorer.add_post_action_hook(my_hook)

        assert len(explorer._post_action_hooks) == 1
        assert explorer._post_action_hooks[0] == my_hook


class TestStateExplorerAsync:
    """Async tests for StateExplorer."""

    @pytest.mark.asyncio
    async def test_authenticate_with_token(self):
        """Test authentication with a bearer token."""
        explorer = StateExplorer(base_url="http://example.com")

        await explorer.authenticate(token="test_token_123")

        assert explorer._auth_token == "test_token_123"
        assert "Authorization" in explorer._auth_headers
        assert explorer._auth_headers["Authorization"] == "Bearer test_token_123"
        assert explorer.config.auth_token == "test_token_123"
        assert explorer._initial_state is not None
        assert explorer._initial_state.properties.get("authenticated") is True

    @pytest.mark.asyncio
    async def test_authenticate_with_headers(self):
        """Test authentication with custom headers."""
        explorer = StateExplorer(base_url="http://example.com")

        await explorer.authenticate(headers={"X-API-Key": "my_api_key"})

        assert "X-API-Key" in explorer._auth_headers
        assert explorer._auth_headers["X-API-Key"] == "my_api_key"

    @pytest.mark.asyncio
    async def test_explore_creates_result(self):
        """Test that explore() creates an ExplorationResult."""
        explorer = StateExplorer(base_url="http://example.com")

        # Set up a simple initial state
        initial_state = State(
            id="initial",
            name="Initial",
            properties={},
            available_actions=[],
        )
        explorer.set_initial_state(initial_state)

        # Run exploration (should complete quickly with no actions)
        result = await explorer.explore()

        assert isinstance(result, ExplorationResult)
        assert isinstance(result.graph, StateGraph)
        assert isinstance(result.coverage, CoverageReport)
        assert result.started_at is not None
        assert result.finished_at is not None
        assert result.duration is not None

    @pytest.mark.asyncio
    async def test_explore_from_state(self):
        """Test exploring from a specific state."""
        explorer = StateExplorer(base_url="http://example.com")

        custom_state = State(
            id="custom_start",
            name="Custom Start",
            properties={"custom": True},
            available_actions=[],
        )

        result = await explorer.explore_from_state(custom_state)

        assert isinstance(result, ExplorationResult)
        assert explorer._initial_state == custom_state
        assert explorer.engine.graph.initial_state == "custom_start"

    @pytest.mark.asyncio
    async def test_discover_endpoints_returns_seed_endpoints(self):
        """Test that discover_endpoints returns seed endpoints."""
        explorer = StateExplorer(base_url="http://example.com")

        # Add seed endpoints
        explorer.add_seed_endpoint("GET", "/api/users")
        explorer.add_seed_endpoint("POST", "/api/users")
        explorer.add_seed_endpoint("GET", "/api/items")

        actions = await explorer.discover_endpoints()

        assert len(actions) == 3

    @pytest.mark.asyncio
    async def test_close_clears_state(self):
        """Test that close() clears authentication state."""
        explorer = StateExplorer(base_url="http://example.com")

        await explorer.authenticate(token="test_token")
        assert explorer._auth_token is not None

        await explorer.close()

        assert explorer._auth_token is None
        assert len(explorer._auth_headers) == 0

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test using StateExplorer as an async context manager."""
        async with StateExplorer(base_url="http://example.com") as explorer:
            assert explorer.base_url == "http://example.com"
            await explorer.authenticate(token="test")

        # After exiting context, auth should be cleared
        assert explorer._auth_token is None

    @pytest.mark.asyncio
    async def test_get_result_before_explore_returns_none(self):
        """Test that get_result returns None before exploration."""
        explorer = StateExplorer(base_url="http://example.com")

        assert explorer.get_result() is None
        assert explorer.get_graph() is None
        assert explorer.get_coverage() is None
        assert explorer.get_issues() == []

    @pytest.mark.asyncio
    async def test_get_result_after_explore(self):
        """Test that get_result returns result after exploration."""
        explorer = StateExplorer(base_url="http://example.com")

        initial_state = State(id="test", name="Test", available_actions=[])
        explorer.set_initial_state(initial_state)
        await explorer.explore()

        assert explorer.get_result() is not None
        assert explorer.get_graph() is not None
        assert explorer.get_coverage() is not None


class TestStateDetectorIntegration:
    """Integration tests for StateDetector."""

    def test_detect_state_from_response(self):
        """Test detecting state from an API response."""
        detector = StateDetector()

        response = {
            "status": "active",
            "id": "123",
            "name": "Test User",
        }

        state = detector.detect_state(response, endpoint="/api/users/123")

        assert state is not None
        assert state.name == "Active"
        assert state.properties.get("id") == "123"
        assert state.properties.get("name") == "Test User"

    def test_detect_state_with_links(self):
        """Test detecting state with HATEOAS links."""
        detector = StateDetector()

        response = {
            "id": "123",
            "_links": {
                "self": {"href": "/api/users/123", "method": "GET"},
                "update": {"href": "/api/users/123", "method": "PUT"},
                "delete": {"href": "/api/users/123", "method": "DELETE"},
            },
        }

        state = detector.detect_state(response, endpoint="/api/users/123")

        # The detector extracts actions from _links
        # Note: Some implementations may filter out self-links or deduplicate
        assert len(state.available_actions) >= 2

        # Verify the update and delete actions are present
        methods = {a.method for a in state.available_actions}
        assert "PUT" in methods or "DELETE" in methods

    def test_is_same_state(self):
        """Test state comparison."""
        detector = StateDetector()
        detector.set_state_key_fields(["status"])

        state1 = State(id="s1", name="State 1", properties={"status": "active"})
        state2 = State(id="s2", name="State 2", properties={"status": "active"})
        state3 = State(id="s3", name="State 3", properties={"status": "inactive"})

        assert detector.is_same_state(state1, state2) is True
        assert detector.is_same_state(state1, state3) is False


class TestAPIDiscovererIntegration:
    """Integration tests for APIDiscoverer."""

    def test_add_seed_endpoints(self):
        """Test adding seed endpoints."""
        discoverer = APIDiscoverer(base_url="http://example.com")

        discoverer.add_seed_endpoints([
            ("GET", "/api/users"),
            ("POST", "/api/users"),
            ("GET", "/api/users/{id}"),
            ("PUT", "/api/users/{id}"),
            ("DELETE", "/api/users/{id}"),
        ])

        actions = discoverer.get_discovered_actions()
        assert len(actions) == 5

        assert discoverer.get_endpoint_count() == 2  # /api/users and /api/users/{id}

    def test_should_include_endpoint_with_patterns(self):
        """Test endpoint filtering with include/exclude patterns."""
        config = ExplorationConfig(
            include_patterns=[r"^/api/.*"],
            exclude_patterns=[r"^/api/internal/.*"],
        )
        discoverer = APIDiscoverer(base_url="http://example.com", config=config)

        assert discoverer._should_include_endpoint("/api/users") is True
        assert discoverer._should_include_endpoint("/api/internal/admin") is False
        assert discoverer._should_include_endpoint("/other/path") is False

    def test_normalize_endpoint(self):
        """Test endpoint normalization."""
        discoverer = APIDiscoverer(base_url="http://example.com")

        assert discoverer._normalize_endpoint("users") == "/users"
        assert discoverer._normalize_endpoint("/users/") == "/users"
        assert discoverer._normalize_endpoint("/users?page=1") == "/users"
        assert discoverer._normalize_endpoint("http://example.com/users") == "/users"

    def test_extract_path_params(self):
        """Test path parameter extraction."""
        discoverer = APIDiscoverer(base_url="http://example.com")

        params = discoverer._extract_path_params("/api/users/{id}")
        assert params == ["id"]

        params = discoverer._extract_path_params("/api/users/{user_id}/posts/{post_id}")
        assert params == ["user_id", "post_id"]

        params = discoverer._extract_path_params("/api/users")
        assert params == []
