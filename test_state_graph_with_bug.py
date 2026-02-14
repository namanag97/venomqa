#!/usr/bin/env python3
"""Test that State Graph catches REAL bugs.

This test intentionally introduces a bug (stale cache simulation)
to verify that VenomQA's invariant checking actually works.
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
    print("STATE GRAPH BUG DETECTION TEST")
    print("=" * 60)
    print("\nThis test simulates a bug where the database has")
    print("data that the API doesn't know about (stale cache).")

    # Create the state graph
    graph = StateGraph(name="todo_app_bug_test")

    # Simple nodes
    graph.add_node("start", description="Initial state", initial=True)
    graph.add_node("after_action", description="After some action")

    # Action that creates a todo via API, then sneaks one in via DB
    def create_todo_with_hidden_db_insert(client, ctx):
        """Create todo via API, then insert directly to DB (simulating cache bug)."""
        # Normal API create
        response = client.post("/todos", json={"title": "API Created"})
        if response.status_code in [200, 201]:
            ctx["api_todo_id"] = response.json().get("id")

        # SNEAKY: Insert directly to DB (simulating another process or cache issue)
        db = psycopg.connect(DB_URL, row_factory=psycopg.rows.dict_row)
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO todos (title, description, completed) VALUES (%s, %s, %s)",
                ("HIDDEN Todo - Direct DB Insert", "This should cause invariant failure", False)
            )
        db.commit()
        db.close()

        print("  [ACTION] Created 1 todo via API, 1 directly in DB")
        return response

    graph.add_edge("start", "after_action", action=create_todo_with_hidden_db_insert, name="create_with_bug")

    # Invariant: Check that listing todos via API shows ALL todos in DB
    def api_lists_all_db_todos(client, db, ctx):
        """API should list ALL todos that exist in the database."""
        # Get from API
        response = client.get("/todos?limit=1000")
        api_todos = response.json().get("todos", [])
        api_count = len(api_todos)

        # Get from DB
        with db.cursor() as cur:
            cur.execute("SELECT * FROM todos")
            db_todos = cur.fetchall()
            db_count = len(db_todos)

        ctx["api_count"] = api_count
        ctx["db_count"] = db_count

        if api_count != db_count:
            print(f"  [INVARIANT FAIL] API shows {api_count} todos, DB has {db_count}")
            print(f"    API todos: {[t['title'] for t in api_todos]}")
            print(f"    DB todos: {[t['title'] for t in db_todos]}")

        return api_count == db_count

    graph.add_invariant(
        name="api_shows_all_db_todos",
        check=api_lists_all_db_todos,
        description="API must list ALL todos in database",
        severity=Severity.CRITICAL,
    )

    # Reset
    db = psycopg.connect(DB_URL, row_factory=psycopg.rows.dict_row)
    with db.cursor() as cur:
        cur.execute("TRUNCATE TABLE todos RESTART IDENTITY")
    db.commit()
    print("\nDatabase reset.")

    # Explore
    print("\nExploring with buggy action...")
    print("-" * 40)

    client = Client(base_url=BASE_URL)
    result = graph.explore(client=client, db=db, max_depth=2)

    print("\n")
    print(result.summary())

    if result.invariant_violations:
        print("\n*** BUG DETECTED! ***")
        print("VenomQA found that the API doesn't show all DB records.")
        print("This is exactly the kind of bug state-based testing catches.")
    else:
        print("\nHmm, no violations detected. The API might be reading directly from DB.")
        print("Let's check the actual counts:")

        response = client.get("/todos?limit=1000")
        api_count = len(response.json().get("todos", []))

        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM todos")
            db_count = cur.fetchone()["count"]

        print(f"  API count: {api_count}")
        print(f"  DB count: {db_count}")

    db.close()
    return not result.success  # Return True if we found the bug


if __name__ == "__main__":
    found_bug = main()
    print(f"\nBug detection test: {'PASSED (bug found)' if found_bug else 'FAILED (bug not found)'}")
