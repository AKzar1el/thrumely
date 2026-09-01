# Datapoint one-response production canary — 2026-09-01

## Status

Completed successfully. This was an engineering/measurement canary, not benchmark evidence and not a methodology/power pilot.

## Purpose

Validate the first paid Datapoint production round trip after the free sandbox transport/rendering check, while bounding financial exposure to one human response.

## Configuration

- task type: comparison;
- serving environment: `prod`;
- datapoints: 1;
- maximum responses per datapoint: 1;
- dimensions/chains: none;
- audience targeting: none;
- client-side creation cap: 25 credits;
- media: two synthetic SVG images authored for this canary;
- prompt: `Create a red square centered on a white canvas.`;
- candidate A: centered red square on white;
- candidate B: centered red circle on white.

The canary guard refuses any payload that is not exactly one production comparison datapoint with one response, no targeting, and no dimensions/chains. It also automatically cancels a newly created canary if Datapoint reports an estimated cost above the configured cap or an inconsistent pricing envelope.

## Observed Datapoint result

GitHub Actions run: `33562622052`

Datapoint job: `job_7900c00278c9`

- status: `completed`;
- serving environment: `prod`;
- total responses: 1;
- effective rate: 5 credits/response;
- base rate: 5 credits/response;
- demographic surcharge: 0;
- geographic surcharge: 0;
- priority surcharge: 0;
- estimated cost at creation: 5 credits;
- final cost: 5 credits;
- refundable credits after completion: 0;
- observed response: `A`;
- expected controlled answer: `A`;
- aggregate consensus: `A`;
- aggregate confidence: 1.0.

No annotator identifier or small-cell geography is retained in this public provenance note.

## Balance check

A separate read-only balance request was run immediately afterward using Datapoint's documented `GET /billing/balance` endpoint.

GitHub Actions run: `33562872651`

Observed balance after the canary:

- available credits: 500,095;
- reserved credits: 0;
- total purchased credits: 0;
- granted credits: 500,100.

The five-credit difference between lifetime granted credits and current available credits matches the canary charge. The observed grant balance is consistent with the external grant award plus signup/promotional credits, but this repository does not assume a universal dollar-to-credit conversion.

At the observed 5-credit basic rate, an approximately 200-response tiny pilot would require approximately 1,000 raw credits before any targeting surcharge. With the observed balance, that is well inside the research specification's reserve constraint. This is a budget observation only; scientific stage gates still control whether a larger pilot may launch.

## Boundaries

This canary establishes only that:

1. real production media upload/job creation/status/results/responses work with the Thrumely Datapoint client;
2. the account's observed untargeted basic rate is 5 credits per response for this job;
3. exactly one capped human comparison response can be collected and parsed;
4. the current grant balance can be read without additional spend.

It does **not** establish:

- provider/model calibration;
- human reliability or agreement from a meaningful sample;
- wording quality across task families;
- pilot variance or statistical power;
- final provider normalization;
- final task-corpus freeze;
- production benchmark validity.

## Current Datapoint documentation used

- Jobs: https://trydatapoint.com/docs/api/jobs/
- Billing: https://trydatapoint.com/docs/billing/

The temporary secret-backed GitHub workflow used for the canary and balance read was removed before integration. The repository contains no Datapoint API key.
