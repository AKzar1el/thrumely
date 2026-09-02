# Modal Open-Weight Reference Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reproducible, zero-idle Modal-hosted FLUX.2 Klein 4B reference backend and exercise it through Thrumely's existing normalized media contract without changing the frozen-v1 provider matrix.

**Architecture:** Keep heavyweight Modal/Diffusers deployment code outside the core package, expose one proxy-authenticated Modal Web Function, and add a thin stdlib HTTP provider adapter inside Thrumely. Reuse the existing calibration artifact/evidence model, keep retries at zero, pin the model revision and inference stack, and execute live verification only through a temporary fail-closed GitHub Actions workflow after offline CI is green.

**Tech Stack:** Python 3.11, Modal 1.5.3, PyTorch 2.13.0, Diffusers 0.40.0, Transformers 5.16.1, Accelerate 1.14.0, Pillow, FastAPI, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-02-modal-reference-backend-design.md`

## Global Constraints

- Modal remains `OPEN_WEIGHT_REFERENCE_BACKEND`, never a frozen-v1 managed-provider candidate.
- Model ID is `black-forest-labs/FLUX.2-klein-4B` at revision `e7b7dc27f91deacad38e78976d1f2b499d76a294`.
- Automatic retries remain zero in deployment app, client adapter, and calibration runner.
- Modal API credentials never enter code, Git, PR text, logs committed to Git, or evidence artifacts.
- Endpoint authentication uses Modal proxy credentials, not the deployment API token.
- `min_containers=0`, `max_containers=1`, no scheduled warmer, no paid-plan upgrade.
- Live execution is dry-run by default and requires explicit authorization.
- Task-005 replay is one bounded trajectory only and is never prompt-rewritten to force success.

---

### Task 1: Modal provider adapter contract

**Files:**
- Create: `tests/test_modal_provider.py`
- Create: `src/thrumely/modal_provider.py`

**Interfaces:**
- Consumes: `NormalizedMediaRequest`, `MediaOperation`, `ProviderMediaResult`, `ProviderExecutionError`.
- Produces: `ModalImageProvider`, `ModalProviderExecutionError`, `quality_tier_to_dimensions(aspect_ratio, quality_tier)`.

- [ ] **Step 1: Write failing tests**

Cover:

```python
assert quality_tier_to_dimensions("1:1", "standard") == (1024, 1024)
assert quality_tier_to_dimensions("16:9", "draft") == (896, 512)
assert quality_tier_to_dimensions("2:3", "high") == (1152, 1728)
```

Use an injected fake transport and assert a generation request sends exactly one JSON POST containing `prompt`, `operation`, `width`, `height`, `seed=0`, and `previous_image_base64=None`, with only `Modal-Key` / `Modal-Secret` authentication headers. Assert `raw_request` contains a redacted endpoint placeholder and never contains proxy values.

Test `edit_previous` requires bytes, includes exactly one base64 previous image, and preserves the exact previous artifact linkage from `NormalizedMediaRequest`.

Test valid PNG/JPEG response decoding, actual dimension validation, pinned revision provenance, `retry_count=0`, and raw-response image redaction.

Test HTTP errors persist only safe numeric/status/error-code fields and never body text, endpoint credentials, or proxy values.

- [ ] **Step 2: Run tests and confirm RED**

Run:

```bash
python -m pytest -q tests/test_modal_provider.py
```

Expected: collection/import failure because `thrumely.modal_provider` does not exist.

- [ ] **Step 3: Implement minimal adapter**

Create `ModalImageProvider` with constants:

```python
MODEL_ID = "black-forest-labs/FLUX.2-klein-4B"
MODEL_REVISION = "e7b7dc27f91deacad38e78976d1f2b499d76a294"
BACKEND_ID = "modal:flux-2-klein-4b-reference"
```

Read runtime configuration from:

```text
THRUMELY_MODAL_ENDPOINT_URL
THRUMELY_MODAL_PROXY_KEY
THRUMELY_MODAL_PROXY_SECRET
```

Use `urllib.request` with a single POST and no retry loop. Validate response media with the same PNG/JPEG dimension logic used by the Cloudflare adapter, but keep implementation local to avoid coupling provider modules.

- [ ] **Step 4: Run targeted tests and confirm GREEN**

```bash
python -m pytest -q tests/test_modal_provider.py
```

Expected: all Modal-provider tests pass.

- [ ] **Step 5: Commit**

Commit message:

```text
feat: add Modal reference provider adapter
```

---

### Task 2: Deployable pinned Modal inference app

**Files:**
- Create: `modal_apps/flux2_klein_reference.py`
- Create: `tests/test_modal_app_contract.py`

**Interfaces:**
- Consumes JSON endpoint contract from the design spec.
- Produces a Modal App named `thrumely-flux2-klein-reference` and proxy-authenticated POST Web Function.

- [ ] **Step 1: Write static contract tests**

Without importing Modal/Torch, read the deployment file as text/AST and require:

```python
MODEL_ID = "black-forest-labs/FLUX.2-klein-4B"
MODEL_REVISION = "e7b7dc27f91deacad38e78976d1f2b499d76a294"
DIFFUSERS_VERSION = "0.40.0"
TORCH_VERSION = "2.13.0"
TRANSFORMERS_VERSION = "5.16.1"
ACCELERATE_VERSION = "1.14.0"
```

Also require `gpu="L4"`, `min_containers=0`, `max_containers=1`, `requires_proxy_auth=True`, a persistent named Volume, `@modal.enter()`, exactly four inference steps, guidance scale 1.0, and the pinned HF revision in `snapshot_download`/`from_pretrained` paths.

- [ ] **Step 2: Run tests and confirm RED**

```bash
python -m pytest -q tests/test_modal_app_contract.py
```

Expected: failure because the deployment file does not exist.

- [ ] **Step 3: Implement deployment app**

Use a dedicated download function attaching `thrumely-flux2-klein-4b-weights` at `/models` and `snapshot_download(..., revision=MODEL_REVISION)`.

Use a GPU class with:

```python
@app.cls(
    image=inference_image,
    gpu="L4",
    volumes={"/models": model_volume},
    min_containers=0,
    max_containers=1,
    scaledown_window=60,
    timeout=300,
)
class Flux2KleinReference:
    @modal.enter()
    def load(self): ...

    @modal.method()
    def infer(self, payload: dict) -> dict: ...
