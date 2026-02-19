#!/usr/bin/env python3
"""Test State Graph with a REAL application bug scenario.

This tests a cross-feature consistency bug:
- User creates todos
- User marks some as completed
- We check if the completed filter actually works correctly

This is EXACTLY what a human QA would check:
"If I mark a todo as completed, does it show up correctly
in the completed filter?"
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
    print("STATE GRAPH: Cross-Feature Consistency Test")
    print("=" * 60)
    print("\nTesting: When I mark a todo as completed, does it")
    print("show correctly in ALL features (list, filter, count)?")

    graph = StateGraph(name="cross_feature_test")

    # States
    graph.add_node("clean", description="No todos", initial=True)
    graph.add_node("has_incomplete", description="Has incomplete todos")
    graph.add_node("has_mixed", description="Has both complete and incomplete")

    # Actions
    def create_incomplete(client, ctx):
        response = client.post("/todos", json={"title": "Incomplete Todo", "completed": False})
        ctx["todo_id"] = response.json().get("id")
        print(f"  [CREATE] Todo {ctx['todo_id']} (incomplete)")
        return response

    def mark_complete(client, ctx):
        todo_id = ctx.get("todo_id")
        response = client.put(f"/todos/{todo_id}", json={"completed": True})
        print(f"  [COMPLETE] Todo {todo_id} marked complete")
        return response

    def create_another_incomplete(client, ctx):
        response = client.post("/todos", json={"title": "Another Incomplete", "completed": False})
        ctx["todo_id_2"] = response.json().get("id")
        print(f"  [CREATE] Todo {ctx['todo_id_2']} (incomplete)")
        return response

    graph.add_edge("clean", "has_incomplete", action=create_incomplete, name="create")
    graph.add_edge("has_incomplete", "has_mixed", action=mark_complete, name="complete_first")
    graph.add_edge("has_mixed", "has_mixed", action=create_another_incomplete, name="add_incomplete")

    # INVARIANTS - Cross-feature consistency checks

    def completed_filter_matches_db(client, db, ctx):
        """The completed=true filter should return exactly what DB says is completed."""
        # API: Get completed todos via filter
        response = client.get("/todos?completed=true&limit=100")
        api_completed_ids = {t["id"] for t in response.json().get("todos", [])}

        # DB: Get completed todos directly
        with db.cursor() as cur:
            cur.execute("SELECT id FROM todos WHERE completed = true")
            db_completed_ids = {row["id"] for row in cur.fetchall()}

        match = api_completed_ids == db_completed_ids
        if not match:
            print(f"  [INVARIANT FAIL] completed filter")
            print(f"    API filter shows: {api_completed_ids}")
            print(f"    DB has completed: {db_completed_ids}")
        return match

    def incomplete_filter_matches_db(client, db, ctx):
        """The completed=false filter should return exactly what DB says is incomplete."""
        response = client.get("/todos?completed=false&limit=100")
        api_incomplete_ids = {t["id"] for t in response.json().get("todos", [])}

        with db.cursor() as cur:
            cur.execute("SELECT id FROM todos WHERE completed = false")
            db_incomplete_ids = {row["id"] for row in cur.fetchall()}

        match = api_incomplete_ids == db_incomplete_ids
        if not match:
            print(f"  [INVARIANT FAIL] incomplete filter")
            print(f"    API filter shows: {api_incomplete_ids}")
            print(f"    DB has incomplete: {db_incomplete_ids}")
        return match

    def total_count_equals_sum_of_parts(client, db, ctx):
        """Total count should equal completed + incomplete count."""
        # Get all via API
        all_response = client.get("/todos?limit=100")
        total = all_response.json().get("pagination", {}).get("total", 0)

        # Get completed via API
        completed_response = client.get("/todos?completed=true&limit=100")
        completed = len(completed_response.json().get("todos", []))

        # Get incomplete via API
        incomplete_response = client.get("/todos?completed=false&limit=100")
        incomplete = len(incomplete_response.json().get("todos", []))

        match = total == (completed + incomplete)
        if not match:
            print(f"  [INVARIANT FAIL] count mismatch")
            print(f"    Total: {total}, Completed: {completed}, Incomplete: {incomplete}")
            print(f"    {completed} + {incomplete} = {completed + incomplete} != {total}")

        ctx["total"] = total
        ctx["completed"] = completed
        ctx["incomplete"] = incomplete
        return match

    def individual_todo_state_correct(client, db, ctx):
        """Each todo's completed status via GET /todos/:id should match DB."""
        with db.cursor() as cur:
            cur.execute("SELECT id, completed FROM todos")
            db_todos = cur.fetchall()

        for todo in db_todos:
            todo_id = todo["id"]
            db_completed = todo["completed"]

            response = client.get(f"/todos/{todo_id}")
            if response.status_code == 200:
                api_completed = response.json().get("completed")
                if api_completed != db_completed:
                    print(f"  [INVARIANT FAIL] todo {todo_id} state mismatch")
                    print(f"    API says completed={api_completed}")
                    print(f"    DB says completed={db_completed}")
                    return False
        return True

    graph.add_invariant("completed_filter", completed_filter_matches_db,
                       "Completed filter matches DB", Severity.CRITICAL)
    graph.add_invariant("incomplete_filter", incomplete_filter_matches_db,
                       "Incomplete filter matches DB", Severity.CRITICAL)
    graph.add_invariant("count_consistency", total_count_equals_sum_of_parts,
                       "Total = completed + incomplete", Severity.HIGH)
    graph.add_invariant("individual_state", individual_todo_state_correct,
                       "Each todo's state matches DB", Severity.CRITICAL)

    # Setup
    db = psycopg.connect(DB_URL, row_factory=psycopg.rows.dict_row)
    with db.cursor() as cur:
        cur.execute("TRUNCATE TABLE todos RESTART IDENTITY")
    db.commit()

    client = Client(base_url=BASE_URL)

    # Show the graph
    print("\n" + graph.to_mermaid())

    # Explore
    print("\n\nExploring state transitions...")
    print("-" * 40)

    result = graph.explore(client=client, db=db, max_depth=4)

    print("\n")
    print(result.summary())

    # Show paths
    print("\nPaths tested:")
    for path in result.paths_explored:
        status = "PASS" if path.success else "FAIL"
        edges = [e.name for e in path.edges_taken]
        print(f"  [{status}] {' -> '.join(path.path)}")
        print(f"         via: {' -> '.join(edges) if edges else '(start)'}")

    db.close()

    if result.success:
        print("\n" + "=" * 60)
        print("ALL CROSS-FEATURE CHECKS PASSED")
        print("The todo app maintains consistency across all features!")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("BUGS FOUND!")
        print("=" * 60)

    return result.success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
