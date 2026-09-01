from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass
from numbers import Real
from typing import Iterable, Mapping, Sequence, TypeVar


def _text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


@dataclass(frozen=True)
class RatingObservation:
    task_id: str
    item_id: str
    annotator_id: str
    rating: int

    def __post_init__(self) -> None:
        _text("task_id", self.task_id)
        _text("item_id", self.item_id)
        _text("annotator_id", self.annotator_id)
        if (
            not isinstance(self.rating, int)
            or isinstance(self.rating, bool)
            or not 1 <= self.rating <= 5
        ):
            raise ValueError("rating must be an integer in [1, 5]")


@dataclass(frozen=True)
class PairwiseObservation:
    task_id: str
    item_id: str
    annotator_id: str
    choice: str

    def __post_init__(self) -> None:
        _text("task_id", self.task_id)
        _text("item_id", self.item_id)
        _text("annotator_id", self.annotator_id)
        if self.choice not in {"A", "B"}:
            raise ValueError("choice must be 'A' or 'B'")


@dataclass(frozen=True)
class RatingSummary:
    task_id: str
    item_id: str
    responses: int
    mean: float
    median: float
    sample_sd: float | None
    minimum: int
    maximum: int
    distribution: tuple[int, int, int, int, int]


@dataclass(frozen=True)
class PairwiseSummary:
    task_id: str
    item_id: str
    responses: int
    votes_a: int
    votes_b: int
    majority: str | None
    majority_fraction: float


@dataclass(frozen=True)
class BootstrapResult:
    observed_mean: float
    lower: float
    upper: float
    confidence: float
    tasks: int
    replicates: int
    seed: int


_Observation = TypeVar("_Observation", RatingObservation, PairwiseObservation)


def _group_unique(
    observations: Iterable[_Observation], *, kind: str
) -> dict[tuple[str, str], list[_Observation]]:
    groups: dict[tuple[str, str], list[_Observation]] = {}
    seen: set[tuple[str, str, str]] = set()
    for observation in observations:
        identity = (
            observation.task_id,
            observation.item_id,
            observation.annotator_id,
        )
        if identity in seen:
            raise ValueError(
                f"duplicate {kind} observation for task/item/annotator {identity!r}"
            )
        seen.add(identity)
        groups.setdefault((observation.task_id, observation.item_id), []).append(
            observation
        )
    if not groups:
        raise ValueError(f"{kind} observations must not be empty")
    return groups


def summarize_ratings(
    observations: Iterable[RatingObservation],
) -> tuple[RatingSummary, ...]:
    groups = _group_unique(observations, kind="rating")
    output: list[RatingSummary] = []
    for (task_id, item_id), rows in sorted(groups.items()):
        ratings = [row.rating for row in rows]
        distribution = tuple(ratings.count(value) for value in range(1, 6))
        output.append(
            RatingSummary(
                task_id=task_id,
                item_id=item_id,
                responses=len(ratings),
                mean=statistics.fmean(ratings),
                median=statistics.median(ratings),
                sample_sd=statistics.stdev(ratings) if len(ratings) >= 2 else None,
                minimum=min(ratings),
                maximum=max(ratings),
                distribution=distribution,
            )
        )
    return tuple(output)


def summarize_pairwise(
    observations: Iterable[PairwiseObservation],
) -> tuple[PairwiseSummary, ...]:
    groups = _group_unique(observations, kind="pairwise")
    output: list[PairwiseSummary] = []
    for (task_id, item_id), rows in sorted(groups.items()):
        votes_a = sum(row.choice == "A" for row in rows)
        votes_b = len(rows) - votes_a
        responses = len(rows)
        majority = "A" if votes_a > votes_b else "B" if votes_b > votes_a else None
        output.append(
            PairwiseSummary(
                task_id=task_id,
                item_id=item_id,
                responses=responses,
                votes_a=votes_a,
                votes_b=votes_b,
                majority=majority,
                majority_fraction=max(votes_a, votes_b) / responses,
            )
        )
    return tuple(output)


def _percentile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    return ordered[lower_index] + (
        ordered[upper_index] - ordered[lower_index]
    ) * (position - lower_index)


def bootstrap_task_mean(
    task_values: Mapping[str, Sequence[float]],
    *,
    replicates: int = 5000,
    confidence: float = 0.95,
    seed: int,
) -> BootstrapResult:
    if not task_values:
        raise ValueError("task_values must not be empty")
    if (
        not isinstance(replicates, int)
        or isinstance(replicates, bool)
        or replicates < 1
    ):
        raise ValueError("replicates must be >= 1")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an integer")

    task_means: list[float] = []
    for task_id, values in task_values.items():
        _text("task_id", task_id)
        if not values:
            raise ValueError(f"task {task_id!r} has no values")
        if not all(isinstance(value, Real) and not isinstance(value, bool) for value in values):
            raise ValueError("task values must be numeric and must not be booleans")
        numeric = [float(value) for value in values]
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("task values must be finite")
        task_means.append(statistics.fmean(numeric))

    observed_mean = statistics.fmean(task_means)
    rng = random.Random(seed)
    task_count = len(task_means)
    bootstrap_means = [
        statistics.fmean(
            task_means[rng.randrange(task_count)] for _ in range(task_count)
        )
        for _ in range(replicates)
    ]
    tail = (1 - confidence) / 2
    return BootstrapResult(
        observed_mean=observed_mean,
        lower=_percentile(bootstrap_means, tail),
        upper=_percentile(bootstrap_means, 1 - tail),
        confidence=confidence,
        tasks=task_count,
        replicates=replicates,
        seed=seed,
    )
