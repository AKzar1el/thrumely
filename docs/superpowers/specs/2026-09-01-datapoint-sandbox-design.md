# Datapoint Sandbox Integration Design

## Status

Approved roadmap work. This design implements the existing `RESEARCH_SPEC.md` Datapoint measurement gate while the hosted image-provider calibration remains postponed for lack of funded API access.

## Goal

Build a zero-credit Datapoint integration path that can validate Thrumely's human-evaluation payloads, media upload contract, job metadata, result parsing, and public export against Datapoint's `sandbox` serving environment without creating production jobs or spending grant credits.

## Current platform facts verified 2026-09-01

- Datapoint jobs accept `serving_environment: "sandbox"`; sandbox is documented as a free test pool with no credits charged.
- `rating` supports a single image subject and a numeric response scale, matching the planned 1–5 instruction-faithfulness endpoint.
- Native `comparison` presents exactly two same-type candidates and collects an A/B forced choice. Datapoint's reported `tie` is an aggregate exact-vote tie, not a per-annotator no-preference response.
- Comparison candidate display order is randomized for annotators while A/B continues to map to submission order.
- Media can be uploaded and referenced using durable `dp://` URIs.
- Raw responses are available separately from aggregate results.

References:
- https://trydatapoint.com/docs/api/jobs/
- https://trydatapoint.com/docs/task-types/comparison/
- https://trydatapoint.com/docs/task-types/rating/
- https://trydatapoint.com/docs/media/

## Methodology decision: secondary pairwise becomes forced choice

The pre-production research spec currently describes pairwise responses as `Image A`, `Image B`, or `Tie / no meaningful preference`. Datapoint's native comparison task does not expose a per-annotator tie option.

For v1, use Datapoint's native A/B forced-choice comparison instead of manufacturing a composite image and multiple-choice task. This preserves native side-by-side rendering, randomized display order, and original media quality. Pairwise preference remains a secondary endpoint. The primary 1–5 instruction-faithfulness rating is unchanged.

The authoritative research spec must be amended before production freeze so it does not claim a response option the measurement platform cannot collect.

## Architecture

### 1. Protocol builders

`src/thrumely/datapoint_protocol.py` owns benchmark-visible payload construction.

It exposes:

- `build_pairwise_sandbox_job(...) -> dict[str, object]`
- `build_rating_sandbox_job(...) -> dict[str, object]`

Both functions always emit `serving_environment: "sandbox"` and `max_responses_per_datapoint: 5` by default. There is no parameter that can switch these helpers to `prod` or `all`.

Pairwise payload:

- task type `comparison`;
- exact benchmark instruction-faithfulness/preference wording;
- two image candidates per datapoint;
- original user instruction in `context` for provenance, even though the comparison job-level question is the visible prompt;
- stable Thrumely metadata retained outside Datapoint payloads so result rows can be rejoined by `datapoint_index`.

Rating payload:

- task type `rating`;
- response scale `[1, 2, 3, 4, 5]`;
- endpoint labels consistent with `RESEARCH_SPEC.md` anchors;
- one image subject per datapoint;
- instruction includes `{context}` so the original task is shown alongside the image.

### 2. Dependency-free API client

`src/thrumely/datapoint_client.py` uses an injectable transport and the Python standard library only.

Capabilities:

- upload image media with multipart `POST /media`;
- create a sandbox job with `POST /jobs`;
- fetch job status;
- fetch aggregate results;
- fetch raw responses.

Hard safety constraints:

- reject any job payload whose `serving_environment` is not exactly `sandbox`;
- never log or export `X-API-Key`;
- sanitize external error payloads before exposing them publicly;
- treat unknown response fields as forward-compatible extras;
- preserve Datapoint job IDs, pricing fields, serving environment, and response counts when returned.

### 3. Result normalization

`src/thrumely/datapoint_results.py` converts Datapoint response envelopes into stable benchmark-owned records without discarding the raw sanitized response.

Normalized pairwise fields include:

- job ID;
- datapoint index;
- A votes / B votes;
- consensus;
- total responses;
- confidence / agreement rate;
- media IDs in submitted A/B order.

Normalized rating fields include:

- job ID;
- datapoint index;
- mean / median;
- distribution;
- total responses;
- weighted fields when present.

Raw annotator exports retain only fields needed for audit/statistics. Direct identifiers do not exist in the API, but location detail more granular than country is excluded from the public-normalization helper by default.

### 4. Offline sandbox fixture

`src/thrumely/datapoint_sandbox.py` provides a credential-free round-trip smoke using a fake transport and synthetic `dp://` media references. It must generate both one comparison job and one rating job, then parse fake status/results/raw-response envelopes.

This is not a real Datapoint sandbox run. Its purpose is to prove the Thrumely-owned client/protocol/result contracts before a `DATAPOINT_KEY` is available.

### 5. Real sandbox command

The same module exposes an opt-in CLI path that requires `DATAPOINT_KEY` and refuses to run if the key is absent. It may upload supplied local synthetic image fixtures and submit only `serving_environment: sandbox` jobs.

No real job is executed in normal CI.

## Testing

TDD coverage must include:

- pairwise payload is forced-choice comparison with exactly two image candidates;
- rating payload carries the five-point scale and `{context}`;
- every builder emits `sandbox` and cannot be configured to `prod`;
- client rejects manually crafted `prod` / `all` jobs before transport invocation;
- API key is present in request headers but absent from exceptions and public payloads;
- media multipart upload is deterministic enough for fake-transport assertions;
- aggregate comparison/rating parsing works with documented fields plus unknown extras;
- raw-response public normalization strips city/region and keeps anonymized annotator ID/country/response timing;
- offline fake round trip exercises create/status/results/responses for both task types;
- existing provider/corpus/offline tests remain green.

## CI gate

Normal CI must add:

```bash
python -m thrumely.datapoint_sandbox --offline
```

It must require no credentials and perform no network calls.

## Explicit non-goals

- no production Datapoint jobs;
- no paid pilot;
- no final 100-task freeze;
- no provider-generated benchmark media;
- no claims about real annotator reliability;
- no change to the primary human instruction-faithfulness endpoint;
- no attempt to emulate per-annotator pairwise ties with composite media.
