from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from numbers import Real
from typing import Iterable

from .power import PowerSimulationConfig, PowerSimulationResult, simulate_power


@dataclass(frozen=True)
class TaskDifferenceEstimate:
    tasks: int
    mean_difference: float
    sample_sd: float


def estimate_task_difference_sd(
    differences: Iterable[float],
) -> TaskDifferenceEstimate:
    raw = tuple(differences)
    if not all(isinstance(value, Real) and not isinstance(value, bool) for value in raw):
        raise ValueError("task differences must be numeric and must not be booleans")
    values = tuple(float(value) for value in raw)
    if len(values) < 2:
        raise ValueError("at least two task differences are required")
    if not all(math.isfinite(value) for value in values):
        raise ValueError("task differences must be finite")
    sample_sd = statistics.stdev(values)
    if sample_sd <= 0:
        raise ValueError("observed task-difference standard deviation must be > 0")
    return TaskDifferenceEstimate(
        tasks=len(values),
        mean_difference=statistics.fmean(values),
        sample_sd=sample_sd,
    )


def simulate_power_from_task_sd(
    differences: Iterable[float],
    *,
    target_tasks: int,
    effect: float,
    simulations: int = 2000,
    alpha: float = 0.05,
    seed: int = 20260901,
) -> PowerSimulationResult:
    if (
        not isinstance(target_tasks, int)
        or isinstance(target_tasks, bool)
        or target_tasks < 2
    ):
        raise ValueError("target_tasks must be an integer >= 2")
    if (
        not isinstance(effect, Real)
        or isinstance(effect, bool)
        or not math.isfinite(float(effect))
    ):
        raise ValueError("effect must be a finite numeric value")
    if (
        not isinstance(simulations, int)
        or isinstance(simulations, bool)
        or simulations < 1
    ):
        raise ValueError("simulations must be an integer >= 1")
    if (
        not isinstance(alpha, Real)
        or isinstance(alpha, bool)
        or not 0 < float(alpha) < 1
    ):
        raise ValueError("alpha must be a numeric value between 0 and 1")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an integer")

    estimate = estimate_task_difference_sd(differences)
    return simulate_power(
        PowerSimulationConfig(
            tasks=target_tasks,
            effect=float(effect),
            between_task_sd=estimate.sample_sd,
            within_task_sd=0.0,
            simulations=simulations,
            alpha=float(alpha),
            seed=seed,
        )
    )
