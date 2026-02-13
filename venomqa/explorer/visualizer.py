"""
Graph Visualizer for the VenomQA State Explorer module.

This module provides the GraphVisualizer class which renders state graphs
as visual diagrams. It supports multiple output formats including DOT,
SVG, PNG, and interactive HTML.

Visualization helps understand the explored state space and identify
patterns or issues in the application's state machine.
"""

from __future__ import annotations

import html as html_module
import json
import subprocess
import tempfile
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from venomqa.explorer.models import StateGraph, State, Transition, Issue


class OutputFormat(str, Enum):
    """Supported visualization output formats."""

    DOT = "dot"  # Graphviz DOT format
    SVG = "svg"  # Scalable Vector Graphics
    PNG = "png"  # Portable Network Graphics
    HTML = "html"  # Interactive HTML
    JSON = "json"  # JSON for web visualization
    MERMAID = "mermaid"  # Mermaid diagram syntax


class VisualizationError(Exception):
    """Error during visualization rendering."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Initialize with message and optional details."""
        super().__init__(message)
        self.message = message
        self.details = details or {}


class GraphVisualizer:
    """
    Renders state graphs as visual diagrams.

    The GraphVisualizer creates visual representations of the explored
    state space, making it easier to understand application behavior
    and identify issues.

    Features:
    - Multiple output formats (DOT, SVG, PNG, HTML, Mermaid)
    - Customizable node and edge styling
    - Issue highlighting
    - Interactive HTML output with zoom/pan
    - Legend generation

    Attributes:
        graph: The state graph to visualize
        options: Visualization options
        issues: Issues to highlight in the diagram

    Example:
        visualizer = GraphVisualizer(graph)
        visualizer.highlight_issues(issues)
        visualizer.render("state_graph.svg", OutputFormat.SVG)
    """

    def __init__(
        self,
        graph: Optional[StateGraph] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize the graph visualizer.

        Args:
            graph: The state graph to visualize
            options: Optional visualization options
        """
        self.graph = graph
        self.options = options or {}
        self.issues: List[Issue] = []
        self._node_styles: Dict[str, Dict[str, str]] = {}
        self._edge_styles: Dict[str, Dict[str, str]] = {}

        # Default options
        self._default_options = {
            "node_color": "#4a90d9",
            "edge_color": "#333333",
            "error_color": "#e74c3c",
            "warning_color": "#f39c12",
            "success_color": "#27ae60",
            "font_family": "Arial, sans-serif",
            "font_size": 12,
            "show_actions": True,
            "show_response_codes": True,
            "layout": "dot",  # dot, neato, fdp, circo, twopi
        }

    def set_graph(self, graph: StateGraph) -> None:
        """
        Set the graph to visualize.

        Args:
            graph: The state graph to visualize
        """
        self.graph = graph

    def highlight_issues(self, issues: List[Issue]) -> None:
        """
        Set issues to highlight in the visualization.

        Args:
            issues: List of issues to highlight
        """
        self.issues = issues

    def render(
        self,
        output_path: str,
        format: OutputFormat = OutputFormat.SVG,
    ) -> str:
        """
        Render the graph to a file.

        Args:
            output_path: Path to save the output file
            format: Output format to use

        Returns:
            Path to the rendered file

        Raises:
            ValueError: If graph is not set
            VisualizationError: If rendering fails
        """
        if self.graph is None:
            raise ValueError("Graph is not set. Call set_graph() first.")

        output_file = Path(output_path)

        if format == OutputFormat.DOT:
            content = self.to_dot()
            output_file.write_text(content)
        elif format == OutputFormat.MERMAID:
            content = self.to_mermaid()
            output_file.write_text(content)
        elif format == OutputFormat.JSON:
            content = json.dumps(self.render_json(), indent=2)
            output_file.write_text(content)
        elif format == OutputFormat.HTML:
            content = self.render_html()
            output_file.write_text(content)
        elif format in (OutputFormat.SVG, OutputFormat.PNG):
            # Requires graphviz
            self._render_graphviz(output_path, format)
        else:
            raise VisualizationError(f"Unsupported format: {format}")

        return str(output_file.absolute())

    def _render_graphviz(self, output_path: str, format: OutputFormat) -> None:
        """
        Render using graphviz command line tool.

        Args:
            output_path: Path to save the output
            format: SVG or PNG

        Raises:
            VisualizationError: If graphviz is not installed or fails
        """
        dot_content = self.to_dot()
        layout = self.options.get("layout", self._default_options["layout"])

        with tempfile.NamedTemporaryFile(mode='w', suffix='.dot', delete=False) as f:
            f.write(dot_content)
            dot_file = f.name

        try:
            format_flag = "svg" if format == OutputFormat.SVG else "png"
            result = subprocess.run(
                [layout, f"-T{format_flag}", dot_file, "-o", output_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise VisualizationError(
                    f"Graphviz failed: {result.stderr or result.stdout}"
                )
        except FileNotFoundError:
            raise VisualizationError(
                f"Graphviz '{layout}' not found. Install graphviz to render {format.value} files."
            )
        except subprocess.TimeoutExpired:
            raise VisualizationError("Graphviz rendering timed out")
        finally:
            Path(dot_file).unlink(missing_ok=True)

    def render_to_string(
        self,
        format: OutputFormat = OutputFormat.DOT,
    ) -> str:
        """
        Render the graph to a string.

        Args:
            format: Output format to use

        Returns:
            String representation of the graph
        """
        if self.graph is None:
            raise ValueError("Graph is not set. Call set_graph() first.")

        if format == OutputFormat.DOT:
            return self.to_dot()
        elif format == OutputFormat.MERMAID:
            return self.to_mermaid()
        elif format == OutputFormat.HTML:
            return self.render_html()
        elif format == OutputFormat.JSON:
            return json.dumps(self.render_json(), indent=2)
        else:
            raise VisualizationError(
                f"Format {format.value} requires file rendering. Use render() instead."
            )

    def to_dot(self) -> str:
        """
        Render the graph in Graphviz DOT format.

        Returns:
            DOT format string representation
        """
        if self.graph is None:
            raise ValueError("Graph is not set. Call set_graph() first.")

        lines = [
            "digraph StateGraph {",
            "    rankdir=TB;",
            '    node [shape=box, style="rounded,filled", fontname="Arial"];',
            '    edge [fontname="Arial", fontsize=10];',
            "",
        ]

        # Add nodes
        for state_id, state in self.graph.states.items():
            label = self._get_node_label(state)
            color = self._get_node_color(state)
            font_color = self._get_font_color(color)

            # Escape for DOT
            safe_label = label.replace('"', '\\"').replace('\n', '\\n')
            node_id = self._sanitize_id(state_id)

            lines.append(
                f'    {node_id} [label="{safe_label}", fillcolor="{color}", '
                f'fontcolor="{font_color}"];'
            )

        lines.append("")

        # Add edges
        for transition in self.graph.transitions:
            from_id = self._sanitize_id(transition.from_state)
            to_id = self._sanitize_id(transition.to_state)
            edge_label = self._get_edge_label(transition)
            edge_color = self._get_edge_color(transition)

            safe_label = edge_label.replace('"', '\\"').replace('\n', '\\n')

            lines.append(
                f'    {from_id} -> {to_id} [label="{safe_label}", '
                f'color="{edge_color}"];'
            )

        lines.append("}")

        return "\n".join(lines)

    def to_mermaid(self) -> str:
        """
        Render the graph in Mermaid diagram syntax.

        Returns:
            Mermaid syntax string
        """
        if self.graph is None:
            raise ValueError("Graph is not set. Call set_graph() first.")

        lines = ["flowchart TD"]

        # Track node styles for styling section
        node_classes: Dict[str, str] = {}

        # Add nodes with shapes
        for state_id, state in self.graph.states.items():
            label = self._get_mermaid_node_label(state)
            node_id = self._sanitize_mermaid_id(state_id)
            color = self._get_node_color(state)

            # Determine class based on color
            if color == self._default_options["error_color"]:
                node_classes[node_id] = "error"
            elif color == self._default_options["warning_color"]:
                node_classes[node_id] = "warning"
            elif color == self._default_options["success_color"]:
                node_classes[node_id] = "success"
            else:
                node_classes[node_id] = "default"

            # Mermaid node definition with rounded box
            lines.append(f"    {node_id}[{label}]")

        # Add edges
        for transition in self.graph.transitions:
            from_id = self._sanitize_mermaid_id(transition.from_state)
            to_id = self._sanitize_mermaid_id(transition.to_state)
            edge_label = self._get_mermaid_edge_label(transition)

            if edge_label:
                lines.append(f"    {from_id} -->|{edge_label}| {to_id}")
            else:
                lines.append(f"    {from_id} --> {to_id}")

        # Add style definitions
        lines.append("")
        lines.append("    %% Style definitions")
        lines.append(f"    classDef default fill:{self._default_options['node_color']},stroke:#333,color:#fff")
        lines.append(f"    classDef error fill:{self._default_options['error_color']},stroke:#333,color:#fff")
        lines.append(f"    classDef warning fill:{self._default_options['warning_color']},stroke:#333,color:#000")
        lines.append(f"    classDef success fill:{self._default_options['success_color']},stroke:#333,color:#fff")

        # Apply classes to nodes
        for node_class in ["error", "warning", "success"]:
            nodes = [nid for nid, nc in node_classes.items() if nc == node_class]
            if nodes:
                lines.append(f"    class {','.join(nodes)} {node_class}")

        return "\n".join(lines)

    def render_html(self) -> str:
        """
        Render the graph as interactive HTML.

        Returns:
            HTML string with embedded visualization
        """
        if self.graph is None:
            raise ValueError("Graph is not set. Call set_graph() first.")

        json_data = self.render_json()
        mermaid_diagram = self.to_mermaid()

        # Escape for HTML embedding
        mermaid_escaped = html_module.escape(mermaid_diagram)

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VenomQA State Graph Visualization</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        body {{
            font-family: {self._default_options['font_family']};
            margin: 20px;
            background-color: #f5f5f5;
        }}
        h1 {{
            color: #333;
        }}
        .container {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        .mermaid {{
            text-align: center;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .stat-card {{
            background: #4a90d9;
            color: white;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 24px;
            font-weight: bold;
        }}
        .stat-label {{
            font-size: 12px;
            opacity: 0.9;
        }}
        .legend {{
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
            margin-top: 15px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .legend-color {{
            width: 20px;
            height: 20px;
            border-radius: 4px;
        }}
        .issues {{
            margin-top: 20px;
        }}
        .issue {{
            padding: 10px;
            margin: 5px 0;
            border-radius: 4px;
            border-left: 4px solid;
        }}
        .issue-critical {{ border-left-color: #e74c3c; background: #fdf2f2; }}
        .issue-high {{ border-left-color: #e67e22; background: #fef6e7; }}
        .issue-medium {{ border-left-color: #f39c12; background: #fefce8; }}
        .issue-low {{ border-left-color: #3498db; background: #eff6ff; }}
        .issue-info {{ border-left-color: #9b9b9b; background: #f9f9f9; }}
    </style>
</head>
<body>
    <h1>State Graph Visualization</h1>

    <div class="stats">
        <div class="stat-card">
            <div class="stat-value">{len(self.graph.states)}</div>
            <div class="stat-label">States</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{len(self.graph.transitions)}</div>
            <div class="stat-label">Transitions</div>
        </div>
        <div class="stat-card" style="background: {self._default_options['error_color'] if self.issues else self._default_options['success_color']}">
            <div class="stat-value">{len(self.issues)}</div>
            <div class="stat-label">Issues</div>
        </div>
    </div>

    <div class="container">
        <h2>Graph</h2>
        <div class="mermaid">
{mermaid_diagram}
        </div>
        <div class="legend">
            <div class="legend-item">
                <div class="legend-color" style="background: {self._default_options['node_color']}"></div>
                <span>Normal State</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: {self._default_options['success_color']}"></div>
                <span>Success</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: {self._default_options['warning_color']}"></div>
                <span>Warning</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: {self._default_options['error_color']}"></div>
                <span>Error</span>
            </div>
        </div>
    </div>

    {self._render_issues_html()}

    <script>
        mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
    </script>
</body>
</html>
"""
        return html_content

    def _render_issues_html(self) -> str:
        """Render issues section for HTML output."""
        if not self.issues:
            return ""

        lines = ['<div class="container issues">', '    <h2>Issues</h2>']

        for issue in self.issues:
            severity = issue.severity.value.lower()
            lines.append(f'    <div class="issue issue-{severity}">')
            lines.append(f'        <strong>[{issue.severity.value.upper()}]</strong> {html_module.escape(issue.error)}')
            if issue.state:
                lines.append(f'        <br><small>State: {html_module.escape(issue.state)}</small>')
            if issue.suggestion:
                lines.append(f'        <br><em>Suggestion: {html_module.escape(issue.suggestion)}</em>')
            lines.append('    </div>')

        lines.append('</div>')
        return "\n".join(lines)

    def render_json(self) -> Dict[str, Any]:
        """
        Render the graph as JSON for web visualization.

        Returns:
            Dictionary with nodes and edges data
        """
        if self.graph is None:
            raise ValueError("Graph is not set. Call set_graph() first.")

        nodes = []
        for state_id, state in self.graph.states.items():
            node_data = {
                "id": state_id,
                "label": self._get_node_label(state),
                "name": state.name,
                "color": self._get_node_color(state),
                "properties": state.properties,
                "metadata": state.metadata,
            }
            nodes.append(node_data)

        edges = []
        for i, transition in enumerate(self.graph.transitions):
            edge_data = {
                "id": f"edge_{i}",
                "source": transition.from_state,
                "target": transition.to_state,
                "label": self._get_edge_label(transition),
                "color": self._get_edge_color(transition),
                "method": transition.action.method,
                "endpoint": transition.action.endpoint,
                "status_code": transition.status_code,
                "success": transition.success,
            }
            edges.append(edge_data)

        issues_data = []
        for issue in self.issues:
            issue_dict = {
                "severity": issue.severity.value,
                "state": issue.state,
                "error": issue.error,
                "suggestion": issue.suggestion,
                "category": issue.category,
            }
            issues_data.append(issue_dict)

        return {
            "nodes": nodes,
            "edges": edges,
            "issues": issues_data,
            "metadata": {
                "initial_state": self.graph.initial_state,
                "total_states": len(self.graph.states),
                "total_transitions": len(self.graph.transitions),
                "total_issues": len(self.issues),
            },
        }

    def set_node_style(
        self,
        state_id: str,
        style: Dict[str, str],
    ) -> None:
        """
        Set custom style for a specific node.

        Args:
            state_id: The state ID to style
            style: Style properties (color, shape, etc.)
        """
        self._node_styles[state_id] = style

    def set_edge_style(
        self,
        from_state: str,
        to_state: str,
        style: Dict[str, str],
    ) -> None:
        """
        Set custom style for a specific edge.

        Args:
            from_state: Source state ID
            to_state: Destination state ID
            style: Style properties (color, width, etc.)
        """
        key = f"{from_state}->{to_state}"
        self._edge_styles[key] = style

    def set_option(self, key: str, value: Any) -> None:
        """
        Set a visualization option.

        Args:
            key: Option key
            value: Option value
        """
        self.options[key] = value

    def _get_node_label(self, state: State) -> str:
        """
        Generate label for a state node.

        Args:
            state: The state to label

        Returns:
            Label string
        """
        label = state.name

        # Optionally add key properties
        if state.properties and self.options.get("show_properties", False):
            props = ", ".join(f"{k}={v}" for k, v in list(state.properties.items())[:3])
            if props:
                label += f"\n({props})"

        return label

    def _get_mermaid_node_label(self, state: State) -> str:
        """
        Generate label for a Mermaid node (simpler, no newlines).

        Args:
            state: The state to label

        Returns:
            Label string safe for Mermaid
        """
        # Mermaid labels need escaping and no special chars
        label = state.name.replace('"', "'").replace('[', '(').replace(']', ')')
        return f'"{label}"'

    def _get_edge_label(self, transition: Transition) -> str:
        """
        Generate label for a transition edge.

        Args:
            transition: The transition to label

        Returns:
            Label string
        """
        parts = []

        if self.options.get("show_actions", self._default_options["show_actions"]):
            parts.append(f"{transition.action.method} {transition.action.endpoint}")

        if self.options.get("show_response_codes", self._default_options["show_response_codes"]):
            if transition.status_code:
                parts.append(f"[{transition.status_code}]")

        return " ".join(parts)

    def _get_mermaid_edge_label(self, transition: Transition) -> str:
        """
        Generate label for a Mermaid edge (simpler format).

        Args:
            transition: The transition to label

        Returns:
            Label string safe for Mermaid
        """
        # Mermaid edge labels need to be simple
        if self.options.get("show_actions", self._default_options["show_actions"]):
            method = transition.action.method
            # Shorten endpoint for readability
            endpoint = transition.action.endpoint
            if len(endpoint) > 20:
                endpoint = "..." + endpoint[-17:]

            label = f"{method} {endpoint}"

            if transition.status_code:
                label += f" [{transition.status_code}]"

            # Escape special Mermaid characters
            label = label.replace("|", "/").replace("[", "(").replace("]", ")")
            return label

        return ""

    def _get_node_color(self, state: State) -> str:
        """
        Determine the color for a state node.

        Args:
            state: The state to color

        Returns:
            Color string (hex or named)
        """
        # Check for custom style
        if state.id in self._node_styles:
            return self._node_styles[state.id].get(
                "color",
                self._default_options["node_color"],
            )

        # Check for issues on this state
        for issue in self.issues:
            if issue.state == state.id:
                if issue.severity.value in ("critical", "high"):
                    return self._default_options["error_color"]
                elif issue.severity.value == "medium":
                    return self._default_options["warning_color"]

        return self._default_options["node_color"]

    def _get_edge_color(self, transition: Transition) -> str:
        """
        Determine the color for a transition edge.

        Args:
            transition: The transition to color

        Returns:
            Color string
        """
        key = f"{transition.from_state}->{transition.to_state}"

        # Check for custom style
        if key in self._edge_styles:
            return self._edge_styles[key].get(
                "color",
                self._default_options["edge_color"],
            )

        # Color based on success/failure
        if not transition.success:
            return self._default_options["error_color"]

        # Color based on status code
        if transition.status_code:
            if transition.status_code >= 500:
                return self._default_options["error_color"]
            elif transition.status_code >= 400:
                return self._default_options["warning_color"]
            elif transition.status_code >= 200 and transition.status_code < 300:
                return self._default_options["success_color"]

        return self._default_options["edge_color"]

    def _get_font_color(self, bg_color: str) -> str:
        """
        Determine font color based on background color for contrast.

        Args:
            bg_color: Background color hex string

        Returns:
            Font color (white or black)
        """
        # Simple luminance check for common colors
        if bg_color in (self._default_options["warning_color"],):
            return "#000000"
        return "#ffffff"

    def _sanitize_id(self, state_id: str) -> str:
        """
        Sanitize state ID for use in DOT format.

        Args:
            state_id: Original state ID

        Returns:
            Sanitized ID safe for DOT
        """
        # Replace non-alphanumeric with underscore, ensure starts with letter
        sanitized = "".join(c if c.isalnum() else "_" for c in state_id)
        if sanitized and sanitized[0].isdigit():
            sanitized = "s_" + sanitized
        return sanitized or "unknown"

    def _sanitize_mermaid_id(self, state_id: str) -> str:
        """
        Sanitize state ID for use in Mermaid format.

        Args:
            state_id: Original state ID

        Returns:
            Sanitized ID safe for Mermaid
        """
        # Mermaid is more restrictive
        sanitized = "".join(c if c.isalnum() else "_" for c in state_id)
        if sanitized and sanitized[0].isdigit():
            sanitized = "s" + sanitized
        return sanitized or "unknown"

    def generate_legend(self) -> str:
        """
        Generate a legend for the visualization.

        Returns:
            Legend as string (DOT format subgraph)
        """
        lines = [
            "subgraph cluster_legend {",
            '    label="Legend";',
            '    style="rounded";',
            '    node [shape=box, style="rounded,filled", fontname="Arial"];',
            "",
            f'    legend_normal [label="Normal State", fillcolor="{self._default_options["node_color"]}", fontcolor="#ffffff"];',
            f'    legend_success [label="Success", fillcolor="{self._default_options["success_color"]}", fontcolor="#ffffff"];',
            f'    legend_warning [label="Warning", fillcolor="{self._default_options["warning_color"]}", fontcolor="#000000"];',
            f'    legend_error [label="Error", fillcolor="{self._default_options["error_color"]}", fontcolor="#ffffff"];',
            "",
            '    legend_normal -> legend_success [style=invis];',
            '    legend_success -> legend_warning [style=invis];',
            '    legend_warning -> legend_error [style=invis];',
            "}",
        ]

        return "\n".join(lines)
