# Corpus, Scoring, and Power Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a validated 150-item unfrozen candidate corpus, dependency-free deterministic scoring scaffolds, and a reproducible synthetic task-level power simulator without making hosted calls or freezing production methodology.

**Architecture:** Keep the existing runtime `TaskSpec` small and add a separate corpus-development model for pre-production authoring. Store candidate tasks as JSONL and validate/hash them with a deterministic CLI. Keep automatic scoring modular: implement only deterministic checks now and register heavy metric families as future optional adapters. Power planning remains a separate standard-library module so it cannot contaminate production analysis code.

**Tech Stack:** Python 3.11+, standard library, pytest. No new mandatory dependencies.

**Spec:** `docs/superpowers/specs/2026-09-01-corpus-scoring-power-design.md`

## Global Constraints

- Zero hosted API calls and zero paid inference.
- Zero Datapoint jobs or credit usage.
- Final v1 production corpus remains unfrozen.
- Candidate corpus contains exactly 150 newly authored tasks, 30 per planned family.
- Automatic questions and deterministic checks are authored before outputs exist.
- Human instruction-faithfulness remains the primary endpoint.
- Heavy scorer/model packages remain optional and are not installed or executed in CI.
- No provider/controller preference may be encoded in task or scoring metadata.
- Core CI remains credential-free.

---

### Task 1: Candidate-task schema and validator

**Files:**
- Create: `src/thrumely/corpus.py`
- Create: `src/thrumely/validate_candidates.py`
- Create: `tests/test_corpus.py`
- Create: `tests/test_validate_candidates.py`

**Interfaces:**
- `CandidateTaskSpec` frozen dataclass with fields `task_id`, `family`, `instruction`, `target_aspect_ratio`, `atomic_requirements`, `evaluation_questions`, `human_rubric_notes`, `deterministic_checks`, `risk_flags`, `corpus_status`.
- `load_candidate_jsonl(path) -> tuple[CandidateTaskSpec, ...]`.
- `validate_candidate_corpus(tasks, *, expected_total=150, expected_per_family=30) -> tuple[str, ...]`.
- `canonical_candidate_corpus_hash(tasks) -> str`.
- CLI `python -m thrumely.validate_candidates PATH` exits non-zero for validation failures and prints count/family distribution/hash for valid candidate data.

- [ ] Write tests requiring the five exact protocol families, supported aspect ratios, non-empty requirements/questions/rubric notes, `corpus_status == "candidate"`, unique IDs, exact total and per-family counts, canonical hash stability, and clear failure messages.
- [ ] Run the focused tests and verify RED because `thrumely.corpus` / validator do not exist.
- [ ] Implement the minimal dataclass, JSONL loader, validation functions, canonical JSON serialization, SHA-256 helper, and CLI.
- [ ] Run focused tests and verify GREEN.
- [ ] Commit schema/validator/tests.

### Task 2: Author the 150-item unfrozen candidate corpus

**Files:**
- Create: `candidates/tasks-v0.1.jsonl`
- Create: `candidates/README.md`
- Create: `tests/test_candidate_dataset.py`

**Interfaces:**
- Corpus consumes `CandidateTaskSpec` and validator from Task 1.
- Every line is one JSON object matching `CandidateTaskSpec`.
- IDs use stable prefixes: `comp-`, `type-`, `style-`, `editorial-`, `revision-` plus three-digit sequence.

- [ ] Write a dataset-level test that loads `candidates/tasks-v0.1.jsonl`, asserts exactly 150 records / 30 per family, zero validation issues, all IDs unique, and `corpus_status` candidate everywhere.
- [ ] Run the dataset test and verify RED because the file does not exist.
- [ ] Author 30 original tasks per family. Each task must include 3-7 observable atomic requirements, 2-6 image-answerable evaluation questions, concise human rubric notes, at least an `aspect_ratio` deterministic check, and no prohibited core-v1 risk category.
- [ ] Add `candidates/README.md` explaining that this is an unfrozen development pool and must not be treated as the future production 100-task corpus.
- [ ] Run dataset + validator tests and verify GREEN.
- [ ] Run `python -m thrumely.validate_candidates candidates/tasks-v0.1.jsonl` and record the development hash.
- [ ] Commit candidate corpus/readme/test.

### Task 3: Deterministic scoring primitives and metric registry

