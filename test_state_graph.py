#!/usr/bin/env python3
"""Test the State Graph feature against the Todo App.

This is a real-world test that:
1. Defines the todo app as a state graph
2. Defines invariants (rules that must always be true)
3. Explores all paths
4. Reports broken nodes/edges
"""

import sys
sys.path.insert(0, '.')

import psycopg
from venomqa import Client
from venomqa.core.graph import StateGraph, Severity

BASE_URL = "http://localhost:5001"
DB_URL = "postgresql://todouser:todopass@localhost:5432/todos"


def main():
    print("\n" + "=" * 60)
    print("STATE GRAPH TEST: Todo App")
    print("=" * 60)

    # Create the state graph
    graph = StateGraph(
        name="todo_app",
        description="State graph for todo application"
    )

    # =========================================
    # DEFINE NODES (Application States)
    # =========================================

    def check_empty(client, db, ctx):
        """Check if there are no todos."""
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM todos")
            row = cur.fetchone()
            count = row["count"] if row else 0
            ctx["db_todo_count"] = count
            return count == 0

    def check_has_todos(client, db, ctx):
        """Check if there are todos."""
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM todos")
            row = cur.fetchone()
            count = row["count"] if row else 0
            ctx["db_todo_count"] = count
            return count > 0

    def check_has_completed(client, db, ctx):
        """Check if there's at least one completed todo."""
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM todos WHERE completed = true")
            row = cur.fetchone()
            count = row["count"] if row else 0
            ctx["db_completed_count"] = count
            return count > 0

    graph.add_node("empty", description="No todos exist", checker=check_empty, initial=True)
    graph.add_node("has_todos", description="At least one todo exists", checker=check_has_todos)
    graph.add_node("has_completed", description="Has completed todos", checker=check_has_completed)

    # =========================================
    # DEFINE EDGES (Actions/Transitions)
    # =========================================

    def create_todo(client, ctx):
        """Create a new todo."""
        response = client.post("/todos", json={
            "title": f"Test Todo {ctx.get('_step', 1)}",
            "description": "Created by state graph test"
        })
        if response.status_code in [200, 201]:
            ctx["last_todo_id"] = response.json().get("id")
            ctx["_step"] = ctx.get("_step", 0) + 1
        return response

    def complete_todo(client, ctx):
        """Mark a todo as completed."""
        todo_id = ctx.get("last_todo_id")
        if not todo_id:
            # Get any todo
            response = client.get("/todos")
            todos = response.json().get("todos", [])
            if todos:
                todo_id = todos[0]["id"]
        if todo_id:
            return client.put(f"/todos/{todo_id}", json={"completed": True})
        return None

    def delete_todo(client, ctx):
        """Delete a todo."""
        todo_id = ctx.get("last_todo_id")
        if todo_id:
            response = client.delete(f"/todos/{todo_id}")
            ctx["last_todo_id"] = None
            return response
        return None

    def delete_all_todos(client, ctx):
        """Delete all todos."""
        response = client.get("/todos?limit=100")
        todos = response.json().get("todos", [])
        for todo in todos:
            client.delete(f"/todos/{todo['id']}")
        ctx["last_todo_id"] = None
        return response

    # Transitions
    graph.add_edge("empty", "has_todos", action=create_todo, name="create_todo")
    graph.add_edge("has_todos", "has_todos", action=create_todo, name="create_another")
    graph.add_edge("has_todos", "has_completed", action=complete_todo, name="complete_todo")
    graph.add_edge("has_todos", "empty", action=delete_all_todos, name="delete_all")
    graph.add_edge("has_completed", "has_completed", action=create_todo, name="create_while_completed")
    graph.add_edge("has_completed", "empty", action=delete_all_todos, name="delete_all_completed")

    # =========================================
    # DEFINE INVARIANTS (Rules that must hold)
    # =========================================

    def api_count_matches_db(client, db, ctx):
        """API todo count should match database count."""
        # Get count from API
        response = client.get("/todos?limit=1000")
        api_data = response.json()
        api_count = api_data.get("pagination", {}).get("total", len(api_data.get("todos", [])))
        ctx["api_todo_count"] = api_count

        # Get count from DB
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM todos")
            row = cur.fetchone()
            db_count = row["count"] if row else 0
            ctx["db_todo_count"] = db_count

        matches = api_count == db_count
        if not matches:
            print(f"    [INVARIANT] api_count={api_count}, db_count={db_count}")
        return matches

    def completed_count_consistent(client, db, ctx):
        """Completed count in API should match DB."""
        # Get from API (filter by completed)
        response = client.get("/todos?completed=true&limit=1000")
        api_completed = len(response.json().get("todos", []))

        # Get from DB
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM todos WHERE completed = true")
            row = cur.fetchone()
            db_completed = row["count"] if row else 0

        matches = api_completed == db_completed
        if not matches:
            print(f"    [INVARIANT] api_completed={api_completed}, db_completed={db_completed}")
        return matches

    def no_orphan_data(client, db, ctx):
        """No data should exist without proper relationships."""
        # For todo app, just check all todos have required fields
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM todos WHERE title IS NULL OR title = ''")
            row = cur.fetchone()
            invalid_count = row["count"] if row else 0
        return invalid_count == 0

    graph.add_invariant(
        name="api_db_count_match",
        check=api_count_matches_db,
        description="API todo count must match database count",
        severity=Severity.CRITICAL,
    )

    graph.add_invariant(
        name="completed_count_consistent",
        check=completed_count_consistent,
        description="Completed todo count must be consistent",
        severity=Severity.HIGH,
    )

    graph.add_invariant(
        name="no_orphan_data",
        check=no_orphan_data,
        description="No todos with missing required fields",
        severity=Severity.MEDIUM,
    )

    # =========================================
    # PRINT THE GRAPH
    # =========================================

    print("\nState Graph Definition:")
    print("-" * 40)
    print(f"Nodes: {list(graph.nodes.keys())}")
    print(f"Edges: {[(e.name, e.from_node, e.to_node) for edges in graph.edges.values() for e in edges]}")
    print(f"Invariants: {[inv.name for inv in graph.invariants]}")

    print("\nMermaid Diagram:")
    print("-" * 40)
    print(graph.to_mermaid())

    # =========================================
    # RESET DATABASE AND EXPLORE
    # =========================================

    print("\n\nPreparing for exploration...")
    print("-" * 40)

    # Connect to database
    db = psycopg.connect(DB_URL, row_factory=psycopg.rows.dict_row)

    # Reset function
    def reset_database():
        with db.cursor() as cur:
            cur.execute("TRUNCATE TABLE todos RESTART IDENTITY")
        db.commit()
        print("  Database reset (todos truncated)")

    # Reset before starting
    reset_database()

    # Create client
    client = Client(base_url=BASE_URL)

    # =========================================
    # EXPLORE THE STATE GRAPH
    # =========================================

    print("\n\nExploring state graph...")
    print("-" * 40)

    result = graph.explore(
        client=client,
        db=db,
        max_depth=5,
        stop_on_violation=False,
        reset_state=reset_database,
    )

    # =========================================
    # PRINT RESULTS
    # =========================================

    print("\n")
    print(result.summary())

    # Visual path display
    print("\n\nPaths Explored:")
    print("-" * 40)
    for i, path in enumerate(result.paths_explored[:10]):  # Show first 10
        status = "OK" if path.success else "FAIL"
        path_str = " -> ".join(path.path)
        print(f"  [{status}] {path_str}")

    if len(result.paths_explored) > 10:
        print(f"  ... and {len(result.paths_explored) - 10} more paths")

    # Broken summary
    if result.broken_nodes():
        print("\n\nBROKEN NODES:")
        for node in result.broken_nodes():
            print(f"  - {node}")

    if result.broken_edges():
        print("\nBROKEN EDGES:")
        for edge in result.broken_edges():
            print(f"  - {edge}")

    # Cleanup
    db.close()

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

    return result.success


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
