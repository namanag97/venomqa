#!/usr/bin/env python3
"""
Test script for context-aware state chain exploration.

This script demonstrates REAL context-aware exploration against the Todo App,
showing how the explorer:
1. Creates todos and extracts IDs
2. Uses those IDs in subsequent requests
3. Builds a deep, connected state graph with meaningful names

Run with:
    python test_state_chain_exploration.py

Requires the Todo App to be running on localhost:5001
"""

import sys
import os

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from venomqa.explorer import (
    ExplorationEngine,
    ExplorationConfig,
    Action,
    ExplorationContext,
    extract_context_from_response,
    substitute_path_params,
    generate_state_name,
)


def main():
    """Run context-aware state chain exploration against Todo App."""
    print("=" * 70)
    print("VENOMQA CONTEXT-AWARE STATE CHAIN EXPLORATION")
    print("=" * 70)
    print("\nTarget: http://localhost:5001")
    print("This test will create, read, update, and delete todos,")
    print("demonstrating proper context passing through the exploration chain.")
    print()

    # Configure the exploration
    config = ExplorationConfig(
        max_depth=6,
        max_states=30,
        max_transitions=100,
        request_timeout_seconds=10,
    )

    # Create the exploration engine
    engine = ExplorationEngine(
        config=config,
        base_url="http://localhost:5001",
    )

    # Define initial actions that don't require context
    # These are the "entry points" into the API
    initial_actions = [
        # Health check
        Action(
            method="GET",
            endpoint="/health",
            description="Check API health",
        ),
        # List all todos
        Action(
            method="GET",
            endpoint="/todos",
            description="List all todos",
        ),
        # Create a new todo (this will give us a todo_id to use)
        Action(
            method="POST",
            endpoint="/todos",
            body={"title": "Test Todo from Explorer", "description": "Created during exploration"},
            description="Create a new todo",
        ),
        # These require context (todo_id) that we'll get from POST /todos
        Action(
            method="GET",
            endpoint="/todos/{todoId}",
            description="Get a specific todo",
        ),
        Action(
            method="PUT",
            endpoint="/todos/{todoId}",
            body={"completed": True},
            description="Mark todo as completed",
        ),
        Action(
            method="DELETE",
            endpoint="/todos/{todoId}",
            description="Delete a todo",
        ),
    ]

    print("-" * 70)
    print("INITIAL ACTIONS")
    print("-" * 70)
    for action in initial_actions:
        print(f"  {action.method:6} {action.endpoint}")
    print()

    # Run the context-aware exploration
    print("-" * 70)
    print("RUNNING EXPLORATION...")
    print("-" * 70)

    try:
        result = engine.explore_with_context(initial_actions)
    except Exception as e:
        print(f"\nERROR: Failed to run exploration: {e}")
        print("\nMake sure the Todo App is running on localhost:5001")
        print("You can start it with: cd examples/todo_app && docker-compose up")
        return 1

    # Print the results
    result.print_graph()

    # Show the context flow
    print("\n" + "=" * 70)
    print("CONTEXT FLOW THROUGH CHAIN")
    print("=" * 70)

    # Find states by depth and show context accumulation
    states_by_depth = {}
    for state in result.chain_states.values():
        depth = state.depth
        if depth not in states_by_depth:
            states_by_depth[depth] = []
        states_by_depth[depth].append(state)

    for depth in sorted(states_by_depth.keys()):
        print(f"\nDepth {depth}:")
        for state in states_by_depth[depth]:
            ctx_items = [
                f"{k}={v}" for k, v in state.context.items()
                if not k.startswith("_")
            ]
            ctx_str = ", ".join(ctx_items) if ctx_items else "(empty)"
            print(f"  [{state.name}]")
            print(f"    Context: {ctx_str}")
            if state.parent_action:
                print(f"    From: {state.parent_action.method} {state.parent_action.endpoint}")

    # Verify key behaviors
    print("\n" + "=" * 70)
    print("VERIFICATION")
    print("=" * 70)

    # Check that we have states with todo_id in context
    states_with_todo_id = [
        s for s in result.chain_states.values()
        if "todo_id" in s.context
    ]
    print(f"\n[{'PASS' if states_with_todo_id else 'FAIL'}] States with todo_id extracted: {len(states_with_todo_id)}")

    # Check that GET /todos/{id} used real IDs
    get_transitions = [
        t for t in result.graph.transitions
        if t.action.method == "GET" and "/todos/" in t.action.endpoint and "{" not in t.action.endpoint
    ]
    print(f"[{'PASS' if get_transitions else 'FAIL'}] GET /todos/N with real IDs: {len(get_transitions)}")
    for t in get_transitions[:3]:
        print(f"    - {t.action.endpoint} -> Status {t.status_code}")

    # Check that PUT /todos/{id} used real IDs
    put_transitions = [
        t for t in result.graph.transitions
        if t.action.method == "PUT" and "/todos/" in t.action.endpoint and "{" not in t.action.endpoint
    ]
    print(f"[{'PASS' if put_transitions else 'FAIL'}] PUT /todos/N with real IDs: {len(put_transitions)}")
    for t in put_transitions[:3]:
        print(f"    - {t.action.endpoint} -> Status {t.status_code}")

    # Check that DELETE was executed
    delete_transitions = [
        t for t in result.graph.transitions
        if t.action.method == "DELETE" and "/todos/" in t.action.endpoint and "{" not in t.action.endpoint
    ]
    print(f"[{'PASS' if delete_transitions else 'FAIL'}] DELETE /todos/N with real IDs: {len(delete_transitions)}")
    for t in delete_transitions[:3]:
        print(f"    - {t.action.endpoint} -> Status {t.status_code}")

    # Check for meaningful state names
    meaningful_names = [
        s.name for s in result.chain_states.values()
        if "Todo:" in s.name
    ]
    print(f"[{'PASS' if meaningful_names else 'FAIL'}] States with meaningful names (Todo:N): {len(meaningful_names)}")
    for name in meaningful_names[:5]:
        print(f"    - {name}")

    # Check that no placeholder 404s occurred (404s only after DELETE are OK)
    placeholder_404s = [
        t for t in result.graph.transitions
        if t.status_code == 404 and "{" in t.action.endpoint
    ]
    print(f"[{'PASS' if not placeholder_404s else 'FAIL'}] No placeholder 404s: {len(placeholder_404s)} found")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total states explored: {len(result.chain_states)}")
    print(f"Total transitions: {len(result.graph.transitions)}")
    print(f"Max depth reached: {max(s.depth for s in result.chain_states.values())}")
    print(f"Actions skipped (unresolved params): {len(result.skipped_actions)}")
    print(f"Issues found: {len(result.issues)}")

    # Return success
    return 0


