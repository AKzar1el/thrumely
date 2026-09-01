# Experiment Matrix and Annotation Manifests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic v1 experiment-cell planning and provider-neutral human-annotation manifests without freezing tasks/providers or spending credits.

**Architecture:** Reuse Thrumely's existing schema and canonical `content_hash` contract. Compile a strict scientific matrix first, then join completed trajectories to that matrix by explicit identity keys and derive rating/pairwise manifests. Add a synthetic zero-network CLI and CI gate.

**Tech Stack:** Python 3.11+, stdlib dataclasses, existing `thrumely.schema`, `thrumely.hashing`, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-01-experiment-matrix-manifests-design.md`

## Global Constraints

- Exactly two controller IDs per experiment plan.
- Exactly three fixed environments plus one chooser environment.
- Chooser backend set must equal the three distinct fixed backend IDs.
- Every environment must have `media_call_budget == 2`.
- Default replications = 2; arbitrary positive replication count remains supported for planning tests.
- Exact task/controller/provider/backend names remain unfrozen.
- No candidate-corpus promotion, provider calls, Datapoint jobs, or credit spend.
- All new production behavior follows TDD: failing test first, then minimal implementation.

---

### Task 1: Deterministic experiment plan compiler

**Files:**
- Create: `src/thrumely/experiment_plan.py`
- Test: `tests/test_experiment_plan.py`

**Interfaces:**
- Consumes: `TaskSpec`, `ControllerConfig`, `ToolEnvironment`.
- Produces: `ExperimentCell`, `ExperimentPlan`, `compile_experiment_plan(...)`.

- [ ] **Step 1: Write failing tests**

Cover:

```python
plan = compile_experiment_plan(tasks, controllers, environments)
assert len(plan.cells) == len(tasks) * 2 * 4 * 2
assert plan.plan_sha256 == compile_experiment_plan(reversed_tasks, reversed_controllers, reversed_environments).plan_sha256
```

Also assert rejection of duplicate IDs, wrong controller count, wrong fixed/chooser structure, chooser/backend mismatch, and any environment whose media-call budget is not 2.

- [ ] **Step 2: Run the focused test module and verify RED**

Run:

```bash
PYTHONPATH=src python -m pytest -q tests/test_experiment_plan.py
```

Expected: import/module failure because `thrumely.experiment_plan` does not exist.

- [ ] **Step 3: Implement minimal compiler**

Create immutable dataclasses:

```python
@dataclass(frozen=True)
class ExperimentCell:
    cell_id: str
    task_id: str
    controller_id: str
    environment_id: str
    replication: int
    environment_mode: str
    available_backends: tuple[str, ...]
    media_call_budget: int

@dataclass(frozen=True)
class ExperimentPlan:
    plan_id: str
    plan_sha256: str
    data_classification: str
    task_ids: tuple[str, ...]
    controller_ids: tuple[str, ...]
    environment_ids: tuple[str, ...]
    replications: int
    cells: tuple[ExperimentCell, ...]
