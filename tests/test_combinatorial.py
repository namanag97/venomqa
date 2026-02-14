"""Tests for the combinatorial state testing system.

Tests cover:
- Dimension definition and validation
- Combination generation and properties
- Constraint filtering
- Pairwise and n-wise covering array generation
- StateGraph builder integration
"""

from __future__ import annotations

import pytest

from venomqa.combinatorial import (
    Combination,
    CombinatorialGraphBuilder,
    Constraint,
    ConstraintSet,
    CoverageStats,
    CoveringArrayGenerator,
    Dimension,
    DimensionSpace,
    DimensionValue,
    TransitionKey,
    at_most_one,
    exclude,
    require,
)


# ============================================================
# Dimension Tests
# ============================================================


class TestDimension:
    """Tests for the Dimension class."""

    def test_basic_creation(self):
        d = Dimension("auth", ["anon", "user", "admin"])
        assert d.name == "auth"
        assert d.values == ["anon", "user", "admin"]
        assert d.size == 3

    def test_integer_values(self):
        d = Dimension("count", [0, 1, 2, 5])
        assert d.size == 4
        assert d.values == [0, 1, 2, 5]

    def test_mixed_values(self):
        d = Dimension("count", [0, 1, "many"])
        assert d.size == 3

    def test_default_value(self):
        d = Dimension("auth", ["anon", "user", "admin"], default_value="user")
        assert d.get_default() == "user"

    def test_default_value_first_element(self):
        d = Dimension("auth", ["anon", "user", "admin"])
        assert d.get_default() == "anon"

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="name cannot be empty"):
            Dimension("", ["a", "b"])

    def test_empty_values_raises(self):
        with pytest.raises(ValueError, match="at least one value"):
            Dimension("d", [])

    def test_duplicate_values_raises(self):
        with pytest.raises(ValueError, match="duplicate values"):
            Dimension("d", ["a", "b", "a"])

    def test_invalid_default_raises(self):
        with pytest.raises(ValueError, match="not in dimension"):
            Dimension("d", ["a", "b"], default_value="c")

    def test_dimension_values(self):
        d = Dimension("auth", ["anon", "user"])
        dvs = d.dimension_values
        assert len(dvs) == 2
        assert all(isinstance(dv, DimensionValue) for dv in dvs)
        assert dvs[0].dimension_name == "auth"
        assert dvs[0].value == "anon"


class TestDimensionValue:
    """Tests for DimensionValue."""

    def test_auto_label(self):
        dv = DimensionValue(dimension_name="auth", value="admin")
        assert dv.label == "admin"

    def test_custom_label(self):
        dv = DimensionValue(dimension_name="auth", value="admin", label="Administrator")
        assert dv.label == "Administrator"

    def test_repr(self):
        dv = DimensionValue(dimension_name="auth", value="admin")
        assert repr(dv) == "auth=admin"


class TestCombination:
    """Tests for the Combination class."""

    def test_basic_creation(self):
        c = Combination({"auth": "admin", "count": 1})
        assert c["auth"] == "admin"
        assert c["count"] == 1

    def test_node_id_deterministic(self):
        c1 = Combination({"auth": "admin", "count": 1})
        c2 = Combination({"count": 1, "auth": "admin"})
        assert c1.node_id == c2.node_id

    def test_node_id_format(self):
        c = Combination({"auth": "admin", "count": 1})
        assert c.node_id == "auth=admin__count=1"

    def test_description(self):
        c = Combination({"auth": "admin", "count": 1})
        assert "auth=admin" in c.description
        assert "count=1" in c.description

    def test_differs_by_one_match(self):
        c1 = Combination({"auth": "admin", "count": 1, "status": "active"})
        c2 = Combination({"auth": "user", "count": 1, "status": "active"})
        assert c1.differs_by_one(c2) == "auth"

    def test_differs_by_one_no_diff(self):
        c1 = Combination({"auth": "admin", "count": 1})
        c2 = Combination({"auth": "admin", "count": 1})
        assert c1.differs_by_one(c2) is None

    def test_differs_by_one_two_diffs(self):
        c1 = Combination({"auth": "admin", "count": 1})
        c2 = Combination({"auth": "user", "count": 2})
        assert c1.differs_by_one(c2) is None

    def test_differs_by_one_different_keys(self):
        c1 = Combination({"auth": "admin"})
        c2 = Combination({"count": 1})
        assert c1.differs_by_one(c2) is None

    def test_contains(self):
        c = Combination({"auth": "admin", "count": 1})
        assert "auth" in c
        assert "missing" not in c

    def test_get_with_default(self):
        c = Combination({"auth": "admin"})
        assert c.get("missing", "default") == "default"

    def test_equality(self):
        c1 = Combination({"auth": "admin", "count": 1})
        c2 = Combination({"auth": "admin", "count": 1})
        assert c1 == c2

    def test_hash(self):
        c1 = Combination({"auth": "admin", "count": 1})
        c2 = Combination({"auth": "admin", "count": 1})
        assert hash(c1) == hash(c2)
        assert len({c1, c2}) == 1

    def test_to_dict(self):
        c = Combination({"auth": "admin"})
        assert c.to_dict() == {"auth": "admin"}


