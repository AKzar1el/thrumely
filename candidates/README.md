# Candidate task pool v0.1

This directory contains **development candidates only** for Thrumely v1.

`tasks-v0.1.jsonl` contains 150 newly authored candidate tasks: 30 for each of the five families in `RESEARCH_SPEC.md`. The file is deliberately broader than the planned 100-task production corpus so calibration and methodology review can remove weak, ambiguous, provider-incompatible, or redundant items without rewriting prompts after observing production results.

## Important status

- `corpus_status` is `candidate` for every record.
- This file is **not** the frozen v1 production corpus.
- Its SHA-256 is a development provenance value only.
- The final 100-task corpus remains blocked by the live provider-normalization gate.
- Calibration prompts must remain separate and must not be promoted into this pool.

Each candidate includes observable atomic requirements, pre-output image-answerable evaluation questions, human-rubric notes, and deterministic check descriptors. These are authored before production outputs exist to reduce evaluator retrofitting and outcome-driven prompt edits.
