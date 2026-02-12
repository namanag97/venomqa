"""Search and ranking assertions for VenomQA.

Provides assertion functions for validating search results, rankings,
and algorithmic outputs commonly used in QA testing of search/recommendation
systems.

Example:
    >>> from venomqa.assertions import assert_top_n_contains, assert_ordered_before
    >>> assert_top_n_contains(results, ["item1", "item2"], n=5)
    >>> assert_ordered_before(results, "item1", "item2")
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from venomqa.assertions.expect import AssertionFailed


class RankingAssertionError(AssertionFailed):
    """Raised when a ranking assertion fails."""

    pass


def assert_top_n_contains(
    results: Sequence[Any],
    expected_ids: Sequence[str | int],
    n: int = 5,
    id_field: str = "id",
) -> None:
    """Assert top N results contain all expected IDs.

    Args:
        results: Sequence of result objects (dicts or objects with id attribute).
        expected_ids: Sequence of IDs that must appear in top N.
        n: Number of top results to check.
        id_field: Field name for ID extraction (default "id").

    Raises:
        RankingAssertionError: If expected IDs not in top N.

    Example:
        >>> results = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        >>> assert_top_n_contains(results, ["a", "b"], n=3)
    """
    top_n = results[:n]
    actual_ids = set()

    for result in top_n:
        if isinstance(result, dict):
            actual_ids.add(result.get(id_field))
        else:
            actual_ids.add(getattr(result, id_field, None))

    missing = set(expected_ids) - actual_ids
    if missing:
        raise RankingAssertionError(
            f"Expected IDs {missing} not found in top {n} results",
            actual=list(actual_ids),
            expected=list(expected_ids),
        )


def assert_top_n_exactly(
    results: Sequence[Any],
    expected_ids: Sequence[str | int],
    n: int = 5,
    id_field: str = "id",
) -> None:
    """Assert top N results contain exactly the expected IDs (order-independent).

    Args:
        results: Sequence of result objects.
        expected_ids: Exact IDs expected in top N.
        n: Number of top results to check.
        id_field: Field name for ID extraction.

    Raises:
        RankingAssertionError: If top N doesn't match expected IDs.

    Example:
        >>> results = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        >>> assert_top_n_exactly(results, ["a", "b", "c"], n=3)
    """
    top_n = results[:n]
    actual_ids = set()

    for result in top_n:
        if isinstance(result, dict):
            actual_ids.add(result.get(id_field))
        else:
            actual_ids.add(getattr(result, id_field, None))

    expected_set = set(expected_ids)
    if actual_ids != expected_set:
        missing = expected_set - actual_ids
        extra = actual_ids - expected_set
        msg = f"Top {n} results don't match expected IDs"
        if missing:
            msg += f", missing: {missing}"
        if extra:
            msg += f", extra: {extra}"
        raise RankingAssertionError(msg, actual=list(actual_ids), expected=list(expected_ids))


def assert_top_n_ordered(
    results: Sequence[Any],
    expected_order: Sequence[str | int],
    id_field: str = "id",
) -> None:
    """Assert top results appear in exact expected order.

    Args:
        results: Sequence of result objects.
        expected_order: IDs in exact expected order.
        id_field: Field name for ID extraction.

    Raises:
        RankingAssertionError: If order doesn't match.

    Example:
        >>> results = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        >>> assert_top_n_ordered(results, ["a", "b", "c"])
    """
    n = len(expected_order)
    top_n = results[:n]
    actual_ids = []

    for result in top_n:
        if isinstance(result, dict):
            actual_ids.append(result.get(id_field))
        else:
            actual_ids.append(getattr(result, id_field, None))

    if actual_ids != list(expected_order):
        raise RankingAssertionError(
            "Results order mismatch",
            actual=actual_ids,
            expected=list(expected_order),
        )


def assert_ordered_before(
    results: Sequence[Any],
    id_a: str | int,
    id_b: str | int,
    id_field: str = "id",
) -> None:
    """Assert id_a appears before id_b in results.

    Args:
        results: Sequence of result objects.
        id_a: ID that should appear first.
        id_b: ID that should appear second.
        id_field: Field name for ID extraction.

    Raises:
        RankingAssertionError: If id_a doesn't appear before id_b.

    Example:
        >>> results = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        >>> assert_ordered_before(results, "a", "b")
    """
    positions = {}

    for idx, result in enumerate(results):
        if isinstance(result, dict):
            result_id = result.get(id_field)
        else:
            result_id = getattr(result, id_field, None)

        if result_id not in positions:
            positions[result_id] = idx

    if id_a not in positions:
        raise RankingAssertionError(
            f"ID {id_a!r} not found in results",
            actual=list(positions.keys()),
            expected=id_a,
        )

    if id_b not in positions:
        raise RankingAssertionError(
            f"ID {id_b!r} not found in results",
            actual=list(positions.keys()),
            expected=id_b,
        )

    if positions[id_a] >= positions[id_b]:
        raise RankingAssertionError(
            f"ID {id_a!r} (position {positions[id_a]}) should appear before "
            f"{id_b!r} (position {positions[id_b]})",
            actual=f"{id_a} at {positions[id_a]}, {id_b} at {positions[id_b]}",
            expected=f"{id_a} before {id_b}",
        )


def assert_score_range(
    results: Sequence[Any],
    min_score: float,
    max_score: float,
    score_field: str = "score",
) -> None:
    """Assert all result scores are within range.

    Args:
        results: Sequence of result objects with scores.
        min_score: Minimum allowed score (inclusive).
        max_score: Maximum allowed score (inclusive).
        score_field: Field name for score extraction.

    Raises:
        RankingAssertionError: If any score is outside range.

    Example:
        >>> results = [{"id": "a", "score": 0.9}, {"id": "b", "score": 0.8}]
        >>> assert_score_range(results, 0.0, 1.0)
    """
    out_of_range = []

    for idx, result in enumerate(results):
        if isinstance(result, dict):
            score = result.get(score_field)
        else:
            score = getattr(result, score_field, None)

        if score is not None and not (min_score <= score <= max_score):
            out_of_range.append((idx, score))

    if out_of_range:
        violations = ", ".join(f"index {i}: {s}" for i, s in out_of_range[:5])
        if len(out_of_range) > 5:
            violations += f" ... and {len(out_of_range) - 5} more"
        raise RankingAssertionError(
            f"Scores outside range [{min_score}, {max_score}]: {violations}",
            actual=[s for _, s in out_of_range],
            expected=f"[{min_score}, {max_score}]",
        )


def assert_score_descending(
    results: Sequence[Any],
    score_field: str = "score",
) -> None:
    """Assert results are sorted by score in descending order.

    Args:
        results: Sequence of result objects with scores.
        score_field: Field name for score extraction.

    Raises:
        RankingAssertionError: If not sorted descending.

    Example:
        >>> results = [{"id": "a", "score": 0.9}, {"id": "b", "score": 0.7}]
        >>> assert_score_descending(results)
    """
    scores = []
    for result in results:
        if isinstance(result, dict):
            score = result.get(score_field)
        else:
            score = getattr(result, score_field, None)
        scores.append(score)

    for i in range(len(scores) - 1):
        if scores[i] is not None and scores[i + 1] is not None:
            if scores[i] < scores[i + 1]:
                raise RankingAssertionError(
                    f"Results not sorted descending: score at index {i} ({scores[i]}) "
                    f"< score at index {i + 1} ({scores[i + 1]})",
                    actual=scores,
                    expected="descending order",
                )


def assert_score_ascending(
    results: Sequence[Any],
    score_field: str = "score",
) -> None:
    """Assert results are sorted by score in ascending order.

    Args:
        results: Sequence of result objects with scores.
        score_field: Field name for score extraction.

    Raises:
        RankingAssertionError: If not sorted ascending.

    Example:
        >>> results = [{"id": "a", "score": 0.1}, {"id": "b", "score": 0.3}]
        >>> assert_score_ascending(results)
    """
    scores = []
    for result in results:
        if isinstance(result, dict):
            score = result.get(score_field)
        else:
            score = getattr(result, score_field, None)
        scores.append(score)

    for i in range(len(scores) - 1):
        if scores[i] is not None and scores[i + 1] is not None:
            if scores[i] > scores[i + 1]:
                raise RankingAssertionError(
                    f"Results not sorted ascending: score at index {i} ({scores[i]}) "
                    f"> score at index {i + 1} ({scores[i + 1]})",
                    actual=scores,
                    expected="ascending order",
                )


def assert_result_count(
    results: Sequence[Any],
    expected: int | tuple[int, int],
) -> None:
    """Assert result count matches expectation.

    Args:
        results: Sequence of results.
        expected: Exact count or (min, max) tuple for range.

    Raises:
        RankingAssertionError: If count doesn't match.

    Example:
        >>> results = [{"id": "a"}, {"id": "b"}]
        >>> assert_result_count(results, 2)
        >>> assert_result_count(results, (1, 10))
    """
    actual = len(results)

    if isinstance(expected, tuple):
        min_count, max_count = expected
        if not (min_count <= actual <= max_count):
            raise RankingAssertionError(
                f"Result count {actual} not in range [{min_count}, {max_count}]",
                actual=actual,
                expected=f"[{min_count}, {max_count}]",
            )
    else:
        if actual != expected:
            raise RankingAssertionError(
                f"Expected {expected} results, got {actual}",
                actual=actual,
                expected=expected,
            )


def assert_minimum_results(
    results: Sequence[Any],
    minimum: int,
) -> None:
    """Assert at least minimum number of results.

    Args:
        results: Sequence of results.
        minimum: Minimum required count.

    Raises:
        RankingAssertionError: If count is below minimum.

    Example:
        >>> results = [{"id": "a"}, {"id": "b"}]
        >>> assert_minimum_results(results, 2)
    """
    actual = len(results)
    if actual < minimum:
        raise RankingAssertionError(
            f"Expected at least {minimum} results, got {actual}",
            actual=actual,
            expected=f">= {minimum}",
        )


def assert_no_duplicates(
    results: Sequence[Any],
    id_field: str = "id",
) -> None:
    """Assert no duplicate IDs in results.

    Args:
        results: Sequence of results.
        id_field: Field name for ID extraction.

    Raises:
        RankingAssertionError: If duplicates found.

    Example:
        >>> results = [{"id": "a"}, {"id": "b"}]
        >>> assert_no_duplicates(results)
    """
    seen = set()
    duplicates = []

    for result in results:
        if isinstance(result, dict):
            result_id = result.get(id_field)
        else:
            result_id = getattr(result, id_field, None)

        if result_id in seen:
            duplicates.append(result_id)
        else:
            seen.add(result_id)

    if duplicates:
        raise RankingAssertionError(
            f"Duplicate IDs found: {duplicates[:5]}",
            actual=list(set(duplicates)),
            expected="no duplicates",
        )


def assert_all_have_field(
    results: Sequence[Any],
    field: str,
) -> None:
    """Assert all results have a specific field.

    Args:
        results: Sequence of results.
        field: Field name that must be present.

    Raises:
        RankingAssertionError: If any result missing field.

    Example:
        >>> results = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
        >>> assert_all_have_field(results, "name")
    """
    missing = []

    for idx, result in enumerate(results):
        if isinstance(result, dict):
            has_field = field in result
        else:
            has_field = hasattr(result, field)

        if not has_field:
            missing.append(idx)

    if missing:
        raise RankingAssertionError(
            f"Results at indices {missing[:5]} missing field {field!r}",
            actual=f"{len(missing)} results missing field",
            expected=f"all results have {field!r}",
        )


def assert_relevance_score_threshold(
    results: Sequence[Any],
    threshold: float,
    score_field: str = "score",
) -> None:
    """Assert all results meet minimum relevance threshold.

    Args:
        results: Sequence of results with relevance scores.
        threshold: Minimum required score.
        score_field: Field name for score extraction.

    Raises:
        RankingAssertionError: If any result below threshold.

    Example:
        >>> results = [{"id": "a", "score": 0.8}, {"id": "b", "score": 0.9}]
        >>> assert_relevance_score_threshold(results, 0.7)
    """
    below_threshold = []

    for idx, result in enumerate(results):
        if isinstance(result, dict):
            score = result.get(score_field)
        else:
            score = getattr(result, score_field, None)

        if score is not None and score < threshold:
            below_threshold.append((idx, score))

    if below_threshold:
        violations = ", ".join(f"index {i}: {s}" for i, s in below_threshold[:5])
        raise RankingAssertionError(
            f"Results below threshold {threshold}: {violations}",
            actual=[s for _, s in below_threshold],
            expected=f">= {threshold}",
        )
