# Experiment Matrix and Annotation Manifests Design

## Status

Approved pre-production design for zero-cost experiment planning and annotation-manifest compilation. This slice does not freeze the v1 task corpus, provider/model identities, or production annotations.

## Goal

Compile the predeclared Thrumely v1 factorial structure into deterministic, auditable experiment cells and derive provider-neutral rating/pairwise annotation manifests from completed trajectories.

The compiler must make configuration drift and missing provenance obvious before any production Datapoint job can be created.

## Scientific boundary

This is planning/provenance infrastructure only.

- The primary endpoint remains human 1–5 instruction faithfulness.
- Pairwise human preference remains secondary.
- The planned structure remains two controllers, three fixed-backend environments, one chooser environment, and two stochastic replications.
- Exact controller IDs, provider/model IDs, backend IDs, and the final 100 task IDs remain unfrozen.
- Candidate tasks are not promoted into the v1 production corpus by this feature.
- No provider calls, Datapoint jobs, or credit spend occur.
- Failed production trajectories remain research data. This first manifest compiler fails closed when a planned cell cannot supply a successful final artifact rather than silently dropping or rerunning it; an explicit production exclusion policy can be added later if the frozen protocol requires one.

## Existing contracts reused

- `thrumely.schema.TaskSpec`, `ControllerConfig`, `ToolEnvironment`, and `TrajectoryRecord` remain the source research entities.
- `thrumely.hashing.content_hash` remains the project canonical SHA-256 mechanism.
- `thrumely.serialization.canonical_json_bytes` remains the project canonical JSON representation.
- `thrumely.datapoint_protocol` remains responsible for Datapoint transport payloads. The new annotation manifests do not contain `dp://` URLs.

No new serialization standard or dependency is introduced in this slice.

## Experiment plan contract

`src/thrumely/experiment_plan.py` defines immutable planning records.

### `ExperimentCell`

Fields:

- `cell_id`
- `task_id`
- `task_spec_sha256`
- `controller_id`
- `controller_config_sha256`
- `environment_id`
- `environment_config_sha256`
- `replication`
- `environment_mode`
- `available_backends`
- `media_call_budget`

A cell ID is the full SHA-256 content hash of the scientific identity tuple, prefixed with `cell-`. The hash input excludes runtime timestamps and provider responses but includes content digests for the task specification, controller configuration, and normalized environment configuration. Consequently, changing an instruction, model/configuration field, or environment semantics under the same human-readable ID cannot masquerade as the same scientific cell.

Environment backend ordering is normalized before hashing because backend membership is a set-like scientific property in this contract.

### `ExperimentPlan`

Fields:

- `plan_id`
- `plan_sha256`
- `data_classification`
- `task_ids`
- `task_spec_sha256s`
- `controller_ids`
- `controller_config_sha256s`
- `environment_ids`
- `environment_config_sha256s`
- `replications`
- `cells`

The plan compiler sorts all identity inputs before expansion, rejects duplicate IDs, and produces the same cells/hash regardless of caller input order. The configuration-digest tables make the plan hash auditable without silently treating a reused ID as an unchanged configuration.

### Structural invariants

The v1 planning compiler requires:

1. exactly two distinct controllers;
2. exactly four environments;
3. exactly three `fixed` environments and one `chooser` environment;
4. each fixed environment exposes exactly one distinct backend;
5. the chooser exposes exactly the set of the three fixed backends;
6. every environment has `media_call_budget == 2`;
7. replication count is a positive integer, with the approved v1 default of 2;
8. at least one task;
9. all task IDs are unique.

The compiler remains agnostic to which exact provider/model/backend names are supplied. It does not freeze those choices by policy; it merely makes any supplied configuration content-addressed and therefore auditable.

For `T` tasks and `R` replications, cell count is:

`T * 2 controllers * 4 environments * R`.

The future frozen v1 case therefore validates to `100 * 2 * 4 * 2 = 1600` cells.

## Annotation manifest contract

`src/thrumely/annotation_manifest.py` compiles successful completed trajectories against an `ExperimentPlan` and task instructions.

