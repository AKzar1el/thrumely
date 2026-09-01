# Pilot Analysis Scaffolding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic zero-cost human-response summaries, task-cluster bootstrap, pilot-derived power inputs, credit-reserve projection, and a synthetic pilot smoke.

**Architecture:** Keep human-analysis records independent of Datapoint transport details. Use the standard library only. Reuse the existing power simulator only after reducing future pilot data to task-level contrast variance; treat all outputs as prospective planning until the analysis plan is frozen.

**Tech Stack:** Python 3.11 standard library, pytest, existing `thrumely.power`.

**Spec:** `docs/superpowers/specs/2026-09-01-pilot-analysis-design.md`

## Global Constraints

- No hosted inference.
- No real Datapoint jobs or credit spend.
- No final 100-task freeze.
- No achieved-power claim.
- No annotator row may be treated as an independent task in the cluster bootstrap.
- Budget math remains in raw Datapoint credits with no assumed USD conversion.
- Primary endpoint and primary contrast remain unchanged.

---

### Task 1: Human observation records and item summaries

**Files:**
- Create: `src/thrumely/human_analysis.py`
- Create: `tests/test_human_analysis.py`

**Interfaces:**
- `RatingObservation(task_id, item_id, annotator_id, rating)`
- `PairwiseObservation(task_id, item_id, annotator_id, choice)`
- `summarize_ratings(observations)`
- `summarize_pairwise(observations)`

- [ ] Write failing validation/summary tests.
- [ ] Verify RED.
- [ ] Implement immutable records, duplicate-observation detection by `(item_id, annotator_id)`, and per-item summaries.
- [ ] Require integer ratings 1–5 and choices exactly A/B.
- [ ] Re-run focused tests to GREEN.

### Task 2: Task-cluster bootstrap

**Files:**
- Modify: `src/thrumely/human_analysis.py`
- Modify: `tests/test_human_analysis.py`

**Interfaces:**
- `bootstrap_task_mean(task_values, *, replicates=5000, confidence=0.95, seed)`
- result record with observed mean, lower/upper percentile CI, tasks, replicates, seed.

- [ ] Write failing deterministic/bootstrap-weighting tests.
- [ ] Verify RED.
- [ ] Implement task-level equal-weight means and seeded cluster resampling.
- [ ] Reject empty tasks, non-finite values, invalid confidence/replicate counts.
- [ ] Re-run focused tests.

### Task 3: Pilot-derived task-difference variance and power

**Files:**
- Create: `src/thrumely/pilot_power.py`
- Create: `tests/test_pilot_power.py`

**Interfaces:**
- `estimate_task_difference_sd(differences)`
- `simulate_power_from_task_sd(differences, *, target_tasks, effect, simulations, alpha, seed)`

- [ ] Write failing tests for mean/SD and deterministic power integration.
- [ ] Verify RED.
- [ ] Implement sample SD over task-level differences and reuse `PowerSimulationConfig` with within-task SD zero.
- [ ] Require at least two finite task differences and positive observed SD.
- [ ] Re-run focused tests.

### Task 4: Raw-credit reserve gate

**Files:**
- Create: `src/thrumely/budget.py`
- Create: `tests/test_budget.py`

**Interfaces:**
- `project_annotation_credits(responses, credits_per_response, *, available_credits=None, min_reserve_fraction=0.20)`

- [ ] Write failing tests for known/unknown balance, exact 20% boundary, and invalid numeric types.
- [ ] Verify RED.
- [ ] Implement integer-credit arithmetic and nullable reserve decision.
- [ ] Re-run focused tests.

### Task 5: Synthetic pilot vertical slice

**Files:**
- Create: `src/thrumely/pilot_synthetic.py`
- Create: `tests/test_pilot_synthetic.py`

**Interfaces:**
- `run_synthetic_pilot() -> dict[str, object]`
- CLI: `python -m thrumely.pilot_synthetic`

- [ ] Write failing test requiring explicit synthetic label, zero network/credit spend, summaries, bootstrap, power, and budget output.
- [ ] Verify RED.
- [ ] Implement deterministic fixture only.
- [ ] Re-run focused tests and CLI.

### Task 6: Documentation, CI, and integration

**Files:**
- Modify: `README.md`
- Modify: `.github/workflows/ci.yml`

- [ ] Document synthetic-pilot command and planning-only semantics.
- [ ] Add `python -m thrumely.pilot_synthetic` to normal credential-free CI.
- [ ] Run full suite and all offline scientific CLIs.
- [ ] Require feature-head GitHub Actions success.
- [ ] Open PR, require PR-triggered CI, squash-merge to `main`.
- [ ] Delete feature branch and verify only `main` remains with merged-main CI green.
