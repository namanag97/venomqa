"""Covering array generators for combinatorial testing.

This module implements algorithms for generating covering arrays --
subsets of the full Cartesian product that guarantee every t-way
combination of values is exercised at least once.

- t=2 (pairwise): Every pair of dimension values appears together.
- t=3 (three-wise): Every triple of dimension values appears together.
- t=N (exhaustive): All combinations (Cartesian product).

Pairwise testing is the most common form. Research shows that most
software defects are caused by interactions of at most 2-3 parameters,
so pairwise covers the majority of real bugs with a fraction of the
full test space.

Example:
    >>> from venomqa.combinatorial import (
    ...     Dimension, DimensionSpace, ConstraintSet, CoveringArrayGenerator
    ... )
    >>>
    >>> space = DimensionSpace([
    ...     Dimension("auth", ["anon", "user", "admin"]),
    ...     Dimension("status", ["active", "archived"]),
    ...     Dimension("count", [0, 1, "many"]),
    ... ])
    >>> constraints = ConstraintSet()
    >>>
    >>> gen = CoveringArrayGenerator(space, constraints)
    >>> combos = gen.pairwise()
    >>> print(f"Pairwise: {len(combos)} tests (vs {space.total_combinations} exhaustive)")
"""

from __future__ import annotations

import itertools
import logging
import random
from collections.abc import Hashable
from dataclasses import dataclass

from venomqa.combinatorial.constraints import ConstraintSet
from venomqa.combinatorial.dimensions import Combination, DimensionSpace

logger = logging.getLogger(__name__)


@dataclass
class CoverageStats:
    """Statistics about how well a test suite covers the dimension space.

    Attributes:
        strength: The t-wise strength that was targeted.
        total_tuples: Total number of t-tuples in the space.
        covered_tuples: Number of t-tuples covered by the test suite.
        coverage_pct: Percentage coverage (0-100).
        test_count: Number of tests in the suite.
        excluded_by_constraints: Tuples excluded due to constraints.
    """

    strength: int
    total_tuples: int
    covered_tuples: int
    coverage_pct: float
    test_count: int
    excluded_by_constraints: int = 0

    def __repr__(self) -> str:
        return (
            f"CoverageStats(t={self.strength}, "
            f"{self.covered_tuples}/{self.total_tuples} tuples covered "
            f"({self.coverage_pct:.1f}%), "
            f"{self.test_count} tests)"
        )


