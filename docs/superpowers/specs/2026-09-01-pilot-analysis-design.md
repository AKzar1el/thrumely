# Pilot Analysis Scaffolding Design

## Status

Pre-pilot, zero-cost analysis infrastructure. This design prepares the Week 7/8 measurement-analysis path without claiming that a Datapoint sandbox or paid pilot has run.

## Goal

Provide a dependency-free, deterministic toolkit that can ingest later human-response exports and answer four predeclared planning questions:

1. What do per-item rating and forced-choice response distributions look like?
2. What uncertainty do we get when resampling at the **task** level rather than treating ratings as independent observations?
3. What task-level contrast variance should replace the current synthetic power placeholders after the methodology pilot?
4. Would a proposed annotation batch violate the approximately 20% grant-reserve rule at the observed Datapoint credit rate?

## Scientific boundary

This module is **planning and measurement infrastructure**, not the frozen confirmatory analysis.

- Human 1–5 instruction-faithfulness remains the primary endpoint.
- Pairwise A/B preference remains secondary.
- No production condition results exist or are inspected by this work.
- No final 100-task corpus is selected or frozen.
- No significance-testing/stopping rule is added.
- No automatic metric is promoted to primary.
- The task-cluster bootstrap implementation is a candidate primary uncertainty primitive because the research spec already requires task-cluster resampling or an equivalently justified clustered method.
- More complex ordinal mixed models and formal ordinal reliability statistics remain optional later analyses; they should not be implemented merely to make the toolkit look sophisticated before pilot data exists.

## Data contracts

`src/thrumely/human_analysis.py` defines immutable records:

- `RatingObservation(task_id, item_id, annotator_id, rating)` where rating is integer 1–5.
- `PairwiseObservation(task_id, item_id, annotator_id, choice)` where choice is `A` or `B`.

The module does not require Datapoint-specific field names. A thin adapter can convert normalized Datapoint rows later.

## Per-item summaries

Rating summary fields:

- task ID;
- item ID;
- number of responses;
- arithmetic mean;
- median;
- sample standard deviation (`None` for n < 2);
- minimum and maximum;
- exact rating distribution for 1–5.

Pairwise summary fields:

- task ID;
- item ID;
- number of responses;
- A votes;
- B votes;
- majority choice (`A`, `B`, or `None` when exactly tied);
- majority fraction / simple agreement rate.

These are descriptive measurement checks. They do not define exclusions or alter the response-count policy.

## Task-cluster bootstrap

`bootstrap_task_mean(...)` consumes a mapping of `task_id -> sequence[float]`.

Algorithm:

1. Compute one mean value per task.
2. Resample task IDs with replacement, preserving all observations belonging to a sampled task as a cluster.
3. For each replicate, compute the mean of the sampled task means.
4. Report the observed task-weighted mean and percentile confidence interval.
5. Use a required explicit seed for deterministic reproducibility.

Each task receives equal weight in this planning primitive. Annotator-level rows are never resampled as if independent tasks.

## Pilot-derived power input

`estimate_task_difference_sd(...)` consumes paired task-level contrast values, such as chooser mean minus equal-weight fixed-backend mean for each pilot task.

It returns:

- number of tasks;
- observed mean difference;
- sample standard deviation across task differences.

`simulate_power_from_task_sd(...)` then reuses `thrumely.power.PowerSimulationConfig` with:

- `between_task_sd = observed task-difference SD`;
- `within_task_sd = 0` because the observed task-difference SD already reflects the task-level aggregated contrast used by this planning route.

This is still prospective planning, not achieved power and not a post-hoc proof that the study was adequately powered.

## Credit planning

`src/thrumely/budget.py` works entirely in **Datapoint raw credits**, not dollars.

Inputs:

- planned response count;
- observed/quoted `credits_per_response` from a Datapoint job;
- current available credit balance when known;
- minimum reserve fraction, default 0.20.

Outputs:

- projected credits required;
- projected remaining credits;
- projected remaining fraction;
- whether the batch passes the reserve gate.

No assumption is made about the monetary conversion of Datapoint credits. If balance is unknown, the projection can report required credits but cannot declare the reserve gate passed.

## Synthetic pilot fixture

`src/thrumely/pilot_synthetic.py` generates a tiny deterministic in-memory fixture and prints:

- `SYNTHETIC_PILOT_ONLY`;
- rating summary;
- pairwise summary;
- task-cluster bootstrap example;
- pilot-derived power example;
- raw-credit reserve projection.

It performs no network calls, reads no credentials, and must never be described as a completed pilot.

## CI gate

Normal CI adds:

```bash
python -m thrumely.pilot_synthetic
```

The existing Datapoint offline smoke and all prior scientific gates remain in CI.

## Explicit non-goals

- no real Datapoint responses;
- no real worker-reliability estimate;
- no Krippendorff alpha or ordinal mixed model yet;
- no human/automatic correlation yet because no paired human/automatic pilot dataset exists;
- no production analysis freeze;
- no Datapoint credit spend;
- no hosted inference.
