# Modal Open-Weight Reference Calibration — 2026-09-02

**Status:** completed live reference calibration  
**Scientific class:** `OPEN_WEIGHT_REFERENCE_BACKEND`  
**Benchmark status:** calibration/reference evidence only; **not** frozen-v1 managed-provider evidence and **not** production benchmark evidence

## Purpose

This calibration added and exercised a self-hosted open-weight image backend so Thrumely can separate basic model/runtime behavior from managed-provider behavior without spending paid OpenAI, Google, or Black Forest Labs API credits.

The reference backend must not be interpreted as a fourth managed provider. It does not satisfy any OpenAI/Google/BFL normalization gate and must not enter the frozen-v1 provider matrix or production corpus.

## Pinned runtime

| Field | Value |
| --- | --- |
| Modal app | `thrumely-flux2-klein-reference` |
| Backend ID | `modal:flux-2-klein-4b-reference` |
| Model | `black-forest-labs/FLUX.2-klein-4B` |
| Model revision | `e7b7dc27f91deacad38e78976d1f2b499d76a294` |
| Model license | Apache-2.0 |
| GPU | NVIDIA L4 |
| Inference steps | 4 |
| Guidance scale | 1.0 |
| Modal SDK | 1.5.3 |
| PyTorch | 2.13.0 |
| Diffusers | 0.40.0 |
| Transformers | 5.16.1 |
| Accelerate | 1.14.0 |
| Hugging Face Hub | 1.29.0 |
| Safetensors | 0.8.0 |
| Idle policy | `min_containers=0` |
| Concurrency ceiling | `max_containers=1` |
| Automatic retries | zero on download/GPU functions; Modal Web Functions do not accept a retry policy |
| Endpoint auth | ephemeral Modal proxy key/secret; deployment API token is not used for inference |

Public reference points checked on 2026-09-02:

- BFL/Hugging Face model card: https://huggingface.co/black-forest-labs/FLUX.2-klein-4B
- Pinned model tree/revision: https://huggingface.co/black-forest-labs/FLUX.2-klein-4B/tree/e7b7dc27f91deacad38e78976d1f2b499d76a294
- Modal pricing: https://modal.com/pricing
- Modal deployed-app semantics: https://modal.com/docs/sdk/py/latest/App
- Modal proxy-token CLI/auth surface: https://modal.com/docs/cli/latest/workspace

The model card documents text-to-image and image-editing support and Apache-2.0 licensing. Modal's public Starter plan currently includes $30/month of free compute and meters actual resource use rather than idle time.

## Permanent compatibility corrections discovered live

The live deployment process exposed two runtime-contract defects that ordinary static tests could not reveal. Both were fixed with regression tests before live execution continued.

1. **Modal Web Function retry policy:** Modal 1.5.3 rejects `retries=0` on a FastAPI/Web Function because Web Functions do not support a retry policy. PR #26 removed the unsupported keyword only from the Web Function while retaining explicit `retries=0` on the model-download function and L4 inference class.
2. **Safetensors dependency:** Diffusers 0.40.0 and Transformers 5.16.1 require `safetensors>=0.8.0`; the original `<0.7` range was unsatisfiable. PR #27 pinned `safetensors==0.8.0` and added regression coverage.

Both fixes passed branch CI, independent pull-request CI, and fresh post-merge `main` CI before the final live calibration continued.

## Live execution provenance

### Primary bounded live run

- GitHub Actions run: https://github.com/AKzar1el/thrumely/actions/runs/33672956973
- Workflow head: `9fcf8bfbe3b451e11c3157677a92bc215830cac4`
- Permanent-code baseline contained in that ops head: `597b2c432e57a56966f45ddb5bc252956502e13b`
- Direct-control run ID: `modal-reference-controls-20260902T192652Z-d3bac9e6`
- Task-005 run ID: `calibration-20260902T192852Z-da029a72`
- Sanitized workflow artifact ID: `9863487997`
- Artifact digest: `sha256:49a2c4efd25633992218b16f3782dce63a1da89bf3fdbfd81434d516b502299e`

All workflow steps completed successfully, including proxy-token deletion.

### Visual-evidence replay