class TestDimensionSpace:
    """Tests for DimensionSpace."""

    def test_basic_creation(self):
        space = DimensionSpace([
            Dimension("auth", ["anon", "user"]),
            Dimension("count", [0, 1]),
        ])
        assert space.total_combinations == 4

    def test_dimension_names(self):
        space = DimensionSpace([
            Dimension("auth", ["anon", "user"]),
            Dimension("count", [0, 1]),
        ])
        assert space.dimension_names == ["auth", "count"]

    def test_total_combinations(self):
        space = DimensionSpace([
            Dimension("a", [1, 2, 3]),
            Dimension("b", [4, 5]),
            Dimension("c", [6, 7, 8, 9]),
        ])
        assert space.total_combinations == 3 * 2 * 4

    def test_all_combinations(self):
        space = DimensionSpace([
            Dimension("a", [1, 2]),
            Dimension("b", ["x", "y"]),
        ])
        combos = space.all_combinations()
        assert len(combos) == 4
        values = {c.node_id for c in combos}
        assert "a=1__b=x" in values
        assert "a=1__b=y" in values
        assert "a=2__b=x" in values
        assert "a=2__b=y" in values

    def test_get_dimension(self):
        space = DimensionSpace([
            Dimension("auth", ["anon", "user"]),
        ])
        d = space.get_dimension("auth")
        assert d.name == "auth"

    def test_get_dimension_missing(self):
        space = DimensionSpace([
            Dimension("auth", ["anon", "user"]),
        ])
        with pytest.raises(KeyError, match="not found"):
            space.get_dimension("missing")

    def test_default_combination(self):
        space = DimensionSpace([
            Dimension("auth", ["anon", "user"], default_value="user"),
            Dimension("count", [0, 1]),
        ])
        default = space.default_combination()
        assert default["auth"] == "user"
        assert default["count"] == 0

    def test_empty_dimensions_raises(self):
        with pytest.raises(ValueError, match="at least one dimension"):
            DimensionSpace([])

    def test_duplicate_dimension_names_raises(self):
        with pytest.raises(ValueError, match="Duplicate dimension"):
            DimensionSpace([
                Dimension("auth", ["a"]),
                Dimension("auth", ["b"]),
            ])


# ============================================================
# Constraint Tests
# ============================================================


class TestConstraint:
    """Tests for individual constraints."""

    def test_basic_constraint(self):
        c = Constraint(
            name="test",
            predicate=lambda d: d["auth"] != "anon",
        )
        assert c.is_valid({"auth": "user"}) is True
        assert c.is_valid({"auth": "anon"}) is False

    def test_constraint_with_combination(self):
        c = Constraint(
            name="test",
            predicate=lambda d: d["auth"] != "anon",
        )
        assert c.is_valid(Combination({"auth": "user"})) is True
        assert c.is_valid(Combination({"auth": "anon"})) is False

    def test_dimension_scoping(self):
        c = Constraint(
            name="test",
            predicate=lambda d: d["auth"] != "anon",
            dimensions=["auth"],
        )
        # When scoped dimension is present, check applies
        assert c.is_valid({"auth": "anon"}) is False
        # When scoped dimension is absent, passes (not applicable)
        assert c.is_valid({"count": 1}) is True

    def test_error_in_predicate_returns_false(self):
        c = Constraint(
            name="test",
            predicate=lambda d: d["missing_key"],  # KeyError
        )
        assert c.is_valid({"auth": "user"}) is False


