# Candidate Corpus, Scoring, and Power Design

**Date:** 2026-09-01
**Status:** approved Week-4 zero-cost design
**Research protocol:** `RESEARCH_SPEC.md`

## Scope

This slice advances Thrumely without any hosted inference, Datapoint spend, or production-corpus freeze.

It adds:

1. a richer candidate-task data contract;
2. an explicitly **unfrozen** candidate corpus of 150 newly authored tasks (30 per planned family);
3. deterministic corpus validation and hashing;
4. frozen-per-task atomic requirements and evaluation questions authored before outputs exist;
5. zero-cost deterministic scorer primitives and a registry for future optional model-backed scorers;
6. a deterministic synthetic task-cluster power-simulation skeleton.

It does **not**:

- select/freeze the final 100 production tasks;
- make provider/model calls;
- download model weights;
- run VQAScore/TIFA/HPSv2/CLIPScore inference;
- create Datapoint jobs;
- alter the primary human endpoint.

## Candidate task contract

`CandidateTaskSpec` extends the existing minimal `TaskSpec` concept for corpus development. Each candidate records:

- `task_id`;
- one of the five protocol task families;
- `instruction` shown to the controller;
- `target_aspect_ratio`;
- `atomic_requirements` authored before outputs;
- `evaluation_questions` authored before outputs;
- `human_rubric_notes`;
- `deterministic_checks` describing checks that do not require model judgment;
- `risk_flags` for screening;
- `corpus_status`, fixed to `candidate` in this slice.

Atomic requirements are observable propositions such as object count, relative placement, required text, requested color, style, or layout constraint. Evaluation questions must be answerable from the final image and must not encode a preferred provider/controller.

## Corpus composition

Author exactly 150 candidates, 30 per family:

1. compositional constraints;
2. typography and layout;
3. styled visual brief;
4. product/editorial scene;
5. revision-sensitive multi-constraint brief.

The corpus is stored separately from calibration prompts and from any future frozen production file. The validator rejects copied IDs, empty atomic requirements, unsupported family/aspect values, missing evaluation questions, and any item marked `frozen`.

The final 100-task production corpus remains blocked by the live provider-normalization gate.

## Scoring architecture

The current slice implements only deterministic, dependency-free pieces:

- exact aspect-ratio/dimension compliance from media metadata;
- normalized required-text matching against externally supplied OCR text;
- atomic requirement bookkeeping/coverage helpers;
- scorer descriptors for future optional model-backed metrics.

The registry records candidate future metric families without running them:

- TIFA-style frozen question answering for instruction faithfulness;
- VQAScore-style semantic faithfulness;
- CLIPScore historical embedding baseline;
- HPSv2 preference/reward baseline;
- pairwise VLM judge with order reversal.

Human instruction-faithfulness remains primary. No automatic metric is promoted based on production labels.

## Power simulation

Add a standard-library-only synthetic simulator operating at the independent-task level. It models paired chooser-vs-fixed task means with:

- configurable number of tasks;
- configurable true mean effect;
- between-task heterogeneity;
- within-task noise;
- replications;
- significance level;
- deterministic RNG seed.

The simulator estimates power using a paired task-level mean difference and a normal approximation. It is a planning skeleton, not the final confirmatory analysis. Later pilot-derived variance parameters will replace synthetic defaults, and the final primary uncertainty calculation remains task-clustered as required by `RESEARCH_SPEC.md`.

## Reproducibility

The candidate corpus validator emits a canonical SHA-256 over normalized JSON content. The candidate file explicitly records that its hash is a development artifact, not the future production corpus hash.

No network access is required for corpus validation, deterministic scoring, or power simulation.

## Verification

Required green commands before merge:

```bash
python -m pytest -q
python -m thrumely.validate_candidates candidates/tasks-v0.1.jsonl
python -m thrumely.power --tasks 100 --effect 0.20 --simulations 2000 --seed 20260901
python -m thrumely.offline --output .verify-offline
```

CI must remain credential-free and must not install optional provider/scorer packages.