def test_extract_context():
    """Test the extract_context_from_response function."""
    print("\n" + "=" * 70)
    print("TESTING extract_context_from_response()")
    print("=" * 70)

    # Test 1: Extract ID from POST /todos response
    response = {"id": 42, "title": "Test", "completed": False}
    ctx = ExplorationContext()
    extract_context_from_response(response, endpoint="/todos", context=ctx)
    print(f"\nTest 1: POST /todos response")
    print(f"  Input: {response}")
    print(f"  Output: {ctx.to_dict()}")
    assert ctx.has("todo_id") and ctx.get("todo_id") == 42, f"Expected todo_id=42, got {ctx.to_dict()}"
    print("  PASS")

    # Test 2: Extract from nested response
    response = {"id": "abc-123", "filename": "doc.pdf", "todo_id": 42}
    ctx = ExplorationContext()
    extract_context_from_response(response, endpoint="/todos/42/attachments", context=ctx)
    print(f"\nTest 2: POST /attachments response")
    print(f"  Input: {response}")
    print(f"  Output: {ctx.to_dict()}")
    assert ctx.has("attachment_id") and ctx.get("attachment_id") == "abc-123", f"Expected attachment_id, got {ctx.to_dict()}"
    assert ctx.has("todo_id") and ctx.get("todo_id") == 42, f"Expected todo_id=42, got {ctx.to_dict()}"
    print("  PASS")

    # Test 3: Preserve existing context
    ctx = ExplorationContext()
    ctx.set("auth_token", "xyz")
    ctx.set("user_id", 1)
    response = {"id": 42, "title": "Test"}
    extract_context_from_response(response, endpoint="/todos", context=ctx)
    print(f"\nTest 3: Preserve existing context")
    print(f"  Existing: auth_token=xyz, user_id=1")
    print(f"  Response: {response}")
    print(f"  Output: {ctx.to_dict()}")
    assert ctx.has("auth_token") and ctx.get("auth_token") == "xyz", f"Lost auth_token"
    assert ctx.has("todo_id") and ctx.get("todo_id") == 42, f"Didn't extract todo_id"
    print("  PASS")