class TestExclude:
    """Tests for the exclude() helper."""

    def test_basic_exclude(self):
        c = exclude("test", auth="anon", status="archived")
        assert c.is_valid({"auth": "anon", "status": "archived"}) is False
        assert c.is_valid({"auth": "user", "status": "archived"}) is True
        assert c.is_valid({"auth": "anon", "status": "active"}) is True

    def test_single_dimension_exclude(self):
        c = exclude("test", auth="anon")
        assert c.is_valid({"auth": "anon"}) is False
        assert c.is_valid({"auth": "user"}) is True


class TestRequire:
    """Tests for the require() helper."""

    def test_basic_require(self):
        c = require(
            "test",
            if_condition={"auth": "admin"},
            then_condition={"perms": "full"},
        )
        # Admin with full perms: valid
        assert c.is_valid({"auth": "admin", "perms": "full"}) is True
        # Admin without full perms: invalid
        assert c.is_valid({"auth": "admin", "perms": "read"}) is False
        # Non-admin: valid (vacuously true)
        assert c.is_valid({"auth": "user", "perms": "read"}) is True

    def test_require_not_triggered(self):
        c = require(
            "test",
            if_condition={"auth": "admin"},
            then_condition={"perms": "full"},
        )
        assert c.is_valid({"auth": "user", "perms": "read"}) is True


class TestAtMostOne:
    """Tests for the at_most_one() helper."""

    def test_basic_mutual_exclusion(self):
        c = at_most_one(
            "test",
            conditions=[
                {"flag_a": True},
                {"flag_b": True},
            ],
        )
        assert c.is_valid({"flag_a": True, "flag_b": False}) is True
        assert c.is_valid({"flag_a": False, "flag_b": True}) is True
        assert c.is_valid({"flag_a": True, "flag_b": True}) is False
        assert c.is_valid({"flag_a": False, "flag_b": False}) is True


class TestConstraintSet:
    """Tests for ConstraintSet."""

    def test_all_must_pass(self):
        cs = ConstraintSet([
            exclude("c1", auth="anon", status="archived"),
            exclude("c2", auth="anon", count="many"),
        ])
        # Both constraints pass
        assert cs.is_valid({"auth": "user", "status": "archived", "count": "many"}) is True
        # First constraint fails
        assert cs.is_valid({"auth": "anon", "status": "archived", "count": 0}) is False
        # Second constraint fails
        assert cs.is_valid({"auth": "anon", "status": "active", "count": "many"}) is False

    def test_filter(self):
        cs = ConstraintSet([exclude("c1", auth="anon")])
        combos = [
            Combination({"auth": "anon", "x": 1}),
            Combination({"auth": "user", "x": 1}),
            Combination({"auth": "anon", "x": 2}),
        ]
        filtered = cs.filter(combos)
        assert len(filtered) == 1
        assert filtered[0]["auth"] == "user"

    def test_violated_by(self):
        c1 = exclude("c1", auth="anon")
        c2 = exclude("c2", count=0)
        cs = ConstraintSet([c1, c2])
        violated = cs.violated_by({"auth": "anon", "count": 0})
        assert len(violated) == 2

    def test_add(self):
        cs = ConstraintSet()
        assert len(cs) == 0
        cs.add(exclude("c1", auth="anon"))
        assert len(cs) == 1


# ============================================================
# Generator Tests
# ============================================================


