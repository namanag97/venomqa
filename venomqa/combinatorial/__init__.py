"""Combinatorial state testing for VenomQA.

This module adds combinatorial/pairwise testing capabilities on top of
VenomQA's StateGraph system. It allows you to define dimensions of
variation (e.g., auth level, data state, feature flags) and automatically
generates a minimal set of test combinations that cover all pairwise
(or n-wise) interactions.

Architecture:
    The combinatorial system is built as a layer on top of the existing
    StateGraph system using composition. It does NOT modify any core
    classes. Instead, it generates StateGraph instances populated with
    nodes and edges derived from dimension combinations.

    Dimension -> DimensionSpace -> CoveringArrayGenerator -> Combinations
        -> CombinatorialGraphBuilder -> StateGraph

Modules:
    dimensions: Dimension, DimensionValue, DimensionSpace, Combination
    constraints: Constraint, ConstraintSet, exclude, require, at_most_one
    generator: CoveringArrayGenerator, CoverageStats
    builder: CombinatorialGraphBuilder, TransitionAction, StateSetup

Quick Start:
    >>> from venomqa.combinatorial import (
    ...     Dimension, DimensionSpace, ConstraintSet,
    ...     CoveringArrayGenerator, CombinatorialGraphBuilder, exclude,
    ... )
    >>>
    >>> # 1. Define dimensions
    >>> space = DimensionSpace([
    ...     Dimension("auth", ["anon", "user", "admin"]),
    ...     Dimension("data", ["empty", "one", "many"]),
    ...     Dimension("format", ["json", "xml"]),
    ... ])
    >>>
    >>> # 2. Define constraints
    >>> constraints = ConstraintSet([
    ...     exclude("no_anon_many", auth="anon", data="many"),
    ... ])
    >>>
    >>> # 3. Generate pairwise combinations
    >>> gen = CoveringArrayGenerator(space, constraints, seed=42)
    >>> combos = gen.pairwise()
    >>> print(f"{len(combos)} tests cover all pairs (vs {space.total_combinations} exhaustive)")
    >>>
    >>> # 4. Build a StateGraph
    >>> builder = CombinatorialGraphBuilder("api_test", space, constraints)
    >>> builder.register_transition("auth", "anon", "user", action=login)
    >>> builder.add_invariant("counts_match", check=verify_counts)
    >>> graph = builder.build(strength=2)
    >>> result = graph.explore(client, db)
"""

from venomqa.combinatorial.builder import (
    CombinatorialGraphBuilder,
    StateSetup,
    TransitionAction,
    TransitionKey,
)
from venomqa.combinatorial.constraints import (
    Constraint,
    ConstraintPredicate,
    ConstraintSet,
    at_most_one,
    exclude,
    require,
)
from venomqa.combinatorial.dimensions import (
    Combination,
    Dimension,
    DimensionSpace,
    DimensionValue,
)
from venomqa.combinatorial.generator import (
    CoverageStats,
    CoveringArrayGenerator,
)

__all__ = [
    # Dimensions
    "Dimension",
    "DimensionValue",
    "DimensionSpace",
    "Combination",
    # Constraints
    "Constraint",
    "ConstraintPredicate",
    "ConstraintSet",
    "exclude",
    "require",
    "at_most_one",
    # Generator
    "CoveringArrayGenerator",
    "CoverageStats",
    # Builder
    "CombinatorialGraphBuilder",
    "TransitionAction",
    "TransitionKey",
    "StateSetup",
]