```

Use `Flux2KleinPipeline.from_pretrained(local_model_path, torch_dtype=torch.bfloat16)` and move/offload according to the lowest-risk supported method observed during live deployment. Validate input before calling the model; return PNG base64 and structured provenance only.

Expose a lightweight CPU endpoint:

```python
@app.function(image=web_image)
@modal.fastapi_endpoint(method="POST", requires_proxy_auth=True)
def infer(payload: dict) -> dict:
    return Flux2KleinReference().infer.remote(payload)
```

- [ ] **Step 4: Run static tests and full unit suite**

```bash
python -m pytest -q tests/test_modal_app_contract.py
python -m pytest -q
```

Expected: all tests pass without importing Modal in ordinary CI.

- [ ] **Step 5: Commit**

```text
feat: add pinned Modal FLUX reference app
```

---

### Task 3: Modal control-surface calibration runner

**Files:**
- Create: `tests/test_modal_control_surface.py`
- Create: `src/thrumely/modal_control_surface.py`

**Interfaces:**
- Consumes: `ModalImageProvider`, calibration task JSON, `ArtifactStore`.
- Produces: dry-run JSON and a four-probe live evidence directory.

- [ ] **Step 1: Write failing tests**

Require dry-run to:

- select exactly one `cal-*` task;
- create no output directory;
- require no endpoint/proxy credentials;
- report four fixed probes and `maximum_transport_requests=4`;
- mark `benchmark_trajectory=false` and `scientific_scope="open-weight-reference-control-calibration-only"`.

Require the live runner with fake provider to execute exactly:

1. standard 1:1 generation, seed 0;
2. standard 1:1 edit of the first exact artifact, seed 1;
3. draft 16:9 generation, seed 2;
4. high 2:3 generation, seed 3.

Require hashes/dimensions/provenance and zero retries; stop on first provider error with explicit terminal status.

- [ ] **Step 2: Confirm RED**

```bash
python -m pytest -q tests/test_modal_control_surface.py
```

- [ ] **Step 3: Implement runner**

Mirror the artifact/sanitization pattern in `cloudflare_control_surface.py`, but use Modal-specific scientific-scope strings and seeds. Never import the Modal SDK.

- [ ] **Step 4: Confirm GREEN and full repository gate**

```bash
python -m pytest -q tests/test_modal_control_surface.py
python -m pytest -q
python -m thrumely.datapoint_sandbox --offline
python -m thrumely.pilot_synthetic
python -m thrumely.experiment_synthetic
python -m thrumely.freeze_preflight --synthetic --output .ci-freeze-preflight
python -m thrumely.validate_candidates candidates/tasks-v0.1.jsonl
python -m thrumely.power --tasks 100 --effect 0.20 --simulations 2000 --seed 20260901
python -m thrumely.validate_normalization
python -m thrumely.offline --output .ci-offline
```

- [ ] **Step 5: Commit**

```text
feat: add Modal reference calibration runner
```

---

### Task 4: Live deployment workflow and cost guard

**Files:**
- Create temporarily on an ops branch: `.github/workflows/modal-reference-live.yml`
- No permanent workflow is merged into `main`.

**Interfaces:**
- Consumes repository secrets `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET`.
- Produces sanitized GitHub Actions artifacts and measured Modal billing evidence.

- [ ] **Step 1: Create fail-closed temporary workflow**

Pin GitHub-owned actions by full SHA. Scope `GITHUB_TOKEN` to `contents: read`. Inject Modal API credentials only into shell steps that require them.

The workflow must stop before Modal package install/deployment if either repository secret is absent.

- [ ] **Step 2: Read-only Modal preflight**

Install `modal==1.5.3`, run `modal token info`, `modal billing rates --json`, and `modal billing summary --json`. Do not print credential values.

- [ ] **Step 3: Deploy and create ephemeral proxy auth**

Run:

```bash
modal run modal_apps/flux2_klein_reference.py::download_model
modal deploy modal_apps/flux2_klein_reference.py
modal workspace proxy-tokens create --json
```

Parse proxy key/secret in-process, immediately emit GitHub `::add-mask::` commands, and never upload the token JSON. Determine the deployed endpoint URL from Modal deployment metadata/log output without hard-coding workspace identifiers into repository evidence.

- [ ] **Step 4: Run direct reference probes**

Set endpoint/proxy values only for the runner step and execute:

```bash
python -m thrumely.modal_control_surface \
  --tasks calibration/tasks/openai-smoke.json \
  --task-id cal-openai-001 \
  --output "$RUNNER_TEMP/modal-reference-controls" \
  --execute-live
