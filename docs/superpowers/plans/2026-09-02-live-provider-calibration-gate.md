# Live Provider Calibration Gate

> **Status:** authoritative continuation plan as of 2026-09-02. This plan supersedes the live-execution sequencing in Task 6 of `2026-09-01-openai-calibration.md`; it does not rewrite the earlier implementation history.

**Goal:** Convert Thrumely from static/fake-client provider compatibility to empirically verified live-provider normalization with the smallest defensible paid exposure, while preserving the frozen scientific boundaries in `RESEARCH_SPEC.md`.

**Current baseline:**

- Datapoint production transport, one-response billing, collection, and parsing were already verified separately. Datapoint is not the current blocker.
- The candidate task pool remains unfrozen and must not be tuned against production-condition outputs.
- OpenAI, Google, and BFL image adapters exist behind the benchmark-owned normalized media contract; Anthropic and OpenAI controller adapters exist behind the same controller semantics.
- Static normalization passes only at the schema level. It does not establish provider comparability.
- PR #12 (`8d65f8fc2dab110d76ef5ee21cf28074abf4da17`) hardened the OpenAI live calibration path so the CLI is dry-run by default, requires exactly one `cal-*` task, requires explicit `--execute-live`, retains the two-media-call ceiling, and disables OpenAI SDK automatic retries (`max_retries=0`).
- No live image-provider calibration result has yet been promoted into benchmark evidence.

## Non-negotiable scientific boundaries

1. Calibration prompts remain under `calibration/`; they are never promoted into the frozen v1 corpus.
2. Calibration output is instrumentation/normalization evidence only. It is not evidence that one provider, model, controller, or chooser policy is better.
3. No provider-specific capability, grounding tool, search tool, hidden retry, or quality-enhancement knob may be exposed asymmetrically to a controller.
4. Failures, refusals, moderation outcomes, malformed responses, and timeouts are data. Do not silently retry, substitute another backend, or repair outputs after the fact.
5. The benchmark-owned maximum remains two media actions per trajectory. Transport-level automatic retries must remain disabled wherever the SDK permits them; explicit retries, if ever introduced, require a separately versioned protocol decision and provenance field.
6. Secrets stay in trusted runtime configuration only and never enter Git, manifests, raw public requests, logs committed to the repository, or test fixtures.
7. Do not freeze provider/model identities, the 100-task corpus, quality-tier semantics, or the production matrix until every gate below that applies to them is explicitly passed.
8. A paid call requires deliberate live authorization. Zero-cost/preflight commands must remain the default.

## Current access and cost facts to re-check at execution time

These facts were reverified from first-party sources on 2026-09-02 and are operational facts, not frozen benchmark constants:

- OpenAI `gpt-5.6-sol`: Free API tier not supported; current standard price shown as $4/M input and $20/M output tokens. Source: https://developers.openai.com/api/docs/models/gpt-5.6-sol
- OpenAI `gpt-image-2` / snapshot `gpt-image-2-2026-04-21`: Free API tier not supported. Source: https://developers.openai.com/api/docs/models/gpt-image-2
- Google `gemini-3.1-flash-image`: Free API tier not available. Current standard image-equivalent prices are documented as approximately $0.045 for 0.5K, $0.067 for 1K, $0.101 for 2K, and $0.151 for 4K. Source: https://ai.google.dev/gemini-api/docs/pricing
- BFL `flux-2-pro`: live API use requires an account/API key and positive prepaid credit balance. Reverify exact per-megapixel generation/edit pricing immediately before live use. Sources: https://docs.bfl.ai/ and https://docs.bfl.ai/llms.txt
- Anthropic `claude-opus-5`: active; current standard price is $5/M input and $25/M output tokens, with tentative retirement not sooner than 2027-07-24. Sources: https://platform.claude.com/docs/en/about-claude/pricing and https://platform.claude.com/docs/en/about-claude/model-deprecations

If a first-party page changes, the live-time fact wins. Record the new verification date and source before freezing anything.

---

## Gate 0 — Zero-cost repository and access preflight

**Purpose:** prove that a live call cannot be launched accidentally and identify which provider accounts can actually execute the next canary without buying anything automatically.

### Required checks

