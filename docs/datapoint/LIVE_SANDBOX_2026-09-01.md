# Datapoint live sandbox verification — 2026-09-01

Status: **PASS**

This note records the first credentialed Thrumely round trip against Datapoint's real API. It is an engineering integration check, not benchmark evidence and not a human-evaluation pilot.

## Verified path

On GitHub Actions run `33560977112`, Thrumely successfully:

1. authenticated with a repository secret;
2. uploaded two harmless synthetic SVG images through `POST /media`;
3. created one `comparison` job with `serving_environment: "sandbox"`;
4. created one `rating` job with `serving_environment: "sandbox"`;
5. read both job statuses;
6. rendered one task from each job through `GET /jobs/{job_id}/preview`;
7. observed `cost_credits: 0` for both sandbox jobs.

Observed summary:

- uploaded media: 2
- comparison preview tasks: 1
- rating preview tasks: 1
- comparison serving environment: `sandbox`
- rating serving environment: `sandbox`
- comparison cost credits: 0
- rating cost credits: 0
- production annotations collected: 0

Datapoint documents sandbox as a free test pool and documents preview as read-only: preview does not assign work, create a response, or consume credits.

References:
- https://trydatapoint.com/docs/api/jobs/
- https://trydatapoint.com/docs/api/media/

## Transport issue discovered during calibration

The first credentialed request was rejected at Datapoint's Cloudflare edge with Error 1010 when Python's default `urllib` User-Agent was used. A read-only `curl` request from the same GitHub-hosted environment and with the same repository secret returned HTTP 200, isolating the problem to the client fingerprint rather than credentials or network access.

Thrumely's Datapoint client now sends the explicit User-Agent:

`Thrumely/0.1 (+https://github.com/AKzar1el/thrumely)`

All Datapoint operations, including preview, use the same client transport and therefore the same authentication, official-host restriction, User-Agent, job-ID validation, and secret-redaction boundaries.

Cloudflare documents Error 1010 as an owner-configured block based on the client's browser signature:
- https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/

## Scientific boundary

This PASS establishes only that the Datapoint transport and task-rendering contract survive the real hosted API. It does **not** establish:

- image-provider calibration;
- production annotation quality;
- annotator agreement;
- pilot-derived variance or achieved power;
- final v1 task/model/provider freeze.

No Datapoint production credits were spent in this verification.
