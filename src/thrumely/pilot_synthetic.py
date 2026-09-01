from __future__ import annotations

import json
from dataclasses import asdict

from .budget import project_annotation_credits
from .human_analysis import (
    PairwiseObservation,
    RatingObservation,
    bootstrap_task_mean,
    summarize_pairwise,
    summarize_ratings,
)
from .pilot_power import estimate_task_difference_sd, simulate_power_from_task_sd


def run_synthetic_pilot() -> dict[str, object]:
    ratings = (
        RatingObservation("task-1", "rating-1", "a1", 3),
        RatingObservation("task-1", "rating-1", "a2", 4),
        RatingObservation("task-1", "rating-1", "a3", 5),
        RatingObservation("task-2", "rating-2", "a1", 2),
        RatingObservation("task-2", "rating-2", "a2", 3),
        RatingObservation("task-2", "rating-2", "a3", 4),
    )
    pairwise = (
        PairwiseObservation("task-1", "pair-1", "a1", "A"),
        PairwiseObservation("task-1", "pair-1", "a2", "A"),
        PairwiseObservation("task-1", "pair-1", "a3", "B"),
    )
    bootstrap = bootstrap_task_mean(
        {
            "task-1": (0.1, 0.3),
            "task-2": (-0.1, 0.2),
            "task-3": (0.2, 0.4),
        },
        replicates=1000,
        confidence=0.95,
        seed=20260901,
    )
    differences = (-0.9, -0.3, 0.2, 0.8, 1.1)
    estimate = estimate_task_difference_sd(differences)
    power = simulate_power_from_task_sd(
        differences,
        target_tasks=100,
        effect=0.2,
        simulations=1000,
        alpha=0.05,
        seed=20260901,
    )
    budget = project_annotation_credits(
        1000,
        5,
        available_credits=10000,
        min_reserve_fraction=0.20,
    )
    return {
        "mode": "SYNTHETIC_PILOT_ONLY",
        "network_calls": 0,
        "credits_spent": 0,
        "rating_summary": [asdict(row) for row in summarize_ratings(ratings)],
        "pairwise_summary": [asdict(row) for row in summarize_pairwise(pairwise)],
        "bootstrap": asdict(bootstrap),
        "task_difference_estimate": asdict(estimate),
        "power": asdict(power),
        "budget": asdict(budget),
    }


def main() -> int:
    print(json.dumps(run_synthetic_pilot(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
