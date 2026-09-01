# Datapoint Sandbox Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a credential-free, sandbox-only Datapoint human-evaluation integration that validates Thrumely's pairwise and 1–5 rating contracts without spending credits.

**Architecture:** Split the work into protocol builders, a dependency-free HTTP client with an injectable transport, normalized result parsers, and an offline fake-sandbox CLI. A hard safety boundary refuses any job whose `serving_environment` is not exactly `sandbox` before network transport is invoked.

**Tech Stack:** Python 3.11 standard library, pytest, existing Thrumely redaction/provenance utilities.

**Spec:** `docs/superpowers/specs/2026-09-01-datapoint-sandbox-design.md`

## Global Constraints

- No hosted model calls.
- No Datapoint production jobs or paid pilot.
- `serving_environment` must be exactly `sandbox` for every supported create-job path.
- No API key may appear in public payloads, exceptions, logs, fixtures, or committed files.
- Human instruction-faithfulness rating remains the primary endpoint.
- Pairwise preference is secondary and uses Datapoint native forced-choice A/B.
- Final 100-task corpus remains unfrozen.
- Core package remains dependency-free.

---

### Task 1: Sandbox protocol builders

**Files:**
- Create: `src/thrumely/datapoint_protocol.py`
- Create: `tests/test_datapoint_protocol.py`

**Interfaces:**
- Produces: `build_pairwise_sandbox_job(name, pairs, max_responses_per_datapoint=5) -> dict[str, object]`
- Produces: `build_rating_sandbox_job(name, items, max_responses_per_datapoint=5) -> dict[str, object]`

- [ ] **Step 1: Write failing tests** asserting pairwise uses `comparison`, contains exactly two image candidates, emits `serving_environment == "sandbox"`, and rating uses `[1,2,3,4,5]` with `{context}` in the instruction.
- [ ] **Step 2: Run `pytest tests/test_datapoint_protocol.py -q`** and confirm import/function failures.
- [ ] **Step 3: Implement minimal immutable-input validation and payload construction.** Reject empty names, non-`dp://`/HTTPS media refs, malformed pair counts, and response counts outside Datapoint's documented range.
- [ ] **Step 4: Re-run focused tests** and require PASS.
- [ ] **Step 5: Commit** `feat: add Datapoint sandbox protocol builders`.

### Task 2: Safe dependency-free API client

**Files:**
- Create: `src/thrumely/datapoint_client.py`
- Create: `tests/test_datapoint_client.py`

**Interfaces:**
- Produces: `DatapointClient(api_key, transport=None, base_url=...)`
- Produces methods: `upload_media`, `create_sandbox_job`, `get_job`, `get_results`, `get_responses`
- Produces: `DatapointClientError`

- [ ] **Step 1: Write failing tests** with a fake transport proving headers contain `X-API-Key`, `prod`/`all` payloads are rejected before transport, and sanitized exceptions never contain the key.
- [ ] **Step 2: Run focused tests** and verify RED for missing client.
- [ ] **Step 3: Implement transport protocol plus standard-library urllib fallback.** JSON calls use UTF-8; upload uses multipart/form-data with a generated boundary and filename-derived image type.
- [ ] **Step 4: Add error sanitization** via existing `sanitize_public_payload` and bounded exception messages.
- [ ] **Step 5: Re-run focused tests** and require PASS.
- [ ] **Step 6: Commit** `feat: add sandbox-only Datapoint client`.

### Task 3: Result and raw-response normalization

**Files:**
- Create: `src/thrumely/datapoint_results.py`
- Create: `tests/test_datapoint_results.py`

**Interfaces:**
- Produces: `normalize_comparison_results(payload) -> tuple[dict[str, object], ...]`
- Produces: `normalize_rating_results(payload) -> tuple[dict[str, object], ...]`
- Produces: `normalize_public_responses(payload) -> tuple[dict[str, object], ...]`

- [ ] **Step 1: Write failing tests** from current documented result shapes, including unknown extra fields.
- [ ] **Step 2: Verify RED.**
- [ ] **Step 3: Implement name-based parsing** that rejects structural contradictions while ignoring forward-compatible unknown fields.
- [ ] **Step 4: Public raw-response normalization** keeps anonymized annotator ID, country, response, response time, timestamp, datapoint index; drops city/region/country-name by default.
- [ ] **Step 5: Re-run tests** and require PASS.
- [ ] **Step 6: Commit** `feat: normalize Datapoint sandbox results`.

### Task 4: Offline fake-sandbox vertical slice

**Files:**
- Create: `src/thrumely/datapoint_sandbox.py`
- Create: `tests/test_datapoint_sandbox.py`

**Interfaces:**
- Produces CLI: `python -m thrumely.datapoint_sandbox --offline`
- Produces helper: `run_offline_sandbox() -> dict[str, object]`

- [ ] **Step 1: Write failing test** requiring one comparison and one rating fake round trip through the actual `DatapointClient` interface.
- [ ] **Step 2: Verify RED.**
- [ ] **Step 3: Implement deterministic fake transport** returning documented create/status/results/responses envelopes and asserting every created job is sandbox-only.
- [ ] **Step 4: Implement CLI output** clearly labeled `OFFLINE_FAKE_SANDBOX`; no environment credentials are read in `--offline` mode.
- [ ] **Step 5: Re-run tests** and manually run the module.
- [ ] **Step 6: Commit** `feat: add offline Datapoint sandbox smoke`.

### Task 5: Protocol amendment and documentation

**Files:**
- Modify: `RESEARCH_SPEC.md`
- Modify: `README.md`
- Create: `docs/decisions/0002-datapoint-pairwise-forced-choice.md`

**Interfaces:**
- Documents the platform constraint and secondary-endpoint change before production freeze.

- [ ] **Step 1: Add a guardrail test** that the research spec no longer claims a per-annotator Tie option and explicitly says pairwise is forced-choice A/B on Datapoint.
- [ ] **Step 2: Verify RED against current spec.**
- [ ] **Step 3: Amend only the pairwise secondary protocol.** Keep the primary 1–5 endpoint unchanged and record why composite-media emulation was rejected.
- [ ] **Step 4: Document sandbox CLI and zero-credit status in README.**
- [ ] **Step 5: Re-run guardrail/full tests.**
- [ ] **Step 6: Commit** `docs: align pairwise protocol with Datapoint`.

### Task 6: CI and completion verification

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- CI adds `python -m thrumely.datapoint_sandbox --offline`.

- [ ] **Step 1: Add CI command** after unit tests and before other offline scientific checks.
- [ ] **Step 2: Run full local suite** and all credential-free CLIs.
- [ ] **Step 3: Push exact feature head and require GitHub Actions success.**
- [ ] **Step 4: Open PR with explicit scientific/cost guardrails.**
- [ ] **Step 5: Require PR-triggered CI.**
- [ ] **Step 6: Squash-merge to `main`, delete feature branch, and verify only `main` remains.**