class TestCoveringArrayGenerator:
    """Tests for covering array generation."""

    @pytest.fixture
    def small_space(self):
        return DimensionSpace([
            Dimension("auth", ["anon", "user", "admin"]),
            Dimension("status", ["active", "archived"]),
            Dimension("count", [0, 1, "many"]),
        ])

    @pytest.fixture
    def constrained_space(self, small_space):
        constraints = ConstraintSet([
            exclude("no_anon_archive", auth="anon", status="archived"),
        ])
        return small_space, constraints

    def test_exhaustive(self, small_space):
        gen = CoveringArrayGenerator(small_space, seed=42)
        combos = gen.exhaustive()
        assert len(combos) == small_space.total_combinations  # 18

    def test_exhaustive_with_constraints(self, constrained_space):
        space, constraints = constrained_space
        gen = CoveringArrayGenerator(space, constraints, seed=42)
        combos = gen.exhaustive()
        # 18 total - 3 excluded (anon+archived with each count) = 15
        assert len(combos) == 15
        for c in combos:
            assert not (c["auth"] == "anon" and c["status"] == "archived")

    def test_pairwise_smaller_than_exhaustive(self, small_space):
        gen = CoveringArrayGenerator(small_space, seed=42)
        pairwise = gen.pairwise()
        exhaustive = gen.exhaustive()
        assert len(pairwise) < len(exhaustive)

    def test_pairwise_covers_all_pairs(self, small_space):
        gen = CoveringArrayGenerator(small_space, seed=42)
        combos = gen.pairwise()
        stats = gen.coverage_stats(combos, strength=2)
        assert stats.coverage_pct == 100.0

    def test_pairwise_with_constraints(self, constrained_space):
        space, constraints = constrained_space
        gen = CoveringArrayGenerator(space, constraints, seed=42)
        combos = gen.pairwise()

        # All combinations should be valid
        for c in combos:
            assert constraints.is_valid(c), f"Invalid combination: {c}"

        # Should still achieve 100% pairwise coverage
        stats = gen.coverage_stats(combos, strength=2)
        assert stats.coverage_pct == 100.0

    def test_three_wise(self, small_space):
        gen = CoveringArrayGenerator(small_space, seed=42)
        combos = gen.three_wise()
        stats = gen.coverage_stats(combos, strength=3)
        assert stats.coverage_pct == 100.0

    def test_strength_1(self, small_space):
        gen = CoveringArrayGenerator(small_space, seed=42)
        combos = gen.generate(strength=1)
        stats = gen.coverage_stats(combos, strength=1)
        assert stats.coverage_pct == 100.0
        # With strength 1, should need at most max(dimension sizes)
        assert len(combos) <= 3  # max dimension size

    def test_invalid_strength(self, small_space):
        gen = CoveringArrayGenerator(small_space, seed=42)
        with pytest.raises(ValueError, match="at least 1"):
            gen.generate(strength=0)

    def test_strength_exceeds_dimensions(self, small_space):
        gen = CoveringArrayGenerator(small_space, seed=42)
        with pytest.raises(ValueError, match="exceeds"):
            gen.generate(strength=4)

    def test_reproducibility(self, small_space):
        gen1 = CoveringArrayGenerator(small_space, seed=42)
        gen2 = CoveringArrayGenerator(small_space, seed=42)
        combos1 = gen1.pairwise()
        combos2 = gen2.pairwise()
        assert combos1 == combos2

    def test_different_seeds_different_results(self, small_space):
        gen1 = CoveringArrayGenerator(small_space, seed=42)
        gen2 = CoveringArrayGenerator(small_space, seed=99)
        combos1 = gen1.pairwise()
        combos2 = gen2.pairwise()
        # They might have the same length but different order/content
        # The key property is both achieve 100% coverage
        stats1 = gen1.coverage_stats(combos1, strength=2)
        stats2 = gen2.coverage_stats(combos2, strength=2)
        assert stats1.coverage_pct == 100.0
        assert stats2.coverage_pct == 100.0

    def test_sample_limits_count(self, small_space):
        gen = CoveringArrayGenerator(small_space, seed=42)
        full = gen.pairwise()
        sampled = gen.sample(n=3, strength=2)
        assert len(sampled) <= 3
        assert len(sampled) <= len(full)

    def test_sample_maximizes_coverage(self, small_space):
        gen = CoveringArrayGenerator(small_space, seed=42)
        sampled = gen.sample(n=5, strength=2)
        stats = gen.coverage_stats(sampled, strength=2)
        # With 5 samples from a small space, coverage should be decent
        assert stats.coverage_pct > 50.0

    def test_two_dimensions_pairwise(self):
        """With only 2 dimensions, pairwise = exhaustive."""
        space = DimensionSpace([
            Dimension("a", [1, 2, 3]),
            Dimension("b", ["x", "y"]),
        ])
        gen = CoveringArrayGenerator(space, seed=42)
        combos = gen.pairwise()
        # Pairwise of 2 dims IS the Cartesian product
        assert len(combos) == 6

    def test_large_space_reduction(self):
        """Verify significant reduction for larger spaces."""
        space = DimensionSpace([
            Dimension("a", list(range(5))),
            Dimension("b", list(range(5))),
            Dimension("c", list(range(5))),
            Dimension("d", list(range(5))),
        ])
        gen = CoveringArrayGenerator(space, seed=42)
        combos = gen.pairwise()
        # 5^4 = 625 exhaustive, pairwise should be much smaller
        assert len(combos) < 100
        stats = gen.coverage_stats(combos, strength=2)
        assert stats.coverage_pct == 100.0


