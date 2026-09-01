# Cloudflare control-surface live calibration result

**Recorded:** 2026-09-02  
**Status:** PASS for provider transport/control instrumentation only. This is not benchmark evidence and does not establish cross-provider quality-tier equivalence.

## Purpose

After the first controller-driven Cloudflare canary proved hosted generation plus visual review/finish, this bounded follow-up exercised the image adapter paths that had not yet been observed live: exact-prior-artifact editing, non-square dimensions, and all three temporary Thrumely quality-tier mappings.

The runner is deliberately **not** an agent trajectory. It executes four independent provider-control probes, each with a one-call environment budget, so it does not alter or bypass the benchmark's two-media-action trajectory ceiling.

## Execution identity

- repository base before live runner: `1929d7243c91fc2e283e0c7905a7cdfc46d06a2c`
- disposable live-run commit: `2910825b8104d967f454269a61a31da981b955f5`
- GitHub Actions run: `33572243332`
- run id: `cloudflare-controls-20260901T234307Z-509691ab`
- provider: `cloudflare`
- logical backend: `cloudflare:flux-2-klein-4b`
- model: `@cf/black-forest-labs/flux-2-klein-4b`
- task: calibration-only `cal-openai-001`
- requested provider executions: 4
- completed provider executions: 4
- successful provider executions: 4
- maximum transport requests: 4
- observed retries: 0 on every probe
- dimension validation: PASS on every probe
- evidence credential scan: PASS

## Observed probes

| Probe | Operation | Tier / aspect | Expected and observed size | Latency | Artifact |
| --- | --- | --- | --- | ---: | --- |
| `standard-square-generate` | generate | standard / 1:1 | 1024x1024 | 14.667711775 s | `25ba09baa33f441b7ec4167e1930db602365802f66db0f83a4458b686afbd7da` (169,387 bytes) |
| `standard-square-edit` | edit previous | standard / 1:1 | 1024x1024 | 3.778836639 s | `782d17058ff3c9aea4c43706d6bdd5d6c220a903bbaf18382a51c30403ceef6e` (275,345 bytes) |
| `draft-wide-generate` | generate | draft / 16:9 | 896x512 | 12.542289838 s | `f0d6f012334725aaca9782ad33283b20ad7094765dedbe2b72e0908cc7252544` (83,917 bytes) |
| `high-portrait-generate` | generate | high / 2:3 | 1152x1728 | 13.513499582 s | `4aa5a64950307279d3e317da753b1159f1338cb16f6c79f68a35e3e28336ba7c` (144,133 bytes) |

The edit request referenced the exact first generated artifact id:

`media:25ba09baa33f441b7ec4167e1930db602365802f66db0f83a4458b686afbd7da`

The provider-side edit reference was transported through Cloudflare's binary `input_image_0` path after the adapter's documented sub-512px reference resize. The stored full-size first artifact remained unchanged.

## Observable image review

Manual inspection was limited to the calibration constraints rather than subjective image-quality scoring:

- the standard generation produced the requested blue square, larger red circle, and yellow triangle in left-to-right order on white;
- the edit retained the same three-object composition and changed the white background to a light neutral gray, with no obvious extra object or text introduced;
- the draft-wide generation produced the same requested object set and ordering in the 16:9 canvas;
- the high-portrait generation produced the same requested object set and ordering in the 2:3 canvas.

This is sufficient to show that the live edit path is not merely accepting a multipart request: the supplied prior image materially influenced the returned result in the intended direction.

## Evidence and cost boundary

The uploaded GitHub Actions artifact was `cloudflare-control-surface-33572243332`, artifact id `9825364777`, final ZIP size 655,243 bytes, SHA-256 `8aaaf4ecfe52505c7a26be055ccd2361ae2f49b7db10aae335b86c94669142ec`. It contained four stored media artifacts plus the task/configuration/results/manifest evidence files.

Persisted request endpoints replace the account identifier with `{ACCOUNT_ID}`. Image payloads are represented as `[MEDIA_BYTES_STORED_SEPARATELY]`. The live validator checked the evidence files for the actual runtime token, actual account id, `Authorization`, `Bearer `, and `cfut_`; none were present.

The FLUX responses exposed neither a request id nor usage accounting in this path (`request_id=null`, `usage={}`, `cost_usd=null`). Therefore this record does **not** infer exact Neuron consumption or monetary cost from the response bundle. The calls were intentionally executed under Cloudflare Workers AI's current recurring free allocation, but that provider policy is external and time-varying.

## Scientific conclusion

**PASS:** Cloudflare FLUX.2 Klein's live generation, exact-prior-artifact edit transport, draft/standard/high dimension mappings, non-square dimensions, media decoding/storage, evidence redaction, and zero-retry bounded execution all work through the Thrumely adapter.

This result strengthens the instrumentation and gives us a concrete warning about the meaning of `quality_tier`: on Cloudflare these labels are currently implemented as **pixel-budget mappings**, not a native provider quality parameter. That supports the existing research plan's requirement to validate the abstraction separately on OpenAI, Google, and BFL before freezing it. Nothing in this calibration establishes that Cloudflare's draft/standard/high outputs are scientifically equivalent to the final paid-provider controls.

Official provider contracts relevant to this run:

- https://developers.cloudflare.com/workers-ai/models/flux-2-klein-4b/
- https://developers.cloudflare.com/workers-ai/platform/pricing/