class CoveringArrayGenerator:
    """Generates covering arrays for combinatorial testing.

    Implements the greedy IPOG-inspired algorithm for generating t-wise
    covering arrays. The algorithm works by:

    1. Start with all pairs (or t-tuples) that need to be covered.
    2. Greedily select combinations that cover the most uncovered tuples.
    3. Fill remaining values to maximize additional coverage.
    4. Repeat until all tuples are covered.

    This produces near-optimal covering arrays. Optimal covering arrays
    are NP-hard to compute, but greedy approaches typically produce
    arrays within 1.5x of optimal.

    Attributes:
        space: The dimension space to generate from.
        constraints: Constraints to filter invalid combinations.
        seed: Random seed for reproducibility.

    Example:
        >>> gen = CoveringArrayGenerator(space, constraints, seed=42)
        >>> combos = gen.generate(strength=2)  # Pairwise
        >>> stats = gen.coverage_stats(combos, strength=2)
        >>> print(stats)
    """

    def __init__(
        self,
        space: DimensionSpace,
        constraints: ConstraintSet | None = None,
        seed: int | None = None,
    ) -> None:
        self.space = space
        self.constraints = constraints or ConstraintSet()
        self._rng = random.Random(seed)

    def pairwise(self) -> list[Combination]:
        """Generate a pairwise (2-wise) covering array.

        Guarantees every pair of (dimension_i=value_a, dimension_j=value_b)
        appears in at least one combination.

        Returns:
            List of Combination objects forming a pairwise covering array.
        """
        return self.generate(strength=2)

    def three_wise(self) -> list[Combination]:
        """Generate a 3-wise covering array.

        Guarantees every triple of dimension values appears together.

        Returns:
            List of Combination objects forming a 3-wise covering array.
        """
        return self.generate(strength=3)

    def exhaustive(self) -> list[Combination]:
        """Generate all valid combinations (full Cartesian product).

        Filtered by constraints.

        Returns:
            List of all valid Combination objects.
        """
        all_combos = self.space.all_combinations()
        return self.constraints.filter(all_combos)

    def generate(self, strength: int = 2) -> list[Combination]:
        """Generate a t-wise covering array.

        Args:
            strength: The interaction strength t. Must be between 1 and
                the number of dimensions.
                - t=1: Each value appears at least once (minimal)
                - t=2: Pairwise coverage
                - t=3: Three-wise coverage
                - t=N: Exhaustive (N = number of dimensions)

        Returns:
            List of Combination objects forming the covering array.

        Raises:
            ValueError: If strength is invalid.
        """
        n_dims = len(self.space.dimensions)

        if strength < 1:
            raise ValueError("Strength must be at least 1")
        if strength > n_dims:
            raise ValueError(
                f"Strength {strength} exceeds number of dimensions ({n_dims}). "
                f"Use exhaustive() instead."
            )

        if strength == n_dims:
            return self.exhaustive()

        logger.info(
            f"Generating {strength}-wise covering array for "
            f"{n_dims} dimensions ({self.space.total_combinations} total combinations)"
        )

        # Collect all t-tuples that need to be covered
        uncovered = self._all_t_tuples(strength)
        original_count = len(uncovered)

        # Filter out tuples that are impossible due to constraints
        uncovered = self._filter_feasible_tuples(uncovered)
        feasible_count = len(uncovered)
        excluded = original_count - feasible_count

        logger.info(
            f"Need to cover {feasible_count} tuples "
            f"({excluded} excluded by constraints)"
        )

        result: list[Combination] = []
        uncovered_set = set(range(len(uncovered)))

        while uncovered_set:
            # Greedily find the combination that covers the most uncovered tuples
            best = self._find_best_combination(uncovered, uncovered_set)

            if best is None:
                logger.warning(
                    f"Could not find valid combination for remaining "
                    f"{len(uncovered_set)} tuples"
                )
                break

            result.append(best)

            # Remove newly covered tuples
            newly_covered = set()
            for idx in uncovered_set:
                if self._combination_covers_tuple(best, uncovered[idx]):
                    newly_covered.add(idx)
            uncovered_set -= newly_covered

            logger.debug(
                f"Added combination {len(result)}, covered {len(newly_covered)} tuples, "
                f"{len(uncovered_set)} remaining"
            )

        logger.info(
            f"Generated {len(result)} tests for {strength}-wise coverage "
            f"(vs {self.space.total_combinations} exhaustive)"
        )

        return result

    def coverage_stats(
        self,
        combinations: list[Combination],
        strength: int = 2,
    ) -> CoverageStats:
        """Compute coverage statistics for a set of combinations.

        Args:
            combinations: The test suite to measure.
            strength: The t-wise strength to measure against.

        Returns:
            CoverageStats with coverage information.
        """
        all_tuples = self._all_t_tuples(strength)
        feasible = self._filter_feasible_tuples(all_tuples)
        excluded = len(all_tuples) - len(feasible)

        covered = set()
        for combo in combinations:
            for i, t in enumerate(feasible):
                if self._combination_covers_tuple(combo, t):
                    covered.add(i)

        total = len(feasible)
        pct = (len(covered) / total * 100) if total > 0 else 100.0

        return CoverageStats(
            strength=strength,
            total_tuples=total,
            covered_tuples=len(covered),
            coverage_pct=pct,
            test_count=len(combinations),
            excluded_by_constraints=excluded,
        )

    def _all_t_tuples(
        self, strength: int
    ) -> list[dict[str, Hashable]]:
        """Generate all t-tuples (dimension subsets x value combos).

        A t-tuple is a specific assignment of values to t dimensions.
        For pairwise (t=2), this is all pairs (dim_i=val_a, dim_j=val_b).
        """
        dims = self.space.dimensions
        tuples: list[dict[str, Hashable]] = []

        # For each subset of t dimensions
        for dim_subset in itertools.combinations(dims, strength):
            names = [d.name for d in dim_subset]
            value_lists = [d.values for d in dim_subset]

            # For each combination of values for these dimensions
            for values in itertools.product(*value_lists):
                tuples.append(dict(zip(names, values, strict=False)))

        return tuples

    def _filter_feasible_tuples(
        self, tuples: list[dict[str, Hashable]]
    ) -> list[dict[str, Hashable]]:
        """Remove tuples that can never be covered due to constraints.

        A tuple is infeasible if no extension to a full combination
        can satisfy all constraints. We approximate this by checking
        the partial assignment against constraints.
        """
        if not self.constraints.constraints:
            return tuples

        feasible = []
        for t in tuples:
            # Quick check: does the partial assignment violate any constraint?
            if self.constraints.is_valid(t):
                feasible.append(t)

        return feasible

    def _combination_covers_tuple(
        self,
        combo: Combination,
        t_tuple: dict[str, Hashable],
    ) -> bool:
        """Check if a combination covers (contains) a t-tuple."""
        return all(
            combo.values.get(k) == v
            for k, v in t_tuple.items()
        )

    def _find_best_combination(
        self,
        all_tuples: list[dict[str, Hashable]],
        uncovered_indices: set[int],
    ) -> Combination | None:
        """Find the combination that covers the most uncovered tuples.

        Uses a greedy approach:
        1. Try random candidate combinations.
        2. Score each by how many uncovered tuples it covers.
        3. Return the best scoring valid combination.
        """
        dims = self.space.dimensions
        best_combo: Combination | None = None
        best_score = -1

        # Number of random candidates to try. More candidates = better
        # coverage but slower generation.
        n_candidates = max(50, len(dims) * 10)

        for _ in range(n_candidates):
            # Build a candidate combination
            candidate = self._build_candidate(all_tuples, uncovered_indices)

            if candidate is None:
                continue

            if not self.constraints.is_valid(candidate):
                continue

            # Score: how many uncovered tuples does this cover?
            score = sum(
                1 for idx in uncovered_indices
                if self._combination_covers_tuple(candidate, all_tuples[idx])
            )

            if score > best_score:
                best_score = score
                best_combo = candidate

        # If random search failed, try a more systematic approach
        if best_combo is None:
            best_combo = self._systematic_search(all_tuples, uncovered_indices)

        return best_combo

    def _build_candidate(
        self,
        all_tuples: list[dict[str, Hashable]],
        uncovered_indices: set[int],
    ) -> Combination | None:
        """Build a candidate combination targeting uncovered tuples.

        Strategy: Pick a random uncovered tuple, use its values as a seed,
        then fill remaining dimensions randomly.
        """
        if not uncovered_indices:
            return None

        # Pick a random uncovered tuple to seed from
        seed_idx = self._rng.choice(list(uncovered_indices))
        seed_tuple = all_tuples[seed_idx]

        # Start with the seed tuple values
        values: dict[str, Hashable] = dict(seed_tuple)

        # Fill in missing dimensions with random values
        for dim in self.space.dimensions:
            if dim.name not in values:
                values[dim.name] = self._rng.choice(dim.values)

        return Combination(values)

    def _systematic_search(
        self,
        all_tuples: list[dict[str, Hashable]],
        uncovered_indices: set[int],
    ) -> Combination | None:
        """Systematic fallback search when random candidates fail.

        Tries to build a valid combination for each uncovered tuple
        by trying all possible extensions.
        """
        uncovered_list = list(uncovered_indices)
        self._rng.shuffle(uncovered_list)

        for idx in uncovered_list[:20]:  # Limit search depth
            seed_tuple = all_tuples[idx]

            # Try to extend this tuple to a full, valid combination
            combo = self._extend_tuple(seed_tuple)
            if combo is not None:
                return combo

        return None

    def _extend_tuple(
        self, partial: dict[str, Hashable]
    ) -> Combination | None:
        """Try to extend a partial assignment to a full valid combination.

        Tries random values for missing dimensions, with limited retries.
        """
        missing_dims = [
            d for d in self.space.dimensions
            if d.name not in partial
        ]

        for _ in range(50):  # Retry limit
            values = dict(partial)
            for dim in missing_dims:
                values[dim.name] = self._rng.choice(dim.values)

            combo = Combination(values)
            if self.constraints.is_valid(combo):
                return combo

        return None

    def sample(self, n: int, strength: int = 2) -> list[Combination]:
        """Generate at most n valid combinations with best coverage.

        If the covering array has fewer than n tests, returns all of them.
        If it has more, selects the n tests that maximize coverage.

        Args:
            n: Maximum number of tests to return.
            strength: Interaction strength for coverage measurement.

        Returns:
            List of at most n Combination objects.
        """
        full = self.generate(strength=strength)
        if len(full) <= n:
            return full

        # Greedily select n tests that maximize coverage
        selected: list[Combination] = []
        remaining = list(full)

        all_tuples = self._all_t_tuples(strength)
        feasible = self._filter_feasible_tuples(all_tuples)
        uncovered = set(range(len(feasible)))

        for _ in range(n):
            if not remaining:
                break

            best_idx = 0
            best_score = -1

            for i, combo in enumerate(remaining):
                score = sum(
                    1 for idx in uncovered
                    if self._combination_covers_tuple(combo, feasible[idx])
                )
                if score > best_score:
                    best_score = score
                    best_idx = i

            chosen = remaining.pop(best_idx)
            selected.append(chosen)

            # Update uncovered
            newly_covered = {
                idx for idx in uncovered
                if self._combination_covers_tuple(chosen, feasible[idx])
            }
            uncovered -= newly_covered

        return selected