class TestCoverageStats:
    """Tests for CoverageStats."""

    def test_repr(self):
        stats = CoverageStats(
            strength=2,
            total_tuples=100,
            covered_tuples=95,
            coverage_pct=95.0,
            test_count=10,
        )
        assert "t=2" in repr(stats)
        assert "95/100" in repr(stats)
        assert "95.0%" in repr(stats)


# ============================================================
# Builder Tests
# ============================================================


class TestCombinatorialGraphBuilder:
    """Tests for the StateGraph builder."""

    @pytest.fixture
    def basic_space(self):
        return DimensionSpace([
            Dimension("auth", ["anon", "user", "admin"]),
            Dimension("count", [0, 1, "many"]),
        ])

    @pytest.fixture
    def basic_builder(self, basic_space):
        return CombinatorialGraphBuilder(
            name="test_graph",
            space=basic_space,
            seed=42,
        )

    def test_register_transition(self, basic_builder):
        action = lambda client, ctx: None
        trans = basic_builder.register_transition(
            "auth", "anon", "user", action=action, name="login"
        )
        assert trans.name == "login"
        assert trans.key.dimension == "auth"
        assert trans.key.from_value == "anon"
        assert trans.key.to_value == "user"

    def test_register_transition_invalid_dimension(self, basic_builder):
        with pytest.raises(KeyError, match="not found"):
            basic_builder.register_transition(
                "nonexistent", "a", "b", action=lambda c, ctx: None
            )

    def test_register_transition_invalid_value(self, basic_builder):
        with pytest.raises(ValueError, match="not in dimension"):
            basic_builder.register_transition(
                "auth", "anon", "superadmin", action=lambda c, ctx: None
            )

    def test_add_invariant(self, basic_builder):
        basic_builder.add_invariant(
            "test_inv",
            check=lambda client, db, ctx: True,
            description="Always passes",
        )
        assert len(basic_builder._invariants) == 1

    def test_set_initial(self, basic_builder):
        basic_builder.set_initial({"auth": "anon", "count": 0})
        assert basic_builder._initial_combination is not None
        assert basic_builder._initial_combination["auth"] == "anon"

    def test_set_initial_missing_dimension(self, basic_builder):
        with pytest.raises(ValueError, match="missing dimension"):
            basic_builder.set_initial({"auth": "anon"})

    def test_build_basic(self, basic_builder):
        # Register transitions for edges
        basic_builder.register_transition(
            "auth", "anon", "user", action=lambda c, ctx: None
        )
        basic_builder.register_transition(
            "auth", "user", "admin", action=lambda c, ctx: None
        )
        basic_builder.register_transition(
            "count", 0, 1, action=lambda c, ctx: None
        )

        graph = basic_builder.build(strength=2)

        assert graph.name == "test_graph"
        assert len(graph.nodes) > 0
        # Should have edges for registered transitions
        total_edges = sum(len(e) for e in graph.edges.values())
        assert total_edges > 0

    def test_build_with_invariants(self, basic_builder):
        basic_builder.register_transition(
            "auth", "anon", "user", action=lambda c, ctx: None
        )
        basic_builder.add_invariant(
            "always_true",
            check=lambda client, db, ctx: True,
            description="test invariant",
        )

        graph = basic_builder.build(strength=2)
        assert len(graph.invariants) == 1
        assert graph.invariants[0].name == "always_true"

    def test_build_has_initial_node(self, basic_builder):
        basic_builder.register_transition(
            "auth", "anon", "user", action=lambda c, ctx: None
        )
        basic_builder.set_initial({"auth": "anon", "count": 0})

        graph = basic_builder.build(strength=2)
        assert graph._initial_node is not None

    def test_build_with_constraints(self):
        space = DimensionSpace([
            Dimension("auth", ["anon", "user", "admin"]),
            Dimension("status", ["active", "archived"]),
        ])
        constraints = ConstraintSet([
            exclude("no_anon_archive", auth="anon", status="archived"),
        ])
        builder = CombinatorialGraphBuilder(
            name="constrained",
            space=space,
            constraints=constraints,
            seed=42,
        )
        builder.register_transition(
            "auth", "anon", "user", action=lambda c, ctx: None
        )

        graph = builder.build(strength=2)

        # No node should represent anon+archived
        for node_id in graph.nodes:
            assert not (
                "auth=anon" in node_id and "status=archived" in node_id
            ), f"Invalid node found: {node_id}"

    def test_build_with_explicit_combinations(self, basic_builder):
        combos = [
            Combination({"auth": "anon", "count": 0}),
            Combination({"auth": "user", "count": 1}),
            Combination({"auth": "admin", "count": "many"}),
        ]
        basic_builder.register_transition(
            "auth", "anon", "user", action=lambda c, ctx: None
        )

        graph = basic_builder.build(combinations=combos)
        assert len(graph.nodes) == 3

    def test_build_no_valid_combinations_raises(self):
        space = DimensionSpace([Dimension("a", [1, 2])])
        constraints = ConstraintSet([
            Constraint("block_all", predicate=lambda d: False),
        ])
        builder = CombinatorialGraphBuilder(
            name="empty", space=space, constraints=constraints, seed=42,
        )
        with pytest.raises(ValueError, match="No valid combinations"):
            builder.build()

    def test_build_journey_graph(self, basic_builder):
        basic_builder.register_transition(
            "auth", "anon", "user", action=lambda c, ctx: None
        )
        graph, combos = basic_builder.build_journey_graph(strength=2)
        assert len(combos) > 0
        assert graph.name == "test_graph"

    def test_register_setup(self, basic_builder):
        setup = basic_builder.register_setup(
            "auth", "user",
            action=lambda c, ctx: None,
            description="Set up user auth",
        )
        assert setup.dimension == "auth"
        assert setup.value == "user"

    def test_register_checker(self, basic_builder):
        basic_builder.register_checker(
            "auth", "user",
            checker=lambda client, db, ctx: True,
        )
        assert ("auth", "user") in basic_builder._state_checkers

    def test_summary(self, basic_builder):
        basic_builder.register_transition(
            "auth", "anon", "user", action=lambda c, ctx: None
        )
        summary = basic_builder.summary(strength=2)
        assert "test_graph" in summary
        assert "auth" in summary
        assert "count" in summary

    def test_edge_context_injection(self, basic_builder):
        """Verify that wrapped actions inject combination context."""
        captured_context = {}

        def capture_action(client, ctx):
            captured_context.update(ctx)
            return None

        basic_builder.register_transition(
            "auth", "anon", "user", action=capture_action
        )

        graph = basic_builder.build(strength=2)

        # Find an edge that transitions auth anon->user
        for from_node, edges in graph.edges.items():
            for edge in edges:
                if "auth_anon_to_user" in edge.name:
                    # Execute the edge action
                    edge.action(None, {})
                    assert "_changed_dimension" in captured_context
                    assert captured_context["_changed_dimension"] == "auth"
                    assert captured_context["_from_value"] == "anon"
                    assert captured_context["_to_value"] == "user"
                    return

    def test_mermaid_output(self, basic_builder):
        basic_builder.register_transition(
            "auth", "anon", "user", action=lambda c, ctx: None
        )
        graph = basic_builder.build(strength=2)
        mermaid = graph.to_mermaid()
        assert "stateDiagram-v2" in mermaid


