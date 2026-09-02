# Modal Open-Weight Reference Backend Design

**Date:** 2026-09-02  
**Status:** approved architectural continuation  
**Scope:** calibration/reference infrastructure only; not a frozen-v1 provider and not benchmark evidence.

## Goal

Add a reproducible, self-hosted FLUX.2 Klein 4B reference backend on Modal so Thrumely can separate model behavior from managed-provider behavior while consuming Modal's recurring Starter compute allowance instead of paid OpenAI/Google/BFL calls.

## Scientific boundary

Modal is an `OPEN_WEIGHT_REFERENCE_BACKEND`. It is not a managed-provider candidate in the frozen-v1 matrix. Results may answer questions about transport, model-family behavior, edit semantics, dimensions, deterministic controls, and provider-wrapper effects. They must not be used to claim that Modal is equivalent to OpenAI, Google, BFL, or Cloudflare, and they do not satisfy the live OpenAI/Google/BFL gates in the authoritative calibration plan.

The first scientific target is a cross-host comparison with Cloudflare because both paths use FLUX.2 Klein 4B. In particular, replaying the benign task-005 correction on the pinned open-weight backend can distinguish a provider-wrapper rejection from a deterministic model/edit failure without modifying the calibration prompt to force success.

## Fixed model identity

- Hugging Face repository: `black-forest-labs/FLUX.2-klein-4B`
- Pinned revision: `e7b7dc27f91deacad38e78976d1f2b499d76a294`
- License: Apache-2.0
- Pipeline: `Flux2KleinPipeline`
- Diffusers: `0.40.0`
- PyTorch: `2.13.0`
- Transformers: `5.16.1`
- Accelerate: `1.14.0`
- Python: `3.11`
- Default inference steps: `4`
- Default guidance scale: `1.0`

The model revision is immutable in source. Any later model revision requires a versioned code change and fresh calibration evidence.

## Modal execution architecture

The deployable app lives outside the core Thrumely package at `modal_apps/flux2_klein_reference.py` so ordinary unit tests and package installs do not require the Modal SDK, Torch, Diffusers, or GPU dependencies.

The app uses:

- Modal App name `thrumely-flux2-klein-reference`;
- persistent Volume `thrumely-flux2-klein-4b-weights` mounted at `/models`;
- `snapshot_download(..., revision=<pinned sha>)` to populate the Volume;
- an L4 GPU for inference because the model card states approximately 13 GB VRAM and Modal's L4 class provides sufficient memory at a low listed per-second rate;
- zero warm containers by default and a short scale-down window so idle time does not consume compute;
- maximum one concurrent GPU container for calibration to prevent accidental parallel spend;
- one authenticated POST Web Function with `requires_proxy_auth=True`.

Modal API credentials (`ak-` / `as-`) are only for deployment and workspace operations. They are never embedded in the app or accepted by the inference endpoint. The endpoint uses Modal proxy credentials (`wk-` / `ws-`) created for a calibration execution and passed through `Modal-Key` / `Modal-Secret` headers.

## Endpoint contract

The Web Function accepts JSON with:

```json
{
  "prompt": "...",
  "operation": "generate|edit_previous",
  "width": 1024,
  "height": 1024,
  "seed": 0,
  "previous_image_base64": null
}
```

Rules:

- `prompt` must be non-empty;
- `operation` is exactly `generate` or `edit_previous`;
- dimensions are positive multiples of 16 and bounded to the dimensions exposed by Thrumely's calibration mapping;
- `seed` is an integer in `[0, 2^32-1]`;
- `previous_image_base64` must be absent/null for generation and present for editing;
- only PNG/JPEG reference images are accepted;
- no automatic retry exists in the app or client adapter.

The GPU method loads the pinned pipeline once per container with `@modal.enter()`. Generation calls the pipeline with the fixed step/guidance settings and an explicit CUDA generator seeded by the request. Editing supplies the decoded prior image to the same pinned pipeline. The response contains base64 PNG bytes plus actual width/height, model ID, revision, steps, guidance scale, seed, and elapsed inference time. It contains no Modal API/proxy credentials and no filesystem path.

## Thrumely provider adapter

`src/thrumely/modal_provider.py` implements the existing `ProviderMediaResult` contract.

Runtime configuration:

- `THRUMELY_MODAL_ENDPOINT_URL`
- `THRUMELY_MODAL_PROXY_KEY`
- `THRUMELY_MODAL_PROXY_SECRET`