**Files:**
- Create: `src/thrumely/scoring.py`
- Create: `tests/test_scoring.py`
- Modify: `README.md`

**Interfaces:**
- `MetricDescriptor(name, role, implementation_status, requires_model, primary_eligible, notes)` frozen dataclass.
- `candidate_metric_registry() -> tuple[MetricDescriptor, ...]` containing TIFA-style QA, VQAScore, CLIPScore, HPSv2, pairwise VLM judge, aspect ratio, OCR required-text match, and tool-validity telemetry.
- `aspect_ratio_score(target: str, width: int, height: int, *, tolerance=0.02) -> float` returns 1.0/0.0.
- `normalize_ocr_text(text: str) -> str` case-folds and collapses non-alphanumeric separators.
- `required_text_score(required: tuple[str, ...], observed_ocr_text: str) -> float | None`; returns `None` when there are no required strings, otherwise fraction found after normalization.
- `atomic_coverage(requirement_ids: tuple[str, ...], satisfied_ids: set[str]) -> float | None` for externally produced atomic judgments.

- [ ] Write tests for aspect-ratio tolerance, OCR normalization, required-text partial/full/no-requirement behavior, atomic coverage, metric-registry uniqueness, and the invariant that no model-backed metric is marked primary-eligible.
- [ ] Run focused tests and verify RED because `thrumely.scoring` does not exist.
- [ ] Implement dependency-free primitives and descriptors only; do not import/download/run external scorer models.
- [ ] Update README with automated-evaluation status and citations/links to upstream metric projects.
- [ ] Run focused and full tests; verify GREEN.
- [ ] Commit scoring primitives/registry/docs/tests.

### Task 4: Synthetic task-level power simulator

**Files:**
- Create: `src/thrumely/power.py`
- Create: `tests/test_power.py`
- Create: `docs/methodology/POWER_PLANNING.md`

**Interfaces:**
- `PowerSimulationConfig(tasks, effect, between_task_sd, within_task_sd, simulations, alpha, seed)` frozen dataclass with validation.
- `simulate_power(config) -> PowerSimulationResult` where result includes estimated power, mean simulated effect, standard error summary, simulations, and seed.
- Use `random.Random(seed)` and `statistics.NormalDist` only.
- Each simulation samples task-level paired differences `effect + N(0, between_task_sd) + N(0, within_task_sd)` and rejects the two-sided null when `abs(mean / se) > NormalDist().inv_cdf(1 - alpha / 2)`.
- CLI: `python -m thrumely.power --tasks 100 --effect 0.20 --simulations 2000 --seed 20260901`.

- [ ] Write tests for invalid configs, deterministic repeatability with identical seed, zero-effect false-positive rate staying near alpha under a stable fixture, and meaningfully higher power for larger effect/more tasks.
- [ ] Run focused tests and verify RED because `thrumely.power` does not exist.
- [ ] Implement the simulator and CLI with no third-party numerical dependency.
- [ ] Document that this is a pre-pilot planning approximation, not final confirmatory analysis, and that pilot-derived variance will replace synthetic defaults.
- [ ] Run focused tests and verify GREEN.
- [ ] Commit power simulator/docs/tests.

### Task 5: Integration verification and scientific guardrails

**Files:**
- Modify: `README.md` if required for discoverability.
- Create: `tests/test_week4_guardrails.py`

**Interfaces:**
- Guardrail test reads the candidate corpus and metric registry.

- [ ] Write tests that assert every candidate is still marked `candidate`, exactly 150 tasks exist, no task ID overlaps calibration prompt IDs, no model-backed automatic metric is primary-eligible, and all zero-cost CLIs import/run without provider SDKs.
- [ ] Verify any new guardrail test fails before its corresponding integration change if applicable.
- [ ] Implement only the minimum integration/documentation required for green guardrails.
- [ ] Run full verification:
  - `python -m pytest -q`
  - `python -m thrumely.validate_candidates candidates/tasks-v0.1.jsonl`
  - `python -m thrumely.power --tasks 100 --effect 0.20 --simulations 2000 --seed 20260901`
  - `python -m thrumely.validate_normalization`
  - `python -m thrumely.offline --output .verify-offline`
- [ ] Confirm no credential environment variables are required and no network call occurs.
- [ ] Open PR only after fresh green verification and review; squash merge after PR CI; delete feature branch; leave only `main`.
