# Cloudflare controller calibration sweep result

**Recorded:** 2026-09-02  
**Status:** mixed calibration result. Controller/image transport is broadly usable for instrumentation, but one live revision degraded required text and one separate revision was rejected by the provider. This remains calibration evidence only, not benchmark evidence.

## Purpose

After the first one-task Cloudflare canary and the deterministic image-provider control-surface run, this sweep exercised the remaining four calibration-only prompt families through the full hosted controller -> image -> visual review -> finish/edit protocol.

The sweep used:

- controller: `@cf/google/gemma-4-26b-a4b-it`
- image backend: `@cf/black-forest-labs/flux-2-klein-4b`
- logical backend: `cloudflare:flux-2-klein-4b`
- maximum controller decisions per task: 2
- maximum media actions per task: 2
- provider retry count: 0
- calibration tasks only: `cal-openai-002` through `cal-openai-005`
- no Datapoint job and no production-corpus/freeze mutation

The main four-task execution was GitHub Actions run `33572776322`. Its evidence artifact was `cloudflare-controller-sweep-33572776322`, artifact id `9825575976`, ZIP size 2,701,538 bytes, SHA-256 `6281ba7c26109269decd68142f639a92c90166e87e7fdf4e6db24e36cc2d4c4e`.

## Per-task observations

### `cal-openai-002` — constrained poster

Result: **transport success; controller chose `media -> finish`.**

- generation: standard / 9:16
- returned media: JPEG, 768x1344, 527,748 bytes
- media SHA-256: `0e54d448869589cd061903ba2a6b16503d0c75365da49575c3b7832460c3b1bd`
- image latency: 25.366822841 seconds
- controller-reported Neurons: 17.46363639831543 on turn 1; 25.790908813476562 on turn 2
- media retries: 0

Manual observable review found the required `NIGHT GARDEN` heading, crescent icon, and `FRIDAY 9 PM` line visibly present with the requested dark botanical treatment. This review is only a calibration sanity check; it is not a quality score.

### `cal-openai-003` — text-sensitive travel poster

Result: **transport success; controller correctly detected a text defect and chose `media -> edit_previous`, but the returned revision did not fix the required text.**

First generation:

- standard / 2:3
- JPEG, 832x1248, 833,730 bytes
- SHA-256: `207341eeca338b15d3f3ef9ecbbb71c3fe954cb65cdae788a9ff138a4f11b3d4`
- latency: 15.869951912 seconds

The controller's second decision explicitly requested an edit to correct the title to `Solmere Botanical Coast` while preserving the visual style and composition. The request referenced the exact first artifact id.

Revision:

- `edit_previous`, standard / 2:3
- JPEG, 832x1248, 802,793 bytes
- SHA-256: `93b5c4ec8d75b6fdaeae6251b037139a3b735939d5d662dc60604d4ee2e644b0`
- latency: 4.351185723 seconds
- media retries: 0

Manual review found that the revision still contained visibly malformed title lettering and did not satisfy the requested correction. This is an important negative calibration observation: a technically successful edit call can worsen or fail a semantic correction, and the benchmark's two-media-action ceiling intentionally provides no hidden third repair attempt.

### `cal-openai-004` — product photograph

Result: **transport success; controller chose `media -> finish`.**

- generation: standard / 3:2
- returned media: JPEG, 1248x832, 519,310 bytes
- media SHA-256: `6ae12610a50cb4edec44f0d65db4763c2ee2953466193b932c2b1d0c6852b810`
- image latency: 17.677079919 seconds
- controller-reported Neurons: 13.827272415161133 on turn 1; 18.918182373046875 on turn 2
- media retries: 0

Manual observable review found an unbranded stainless-steel bottle, pale stone pedestal, linen cloth, rosemary, neutral background, and no visible text/logo. This is again a calibration sanity check rather than a quality rating.

### `cal-openai-005` — cafe menu board

The main sweep ended with a provider failure before a media artifact was returned. At that time the adapter preserved only the Python exception type `HTTPError`, which was insufficient to diagnose the provider response safely.