```

Validate exactly four successful provider executions, dimensions, seeds, model revision, retry_count=0, and secret/base64 redaction.

- [ ] **Step 5: Replay task 005 once**

After Task 4 direct probes pass, invoke a one-task reference-backend replay of `cal-openai-005` using the existing two-media-action trajectory ceiling. Do not retry or mutate the prompt if it fails.

- [ ] **Step 6: Capture billing evidence and clean proxy token**

Run `modal billing report --for today --show-resources --json` and `modal billing summary --json`; persist only sanitized cost/resource metadata. Delete the ephemeral proxy token even when calibration fails, using an always-run cleanup step.

- [ ] **Step 7: Upload evidence and inspect actual images**

Upload sanitized evidence/artifacts for manual and programmatic inspection. Verify no `ak-`, `as-`, `wk-`, `ws-`, `Authorization`, `Modal-Key`, or `Modal-Secret` material is present.

---

### Task 5: Record findings, integrate, and remove temporary live workflow

**Files:**
- Create: `docs/providers/MODAL_REFERENCE_CALIBRATION_2026-09-02.md`
- Modify: `docs/superpowers/plans/2026-09-02-live-provider-calibration-gate.md`
- Remove/reset temporary ops branch/workflow after evidence capture.

- [ ] **Step 1: Record measured facts only**

Document deployed app/model/revision, actual GPU class, successful/failed probes, hashes/dimensions, task-005 outcome, latency, billing observations, and exact run IDs. Do not infer provider/filter causality beyond evidence.

- [ ] **Step 2: Preserve scientific boundary**

State explicitly that Modal reference evidence does not pass OpenAI/Google/BFL managed-provider gates and does not enter the production corpus/freeze matrix.

- [ ] **Step 3: Run final full CI on exact integration head**

Require every ordinary/scientific gate from Task 3 to pass.

- [ ] **Step 4: Squash-merge reviewed PR and verify `main`**

Merge only a green reviewed head. Run fresh post-merge CI on the resulting `main` SHA.

- [ ] **Step 5: Collapse temporary refs**

Reset all Modal feature/live/docs refs to the verified `main` SHA if branch deletion remains unavailable through the connector. Confirm the temporary live workflow is absent from every branch tip.
