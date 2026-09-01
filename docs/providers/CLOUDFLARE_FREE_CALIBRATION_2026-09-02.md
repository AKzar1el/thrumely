# Zero-cost Cloudflare Workers AI calibration path

**Recorded:** 2026-09-02  
**Status:** calibration/instrumentation only; not benchmark evidence and not part of the frozen v1 provider matrix.

This path exists to exercise Thrumely's real hosted controller -> image backend -> visual review -> finish/edit trajectory without requiring paid OpenAI, Google, Anthropic, or BFL API balance.

## Fixed calibration identities

- Controller: Cloudflare Workers AI `@cf/google/gemma-4-26b-a4b-it`
- Image backend: Cloudflare Workers AI `@cf/black-forest-labs/flux-2-klein-4b`
- Logical backend ID exposed to the controller: `cloudflare:flux-2-klein-4b`
- Maximum controller calls per trajectory: 2
- Maximum media calls per trajectory: 2
- Maximum inference transport requests per successful trajectory: 4
- Automatic benchmark retries: 0

Cloudflare documents Gemma 4 26B A4B as supporting vision, function calling, and reasoning. Thrumely uses Cloudflare's OpenAI-compatible `/v1/chat/completions` surface with benchmark-owned `generate_or_edit` and `finish` tools. `parallel_tool_calls` is disabled and `tool_choice="required"` is used so the controller must produce one explicit action.

Cloudflare documents FLUX.2 Klein 4B as a combined generation/editing model. Its REST input is multipart form data even for text-only generation. Edit/reference images are binary multipart fields named `input_image_0` through `input_image_3`, and Cloudflare currently requires all reference images to be smaller than 512x512. Thrumely therefore downsizes only the provider-side edit reference to at most 480x480 while retaining the original full-size generated artifact in the trajectory bundle and giving the controller the full-size artifact for its review decision.

That edit-reference resize is a **provider transport constraint**, not a claim of equivalence to the final candidate backends. A Cloudflare trajectory that uses `edit_previous` can validate the orchestration and evidence path, but it cannot establish cross-provider edit-quality comparability.

## Cost boundary

Cloudflare Workers AI currently includes 10,000 Neurons per day at no charge on Workers Free, resetting at 00:00 UTC. This calibration path is intended to stay within that free allocation. The repository does not hard-code a monetary guarantee because model pricing and free-tier policy are external, time-varying provider facts.

Official sources rechecked for this implementation:

- https://developers.cloudflare.com/ai/models/%40cf/google/gemma-4-26b-a4b-it/
- https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/
- https://developers.cloudflare.com/workers-ai/models/flux-2-klein-4b/
- https://developers.cloudflare.com/changelog/post/2026-01-15-flux-2-klein-4b-workers-ai/
- https://developers.cloudflare.com/workers-ai/platform/pricing/

## Credential handling

The implementation reads only runtime environment variables:

```text
CLOUDFLARE_API_TOKEN
CLOUDFLARE_ACCOUNT_ID
```

Never place either value in Git history, task files, CLI arguments, result metadata, or public logs. Tests use fake values and injected transports. The public request/response evidence excludes bearer headers and replaces returned base64 image payloads with `[MEDIA_BYTES_STORED_SEPARATELY]`.

## Dry-run preflight

The CLI is dry-run by default and does not require credentials, create an output directory, import a provider SDK, or make a network request:

```bash
python -m thrumely.cloudflare_calibration \
  --tasks calibration/tasks/openai-smoke.json \
  --task-id cal-openai-001 \
  --output results/cloudflare-calibration
```

The `cal-openai-*` IDs are historical names for the shared calibration-only prompt set; using the same prompt across provider calibration paths is intentional. These tasks remain excluded from the future production corpus.

## One-task live canary

Install the optional image-resize dependency before a live trajectory so a second-call edit can satisfy Cloudflare's <512x512 reference-image constraint:

```bash
python -m pip install -e '.[test,cloudflare]'
```

Set the two runtime environment variables outside the repository, then explicitly authorize exactly one selected calibration task:

```bash
python -m thrumely.cloudflare_calibration \
  --tasks calibration/tasks/openai-smoke.json \
  --task-id cal-openai-001 \
  --output results/cloudflare-calibration \
  --execute-live
```

Do not batch all five prompts on the first live attempt. Inspect the first bundle before authorizing another task.

## PASS criteria for the first live trajectory

The first live trajectory is transport/instrumentation PASS only if all of the following hold:

1. the requested Cloudflare controller and image model identities are returned or otherwise unambiguously recorded;
2. controller call 1 yields exactly one valid `generate_or_edit` action;
3. one image is returned, decoded, dimension-validated, content-addressed, and stored separately from JSON metadata;
4. controller call 2 receives the full current image and yields exactly one `finish`, `generate`, or `edit_previous` action;
5. a second media call occurs only when the controller selects it;
6. the trajectory never exceeds two controller calls or two media calls;
7. no API token, Authorization header, raw image base64, or private reasoning appears in the public evidence bundle;
8. terminal provider/controller failures are represented as typed trajectory failures rather than hidden retries;
9. no Datapoint job is created and no production-corpus/freeze state changes.

A PASS establishes only that the free Cloudflare path can exercise the real Thrumely trajectory contract. It does **not** establish that Cloudflare quality tiers are equivalent to OpenAI/Google/BFL controls, that Gemma is comparable to the intended final controllers, or that the v1 provider/model matrix is ready to freeze.
