#!/usr/bin/env python3
"""Example: How to use VenomQA State Graph for testing.

This shows the developer experience - simple, clean, powerful.
"""

from venomqa import Client, StateGraph

# ============================================
# STEP 1: Define your app's states
# ============================================

graph = StateGraph(name="my_app")

graph.add_node("empty", description="No data", initial=True)
graph.add_node("has_data", description="Data exists")
graph.add_node("data_processed", description="Data has been processed")

# ============================================
# STEP 2: Define actions (transitions)
# ============================================

def create_item(client, ctx):
    """Create an item via API."""
    response = client.post("/items", json={"name": "Test Item"})
    ctx["item_id"] = response.json().get("id")
    return response

def process_item(client, ctx):
    """Process an existing item."""
    return client.post(f"/items/{ctx['item_id']}/process")

def delete_item(client, ctx):
    """Delete an item."""
    return client.delete(f"/items/{ctx['item_id']}")

graph.add_edge("empty", "has_data", action=create_item, name="create")
graph.add_edge("has_data", "data_processed", action=process_item, name="process")
graph.add_edge("has_data", "empty", action=delete_item, name="delete")
graph.add_edge("data_processed", "empty", action=delete_item, name="delete_processed")

# ============================================
# STEP 3: Define invariants (rules)
# ============================================

def count_matches_api(client, db, ctx):
    """API item count should match database."""
    api_count = len(client.get("/items").json())
    db_count = db.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    return api_count == db_count

def no_orphan_processed(client, db, ctx):
    """Processed items should have valid parent items."""
    orphans = db.execute("""
        SELECT COUNT(*) FROM processed_items p
        LEFT JOIN items i ON p.item_id = i.id
        WHERE i.id IS NULL
    """).fetchone()[0]
    return orphans == 0

graph.add_invariant("count_match", count_matches_api, "Counts must match")
graph.add_invariant("no_orphans", no_orphan_processed, "No orphan data")

# ============================================
# STEP 4: Run the test
# ============================================

if __name__ == "__main__":
    # Show the graph
    print("State Graph:")
    print(graph.to_mermaid())
    print()

    # In real usage:
    # client = Client(base_url="http://localhost:8000")
    # db = connect_to_database()
    # result = graph.explore(client, db)
    # print(result.summary())