```

`compile_experiment_plan(...)` sorts identity inputs, expands the Cartesian product, derives full-hash `cell-*` IDs, and derives plan hash from the full plan payload excluding `plan_id`/`plan_sha256`.

- [ ] **Step 4: Run focused tests and verify GREEN**

- [ ] **Step 5: Add 100-task arithmetic regression**

Assert exactly `1600` cells for 100 synthetic task IDs, 2 controllers, 4 environments, 2 replications.

- [ ] **Step 6: Run focused tests again**

---

### Task 2: Rating and pairwise annotation manifest compiler

**Files:**
- Create: `src/thrumely/annotation_manifest.py`
- Test: `tests/test_annotation_manifest.py`

**Interfaces:**
- Consumes: `ExperimentPlan`, task instruction mapping, `TrajectoryRecord` rows.
- Produces: `RatingAnnotationItem`, `PairwiseAnnotationItem`, `AnnotationManifestBundle`, `compile_annotation_manifests(...)`.

- [ ] **Step 1: Write failing happy-path tests**

Construct a small 2-task complete synthetic plan and successful trajectories in deliberately shuffled order. Assert rating items join to cells by `(task_id, controller_id, environment_id, replication)`, not row position.

- [ ] **Step 2: Run and verify RED**

```bash
PYTHONPATH=src python -m pytest -q tests/test_annotation_manifest.py
```

- [ ] **Step 3: Implement strict trajectory join**

Build a unique identity-key mapping for all trajectories and reject:

```text
missing planned cell
extra trajectory outside plan
duplicate scientific cell
duplicate trajectory_id
non-success completion
missing final_artifact_id
missing task instruction
```

- [ ] **Step 4: Implement rating items**

Produce exactly one rating item per cell with deterministic full-hash annotation ID.

- [ ] **Step 5: Implement pairwise items**

For each task/controller/replication, emit chooser-vs-each-fixed pairs. For each task/replication, emit one cross-controller chooser pair. Candidate identity ordering must be deterministic.

- [ ] **Step 6: Implement bundle hash and counts**

`manifest_sha256` hashes the plan SHA and manifest rows excluding the field itself.

- [ ] **Step 7: Run focused tests and verify GREEN**

- [ ] **Step 8: Add future v1 arithmetic regression**

For 100 synthetic task IDs assert:

```python
assert bundle.rating_count == 1600
assert bundle.pairwise_count == 1400
assert chooser_vs_fixed_count == 1200
assert cross_controller_chooser_count == 200
```

---

### Task 3: Synthetic preflight, docs, and CI

**Files:**
- Create: `src/thrumely/experiment_synthetic.py`
- Test: `tests/test_experiment_synthetic.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 1/2 APIs only.
- Produces: a deterministic zero-network JSON preflight report.

- [ ] **Step 1: Write failing CLI test**

Call `build_synthetic_report()` and assert:

```python
assert report["mode"] == "SYNTHETIC_EXPERIMENT_PLAN_ONLY"
assert report["network_calls"] == 0
assert report["hosted_calls"] == 0
assert report["datapoint_jobs"] == 0
assert report["credits_spent"] == 0
```

Also assert counts equal formulas for the small fixture and hashes are stable across repeated calls.

- [ ] **Step 2: Run and verify RED**

- [ ] **Step 3: Implement the synthetic fixture/CLI**

Use only in-memory task/controller/backend IDs. Create synthetic successful `TrajectoryRecord` rows with placeholder artifact IDs. Do not read candidate or calibration files.

- [ ] **Step 4: Run focused tests and verify GREEN**

- [ ] **Step 5: Add CI command**

Append:

```yaml
- run: python -m thrumely.experiment_synthetic
```

without removing any existing gate.

- [ ] **Step 6: Update README**

Document the experiment compiler as pre-production planning infrastructure, state the 1600/1400 future v1 arithmetic, and explicitly state that synthetic output is not a frozen corpus/run or human annotation result.

- [ ] **Step 7: Run full suite**

```bash
python -m pytest -q
python -m thrumely.datapoint_sandbox --offline
python -m thrumely.pilot_synthetic
python -m thrumely.experiment_synthetic
python -m thrumely.validate_candidates candidates/tasks-v0.1.jsonl
python -m thrumely.power --tasks 100 --effect 0.20 --simulations 2000 --seed 20260901
python -m thrumely.validate_normalization
python -m thrumely.offline --output .ci-offline
```

Expected: all commands exit 0; all synthetic commands report no network/credit spend.

---

## Self-review checklist

- Spec coverage: all approved matrix, count, provenance, pair-family, zero-cost, and CI requirements map to Tasks 1–3.
- Placeholder scan: no implementation placeholders remain.
- Type consistency: Task 2 consumes Task 1's exact `ExperimentPlan`; Task 3 consumes Tasks 1/2 only.
- Scope: no provider execution, Datapoint transport, corpus freeze, statistical analysis, or exclusion-policy work is included.
