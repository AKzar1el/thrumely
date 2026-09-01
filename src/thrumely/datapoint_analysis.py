from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .human_analysis import PairwiseObservation, RatingObservation


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class DatapointItemBinding:
    job_id: str
    datapoint_index: int
    task_id: str
    item_id: str

    def __post_init__(self) -> None:
        _text("job_id", self.job_id)
        _text("task_id", self.task_id)
        _text("item_id", self.item_id)
        if (
            not isinstance(self.datapoint_index, int)
            or isinstance(self.datapoint_index, bool)
            or self.datapoint_index < 0
        ):
            raise ValueError("datapoint_index must be a non-negative integer")


def _binding_index(
    bindings: Iterable[DatapointItemBinding],
) -> dict[tuple[str, int], DatapointItemBinding]:
    index: dict[tuple[str, int], DatapointItemBinding] = {}
    for binding in bindings:
        key = (binding.job_id, binding.datapoint_index)
        if key in index:
            raise ValueError(f"duplicate binding for job/datapoint {key!r}")
        index[key] = binding
    return index


def _row_binding(
    row: Mapping[str, object],
    bindings: Mapping[tuple[str, int], DatapointItemBinding],
    *,
    expected_task_type: str,
) -> tuple[DatapointItemBinding, str, object]:
    job_id = _text("job_id", row.get("job_id"))
    task_type = _text("job_task_type", row.get("job_task_type"))
    if task_type != expected_task_type:
        raise ValueError(
            f"Datapoint task type must be {expected_task_type!r}, found {task_type!r}"
        )
    datapoint_index = row.get("datapoint_index")
    if (
        not isinstance(datapoint_index, int)
        or isinstance(datapoint_index, bool)
        or datapoint_index < 0
    ):
        raise ValueError("datapoint_index must be a non-negative integer")
    binding = bindings.get((job_id, datapoint_index))
    if binding is None:
        raise ValueError(
            f"missing binding for Datapoint row {(job_id, datapoint_index)!r}"
        )
    annotator_id = _text("annotator_id", row.get("annotator_id"))
    return binding, annotator_id, row.get("response")


def rating_observations_from_datapoint(
    rows: Iterable[Mapping[str, object]],
    bindings: Iterable[DatapointItemBinding],
) -> tuple[RatingObservation, ...]:
    binding_map = _binding_index(bindings)
    observations: list[RatingObservation] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("Datapoint response row must be a mapping")
        binding, annotator_id, response = _row_binding(
            row,
            binding_map,
            expected_task_type="rating",
        )
        if not isinstance(response, str) or response not in {"1", "2", "3", "4", "5"}:
            raise ValueError("rating response must be one of the strings '1' through '5'")
        observations.append(
            RatingObservation(
                task_id=binding.task_id,
                item_id=binding.item_id,
                annotator_id=annotator_id,
                rating=int(response),
            )
        )
    return tuple(observations)


def pairwise_observations_from_datapoint(
    rows: Iterable[Mapping[str, object]],
    bindings: Iterable[DatapointItemBinding],
) -> tuple[PairwiseObservation, ...]:
    binding_map = _binding_index(bindings)
    observations: list[PairwiseObservation] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("Datapoint response row must be a mapping")
        binding, annotator_id, response = _row_binding(
            row,
            binding_map,
            expected_task_type="comparison",
        )
        if response not in {"A", "B"}:
            raise ValueError("pairwise response must be 'A' or 'B'")
        observations.append(
            PairwiseObservation(
                task_id=binding.task_id,
                item_id=binding.item_id,
                annotator_id=annotator_id,
                choice=response,
            )
        )
    return tuple(observations)