The first live artifact intentionally contained only sanitized JSON summaries and therefore could not support manual visual QA. A second bounded run reused the already-deployed app without rebuilding or redeploying it and preserved the generated PNGs.

- GitHub Actions run: https://github.com/AKzar1el/thrumely/actions/runs/33673961952
- Workflow head: `0e7f5e38f5a1b315fc63f4a2b11198b46942260b`
- Direct-control run ID: `modal-reference-controls-20260902T193318Z-ce08e0a2`
- Task-005 run ID: `calibration-20260902T193451Z-57e2c549`
- Sanitized workflow artifact ID: `9863707136`
- Artifact digest: `sha256:4db48ede4d514c5e83755041000490dfd962ea2a45b7e26a4a4fc3fd5a5f3f4c`

The artifact contained six hash-verified PNGs: four direct controls and two task-005 media calls. The temporary Actions artifact has finite retention; the immutable media hashes below are the durable provenance references.

## Direct reference-control results

All four fixed probes completed with the requested dimensions, pinned model revision, deterministic seeds, and `retry_count=0`.

| Probe | Seed | Dimensions | SHA-256 | End-to-end latency | Model inference time |
| --- | ---: | ---: | --- | ---: | ---: |
| standard square generate | 0 | 1024×1024 | `992131aff65961d64a207facb45c57aa26a1c1371635c82c277dc2645509bbbd` | 49.453 s | 20.420 s |
| standard square edit | 1 | 1024×1024 | `8ec90b9c1c033a88287cf155ed83f5f5555863186a16f5db477a8beb1479098c` | 18.680 s | 15.385 s |
| draft wide generate | 2 | 896×512 | `da0e5e51bee72a1df6420e50c91437a6c24fa68628311fc41f19596bf34d48a4` | 9.853 s | 8.777 s |
| high portrait generate | 3 | 1152×1728 | `f0c9e631dfdc45144122cd05d6f087cccca7eb70ca1762c17f80d22dd31103c1` | 15.449 s | 14.323 s |

The four output hashes were identical in the primary live run and the later visual-evidence replay. This is evidence of exact repeatability for these four seeded requests under this pinned deployment; it should not be generalized beyond the tested runtime/hardware/software state.

### Manual visual QA

The generation brief for `cal-openai-001` requires exactly three non-overlapping objects: blue square left, slightly larger red circle center, yellow triangle right.

Observed:

- all three generation probes satisfy the requested object count, colors, left/center/right order, non-overlap, and visibly larger center circle;
- the wide and portrait probes adapt composition to the requested canvas without introducing extra objects or text;
- the edit probe successfully changes the white background to a very light neutral gray while preserving the three-object composition;
- the edit is **not perfectly pixel-local**: subtle shading/edge-rendering changes appear on the shapes as well. The edit path is therefore operationally viable, but strict “change only the background” preservation should not be claimed from this result.

## Task-005 agent replay

Task `cal-openai-005` is the revision-sensitive menu-board task requiring exactly these three drink names and matching icons:

- `Espresso` + cup icon
- `Cocoa` + cocoa-bean icon
- `Mint Tea` + mint-leaf icon

The trajectory completed successfully as instrumentation:

- requested trajectories: 1
- completed trajectories: 1
- maximum media calls: 2
- observed media calls: 2
- automatic retries: 0
- infrastructure error: `null`
- controller: Cloudflare `@cf/google/gemma-4-26b-a4b-it`
- image backend: pinned Modal FLUX.2 Klein 4B reference backend
- both captured outputs: 1248×832 PNG

Captured image hashes:

- `b188fcfaafefc0acacdaca8b8fdb3e85e4d78dac43f8302955a828134cceb9ea`
- `e0f1879e1bbcc679efa85e2a31266d135ed40696c3e01c79af68c64bd2f6e1d5`

### Manual visual QA

Both images show a coherent warm cafe-counter scene with a framed menu board and the intended cup, cocoa-bean, and mint-leaf icon associations. No prices are shown.

However, **the exact-text task constraint is not satisfied**:

- one captured output reads `Esprese`, `Cocca`, and `Mint Tea`;
- the other reads `Espreso`, `Cocca`, and `Mint Tea`;
- both also render `Juniper Cup` on the board, which is additional board text beyond the three required drink names under a strict reading of “without any other text.”

The controller stopped after its allowed second media call. No third attempt, prompt mutation, or hidden retry was performed.

Therefore:

- **instrumentation/trajectory status:** success;
- **task-constraint quality status:** fail on exact typography/additional-text constraints.

This distinction is important. `completion_status=success` means the bounded trajectory completed without infrastructure failure; it is not a human-quality or task-correctness label.

## What the result does and does not establish

### Established

- The pinned open-weight model can be deployed reproducibly on Modal L4 infrastructure under the bounded Thrumely adapter.
- Generation and exact-prior-image edit transport both work.
- All direct normalized dimension mappings tested here are operational.
- The four seeded direct probes were byte-for-byte reproducible across two separate live runs.
- A Cloudflare Gemma controller can complete a two-media-call task-005 trajectory against the Modal reference backend without provider/infrastructure rejection.
- Exact text remains a substantive weakness on task 005 despite the second allowed media call.

### Not established

- This does **not** prove why any managed provider accepted, rejected, or behaved differently on a corresponding task.
- This does **not** pass OpenAI, Google, or BFL managed-provider normalization gates.
- This does **not** justify substituting Modal for a frozen-v1 provider.
- This does **not** promote any Modal trajectory into the production benchmark corpus.
- This does **not** establish perfect edit preservation; the manual edit review observed small non-background rendering changes.

The strongest defensible interpretation is that task 005 is executable through a self-hosted open-weight path, while its exact typography constraints remain difficult. Managed-provider causality remains unresolved until the corresponding managed-provider gates are executed.

## Billing observations

Billing data was captured as numeric-only sanitized observations because Modal accounting can update asynchronously.

### Primary run capture

Immediately after the primary live run, the billing summary reported:

- metered cost: `$0.03`
- credits adjustment: `-$0.03`
- billed cost: `$0.00`

A later pre-run observation had already moved the aggregate day-to-date metered amount higher, so `$0.03` must not be interpreted as a final exact attribution for the primary run alone.

### Visual-evidence replay window

Before the visual replay:

- top-line metered cost: `$0.09`
- credits adjustment: `-$0.09`
- billed cost: `$0.00`
- deployed-apps counter: `$0.08440307`
- ephemeral-apps counter: `$0.01008215`

After the visual replay:

- top-line metered cost: `$0.13`
- credits adjustment: `-$0.13`
- billed cost: `$0.00`
- deployed-apps counter: `$0.11527024`
- ephemeral-apps counter: `$0.01008215`

The detailed deployed-apps counter increased by **`$0.03086717`** during the visual-evidence replay. The top-line values are rounded and moved from `$0.09` to `$0.13`. All observed metered cost remained covered by credits and the captured billed cost stayed **`$0.00`**.

Because the day also contained failed pre-inference deployment attempts and Modal accounting is not instantaneous, aggregate daily totals should not be retroactively assigned to one individual request set without provider-level billing attribution.

## Credential and evidence hygiene

- Modal deployment credentials were stored only as GitHub Actions repository secrets.
- Inference used separate ephemeral Modal proxy credentials.
- The proxy token from the primary run was deleted successfully in the workflow's `always()` cleanup.
- The proxy token from the visual-evidence run was also deleted successfully.
- Sanitized JSON evidence contains no endpoint, proxy credential, Cloudflare credential, authorization header, or known credential-prefix marker.
- The six preserved PNGs contain only PNG structural/image-data chunks (`IHDR`, `IDAT`, `IEND`) and no textual metadata chunks (`tEXt`, `zTXt`, `iTXt`).
- All six media byte lengths and SHA-256 digests were independently revalidated against the uploaded media index.

## Scientific boundary / next action

The Modal work closes the **open-weight reference instrumentation** question only.

The frozen-v1 managed-provider calibration plan remains unchanged: paid OpenAI/Google/BFL live normalization gates are still separate prerequisites, and their evidence must remain provider-specific. Modal results may be cited as reference context but must not be pooled into managed-provider acceptance decisions or benchmark scores.
