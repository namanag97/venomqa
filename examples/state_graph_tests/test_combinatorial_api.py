#!/usr/bin/env python3
"""Example: Combinatorial State Testing with VenomQA.

This example demonstrates how to use the combinatorial testing system to
automatically generate test states from dimension definitions, rather than
manually defining every node and edge in a StateGraph.

Scenario:
    Testing a REST API where behavior varies along three dimensions:
    - Authentication level: anonymous, regular user, admin
    - Data state: empty (no items), single item, many items
    - Response format: JSON, XML

    Instead of manually creating 3x3x2 = 18 state nodes and connecting
    them, we define the dimensions and let the combinatorial system
    generate a pairwise covering array (typically 9-12 tests) that covers
    every pair of dimension values.

Usage:
    python examples/state_graph_tests/test_combinatorial_api.py

    (Does not require a running server -- uses mock actions for demonstration)
"""

import sys
sys.path.insert(0, ".")

from venomqa.combinatorial import (
    Combination,
    CombinatorialGraphBuilder,
    ConstraintSet,
    CoveringArrayGenerator,
    Dimension,
    DimensionSpace,
    exclude,
    require,
)


def main():
    print("=" * 60)
    print("COMBINATORIAL STATE TESTING EXAMPLE")
    print("=" * 60)

    # =========================================
    # 1. DEFINE DIMENSIONS
    # =========================================

    print("\n1. Defining dimensions...")

    space = DimensionSpace([
        Dimension(
            name="auth",
            values=["anon", "user", "admin"],
            description="Authentication level",
            default_value="anon",
        ),
        Dimension(
            name="data_state",
            values=["empty", "one", "many"],
            description="Number of items in the system",
            default_value="empty",
        ),
        Dimension(
            name="format",
            values=["json", "xml"],
            description="Response format",
            default_value="json",
        ),
    ])

    print(f"   Dimensions: {space.dimension_names}")
    print(f"   Total exhaustive combinations: {space.total_combinations}")

    # =========================================
    # 2. DEFINE CONSTRAINTS
    # =========================================

    print("\n2. Defining constraints...")

    constraints = ConstraintSet([
        # Anonymous users cannot request XML format
        exclude(
            "no_anon_xml",
            auth="anon",
            format="xml",
            description="XML format requires authentication",
        ),
        # If auth is admin, data_state cannot be empty
        # (admin tests need data to exercise permissions)
        exclude(
            "admin_needs_data",
            auth="admin",
            data_state="empty",
            description="Admin tests require existing data",
        ),
    ])

    print(f"   Constraints: {len(constraints)}")

    # =========================================
    # 3. GENERATE COVERING ARRAY
    # =========================================

    print("\n3. Generating pairwise covering array...")

    gen = CoveringArrayGenerator(space, constraints, seed=42)

    # Pairwise (t=2) -- every pair of values appears together
    pairwise_combos = gen.pairwise()
    pairwise_stats = gen.coverage_stats(pairwise_combos, strength=2)

    print(f"   Pairwise tests: {len(pairwise_combos)}")
    print(f"   Tuple coverage: {pairwise_stats.coverage_pct:.1f}%")
    print(f"   Reduction: {space.total_combinations - len(pairwise_combos)} "
          f"fewer tests ({(1 - len(pairwise_combos) / space.total_combinations) * 100:.0f}%)")

    print("\n   Generated combinations:")
    for i, combo in enumerate(pairwise_combos, 1):
        print(f"     {i:2d}. {combo.description}")

    # Compare with exhaustive
    exhaustive_combos = gen.exhaustive()
    print(f"\n   vs. Exhaustive: {len(exhaustive_combos)} valid combinations")

    # =========================================
    # 4. BUILD STATE GRAPH
    # =========================================

    print("\n4. Building StateGraph from combinations...")

    builder = CombinatorialGraphBuilder(
        name="api_combinatorial_test",
        space=space,
        constraints=constraints,
        description="Combinatorial test of API across auth, data, and format dimensions",
        seed=42,
    )

    # Register transitions for the "auth" dimension
    def login_as_user(client, ctx):
        """Transition: anon -> user."""
        print(f"      [ACTION] Logging in as user (from {ctx.get('_from_combination', {})})")
        ctx["auth_token"] = "user_token_123"
        return {"status": "logged_in", "role": "user"}

    def elevate_to_admin(client, ctx):
        """Transition: user -> admin."""
        print(f"      [ACTION] Elevating to admin")
        ctx["auth_token"] = "admin_token_456"
        return {"status": "elevated", "role": "admin"}

    def logout(client, ctx):
        """Transition: user -> anon or admin -> anon."""
        print(f"      [ACTION] Logging out")
        ctx.pop("auth_token", None)
        return {"status": "logged_out"}

    builder.register_transition("auth", "anon", "user", action=login_as_user, name="login")
    builder.register_transition("auth", "user", "admin", action=elevate_to_admin, name="elevate")
    builder.register_transition("auth", "user", "anon", action=logout, name="logout_user")
    builder.register_transition("auth", "admin", "anon", action=logout, name="logout_admin")

    # Register transitions for the "data_state" dimension
    def create_first_item(client, ctx):
        """Transition: empty -> one."""
        print(f"      [ACTION] Creating first item")
        ctx["item_count"] = 1
        return {"id": 1, "title": "First item"}

    def create_many_items(client, ctx):
        """Transition: one -> many."""
        print(f"      [ACTION] Creating many items")
        ctx["item_count"] = 100
        return {"created": 99}

    def delete_all_items(client, ctx):
        """Transition: one -> empty or many -> empty."""
        print(f"      [ACTION] Deleting all items")
        ctx["item_count"] = 0
        return {"deleted": "all"}

    builder.register_transition("data_state", "empty", "one", action=create_first_item, name="create_item")
    builder.register_transition("data_state", "one", "many", action=create_many_items, name="bulk_create")
    builder.register_transition("data_state", "one", "empty", action=delete_all_items, name="delete_from_one")
    builder.register_transition("data_state", "many", "empty", action=delete_all_items, name="delete_from_many")

    # Register transitions for the "format" dimension
    def switch_to_xml(client, ctx):
        """Transition: json -> xml."""
        print(f"      [ACTION] Switching to XML format")
        ctx["accept"] = "application/xml"
        return {"format": "xml"}

    def switch_to_json(client, ctx):
        """Transition: xml -> json."""
        print(f"      [ACTION] Switching to JSON format")
        ctx["accept"] = "application/json"
        return {"format": "json"}

    builder.register_transition("format", "json", "xml", action=switch_to_xml, name="use_xml")
    builder.register_transition("format", "xml", "json", action=switch_to_json, name="use_json")

    # Add invariants
    builder.add_invariant(
        "auth_consistent",
        check=lambda client, db, ctx: True,  # Placeholder
        description="Authentication state is consistent between API and session",
    )
    builder.add_invariant(
        "data_count_matches",
        check=lambda client, db, ctx: True,  # Placeholder
        description="Item count matches between API response and database",
    )

    # Set starting state
    builder.set_initial({"auth": "anon", "data_state": "empty", "format": "json"})

    # Print summary
    print(builder.summary(strength=2))

    # Build the graph
    graph = builder.build(strength=2)

    print(f"\n   Graph nodes: {len(graph.nodes)}")
    total_edges = sum(len(e) for e in graph.edges.values())
    print(f"   Graph edges: {total_edges}")
    print(f"   Invariants: {len(graph.invariants)}")

    # =========================================
    # 5. VISUALIZE
    # =========================================

    print("\n5. Mermaid diagram:")
    print("-" * 40)
    mermaid = graph.to_mermaid()
    # Print first 20 lines of the diagram
    for line in mermaid.split("\n")[:25]:
        print(f"   {line}")
    if len(mermaid.split("\n")) > 25:
        print(f"   ... ({len(mermaid.split(chr(10))) - 25} more lines)")

    # =========================================
    # 6. COVERAGE ANALYSIS
    # =========================================

    print("\n6. Coverage analysis:")
    print("-" * 40)

    for strength in [1, 2, 3]:
        if strength > len(space.dimensions):
            break
        stats = gen.coverage_stats(pairwise_combos, strength=strength)
        print(f"   {strength}-wise: {stats.covered_tuples}/{stats.total_tuples} "
              f"tuples covered ({stats.coverage_pct:.1f}%)")

    # =========================================
    # 7. SAMPLING
    # =========================================

    print("\n7. Sampling (budget = 5 tests):")
    print("-" * 40)
    sampled = gen.sample(n=5, strength=2)
    sample_stats = gen.coverage_stats(sampled, strength=2)
    print(f"   Selected {len(sampled)} tests with "
          f"{sample_stats.coverage_pct:.1f}% pairwise coverage:")
    for i, combo in enumerate(sampled, 1):
        print(f"     {i}. {combo.description}")

    print("\n" + "=" * 60)
    print("EXAMPLE COMPLETE")
    print("=" * 60)

    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