- Run the complete ordinary CI/offline gate on the exact intended commit.
- Run static normalization and require the explicit `STATIC_ONLY` warning.
- Run the OpenAI calibration CLI without `--execute-live` on exactly `cal-openai-001`; require `DRY_RUN_ONLY`, one selected task, and `maximum_media_calls=2`.
- Confirm the live runner creates no output directory during dry-run.
- Confirm the OpenAI controller and image provider instantiate SDK clients with automatic retries disabled.
- Perform only read-only account/balance/tier checks that are already legitimately available. Do not purchase credits, enable billing, create jobs, or make inference requests as part of Gate 0.
- Record only non-secret operational state: provider accessible/unavailable, balance sufficient/insufficient, account verification blocker, and date checked.

### Gate 0 pass condition

All zero-cost checks pass and at least one intended live provider path has deliberately available paid API access. If none does, stop here; the correct state is `LIVE_CALIBRATION_BLOCKED_BY_PROVIDER_ACCESS`, not an improvised browser/manual substitute.

---

## Gate 1 — Single-task OpenAI end-to-end canary

**Purpose:** validate one real controller → benchmark-owned tool decision → GPT Image request → artifact → controller review/stop-or-revise round trip before expanding any hosted calibration.

### Zero-cost preflight command

```bash
python -m thrumely.calibration \
  --tasks calibration/tasks/openai-smoke.json \
  --task-id cal-openai-001 \
  --output results/calibration
```

Expected: a `DRY_RUN_ONLY` JSON response. No SDK import is required, no key is required, no output bundle is created, and no hosted call occurs.

### Deliberately authorized live command

Only after paid API access is intentionally available:

```bash
python -m pip install -e '.[test,openai]'
python -m thrumely.calibration \
  --tasks calibration/tasks/openai-smoke.json \
  --task-id cal-openai-001 \
  --output results/calibration \
  --execute-live
```

### Hard bounds

- exactly one calibration task;
- one controller decision before the first image;
- at most two media actions total;
- one controller review decision after the first image;
- no SDK automatic retries;
- no Datapoint job;
- no production candidate task;
- no automatic expansion to `cal-openai-002` through `005`.

### Inspect before any second live task

Verify the generated bundle manually/programmatically before further spend:

- `manifest.json` is `live-calibration` and records exactly one requested trajectory;
- `configuration.json` contains the intended controller/provider/model identities and hashes, but no secret material;
- `tasks.json` contains only the selected calibration task;
- `trajectories.jsonl` has exactly one trajectory with explicit success/error state;
- each media action records the actual provider/model, request ID when available, usage when available, latency, error/moderation state, and `retry_count=0`;
- raw response metadata does not duplicate base64 media bytes;
- stored media hashes and dimensions verify;
- controller observable output contains no hidden reasoning material;
- actual provider response shape still matches the adapter assumptions;
- any unexpected API behavior becomes a reproduced failing test before the adapter is changed.

### Gate 1 pass condition

One live OpenAI calibration task completes or fails in a fully auditable, protocol-consistent way. A provider failure can still pass the instrumentation gate if the failure is represented correctly; it does not pass provider usability if generation never succeeds.

Do **not** run the remaining four OpenAI calibration prompts automatically. Expansion is a separate Gate 2 decision.

---

## Gate 2 — Minimal OpenAI control-surface calibration

**Purpose:** determine whether the proposed normalized aspect/quality/edit controls behave as represented, not whether image quality is good.

Only enter after Gate 1 artifact inspection passes.

Use calibration-only prompts and the smallest matrix that exercises each distinct semantic control. Prefer reusing one neutral prompt where possible so control changes are interpretable.

Minimum evidence required before OpenAI normalization can be marked live-verified:

- generation works at the normalized standard setting;
- `edit_previous` consumes the exact prior artifact and produces a new auditable artifact;
- at least one non-square aspect-ratio mapping returns dimensions consistent with the requested benchmark mapping;
- the `draft`, `standard`, and `high` mappings are accepted by the live API and their actual output metadata/dimensions/usage are recorded;
- refusal/moderation behavior is captured explicitly if triggered accidentally by a rights-clean calibration prompt;
- measured cost/usage is recorded as observation, not frozen as a benchmark constant.

Do not human-rank these outputs and do not select mappings because one looks better. This gate asks whether controls are semantically usable and auditable.

---

## Gate 3 — Google and BFL transport canaries

**Purpose:** kill the remaining fake-client uncertainty for the two other image candidates before any cross-provider normalization claim.

This gate requires dedicated fail-closed live entry points or a generalized calibration runner that preserves the same safety properties as the OpenAI path:

