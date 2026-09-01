import math

import pytest

from thrumely.human_analysis import (
    PairwiseObservation,
    RatingObservation,
    bootstrap_task_mean,
    summarize_pairwise,
    summarize_ratings,
)


def test_rating_and_pairwise_summaries():
    ratings = (
        RatingObservation("t1", "i1", "a1", 3),
        RatingObservation("t1", "i1", "a2", 4),
        RatingObservation("t1", "i1", "a3", 5),
    )
    rating = summarize_ratings(ratings)[0]
    assert (
        rating.task_id,
        rating.item_id,
        rating.responses,
        rating.mean,
        rating.median,
        rating.minimum,
        rating.maximum,
    ) == ("t1", "i1", 3, 4.0, 4, 3, 5)
    assert rating.distribution == (0, 0, 1, 1, 1)
    assert rating.sample_sd == pytest.approx(1.0)

    pairwise = (
        PairwiseObservation("t1", "p1", "a1", "A"),
        PairwiseObservation("t1", "p1", "a2", "A"),
        PairwiseObservation("t1", "p1", "a3", "B"),
    )
    comparison = summarize_pairwise(pairwise)[0]
    assert (
        comparison.votes_a,
        comparison.votes_b,
        comparison.majority,
        comparison.majority_fraction,
    ) == (2, 1, "A", pytest.approx(2 / 3))


def test_observations_validate_and_duplicate_raters_rejected():
    with pytest.raises(ValueError):
        RatingObservation("t", "i", "a", 6)
    with pytest.raises(ValueError):
        PairwiseObservation("t", "i", "a", "tie")
    duplicates = (
        RatingObservation("t", "i", "a", 4),
        RatingObservation("t", "i", "a", 5),
    )
    with pytest.raises(ValueError, match="duplicate"):
        summarize_ratings(duplicates)


def test_bootstrap_is_seeded_and_task_weighted():
    values = {"t1": (1.0, 1.0, 1.0, 1.0), "t2": (3.0,)}
    first = bootstrap_task_mean(values, replicates=1000, confidence=0.95, seed=7)
    second = bootstrap_task_mean(values, replicates=1000, confidence=0.95, seed=7)
    assert first == second
    assert first.observed_mean == pytest.approx(2.0)
    assert first.tasks == 2
    assert first.lower <= first.observed_mean <= first.upper
    with pytest.raises(ValueError):
        bootstrap_task_mean({}, seed=1)
    with pytest.raises(ValueError):
        bootstrap_task_mean({"t": (math.nan,)}, seed=1)


def test_same_item_and_annotator_ids_can_exist_under_different_tasks():
    rows = (
        RatingObservation("task-a", "shared-item", "worker-1", 4),
        RatingObservation("task-b", "shared-item", "worker-1", 5),
    )
    summaries = summarize_ratings(rows)
    assert [(row.task_id, row.item_id, row.mean) for row in summaries] == [
        ("task-a", "shared-item", 4.0),
        ("task-b", "shared-item", 5.0),
    ]


def test_bootstrap_rejects_boolean_values_and_boolean_seed():
    with pytest.raises((TypeError, ValueError), match="numeric"):
        bootstrap_task_mean({"t": (True, 1.0)}, seed=1)
    with pytest.raises((TypeError, ValueError), match="seed"):
        bootstrap_task_mean({"t": (1.0, 2.0)}, seed=True)
