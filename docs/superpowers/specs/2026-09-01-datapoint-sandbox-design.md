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
- Datapoint explicitly documents `{context}` substitution for rating. Its comparison contract guarantees the job-level `instruction` is shown, but does not document per-datapoint context substitution for comparison.
- Media can be uploaded and referenced using durable `dp://` URIs.
- Aggregate `/results` and raw `/responses` are paginated. Raw responses cap `per_page` at 1000 and must be iterated using the returned `total_pages`, because pages are grouped by annotator and can contain more rows than `per_page`.

References:
- https://trydatapoint.com/docs/api/jobs/
- https://trydatapoint.com/docs/task-types/comparison/
- https://trydatapoint.com/docs/task-types/rating/
- https://trydatapoint.com/docs/media/

## Methodology decision: secondary pairwise becomes forced choice

The pre-production research spec originally described pairwise responses as `Image A`, `Image B`, or `Tie / no meaningful preference`. Datapoint's native comparison task does not expose a per-annotator tie option.

For v1, use Datapoint's native A/B forced-choice comparison instead of manufacturing a composite image and multiple-choice task. This preserves native side-by-side rendering, randomized display order, and original media quality. Pairwise preference remains a secondary endpoint. The primary 1–5 instruction-faithfulness rating is unchanged.

To guarantee that pairwise annotators see the original user request without relying on undocumented comparison-context behavior, create **one Datapoint comparison job per benchmark task**. Embed that task's exact request in the visible job-level instruction and batch all predeclared A/B pairs for the task as datapoints in that job.

## Architecture

### 1. Protocol builders

`src/thrumely/datapoint_protocol.py` owns benchmark-visible payload construction.

It exposes:

- `build_pairwise_sandbox_job(name, user_instruction, pairs, max_responses_per_datapoint=5) -> dict[str, object]`
- `build_rating_sandbox_job(name, items, max_responses_per_datapoint=5) -> dict[str, object]`

Both functions always emit `serving_environment: "sandbox"` and `max_responses_per_datapoint: 5` by default. There is no parameter that can switch these helpers to `prod` or `all`.

Pairwise payload:

- task type `comparison`;
- one Datapoint comparison job per benchmark task;
- exact original user instruction embedded in that job's visible `instruction`;
- all predeclared A/B pairs for the task batched as datapoints within that job;
- two image candidates per datapoint;
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
- fetch individual result/response pages;
- fetch **all** aggregate result pages without first-page truncation;
- fetch **all** raw-response pages by following Datapoint's returned `total_pages` value.

Hard safety constraints:

- reject any job payload whose `serving_environment` is not exactly `sandbox`;
- pin requests to the official Datapoint API base URL;
- never log or export `X-API-Key`;
- remove the raw API key even if an upstream error body echoes it under an unrelated field;
- reject unsafe job IDs before constructing request paths;
- reject multipart filenames containing header-unsafe characters;
- sanitize external error payloads before exposing them publicly;
- fail loudly on malformed or non-progressing pagination rather than returning partial data;
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

`src/thrumely/datapoint_sandbox.py` provides a credential-free round-trip smoke using a fake transport and synthetic `dp://` media references. It generates both one comparison job and one rating job, then parses fake status/results/raw-response envelopes through the same fetch-all pagination paths intended for the pilot.

This is not a real Datapoint sandbox run. Its purpose is to prove the Thrumely-owned client/protocol/result contracts before a `DATAPOINT_KEY` is available.

### 5. Real sandbox execution gate

This zero-cost slice intentionally enables only the credential-free `--offline` contract. A real Datapoint sandbox round trip is the next measurement check once `DATAPOINT_KEY` is available in a suitable execution environment. That future path must reuse the same sandbox-only client boundary and may not expose a `prod` or `all` switch.

No real job is executed in normal CI.

## Testing

TDD coverage includes:

- pairwise payload is forced-choice comparison with exactly two image candidates and the task request in the job-level instruction;
- rating payload carries the five-point scale and `{context}`;
- every builder emits `sandbox` and cannot be configured to `prod`;
- client rejects manually crafted `prod` / `all` jobs before transport invocation;
- API key is present in request headers but absent from exceptions and public payloads;
- HTTP error payloads cannot echo the API key into exceptions;
- unsafe job IDs, non-Datapoint API bases, and multipart filenames are rejected before transport;
- fetch-all result pagination continues until `total_results` is satisfied;
- fetch-all raw-response pagination follows returned `total_pages` rather than deriving page count from response totals;
- aggregate comparison/rating parsing works with documented fields plus unknown extras;
- raw-response public normalization strips city/region and keeps anonymized annotator ID/country/response timing;
- offline fake round trip exercises create/status/fetch-all-results/fetch-all-responses for both task types;
- existing provider/corpus/offline tests remain green.

## CI gate

Normal CI adds:

```bash
python -m thrumely.datapoint_sandbox --offline
```

It requires no credentials and performs no network calls.

## Explicit non-goals

- no production Datapoint jobs;
- no paid pilot;
- no final 100-task freeze;
- no provider-generated benchmark media;
- no claims about real annotator reliability;
- no change to the primary human instruction-faithfulness endpoint;
- no attempt to emulate per-annotator pairwise ties with composite media.