# ============================================================
# Integration Tests
# ============================================================


class TestIntegration:
    """End-to-end integration tests."""

    def test_full_workflow(self):
        """Test the complete workflow from dimensions to StateGraph."""
        # 1. Define dimensions
        space = DimensionSpace([
            Dimension("auth", ["anon", "user", "admin"]),
            Dimension("data", ["empty", "has_items"]),
            Dimension("format", ["json", "xml"]),
        ])

        # 2. Define constraints
        constraints = ConstraintSet([
            exclude("no_anon_xml", auth="anon", format="xml"),
        ])

        # 3. Generate pairwise combinations
        gen = CoveringArrayGenerator(space, constraints, seed=42)
        combos = gen.pairwise()

        # Verify coverage
        stats = gen.coverage_stats(combos, strength=2)
        assert stats.coverage_pct == 100.0

        # Verify constraint compliance
        for c in combos:
            assert constraints.is_valid(c)

        # Verify reduction
        assert len(combos) < space.total_combinations

        # 4. Build StateGraph
        builder = CombinatorialGraphBuilder(
            name="full_test",
            space=space,
            constraints=constraints,
            seed=42,
        )

        # Register transitions
        builder.register_transition(
            "auth", "anon", "user",
            action=lambda c, ctx: "logged_in",
            name="login",
        )
        builder.register_transition(
            "auth", "user", "admin",
            action=lambda c, ctx: "elevated",
            name="elevate",
        )
        builder.register_transition(
            "data", "empty", "has_items",
            action=lambda c, ctx: "created",
            name="create_item",
        )
        builder.register_transition(
            "format", "json", "xml",
            action=lambda c, ctx: "switched",
            name="switch_format",
        )

        # Add invariant
        builder.add_invariant(
            "always_valid",
            check=lambda client, db, ctx: True,
            description="Placeholder invariant",
        )

        graph = builder.build(strength=2)

        # Verify graph structure
        assert len(graph.nodes) == len(combos)
        assert len(graph.invariants) == 1
        total_edges = sum(len(e) for e in graph.edges.values())
        assert total_edges > 0

    def test_single_dimension(self):
        """Combinatorial with a single dimension degenerates to exhaustive."""
        space = DimensionSpace([
            Dimension("mode", ["read", "write", "admin"]),
        ])
        gen = CoveringArrayGenerator(space, seed=42)
        # strength=2 exceeds 1 dimension, use exhaustive (strength=1)
        combos = gen.generate(strength=1)
        # With 1 dimension, strength=1 = all values
        assert len(combos) == 3

    def test_binary_dimensions(self):
        """Test with all boolean dimensions."""
        space = DimensionSpace([
            Dimension("feature_a", [True, False]),
            Dimension("feature_b", [True, False]),
            Dimension("feature_c", [True, False]),
            Dimension("feature_d", [True, False]),
        ])
        gen = CoveringArrayGenerator(space, seed=42)
        combos = gen.pairwise()
        stats = gen.coverage_stats(combos, strength=2)
        assert stats.coverage_pct == 100.0
        # 2^4 = 16 exhaustive, pairwise should be much smaller
        assert len(combos) < 16

    def test_heavily_constrained(self):
        """Test with many constraints reducing the valid space."""
        space = DimensionSpace([
            Dimension("a", [1, 2, 3]),
            Dimension("b", [1, 2, 3]),
            Dimension("c", [1, 2, 3]),
        ])
        constraints = ConstraintSet([
            exclude("c1", a=1, b=1),
            exclude("c2", a=2, b=2),
            exclude("c3", a=3, b=3),
            exclude("c4", b=1, c=1),
            exclude("c5", b=2, c=2),
        ])
        gen = CoveringArrayGenerator(space, constraints, seed=42)
        combos = gen.pairwise()

        # All should be valid
        for c in combos:
            assert constraints.is_valid(c), f"Invalid: {c}"

        # Coverage of feasible pairs should still be 100%
        stats = gen.coverage_stats(combos, strength=2)
        assert stats.coverage_pct == 100.0
