import pytest

from thrumely.datapoint_analysis import (
    DatapointItemBinding,
    pairwise_observations_from_datapoint,
    rating_observations_from_datapoint,
)


def test_rating_rows_convert_to_typed_observations():
    bindings = (DatapointItemBinding("job_rate", 0, "task-1", "rating-1"),)
    rows = (
        {
            "job_id": "job_rate",
            "job_task_type": "rating",
            "datapoint_index": 0,
            "annotator_id": "anon_0000000001",
            "response": "4",
        },
    )
    observations = rating_observations_from_datapoint(rows, bindings)
    assert len(observations) == 1
    observation = observations[0]
    assert (
        observation.task_id,
        observation.item_id,
        observation.annotator_id,
        observation.rating,
    ) == ("task-1", "rating-1", "anon_0000000001", 4)


def test_pairwise_rows_convert_to_typed_observations():
    bindings = (DatapointItemBinding("job_cmp", 3, "task-7", "pair-3"),)
    rows = (
        {
            "job_id": "job_cmp",
            "job_task_type": "comparison",
            "datapoint_index": 3,
            "annotator_id": "anon_0000000002",
            "response": "B",
        },
    )
    observations = pairwise_observations_from_datapoint(rows, bindings)
    assert observations[0].choice == "B"
    assert observations[0].task_id == "task-7"


def test_adapter_rejects_missing_binding_wrong_type_and_invalid_response():
    binding = (DatapointItemBinding("job_rate", 0, "task-1", "rating-1"),)
    with pytest.raises(ValueError, match="binding"):
        rating_observations_from_datapoint(
            (
                {
                    "job_id": "job_rate",
                    "job_task_type": "rating",
                    "datapoint_index": 1,
                    "annotator_id": "a",
                    "response": "4",
                },
            ),
            binding,
        )
    with pytest.raises(ValueError, match="task type"):
        rating_observations_from_datapoint(
            (
                {
                    "job_id": "job_rate",
                    "job_task_type": "comparison",
                    "datapoint_index": 0,
                    "annotator_id": "a",
                    "response": "4",
                },
            ),
            binding,
        )
    with pytest.raises(ValueError, match="rating response"):
        rating_observations_from_datapoint(
            (
                {
                    "job_id": "job_rate",
                    "job_task_type": "rating",
                    "datapoint_index": 0,
                    "annotator_id": "a",
                    "response": "4.0",
                },
            ),
            binding,
        )


def test_binding_identity_must_be_unique():
    bindings = (
        DatapointItemBinding("job_rate", 0, "task-1", "rating-1"),
        DatapointItemBinding("job_rate", 0, "task-2", "rating-2"),
    )
    with pytest.raises(ValueError, match="duplicate binding"):
        rating_observations_from_datapoint((), bindings)