def test_substitute_path_params():
    """Test the substitute_path_params function."""
    print("\n" + "=" * 70)
    print("TESTING substitute_path_params()")
    print("=" * 70)

    # Test 1: Simple substitution
    ctx = ExplorationContext()
    ctx.set("todo_id", 42)
    endpoint = "/todos/{todoId}"
    result = substitute_path_params(endpoint, ctx)
    print(f"\nTest 1: Simple {endpoint}")
    print(f"  Context: {ctx.to_dict()}")
    print(f"  Result: {result}")
    assert result == "/todos/42", f"Expected /todos/42, got {result}"
    print("  PASS")

    # Test 2: Multiple params
    ctx = ExplorationContext()
    ctx.set("todo_id", 42)
    ctx.set("file_id", "abc-123")
    endpoint = "/todos/{todoId}/attachments/{fileId}"
    result = substitute_path_params(endpoint, ctx)
    print(f"\nTest 2: Multiple params {endpoint}")
    print(f"  Context: {ctx.to_dict()}")
    print(f"  Result: {result}")
    assert result == "/todos/42/attachments/abc-123", f"Expected full path, got {result}"
    print("  PASS")

    # Test 3: Missing param returns None
    ctx = ExplorationContext()
    ctx.set("todo_id", 42)
    endpoint = "/users/{userId}"
    result = substitute_path_params(endpoint, ctx)
    print(f"\nTest 3: Missing param {endpoint}")
    print(f"  Context: {ctx.to_dict()}")
    print(f"  Result: {result}")
    assert result is None, f"Expected None for missing param, got {result}"
    print("  PASS")

    # Test 4: No params needed
    ctx = ExplorationContext()
    endpoint = "/todos"
    result = substitute_path_params(endpoint, ctx)
    print(f"\nTest 4: No params {endpoint}")
    print(f"  Result: {result}")
    assert result == "/todos", f"Expected /todos, got {result}"
    print("  PASS")


def test_generate_state_name():
    """Test the generate_state_name function."""
    print("\n" + "=" * 70)
    print("TESTING generate_state_name()")
    print("=" * 70)

    # Test 1: Anonymous state
    ctx = ExplorationContext()
    name = generate_state_name(ctx, {})
    print(f"\nTest 1: Empty context")
    print(f"  Result: {name}")
    assert "Anonymous" in name, f"Expected Anonymous, got {name}"
    print("  PASS")

    # Test 2: With todo_id
    ctx = ExplorationContext()
    ctx.set("todo_id", 42)
    name = generate_state_name(ctx, {})
    print(f"\nTest 2: With todo_id")
    print(f"  Context: {ctx.to_dict()}")
    print(f"  Result: {name}")
    assert "Todo:42" in name, f"Expected Todo:42, got {name}"
    print("  PASS")

    # Test 3: With completed status
    ctx = ExplorationContext()
    ctx.set("todo_id", 42)
    ctx.set("completed", True)
    name = generate_state_name(ctx, {"completed": True})
    print(f"\nTest 3: With completed status")
    print(f"  Context: {ctx.to_dict()}")
    print(f"  Result: {name}")
    assert "Todo:42" in name and "Completed" in name, f"Expected Todo:42 | Completed, got {name}"
    print("  PASS")

    # Test 4: Authenticated user
    ctx = ExplorationContext()
    ctx.set("auth_token", "abc")
    ctx.set("user_id", 1)
    ctx.set("todo_id", 42)
    name = generate_state_name(ctx, {})
    print(f"\nTest 4: Authenticated user")
    print(f"  Context: {ctx.to_dict()}")
    print(f"  Result: {name}")
    assert "User:1" in name and "Todo:42" in name, f"Expected User:1 | Todo:42, got {name}"
    print("  PASS")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test context-aware state chain exploration")
    parser.add_argument("--unit-tests", action="store_true", help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration test against Todo App")
    args = parser.parse_args()

    if args.unit_tests:
        test_extract_context()
        test_substitute_path_params()
        test_generate_state_name()
        print("\n" + "=" * 70)
        print("ALL UNIT TESTS PASSED")
        print("=" * 70)
    elif args.integration or not (args.unit_tests or args.integration):
        # Default: run integration test
        sys.exit(main())