That diagnostic blind spot was fixed in PR #23 with a red-green regression: Cloudflare image HTTP failures now preserve only HTTP status, the first numeric Cloudflare internal error code when present, and an integer `Retry-After` value when present. Provider messages, bodies, prompts, credentials, and account identifiers are not copied into the error string. Automatic retry behavior remains unchanged at zero.

A single separately authorized diagnostic trajectory was then executed as GitHub Actions run `33573364336`. Its evidence artifact was `cloudflare-task005-diagnostic-33573364336`, artifact id `9825747697`, ZIP size 635,877 bytes, SHA-256 `a1759f1c07a7f501bf9e3e4e15963d45c5f77c1f731d06edec80487987559dfd`.

Observed diagnostic sequence:

1. Gemma requested a standard 3:2 generation.
2. FLUX returned a JPEG, 1248x832, 631,529 bytes, SHA-256 `dc4cbab5b31aa9b57d5a9da04dea6685179c59e7d4f667b985fa3be05440593a`, in 13.766084614 seconds with zero retry.
3. Manual review and Gemma's own second decision agreed that the generated menu text contained visible spelling errors: `Espreso` instead of `Espresso` and `Cocca` instead of `Cocoa`.
4. Gemma requested `edit_previous` against the exact first artifact id and asked only to correct those spellings while retaining the scene.
5. That second FLUX call was rejected as `HTTP 400, code 3030` before a revision artifact was returned.

The edit request shape itself was consistent with Cloudflare's documented FLUX.2 Klein contract: binary multipart `input_image_0`, and the adapter resizes only the provider-side reference to below 512x512. The same adapter successfully completed both the deterministic control-surface edit and the controller-driven edit in `cal-openai-003`, so this observation does not support a generic edit-transport defect.

Cloudflare's current official Workers AI error table documents codes such as `3036` for exhausted daily allocation and `3040` for capacity exhaustion, but does not document `3030`. Public Cloudflare repository issues show that code `3030` has been used for model-input rejection and that FLUX image models can return `3030` for aggressive false-positive content filtering on benign prompts. Because the live evidence intentionally stores only sanitized numeric diagnostics rather than arbitrary provider messages, the exact subreason for this specific `3030` is **not established**.

**Protocol decision:** do not rewrite or euphemize the calibration prompt to evade a possible provider filter and do not keep retrying until a favorable output appears. Record the provider rejection as calibration evidence.

Relevant current sources:

- https://developers.cloudflare.com/workers-ai/platform/errors/
- https://developers.cloudflare.com/workers-ai/models/flux-2-klein-4b/
- https://developers.cloudflare.com/changelog/post/2026-01-15-flux-2-klein-4b-workers-ai/
- https://github.com/cloudflare/workers-sdk/issues/13970
- https://github.com/cloudflare/cloudflare-docs/issues/21061

## Aggregate interpretation

Across the five controller-driven Cloudflare calibration tasks including the original `cal-openai-001` canary:

- the controller/tool contract is live-operational;
- the controller can inspect generated media and choose either `finish` or `edit_previous`;
- the image adapter has produced auditable generation and edit artifacts;
- zero-retry boundedness and credential redaction have held;
- text-heavy image tasks exposed real semantic failure modes despite successful transport;
- one valid correction request was rejected by the provider with an undocumented `3030` input-error family code;
- successful API completion must therefore remain distinct from task success or image quality.

This is exactly the boundary the research protocol intends to preserve. These Cloudflare outputs are useful for instrumentation hardening and for discovering failure modes, but they do not justify tuning the task corpus, ranking models, or freezing cross-provider normalization.

## Stop condition for the Cloudflare exploratory path

Further Cloudflare inference is not currently justified. The free path has already exercised:

- generation;
- exact-prior-artifact editing;
- controller visual review and finish/edit decisions;
- all temporary quality-tier pixel mappings;
- square and non-square dimensions;
- successful and failed revision behavior;
- safe HTTP failure provenance;
- provider rejection handling;
- zero-retry and credential-redaction boundaries.

Additional Cloudflare samples would primarily add model-quality observations from a provider that is not in the intended frozen v1 matrix. They would not satisfy the authoritative OpenAI/Google/BFL live-normalization gates. The next scientifically material live step therefore returns to the paid-provider calibration plan when legitimate access is available.