- dry-run by default;
- exactly one calibration task/request selected explicitly;
- explicit live-authorization flag;
- credentials required only after authorization;
- bounded provider polling/retries;
- no secret persistence;
- exact media/artifact hashing and dimensions;
- explicit terminal failure states;
- no automatic expansion to multiple prompts.

### Google canary requirements

- reverify `gemini-3.1-flash-image` exact live API surface and SDK pin;
- one standard 1:1 generation canary first;
- verify image bytes, actual dimensions, response metadata, usage/cost fields when available, and no grounding/search activation;
- separately exercise `edit_previous` only after the generation transport passes;
- test 0.5K/1K/2K mapping acceptance without claiming equivalence to OpenAI quality levels.

### BFL canary requirements

- reverify `/flux-2-pro` endpoint, positive credit balance, pricing, and edit payload before execution;
- one standard 1:1 generation canary first;
- verify submit → bounded poll → download behavior, terminal status handling, actual dimensions, provider job/request ID, and returned cost metadata;
- ensure expiring signed result URLs never become artifact identity;
- exercise edit only after the generation transport passes;
- keep polling bounded and explicit; do not convert provider pending states into unbounded retry loops.

### Gate 3 pass condition

OpenAI, Google, and BFL have each produced at least one live, auditable calibration artifact through Thrumely's own adapter, and generate/edit semantics required by the planned matrix have been exercised without hidden provider-specific capabilities.

---

## Gate 4 — Cross-provider normalization decision

**Purpose:** decide whether a common normalized media-control surface is scientifically defensible.

After all three live transports pass, compare **semantics and resource controls**, not subjective output quality:

- supported operations (`generate`, `edit_previous`);
- accepted aspect-ratio/dimension mappings and actual dimensions;
- native quality/resolution controls and what they materially change;
- provider cost/usage units;
- latency and asynchronous behavior;
- safety/refusal/moderation representation;
- version/snapshot stability;
- output ownership/release constraints.

The key decision is the current `quality_tier` abstraction. OpenAI exposes provider-defined quality, Google exposes image resolution, and BFL currently approximates tiers through pixel budgets. If live evidence shows these controls are not materially comparable, **remove or redesign `quality_tier` before production freeze** rather than forcing a false equivalence.

Possible outcomes:

- `NORMALIZATION_PASS`: current action surface is materially defensible;
- `NORMALIZATION_PASS_WITH_REDESIGN`: operation/aspect surface survives but quality-tier semantics require a pre-production schema change;
- `NORMALIZATION_FAIL`: one or more providers cannot participate fairly; replace/drop the candidate before corpus freeze.

Any redesign happens before production tasks are exposed to production-condition outputs and requires updated tests, provider inventory, and hashes.

---

## Gate 5 — Controller comparability canary

**Purpose:** verify that the second controller candidate can operate the same benchmark-owned tool contract without privileged information.

Only after at least one image backend is live-stable:

- run one calibration-only task with the OpenAI controller and one with the Anthropic controller against the same fixed backend/environment contract;
- keep the same media-call ceiling and visible tool semantics;
- capture only observable tool decisions and usage/provenance;
- verify Anthropic receives no server tools and OpenAI receives no native image-generation tool;
- verify both can inspect the first image and either finish or make one final media action;
- do not compare winner/quality from this tiny controller canary.

If controller semantics cannot be made materially symmetric, revise the controller contract before model freeze.

---

## Gate 6 — Freeze preparation, not production launch

Only after Gates 1–5 pass where applicable:

1. update `docs/providers/INVENTORY.md` with exact live-verified IDs, dates, API surfaces, pricing observations, version status, and sources;
2. resolve the `quality_tier` decision explicitly;
3. select the three image backends and two controller models for `frozen-v1`;
4. finalize the 100-task corpus from the still-unfrozen 150-task development pool **without tuning tasks to increase observed provider separation**;
5. freeze the analysis plan and hashes;
6. run the real production freeze preflight and require every non-synthetic check to pass;
7. only then authorize the production trajectory matrix and subsequent Datapoint pilot/annotation workflow.

The existing synthetic freeze preflight must remain permanently unable to authorize production.

## Immediate next executable action

The next paid action, when legitimate OpenAI API balance/access is deliberately available, is **Gate 1 only: one `cal-openai-001` trajectory**. Until then, all productive work should stay in Gates 0/3 infrastructure and documentation and must consume zero hosted-inference credits.

This plan intentionally does not schedule the remaining four OpenAI calibration tasks or a human pilot. Those become justified only by evidence from the preceding gate, not by momentum.
