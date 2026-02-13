#!/usr/bin/env python3
"""
Run State Explorer on the Todo App API.
This demonstrates real state mapping from an OpenAPI spec.
"""

import sys
import os
from pathlib import Path

# Add parent paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from venomqa.explorer import (
    StateExplorer,
    StateGraph,
    State,
    Action,
    APIDiscoverer,
    ExplorationEngine,
    ExplorationStrategy,
    StateDetector,
    GraphVisualizer,
    OutputFormat,
)
from venomqa.explorer.models import ExplorationConfig

def main():
    print("=" * 70)
    print("VenomQA State Explorer - Todo App API")
    print("=" * 70)

    base_url = "http://localhost:5001"
    openapi_path = Path(__file__).parent.parent / "openapi.yaml"

    print(f"\nTarget: {base_url}")
    print(f"OpenAPI Spec: {openapi_path}")

    # Step 1: Discover endpoints from OpenAPI
    print("\n" + "=" * 70)
    print("PHASE 1: API Discovery from OpenAPI Spec")
    print("=" * 70)

    discoverer = APIDiscoverer(base_url=base_url)
    actions = discoverer.from_openapi(str(openapi_path))

    print(f"\nDiscovered {len(actions)} API actions:")
    for action in actions:
        auth = " [AUTH]" if action.requires_auth else ""
        print(f"  {action.method:6} {action.endpoint}{auth}")
        if action.params:
            print(f"         params: {list(action.params.keys())}")
        if action.body:
            print(f"         body: {list(action.body.keys()) if isinstance(action.body, dict) else 'data'}")

    # Step 2: Set up the explorer
    print("\n" + "=" * 70)
    print("PHASE 2: State Exploration")
    print("=" * 70)

    config = ExplorationConfig(
        max_depth=5,
        max_states=50,
        max_transitions=100,
        timeout_seconds=60,
    )

    # Create initial state (anonymous, no todos)
    initial_state = State(
        id="initial",
        name="Anonymous - Empty",
        properties={"authenticated": False, "has_todos": False},
        available_actions=[a for a in actions if a.method == "GET" or a.method == "POST"]
    )

    # Create engine and run exploration
    engine = ExplorationEngine(
        base_url=base_url,
        config=config,
        strategy=ExplorationStrategy.BFS,
    )

    # Add custom state detector
    detector = StateDetector()
    detector.add_state_key_field("id")
    detector.add_state_key_field("completed")
    engine.set_state_detector(detector.detect_state)

    print(f"\nStarting BFS exploration...")
    print(f"  Max depth: {config.max_depth}")
    print(f"  Max states: {config.max_states}")
    print(f"  Strategy: BFS")

    # Run exploration
    graph = engine.explore_bfs(initial_state)

    # Step 3: Analyze results
    print("\n" + "=" * 70)
    print("PHASE 3: State Graph Analysis")
    print("=" * 70)

    print(f"\nStates discovered: {len(graph.states)}")
    print(f"Transitions found: {len(graph.transitions)}")

    print("\n--- States ---")
    for state_id, state in graph.states.items():
        props = state.properties
        print(f"  [{state_id[:20]}...] {state.name}")
        if props:
            print(f"      properties: {props}")

    print("\n--- Transitions ---")
    for t in graph.transitions[:20]:  # Show first 20
        status = "OK" if t.success else f"FAIL({t.status_code})"
        print(f"  {t.from_state[:15]}... --[{t.action.method} {t.action.endpoint}]--> {t.to_state[:15]}... [{status}]")

    if len(graph.transitions) > 20:
        print(f"  ... and {len(graph.transitions) - 20} more transitions")

    # Step 4: Detect issues
    print("\n" + "=" * 70)
    print("PHASE 4: Issue Detection")
    print("=" * 70)

    # Find dead ends
    dead_ends = graph.find_dead_ends()
    print(f"\nDead-end states (no outgoing transitions): {len(dead_ends)}")
    for de in dead_ends[:5]:
        print(f"  - {de}")

    # Find cycles
    cycles = graph.find_cycles()
    print(f"\nCycles detected: {len(cycles)}")
    for cycle in cycles[:3]:
        print(f"  - {' -> '.join(c[:15] + '...' for c in cycle)}")

    # Check issues from engine
    issues = engine.issues
    print(f"\nIssues captured: {len(issues)}")
    for issue in issues[:10]:
        print(f"  [{issue.severity.upper()}] {issue.error}")

    # Step 5: Generate visualizations
    print("\n" + "=" * 70)
    print("PHASE 5: Visualization")
    print("=" * 70)

    output_dir = Path(__file__).parent / "reports"
    output_dir.mkdir(exist_ok=True)

    visualizer = GraphVisualizer()

    # Generate Mermaid diagram
    mermaid = visualizer.to_mermaid(graph)
    mermaid_path = output_dir / "state_graph.mmd"
    mermaid_path.write_text(mermaid)
    print(f"\nMermaid diagram: {mermaid_path}")

    # Generate DOT format
    dot = visualizer.to_dot(graph)
    dot_path = output_dir / "state_graph.dot"
    dot_path.write_text(dot)
    print(f"DOT format: {dot_path}")

    # Generate JSON for web visualization
    json_data = visualizer.render_json(graph)
    json_path = output_dir / "state_graph.json"
    json_path.write_text(json_data)
    print(f"JSON data: {json_path}")

    # Step 6: Coverage report
    print("\n" + "=" * 70)
    print("PHASE 6: Coverage Report")
    print("=" * 70)

    coverage = engine.get_coverage_report()
    print(f"\nEndpoints discovered: {coverage.endpoints_discovered}")
    print(f"Endpoints tested: {coverage.endpoints_tested}")
    print(f"Coverage: {coverage.coverage_percent:.1f}%")
    print(f"States found: {coverage.states_found}")
    print(f"Transitions found: {coverage.transitions_found}")

    if coverage.uncovered_actions:
        print(f"\nUncovered actions ({len(coverage.uncovered_actions)}):")
        for action in coverage.uncovered_actions[:5]:
            print(f"  - {action.method} {action.endpoint}")

    # Print the Mermaid diagram for inline viewing
    print("\n" + "=" * 70)
    print("STATE GRAPH (Mermaid)")
    print("=" * 70)
    print(mermaid)

    print("\n" + "=" * 70)
    print("EXPLORATION COMPLETE")
    print("=" * 70)

    return 0

if __name__ == "__main__":
    sys.exit(main())
