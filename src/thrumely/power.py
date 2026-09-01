from __future__ import annotations

import argparse
import math
import random
import statistics
from dataclasses import dataclass
from statistics import NormalDist


@dataclass(frozen=True)
class PowerSimulationConfig:
    tasks: int
    effect: float
    between_task_sd: float = 0.6
    within_task_sd: float = 0.8
    simulations: int = 2000
    alpha: float = 0.05
    seed: int = 20260901

    def __post_init__(self) -> None:
        if self.tasks < 2:
            raise ValueError("tasks must be >= 2")
        if self.between_task_sd < 0 or self.within_task_sd < 0:
            raise ValueError("standard deviations must be >= 0")
        if self.between_task_sd == 0 and self.within_task_sd == 0:
            raise ValueError("at least one standard deviation must be > 0")
        if self.simulations < 1:
            raise ValueError("simulations must be >= 1")
        if not 0 < self.alpha < 1:
            raise ValueError("alpha must be between 0 and 1")


@dataclass(frozen=True)
class PowerSimulationResult:
    estimated_power: float
    mean_simulated_effect: float
    mean_standard_error: float
    simulations: int
    tasks: int
    alpha: float
    seed: int


def simulate_power(config: PowerSimulationConfig) -> PowerSimulationResult:
    rng = random.Random(config.seed)
    threshold = NormalDist().inv_cdf(1 - config.alpha / 2)
    rejected = 0
    means: list[float] = []
    standard_errors: list[float] = []

    for _ in range(config.simulations):
        differences = [
            config.effect
            + rng.gauss(0.0, config.between_task_sd)
            + rng.gauss(0.0, config.within_task_sd)
            for _ in range(config.tasks)
        ]
        mean_difference = statistics.fmean(differences)
        se = statistics.stdev(differences) / math.sqrt(config.tasks)
        means.append(mean_difference)
        standard_errors.append(se)
        if se == 0:
            reject = mean_difference != 0
        else:
            reject = abs(mean_difference / se) > threshold
        rejected += int(reject)

    return PowerSimulationResult(
        estimated_power=rejected / config.simulations,
        mean_simulated_effect=statistics.fmean(means),
        mean_standard_error=statistics.fmean(standard_errors),
        simulations=config.simulations,
        tasks=config.tasks,
        alpha=config.alpha,
        seed=config.seed,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic task-level planning power simulation for Thrumely.")
    parser.add_argument("--tasks", type=int, default=100)
    parser.add_argument("--effect", type=float, required=True)
    parser.add_argument("--between-task-sd", type=float, default=0.6)
    parser.add_argument("--within-task-sd", type=float, default=0.8)
    parser.add_argument("--simulations", type=int, default=2000)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=20260901)
    args = parser.parse_args(argv)
    config = PowerSimulationConfig(
        tasks=args.tasks,
        effect=args.effect,
        between_task_sd=args.between_task_sd,
        within_task_sd=args.within_task_sd,
        simulations=args.simulations,
        alpha=args.alpha,
        seed=args.seed,
    )
    result = simulate_power(config)
    print("Synthetic planning simulation only; not final confirmatory analysis.")
    print(f"Tasks: {result.tasks}")
    print(f"Simulations: {result.simulations}")
    print(f"Estimated power: {result.estimated_power:.4f}")
    print(f"Mean simulated effect: {result.mean_simulated_effect:.4f}")
    print(f"Mean standard error: {result.mean_standard_error:.4f}")
    print(f"Alpha: {result.alpha:.4f}")
    print(f"Seed: {result.seed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