The adapter:

- accepts only backend ID `modal:flux-2-klein-4b-reference`;
- maps normalized aspect/quality controls to the same fixed pixel-budget table used for the Cloudflare exploratory reference so cross-host comparisons hold requested dimensions constant;
- uses a deterministic request seed supplied by the calibration runner, with default seed `0` for direct control probes;
- encodes only the exact previous artifact for `edit_previous`;
- sends one HTTP request per provider execution;
- sets no HTTP retry loop;
- validates returned media bytes and dimensions;
- redacts base64 output from public `raw_response` evidence;
- records the pinned model revision in usage/provenance;
- converts HTTP failures into typed `ModalProviderExecutionError` containing only HTTP status and a safe machine-readable error code when available, never provider body text or credentials.

## Calibration runner

`src/thrumely/modal_control_surface.py` mirrors the existing Cloudflare control-surface structure but is explicitly reference-backend calibration.

It has a dry-run default and an explicit `--execute-live`. The fixed initial four-probe matrix is:

1. standard 1:1 generation;
2. standard 1:1 exact-prior edit changing only the background;
3. draft 16:9 generation;
4. high 2:3 generation.

The runner records exact seeds, dimensions, hashes, latency, model revision, and zero-retry state. It then supports a separately invoked one-task replay through the existing agent calibration path once the direct transport probes pass; task-005 is not automatically retried or rewritten.

## Deployment and live verification

A temporary, non-merged GitHub Actions workflow is used for live deployment/calibration because the ChatGPT execution container cannot resolve external package/API hosts. Modal's documented GitHub CI pattern requires repository secrets `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`.

The workflow must:

1. check out an exact verified branch head with persisted Git credentials disabled;
2. install a pinned Modal SDK;
3. verify Modal credentials with a read-only token/workspace call;
4. query the current billing summary/rates before GPU execution and record only non-secret cost metadata;
5. deploy the pinned app;
6. create an ephemeral Modal proxy token and mask both returned values immediately;
7. run the Modal control-surface dry-run;
8. execute exactly the four fixed live probes;
9. verify artifacts, exact dimensions, zero retries, and absence of API/proxy credentials from evidence;
10. replay `cal-openai-005` only after the four probes pass, at most one trajectory with the existing two-media-call ceiling;
11. collect a post-run Modal billing report/summary as observed cost evidence;
12. delete the ephemeral proxy token;
13. upload the sanitized evidence bundle;
14. leave the deployed app and cached model Volume available for future reference-calibration reuse unless a later cleanup decision explicitly removes them.

The workflow file itself must never contain credential values. If the two required GitHub Actions secrets are absent, it exits before installing/deploying or making a Modal inference request.

## Security requirements

- Never commit Modal API or proxy credentials.
- Never place credentials in CLI arguments, task files, workflow names, artifacts, or PR bodies.
- Deployment API tokens and inference proxy tokens are separate credential classes.
- `requires_proxy_auth=True` remains mandatory.
- Evidence must not persist `Modal-Key`, `Modal-Secret`, `Authorization`, API token prefixes, proxy-token prefixes, or raw base64 media.
- GitHub live workflow dependencies are pinned by full commit SHA.
- Temporary live workflows are removed/reset after results are recorded.

## Cost boundary

Modal Starter currently documents $30/month included compute. This is an external operational fact, not a frozen experimental constant. Before every live run, re-check current Modal pricing and billing state. The reference backend must use `min_containers=0`, bounded `max_containers=1`, and no scheduled warmers. No paid-plan upgrade, purchased credits, or automatic expansion is authorized by this design.

## PASS criteria

The Modal reference gate passes when:

1. the pinned app deploys with the exact model revision;
2. generation and exact-prior editing both produce valid auditable media;
3. non-square dimensions match the requested mapping;
4. all provider executions have `retry_count=0`;
5. model revision, seed, steps, guidance, latency, and actual dimensions are recorded;
6. credentials/base64 media do not appear in public evidence;
7. Modal billing evidence remains within the existing free allowance without a paid-plan action;
8. the task-005 replay either succeeds or fails in a fully auditable way without prompt manipulation;
9. all repository tests/scientific guards remain green;
10. documentation explicitly preserves the `OPEN_WEIGHT_REFERENCE_BACKEND` boundary.

A task-005 failure can still pass the instrumentation gate if it is protocol-consistent and auditable. Subjective image quality is not a PASS criterion.
