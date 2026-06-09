"""Tests for the eval harness logic (no model needed)."""
from __future__ import annotations

from evals.run_eval import _percentile, load_questions, results_equivalent


def test_identical_results_equivalent() -> None:
    assert results_equivalent([(1, 2)], [(1, 2)])


def test_row_order_ignored() -> None:
    assert results_equivalent([(1,), (2,)], [(2,), (1,)])


def test_column_order_ignored() -> None:
    assert results_equivalent([("a", 1)], [(1, "a")])


def test_float_noise_tolerated() -> None:
    assert results_equivalent([(39.62,)], [(39.6200001,)])


def test_duplicates_are_significant() -> None:
    # Multiset, not set: returning a row twice is a real difference.
    assert not results_equivalent([(1,)], [(1,), (1,)])


def test_different_values_not_equivalent() -> None:
    assert not results_equivalent([(1,)], [(2,)])


def test_percentile_basic() -> None:
    assert _percentile([], 0.5) == 0.0
    assert _percentile([10.0], 0.5) == 10.0
    assert _percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5


def test_question_set_shape() -> None:
    questions = load_questions()
    assert len(questions) == 20
    tiers = {q["difficulty"] for q in questions}
    assert tiers == {"easy", "medium", "hard"}
    # ids are unique
    assert len({q["id"] for q in questions}) == 20
