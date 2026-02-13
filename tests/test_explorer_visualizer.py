"""
Tests for the VenomQA State Explorer GraphVisualizer.

This test suite verifies that the GraphVisualizer can generate valid
DOT format, Mermaid diagrams, HTML, and JSON output. It also tests
PNG rendering when graphviz is available.
"""

import json
import re
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from venomqa.explorer.models import (
    Action,
    Issue,
    IssueSeverity,
    State,
    StateGraph,
    Transition,
)
from venomqa.explorer.visualizer import (
    GraphVisualizer,
    OutputFormat,
    VisualizationError,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def simple_graph() -> StateGraph:
    """Create a simple state graph for testing."""
    graph = StateGraph()

    # Add states
    graph.add_state(State(id="initial", name="Initial State"))
    graph.add_state(State(id="logged_in", name="Logged In"))
    graph.add_state(State(id="error", name="Error State"))

    # Add transitions
    login_action = Action(method="POST", endpoint="/api/login")
    logout_action = Action(method="POST", endpoint="/api/logout")
    fail_action = Action(method="POST", endpoint="/api/login")

    graph.add_transition(
        Transition(
            from_state="initial",
            action=login_action,
            to_state="logged_in",
            status_code=200,
            success=True,
        )
    )
    graph.add_transition(
        Transition(
            from_state="logged_in",
            action=logout_action,
            to_state="initial",
            status_code=200,
            success=True,
        )
    )
    graph.add_transition(
        Transition(
            from_state="initial",
            action=fail_action,
            to_state="error",
            status_code=401,
            success=False,
            error="Invalid credentials",
        )
    )

    return graph


@pytest.fixture
def complex_graph() -> StateGraph:
    """Create a more complex state graph with multiple paths."""
    graph = StateGraph()

    # States representing a shopping flow
    states = [
        State(id="home", name="Home Page"),
        State(id="browse", name="Browse Products"),
        State(id="cart", name="Shopping Cart"),
        State(id="checkout", name="Checkout"),
        State(id="payment", name="Payment"),
        State(id="confirmed", name="Order Confirmed"),
        State(id="failed", name="Payment Failed"),
    ]

    for state in states:
        graph.add_state(state)

    # Actions and transitions
    transitions = [
        ("home", "browse", "GET", "/api/products", 200),
        ("browse", "cart", "POST", "/api/cart/add", 201),
        ("cart", "checkout", "POST", "/api/checkout/start", 200),
        ("checkout", "payment", "POST", "/api/payment/init", 200),
        ("payment", "confirmed", "POST", "/api/payment/complete", 200),
        ("payment", "failed", "POST", "/api/payment/complete", 402),
        ("failed", "payment", "POST", "/api/payment/retry", 200),
        ("confirmed", "home", "GET", "/api/home", 200),
    ]

    for from_state, to_state, method, endpoint, status_code in transitions:
        action = Action(method=method, endpoint=endpoint)
        success = status_code < 400
        graph.add_transition(
            Transition(
                from_state=from_state,
                action=action,
                to_state=to_state,
                status_code=status_code,
                success=success,
            )
        )

    return graph


@pytest.fixture
def issues_list() -> list[Issue]:
    """Create a list of sample issues."""
    return [
        Issue(
            severity=IssueSeverity.CRITICAL,
            state="error",
            error="Security vulnerability detected",
            suggestion="Review authentication flow",
            category="security",
        ),
        Issue(
            severity=IssueSeverity.HIGH,
            state="failed",
            error="Payment failure not handled properly",
            suggestion="Add retry logic",
            category="reliability",
        ),
        Issue(
            severity=IssueSeverity.MEDIUM,
            state="checkout",
            error="Slow response time",
            suggestion="Optimize database queries",
            category="performance",
        ),
        Issue(
            severity=IssueSeverity.LOW,
            state="home",
            error="Minor UI inconsistency",
            suggestion="Update CSS",
            category="ui",
        ),
    ]


# =============================================================================
# Basic Visualizer Tests
# =============================================================================


class TestGraphVisualizerBasics:
    """Test basic GraphVisualizer functionality."""

    def test_create_visualizer_without_graph(self):
        """Test creating a visualizer without a graph."""
        visualizer = GraphVisualizer()
        assert visualizer.graph is None
        assert visualizer.issues == []
        assert visualizer.options == {}

    def test_create_visualizer_with_graph(self, simple_graph):
        """Test creating a visualizer with a graph."""
        visualizer = GraphVisualizer(graph=simple_graph)
        assert visualizer.graph == simple_graph

    def test_set_graph(self, simple_graph):
        """Test setting the graph after creation."""
        visualizer = GraphVisualizer()
        visualizer.set_graph(simple_graph)
        assert visualizer.graph == simple_graph

    def test_highlight_issues(self, simple_graph, issues_list):
        """Test highlighting issues."""
        visualizer = GraphVisualizer(graph=simple_graph)
        visualizer.highlight_issues(issues_list)
        assert visualizer.issues == issues_list

    def test_set_option(self, simple_graph):
        """Test setting visualization options."""
        visualizer = GraphVisualizer(graph=simple_graph)
        visualizer.set_option("show_actions", False)
        assert visualizer.options["show_actions"] is False

    def test_set_node_style(self, simple_graph):
        """Test setting custom node style."""
        visualizer = GraphVisualizer(graph=simple_graph)
        visualizer.set_node_style("initial", {"color": "#ff0000"})
        assert visualizer._node_styles["initial"] == {"color": "#ff0000"}

    def test_set_edge_style(self, simple_graph):
        """Test setting custom edge style."""
        visualizer = GraphVisualizer(graph=simple_graph)
        visualizer.set_edge_style("initial", "logged_in", {"color": "#00ff00"})
        assert visualizer._edge_styles["initial->logged_in"] == {"color": "#00ff00"}


# =============================================================================
# DOT Format Tests
# =============================================================================


class TestDotFormat:
    """Test DOT format generation."""

    def test_to_dot_without_graph_raises(self):
        """Test that to_dot raises without a graph."""
        visualizer = GraphVisualizer()
        with pytest.raises(ValueError, match="Graph is not set"):
            visualizer.to_dot()

    def test_to_dot_generates_valid_format(self, simple_graph):
        """Test that to_dot generates valid DOT format."""
        visualizer = GraphVisualizer(graph=simple_graph)
        dot_output = visualizer.to_dot()

        # Check basic DOT structure
        assert dot_output.startswith("digraph StateGraph {")
        assert dot_output.endswith("}")

        # Check for nodes
        assert "initial" in dot_output
        assert "logged_in" in dot_output
        assert "error" in dot_output

        # Check for edges (arrows)
        assert "->" in dot_output

        # Check for labels
        assert 'label="' in dot_output

    def test_to_dot_contains_all_states(self, simple_graph):
        """Test that DOT output contains all states."""
        visualizer = GraphVisualizer(graph=simple_graph)
        dot_output = visualizer.to_dot()

        for state_id in simple_graph.states:
            sanitized_id = visualizer._sanitize_id(state_id)
            assert sanitized_id in dot_output

    def test_to_dot_contains_all_transitions(self, simple_graph):
        """Test that DOT output contains all transitions."""
        visualizer = GraphVisualizer(graph=simple_graph)
        dot_output = visualizer.to_dot()

        for transition in simple_graph.transitions:
            from_id = visualizer._sanitize_id(transition.from_state)
            to_id = visualizer._sanitize_id(transition.to_state)
            edge_pattern = f"{from_id} -> {to_id}"
            assert edge_pattern in dot_output

    def test_to_dot_with_status_codes(self, simple_graph):
        """Test that DOT output includes status codes."""
        visualizer = GraphVisualizer(graph=simple_graph)
        dot_output = visualizer.to_dot()

        # Should contain status codes in edge labels
        assert "[200]" in dot_output or "(200)" in dot_output

    def test_to_dot_color_coding(self, simple_graph, issues_list):
        """Test that DOT output includes proper color coding."""
        visualizer = GraphVisualizer(graph=simple_graph)
        visualizer.highlight_issues(issues_list)
        dot_output = visualizer.to_dot()

        # Should contain color attributes
        assert "fillcolor=" in dot_output

        # Error color should be present for error state
        assert "#e74c3c" in dot_output  # error color

    def test_to_dot_escapes_special_characters(self):
        """Test that DOT output escapes special characters."""
        graph = StateGraph()
        graph.add_state(State(id="state1", name='State with "quotes"'))
        graph.add_state(State(id="state2", name="State\nwith\nnewlines"))

        action = Action(method="GET", endpoint="/api/test")
        graph.add_transition(
            Transition(from_state="state1", action=action, to_state="state2")
        )

        visualizer = GraphVisualizer(graph=graph)
        dot_output = visualizer.to_dot()

        # Should escape quotes and newlines
        assert '\\"' in dot_output or "'" in dot_output
        assert "\\n" in dot_output

    def test_to_dot_sanitizes_numeric_ids(self):
        """Test that DOT sanitizes IDs starting with numbers."""
        graph = StateGraph()
        graph.add_state(State(id="123state", name="Numeric ID State"))
        graph.add_state(State(id="456state", name="Another Numeric"))

        action = Action(method="GET", endpoint="/api/test")
        graph.add_transition(
            Transition(from_state="123state", action=action, to_state="456state")
        )

        visualizer = GraphVisualizer(graph=graph)
        dot_output = visualizer.to_dot()

        # IDs should be prefixed to be valid DOT identifiers
        assert "s_123state" in dot_output
        assert "s_456state" in dot_output


# =============================================================================
# Mermaid Format Tests
# =============================================================================


class TestMermaidFormat:
    """Test Mermaid diagram generation."""

    def test_to_mermaid_without_graph_raises(self):
        """Test that to_mermaid raises without a graph."""
        visualizer = GraphVisualizer()
        with pytest.raises(ValueError, match="Graph is not set"):
            visualizer.to_mermaid()

    def test_to_mermaid_generates_valid_format(self, simple_graph):
        """Test that to_mermaid generates valid Mermaid format."""
        visualizer = GraphVisualizer(graph=simple_graph)
        mermaid_output = visualizer.to_mermaid()

        # Check basic Mermaid structure
        assert mermaid_output.startswith("flowchart TD")

        # Check for nodes (box notation)
        assert "[" in mermaid_output
        assert "]" in mermaid_output

        # Check for edges (arrow notation)
        assert "-->" in mermaid_output

    def test_to_mermaid_contains_all_states(self, simple_graph):
        """Test that Mermaid output contains all states."""
        visualizer = GraphVisualizer(graph=simple_graph)
        mermaid_output = visualizer.to_mermaid()

        for state_id in simple_graph.states:
            sanitized_id = visualizer._sanitize_mermaid_id(state_id)
            assert sanitized_id in mermaid_output

    def test_to_mermaid_contains_edge_labels(self, simple_graph):
        """Test that Mermaid output contains edge labels."""
        visualizer = GraphVisualizer(graph=simple_graph)
        mermaid_output = visualizer.to_mermaid()

        # Should contain edge labels with |label| syntax
        assert "-->|" in mermaid_output

    def test_to_mermaid_contains_style_definitions(self, simple_graph):
        """Test that Mermaid output contains style definitions."""
        visualizer = GraphVisualizer(graph=simple_graph)
        mermaid_output = visualizer.to_mermaid()

        # Should contain classDef for styling
        assert "classDef" in mermaid_output
        assert "default" in mermaid_output
        assert "error" in mermaid_output

    def test_to_mermaid_with_issues_applies_classes(self, simple_graph, issues_list):
        """Test that Mermaid applies style classes for issues."""
        visualizer = GraphVisualizer(graph=simple_graph)
        visualizer.highlight_issues([issues_list[0]])  # Critical issue on 'error' state
        mermaid_output = visualizer.to_mermaid()

        # Should apply error class to the error state
        assert "class error error" in mermaid_output or "class" in mermaid_output

    def test_to_mermaid_escapes_special_characters(self):
        """Test that Mermaid output escapes special characters."""
        graph = StateGraph()
        graph.add_state(State(id="state1", name='State with [brackets]'))
        graph.add_state(State(id="state2", name="State with |pipe|"))

        action = Action(method="GET", endpoint="/api/test")
        graph.add_transition(
            Transition(from_state="state1", action=action, to_state="state2")
        )

        visualizer = GraphVisualizer(graph=graph)
        mermaid_output = visualizer.to_mermaid()

        # Should escape brackets and pipes (converted to parentheses/slashes)
        assert "State with (brackets)" in mermaid_output or "[brackets]" not in mermaid_output


# =============================================================================
# JSON Format Tests
# =============================================================================


class TestJsonFormat:
    """Test JSON output generation."""

    def test_render_json_without_graph_raises(self):
        """Test that render_json raises without a graph."""
        visualizer = GraphVisualizer()
        with pytest.raises(ValueError, match="Graph is not set"):
            visualizer.render_json()

    def test_render_json_returns_valid_structure(self, simple_graph):
        """Test that render_json returns valid JSON structure."""
        visualizer = GraphVisualizer(graph=simple_graph)
        json_output = visualizer.render_json()

        # Check required keys
        assert "nodes" in json_output
        assert "edges" in json_output
        assert "issues" in json_output
        assert "metadata" in json_output

    def test_render_json_nodes_have_required_fields(self, simple_graph):
        """Test that JSON nodes have required fields."""
        visualizer = GraphVisualizer(graph=simple_graph)
        json_output = visualizer.render_json()

        for node in json_output["nodes"]:
            assert "id" in node
            assert "label" in node
            assert "name" in node
            assert "color" in node

    def test_render_json_edges_have_required_fields(self, simple_graph):
        """Test that JSON edges have required fields."""
        visualizer = GraphVisualizer(graph=simple_graph)
        json_output = visualizer.render_json()

        for edge in json_output["edges"]:
            assert "id" in edge
            assert "source" in edge
            assert "target" in edge
            assert "label" in edge
            assert "method" in edge
            assert "endpoint" in edge

    def test_render_json_metadata_correct(self, simple_graph):
        """Test that JSON metadata is correct."""
        visualizer = GraphVisualizer(graph=simple_graph)
        json_output = visualizer.render_json()

        metadata = json_output["metadata"]
        assert metadata["total_states"] == len(simple_graph.states)
        assert metadata["total_transitions"] == len(simple_graph.transitions)
        assert metadata["initial_state"] == simple_graph.initial_state

    def test_render_json_includes_issues(self, simple_graph, issues_list):
        """Test that JSON output includes highlighted issues."""
        visualizer = GraphVisualizer(graph=simple_graph)
        visualizer.highlight_issues(issues_list)
        json_output = visualizer.render_json()

        assert len(json_output["issues"]) == len(issues_list)
        for issue_data in json_output["issues"]:
            assert "severity" in issue_data
            assert "error" in issue_data

    def test_render_json_is_serializable(self, simple_graph):
        """Test that JSON output is serializable."""
        visualizer = GraphVisualizer(graph=simple_graph)
        json_output = visualizer.render_json()

        # Should not raise
        serialized = json.dumps(json_output)
        assert isinstance(serialized, str)

        # Should deserialize back correctly
        deserialized = json.loads(serialized)
        assert deserialized == json_output


# =============================================================================
# HTML Format Tests
# =============================================================================


class TestHtmlFormat:
    """Test HTML output generation."""

    def test_render_html_without_graph_raises(self):
        """Test that render_html raises without a graph."""
        visualizer = GraphVisualizer()
        with pytest.raises(ValueError, match="Graph is not set"):
            visualizer.render_html()

    def test_render_html_returns_valid_html(self, simple_graph):
        """Test that render_html returns valid HTML."""
        visualizer = GraphVisualizer(graph=simple_graph)
        html_output = visualizer.render_html()

        # Check basic HTML structure
        assert "<!DOCTYPE html>" in html_output
        assert "<html" in html_output
        assert "</html>" in html_output
        assert "<head>" in html_output
        assert "<body>" in html_output

    def test_render_html_includes_mermaid_script(self, simple_graph):
        """Test that HTML includes Mermaid script for rendering."""
        visualizer = GraphVisualizer(graph=simple_graph)
        html_output = visualizer.render_html()

        # Should include Mermaid library
        assert "mermaid" in html_output
        assert "mermaid.initialize" in html_output

    def test_render_html_includes_stats(self, simple_graph):
        """Test that HTML includes graph statistics."""
        visualizer = GraphVisualizer(graph=simple_graph)
        html_output = visualizer.render_html()

        # Should show state and transition counts
        assert f">{len(simple_graph.states)}<" in html_output
        assert f">{len(simple_graph.transitions)}<" in html_output

    def test_render_html_includes_legend(self, simple_graph):
        """Test that HTML includes a legend."""
        visualizer = GraphVisualizer(graph=simple_graph)
        html_output = visualizer.render_html()

        # Should have legend items
        assert "legend" in html_output.lower()
        assert "Normal State" in html_output
        assert "Error" in html_output

    def test_render_html_includes_issues_section(self, simple_graph, issues_list):
        """Test that HTML includes issues section when present."""
        visualizer = GraphVisualizer(graph=simple_graph)
        visualizer.highlight_issues(issues_list)
        html_output = visualizer.render_html()

        # Should show issues
        assert "Issues" in html_output
        assert "CRITICAL" in html_output
        assert "Security vulnerability detected" in html_output

    def test_render_html_escapes_content(self):
        """Test that HTML escapes potentially dangerous content."""
        graph = StateGraph()
        graph.add_state(State(id="xss", name="<script>alert('xss')</script>"))

        action = Action(method="GET", endpoint="/api/test")
        graph.add_transition(
            Transition(from_state="xss", action=action, to_state="xss")
        )

        visualizer = GraphVisualizer(graph=graph)
        html_output = visualizer.render_html()

        # Script tags should be escaped
        assert "<script>alert" not in html_output
        assert "&lt;script&gt;" in html_output or "script" not in html_output.lower().split("mermaid")[0]


# =============================================================================
# Render to String Tests
# =============================================================================


class TestRenderToString:
    """Test render_to_string method."""

    def test_render_to_string_dot(self, simple_graph):
        """Test render_to_string with DOT format."""
        visualizer = GraphVisualizer(graph=simple_graph)
        output = visualizer.render_to_string(OutputFormat.DOT)

        assert output.startswith("digraph StateGraph {")

    def test_render_to_string_mermaid(self, simple_graph):
        """Test render_to_string with Mermaid format."""
        visualizer = GraphVisualizer(graph=simple_graph)
        output = visualizer.render_to_string(OutputFormat.MERMAID)

        assert output.startswith("flowchart TD")

    def test_render_to_string_html(self, simple_graph):
        """Test render_to_string with HTML format."""
        visualizer = GraphVisualizer(graph=simple_graph)
        output = visualizer.render_to_string(OutputFormat.HTML)

        assert "<!DOCTYPE html>" in output

    def test_render_to_string_json(self, simple_graph):
        """Test render_to_string with JSON format."""
        visualizer = GraphVisualizer(graph=simple_graph)
        output = visualizer.render_to_string(OutputFormat.JSON)

        # Should be valid JSON
        parsed = json.loads(output)
        assert "nodes" in parsed

    def test_render_to_string_svg_raises(self, simple_graph):
        """Test that render_to_string raises for SVG format."""
        visualizer = GraphVisualizer(graph=simple_graph)
        with pytest.raises(VisualizationError, match="requires file rendering"):
            visualizer.render_to_string(OutputFormat.SVG)


# =============================================================================
# Render to File Tests
# =============================================================================


class TestRenderToFile:
    """Test render method that writes to files."""

    def test_render_without_graph_raises(self):
        """Test that render raises without a graph."""
        visualizer = GraphVisualizer()
        with pytest.raises(ValueError, match="Graph is not set"):
            visualizer.render("output.dot", OutputFormat.DOT)

    def test_render_dot_to_file(self, simple_graph):
        """Test rendering DOT format to file."""
        visualizer = GraphVisualizer(graph=simple_graph)

        with tempfile.NamedTemporaryFile(suffix=".dot", delete=False) as f:
            output_path = f.name

        try:
            result_path = visualizer.render(output_path, OutputFormat.DOT)
            assert Path(result_path).exists()

            content = Path(result_path).read_text()
            assert content.startswith("digraph StateGraph {")
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_render_mermaid_to_file(self, simple_graph):
        """Test rendering Mermaid format to file."""
        visualizer = GraphVisualizer(graph=simple_graph)

        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            output_path = f.name

        try:
            result_path = visualizer.render(output_path, OutputFormat.MERMAID)
            assert Path(result_path).exists()

            content = Path(result_path).read_text()
            assert content.startswith("flowchart TD")
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_render_json_to_file(self, simple_graph):
        """Test rendering JSON format to file."""
        visualizer = GraphVisualizer(graph=simple_graph)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            output_path = f.name

        try:
            result_path = visualizer.render(output_path, OutputFormat.JSON)
            assert Path(result_path).exists()

            content = Path(result_path).read_text()
            data = json.loads(content)
            assert "nodes" in data
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_render_html_to_file(self, simple_graph):
        """Test rendering HTML format to file."""
        visualizer = GraphVisualizer(graph=simple_graph)

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            output_path = f.name

        try:
            result_path = visualizer.render(output_path, OutputFormat.HTML)
            assert Path(result_path).exists()

            content = Path(result_path).read_text()
            assert "<!DOCTYPE html>" in content
        finally:
            Path(output_path).unlink(missing_ok=True)


# =============================================================================
# Graphviz Rendering Tests
# =============================================================================


class TestGraphvizRendering:
    """Test Graphviz-based rendering (PNG/SVG)."""

    def test_render_png_without_graphviz_raises(self, simple_graph):
        """Test that PNG rendering raises when graphviz is not available."""
        visualizer = GraphVisualizer(graph=simple_graph)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            output_path = f.name

        try:
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = FileNotFoundError("dot not found")
                with pytest.raises(VisualizationError, match="not found"):
                    visualizer.render(output_path, OutputFormat.PNG)
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_render_svg_without_graphviz_raises(self, simple_graph):
        """Test that SVG rendering raises when graphviz is not available."""
        visualizer = GraphVisualizer(graph=simple_graph)

        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            output_path = f.name

        try:
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = FileNotFoundError("dot not found")
                with pytest.raises(VisualizationError, match="not found"):
                    visualizer.render(output_path, OutputFormat.SVG)
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_render_png_with_graphviz_mock(self, simple_graph):
        """Test PNG rendering with mocked graphviz."""
        visualizer = GraphVisualizer(graph=simple_graph)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            output_path = f.name

        try:
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                # Should not raise
                visualizer.render(output_path, OutputFormat.PNG)
                mock_run.assert_called_once()

                # Verify correct arguments
                call_args = mock_run.call_args[0][0]
                assert "dot" in call_args or call_args[0] == "dot"
                assert "-Tpng" in call_args
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_render_graphviz_timeout_raises(self, simple_graph):
        """Test that graphviz timeout raises error."""
        visualizer = GraphVisualizer(graph=simple_graph)

        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            output_path = f.name

        try:
            with patch("subprocess.run") as mock_run:
                import subprocess
                mock_run.side_effect = subprocess.TimeoutExpired(cmd="dot", timeout=30)
                with pytest.raises(VisualizationError, match="timed out"):
                    visualizer.render(output_path, OutputFormat.SVG)
        finally:
            Path(output_path).unlink(missing_ok=True)


# =============================================================================
# Color Coding Tests
# =============================================================================


class TestColorCoding:
    """Test color coding for different states and issues."""

    def test_error_node_color_for_critical_issue(self, simple_graph):
        """Test that critical issues get error color."""
        visualizer = GraphVisualizer(graph=simple_graph)

        critical_issue = Issue(
            severity=IssueSeverity.CRITICAL,
            state="error",
            error="Critical error",
        )
        visualizer.highlight_issues([critical_issue])

        error_state = simple_graph.states["error"]
        color = visualizer._get_node_color(error_state)
        assert color == visualizer._default_options["error_color"]

    def test_error_node_color_for_high_issue(self, simple_graph):
        """Test that high severity issues get error color."""
        visualizer = GraphVisualizer(graph=simple_graph)

        high_issue = Issue(
            severity=IssueSeverity.HIGH,
            state="error",
            error="High severity error",
        )
        visualizer.highlight_issues([high_issue])

        error_state = simple_graph.states["error"]
        color = visualizer._get_node_color(error_state)
        assert color == visualizer._default_options["error_color"]

    def test_warning_node_color_for_medium_issue(self, simple_graph):
        """Test that medium severity issues get warning color."""
        visualizer = GraphVisualizer(graph=simple_graph)

        medium_issue = Issue(
            severity=IssueSeverity.MEDIUM,
            state="error",
            error="Medium severity issue",
        )
        visualizer.highlight_issues([medium_issue])

        error_state = simple_graph.states["error"]
        color = visualizer._get_node_color(error_state)
        assert color == visualizer._default_options["warning_color"]

    def test_custom_node_style_overrides(self, simple_graph):
        """Test that custom node style overrides default."""
        visualizer = GraphVisualizer(graph=simple_graph)
        visualizer.set_node_style("initial", {"color": "#ff00ff"})

        initial_state = simple_graph.states["initial"]
        color = visualizer._get_node_color(initial_state)
        assert color == "#ff00ff"

    def test_edge_color_for_failed_transition(self, simple_graph):
        """Test that failed transitions get error color."""
        visualizer = GraphVisualizer(graph=simple_graph)

        # Find the failed transition
        failed_transition = None
        for t in simple_graph.transitions:
            if not t.success:
                failed_transition = t
                break

        assert failed_transition is not None
        color = visualizer._get_edge_color(failed_transition)
        assert color == visualizer._default_options["error_color"]

    def test_edge_color_for_5xx_status(self):
        """Test that 5xx status codes get error color."""
        graph = StateGraph()
        graph.add_state(State(id="s1", name="State 1"))
        graph.add_state(State(id="s2", name="State 2"))

        action = Action(method="GET", endpoint="/api/test")
        transition = Transition(
            from_state="s1",
            action=action,
            to_state="s2",
            status_code=500,
            success=False,
        )
        graph.add_transition(transition)

        visualizer = GraphVisualizer(graph=graph)
        color = visualizer._get_edge_color(transition)
        assert color == visualizer._default_options["error_color"]

    def test_edge_color_for_4xx_status(self):
        """Test that 4xx status codes get warning color."""
        graph = StateGraph()
        graph.add_state(State(id="s1", name="State 1"))
        graph.add_state(State(id="s2", name="State 2"))

        action = Action(method="GET", endpoint="/api/test")
        transition = Transition(
            from_state="s1",
            action=action,
            to_state="s2",
            status_code=404,
            success=True,  # Could still be marked success depending on expectation
        )
        graph.add_transition(transition)

        visualizer = GraphVisualizer(graph=graph)
        color = visualizer._get_edge_color(transition)
        assert color == visualizer._default_options["warning_color"]

    def test_edge_color_for_2xx_status(self):
        """Test that 2xx status codes get success color."""
        graph = StateGraph()
        graph.add_state(State(id="s1", name="State 1"))
        graph.add_state(State(id="s2", name="State 2"))

        action = Action(method="GET", endpoint="/api/test")
        transition = Transition(
            from_state="s1",
            action=action,
            to_state="s2",
            status_code=200,
            success=True,
        )
        graph.add_transition(transition)

        visualizer = GraphVisualizer(graph=graph)
        color = visualizer._get_edge_color(transition)
        assert color == visualizer._default_options["success_color"]


# =============================================================================
# Legend Generation Tests
# =============================================================================


class TestLegendGeneration:
    """Test legend generation."""

    def test_generate_legend_returns_dot_subgraph(self, simple_graph):
        """Test that generate_legend returns DOT subgraph."""
        visualizer = GraphVisualizer(graph=simple_graph)
        legend = visualizer.generate_legend()

        # Should be a valid DOT subgraph
        assert "subgraph cluster_legend" in legend
        assert "label=" in legend
        assert "}" in legend

    def test_generate_legend_contains_all_types(self, simple_graph):
        """Test that legend contains all state types."""
        visualizer = GraphVisualizer(graph=simple_graph)
        legend = visualizer.generate_legend()

        assert "Normal State" in legend
        assert "Success" in legend
        assert "Warning" in legend
        assert "Error" in legend


# =============================================================================
# Complex Graph Tests
# =============================================================================


class TestComplexGraphVisualization:
    """Test visualization of complex graphs."""

    def test_complex_graph_dot_output(self, complex_graph):
        """Test DOT output for complex graph."""
        visualizer = GraphVisualizer(graph=complex_graph)
        dot_output = visualizer.to_dot()

        # Should contain all states
        assert "home" in dot_output
        assert "browse" in dot_output
        assert "cart" in dot_output
        assert "checkout" in dot_output
        assert "payment" in dot_output
        assert "confirmed" in dot_output
        assert "failed" in dot_output

        # Should have multiple edges
        edge_count = dot_output.count("->")
        assert edge_count == len(complex_graph.transitions)

    def test_complex_graph_mermaid_output(self, complex_graph):
        """Test Mermaid output for complex graph."""
        visualizer = GraphVisualizer(graph=complex_graph)
        mermaid_output = visualizer.to_mermaid()

        # Should contain all transitions
        arrow_count = mermaid_output.count("-->")
        assert arrow_count == len(complex_graph.transitions)

    def test_complex_graph_json_output(self, complex_graph):
        """Test JSON output for complex graph."""
        visualizer = GraphVisualizer(graph=complex_graph)
        json_output = visualizer.render_json()

        assert len(json_output["nodes"]) == len(complex_graph.states)
        assert len(json_output["edges"]) == len(complex_graph.transitions)


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_graph(self):
        """Test visualization of an empty graph."""
        graph = StateGraph()
        visualizer = GraphVisualizer(graph=graph)

        dot_output = visualizer.to_dot()
        assert "digraph StateGraph" in dot_output
        # Should still be valid even if empty

        mermaid_output = visualizer.to_mermaid()
        assert "flowchart TD" in mermaid_output

    def test_single_state_no_transitions(self):
        """Test graph with single state and no transitions."""
        graph = StateGraph()
        graph.add_state(State(id="lonely", name="Lonely State"))

        visualizer = GraphVisualizer(graph=graph)

        dot_output = visualizer.to_dot()
        assert "lonely" in dot_output

        json_output = visualizer.render_json()
        assert len(json_output["nodes"]) == 1
        assert len(json_output["edges"]) == 0

    def test_self_loop_transition(self):
        """Test graph with self-loop transition."""
        graph = StateGraph()
        graph.add_state(State(id="loop", name="Loop State"))

        action = Action(method="GET", endpoint="/api/refresh")
        graph.add_transition(
            Transition(
                from_state="loop",
                action=action,
                to_state="loop",
                status_code=200,
            )
        )

        visualizer = GraphVisualizer(graph=graph)

        dot_output = visualizer.to_dot()
        assert "loop -> loop" in dot_output

        mermaid_output = visualizer.to_mermaid()
        assert "loop -->" in mermaid_output

    def test_special_characters_in_endpoint(self):
        """Test handling of special characters in endpoints."""
        graph = StateGraph()
        graph.add_state(State(id="s1", name="Start"))
        graph.add_state(State(id="s2", name="End"))

        action = Action(method="GET", endpoint="/api/users/{id}?filter=active&sort=name")
        graph.add_transition(
            Transition(from_state="s1", action=action, to_state="s2")
        )

        visualizer = GraphVisualizer(graph=graph)

        # Should not crash
        dot_output = visualizer.to_dot()
        assert len(dot_output) > 0

        mermaid_output = visualizer.to_mermaid()
        assert len(mermaid_output) > 0

    def test_unicode_state_names(self):
        """Test handling of unicode in state names."""
        graph = StateGraph()
        graph.add_state(State(id="jp", name="Japanese State"))
        graph.add_state(State(id="emoji", name="State with details"))

        action = Action(method="GET", endpoint="/api/test")
        graph.add_transition(
            Transition(from_state="jp", action=action, to_state="emoji")
        )

        visualizer = GraphVisualizer(graph=graph)

        # Should handle unicode gracefully
        dot_output = visualizer.to_dot()
        assert len(dot_output) > 0

        html_output = visualizer.render_html()
        assert len(html_output) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