The compiler requires exactly one trajectory for every planned cell, and verifies that each trajectory's `(task_id, controller_id, environment_id, replication)` matches the cell identity.

It also requires:

- trajectory completion status `success`;
- a non-empty `final_artifact_id`;
- no duplicate trajectory IDs;
- no extra trajectories outside the plan;
- an instruction for every task ID.

This fail-closed behavior prevents silent annotation undercounting or row-order joins.

### Rating item

One item per experiment cell:

- `annotation_item_id`
- `task_id`
- `instruction`
- `trajectory_id`
- `artifact_id`
- `controller_id`
- `environment_id`
- `replication`

For a complete future v1 matrix this yields 1600 rating items.

### Pairwise item

Fields:

- `annotation_item_id`
- `pair_kind`
- `task_id`
- `instruction`
- `trajectory_a_id`
- `artifact_a_id`
- `controller_a_id`
- `environment_a_id`
- `trajectory_b_id`
- `artifact_b_id`
- `controller_b_id`
- `environment_b_id`
- `replication`

Pair identities are deterministic content hashes and never depend on list row numbers.

Two predeclared pair families are compiled:

1. **chooser vs fixed** — for each task, controller, replication, compare the chooser output with each of the three fixed-backend outputs;
2. **cross-controller chooser** — for each task and replication, compare chooser output from controller 1 against chooser output from controller 2.

With `T` tasks and `R` replications:

- chooser-vs-fixed pairs = `T * 2 * 3 * R`;
- cross-controller chooser pairs = `T * R`;
- total pairwise items = `T * R * 7`.

The future frozen v1 case therefore yields `100 * 2 * 7 = 1400` pairwise items.

Candidate A/B identity remains deterministic in the manifest. Datapoint's comparison UI randomizes annotator display order, while API results preserve mapping to the submitted candidates, so transport randomization does not become part of scientific identity.

## Manifest bundle

`AnnotationManifestBundle` contains:

- `plan_sha256`
- `ratings`
- `pairwise`
- `rating_count`
- `pairwise_count`
- `manifest_sha256`

The bundle hash is computed from the plan hash and full manifest content, excluding the bundle's own hash.

## Synthetic preflight CLI

`src/thrumely/experiment_synthetic.py` creates only in-memory synthetic IDs and synthetic successful trajectory records.

It compiles:

- a small deterministic matrix for readable CI output;
- rating and pairwise manifests;
- expected counts;
- plan and manifest hashes.

Output includes:

- `mode: SYNTHETIC_EXPERIMENT_PLAN_ONLY`;
- `network_calls: 0`;
- `hosted_calls: 0`;
- `datapoint_jobs: 0`;
- `credits_spent: 0`.

The CLI must not read `candidates/tasks-v0.1.jsonl` and must not label any plan as frozen or production.

## Test gates

Tests cover at least:

- input-order-independent plan/hash;
- task/controller configuration drift changes plan and affected cell identity;
- duplicate task/controller/environment rejection;
- exact two-controller / three-fixed-plus-chooser structure;
- chooser backend set equals fixed backend set;
- media call budget exactly 2;
- 100-task v1 arithmetic produces 1600 cells;
- complete trajectory-to-cell join does not rely on row order;
- missing, duplicate, failed, or extra trajectories fail closed;
- rating count equals cell count;
- 100-task v1 manifest arithmetic produces 1600 ratings and 1400 pairwise items;
- pairwise families contain 1200 chooser-vs-fixed and 200 cross-controller chooser items in the future 100-task/2-rep case;
- deterministic plan and manifest hashes;
- synthetic CLI reports zero network/hosted/Datapoint activity.

Normal CI adds `python -m thrumely.experiment_synthetic` while retaining every existing gate.

## Explicit non-goals

- no final 100-task freeze;
- no provider/model freeze;
- no hosted generation;
- no Datapoint media upload or job creation;
- no production exclusion/adjudication policy;
- no analysis of human responses;
- no automatic scoring changes;
- no leaderboard or public benchmark result claim.
