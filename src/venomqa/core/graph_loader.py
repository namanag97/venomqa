"""YAML-based State Graph definition loader.

Allows developers to define state graphs in YAML for easier maintenance.

Example YAML:
```yaml
name: todo_app
description: State graph for todo application

nodes:
  empty:
    description: No todos exist
    initial: true

  has_todos:
    description: At least one todo exists

  has_completed:
    description: Has completed todos

edges:
  create_todo:
    from: empty
    to: has_todos
    action: create_todo  # References a Python function

  complete_todo:
    from: has_todos
    to: has_completed
    action: complete_todo

invariants:
  api_matches_db:
    description: API count matches database count
    severity: critical
    check: api_matches_db  # References a Python function
```

Usage:
    >>> from venomqa.core.graph_loader import load_graph
    >>>
    >>> # Define your actions
    >>> def create_todo(client, ctx):
    ...     return client.post("/todos", json={"title": "Test"})
    >>>
    >>> actions = {"create_todo": create_todo}
    >>> graph = load_graph("graph.yaml", actions=actions)
    >>> result = graph.explore(client, db)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from venomqa.core.graph import (
    ActionCallable,
    InvariantChecker,
    Severity,
    StateGraph,
)

logger = logging.getLogger(__name__)


def load_graph(
    yaml_path: str | Path,
    actions: dict[str, ActionCallable] | None = None,
    invariant_checks: dict[str, InvariantChecker] | None = None,
    state_checkers: dict[str, Callable] | None = None,
) -> StateGraph:
    """Load a StateGraph from a YAML file.

    Args:
        yaml_path: Path to the YAML file
        actions: Dict mapping action names to callables
        invariant_checks: Dict mapping invariant names to check functions
        state_checkers: Dict mapping node names to state checker functions

    Returns:
        Configured StateGraph ready for exploration

    Example:
        >>> actions = {
        ...     "create_todo": lambda c, ctx: c.post("/todos", json={"title": "Test"}),
        ...     "delete_todo": lambda c, ctx: c.delete(f"/todos/{ctx['todo_id']}"),
        ... }
        >>> graph = load_graph("my_app.yaml", actions=actions)
    """
    yaml_path = Path(yaml_path)

    if not yaml_path.exists():
        raise FileNotFoundError(f"Graph YAML not found: {yaml_path}")

    with open(yaml_path) as f:
        config = yaml.safe_load(f)

    return load_graph_from_dict(
        config,
        actions=actions,
        invariant_checks=invariant_checks,
        state_checkers=state_checkers,
    )


def load_graph_from_dict(
    config: dict[str, Any],
    actions: dict[str, ActionCallable] | None = None,
    invariant_checks: dict[str, InvariantChecker] | None = None,
    state_checkers: dict[str, Callable] | None = None,
) -> StateGraph:
    """Load a StateGraph from a dictionary (parsed YAML).

    Args:
        config: Dictionary with graph configuration
        actions: Dict mapping action names to callables
        invariant_checks: Dict mapping invariant names to check functions
        state_checkers: Dict mapping node names to state checker functions

    Returns:
        Configured StateGraph
    """
    actions = actions or {}
    invariant_checks = invariant_checks or {}
    state_checkers = state_checkers or {}

    # Create graph
    graph = StateGraph(
        name=config.get("name", "unnamed_graph"),
        description=config.get("description", ""),
    )

    # Add nodes
    nodes_config = config.get("nodes", {})
    for node_id, node_config in nodes_config.items():
        if isinstance(node_config, str):
            # Simple format: just description
            graph.add_node(node_id, description=node_config)
        else:
            # Full format
            checker = None
            checker_name = node_config.get("checker")
            if checker_name and checker_name in state_checkers:
                checker = state_checkers[checker_name]

            graph.add_node(
                node_id,
                description=node_config.get("description", ""),
                checker=checker,
                initial=node_config.get("initial", False),
            )

    # Add edges
    edges_config = config.get("edges", {})
    for edge_name, edge_config in edges_config.items():
        action_name = edge_config.get("action", edge_name)

        if action_name not in actions:
            logger.warning(f"Action '{action_name}' not found for edge '{edge_name}'")
            # Create a placeholder that will fail
            action = _create_missing_action_placeholder(action_name)
        else:
            action = actions[action_name]

        # Handle multiple 'from' nodes
        from_nodes = edge_config.get("from", [])
        if isinstance(from_nodes, str):
            from_nodes = [from_nodes]

        to_node = edge_config.get("to")

        for from_node in from_nodes:
            graph.add_edge(
                from_node=from_node,
                to_node=to_node,
                action=action,
                name=edge_name,
                description=edge_config.get("description", ""),
            )

    # Add invariants
    invariants_config = config.get("invariants", {})
    for inv_name, inv_config in invariants_config.items():
        if isinstance(inv_config, str):
            # Simple format: just description, check name = inv_name
            check_name = inv_name
            description = inv_config
            severity = Severity.HIGH
        else:
            check_name = inv_config.get("check", inv_name)
            description = inv_config.get("description", "")
            severity_str = inv_config.get("severity", "high").lower()
            severity = Severity(severity_str)

        if check_name not in invariant_checks:
            logger.warning(f"Invariant check '{check_name}' not found for '{inv_name}'")
            check = _create_missing_invariant_placeholder(check_name)
        else:
            check = invariant_checks[check_name]

        graph.add_invariant(
            name=inv_name,
            check=check,
            description=description,
            severity=severity,
            sql=inv_config.get("sql") if isinstance(inv_config, dict) else None,
        )

    return graph


def _create_missing_action_placeholder(name: str) -> ActionCallable:
    """Create a placeholder action that raises an error."""
    def missing_action(client, ctx):
        raise NotImplementedError(f"Action '{name}' not implemented")
    return missing_action


def _create_missing_invariant_placeholder(name: str) -> InvariantChecker:
    """Create a placeholder invariant that raises an error."""
    def missing_check(client, db, ctx):
        raise NotImplementedError(f"Invariant check '{name}' not implemented")
    return missing_check


# Convenience function for quick graph creation
def quick_graph(
    name: str,
    nodes: list[str],
    edges: list[tuple[str, str, str, ActionCallable]],
    invariants: list[tuple[str, InvariantChecker, str]] | None = None,
    initial: str | None = None,
) -> StateGraph:
    """Quickly create a StateGraph with minimal code.

    Args:
        name: Graph name
        nodes: List of node IDs
        edges: List of (from_node, to_node, edge_name, action) tuples
        invariants: List of (name, check_fn, description) tuples
        initial: Initial node ID (defaults to first node)

    Returns:
        Configured StateGraph

    Example:
        >>> graph = quick_graph(
        ...     "my_app",
        ...     nodes=["empty", "has_data"],
        ...     edges=[
        ...         ("empty", "has_data", "create", create_fn),
        ...         ("has_data", "empty", "delete", delete_fn),
        ...     ],
        ...     invariants=[
        ...         ("count_ok", count_check, "Count must match"),
        ...     ],
        ... )
    """
    graph = StateGraph(name=name)

    # Add nodes
    for i, node_id in enumerate(nodes):
        is_initial = (initial == node_id) or (initial is None and i == 0)
        graph.add_node(node_id, initial=is_initial)

    # Add edges
    for from_node, to_node, edge_name, action in edges:
        graph.add_edge(from_node, to_node, action=action, name=edge_name)

    # Add invariants
    if invariants:
        for inv_name, check_fn, description in invariants:
            graph.add_invariant(inv_name, check_fn, description)

    return graph
