# Zero-Cost Provider Scaffolding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add zero-cost, fake-client-tested Google image, BFL image, and Anthropic controller adapters plus an offline normalization validator, without making any hosted API calls or freezing the v1 provider matrix.

**Architecture:** Preserve Thrumely's existing benchmark-owned `NormalizedMediaRequest`/`ControllerDecision` contracts. Each provider/controller adapter translates only at the outer API boundary and accepts an injected fake transport/client so every behavior can be verified offline. A provider-capability registry statically proves which normalized operations/aspect ratios/quality tiers each candidate can represent and refuses to mark the v1 matrix "normalization ready" until all three candidate image providers have comparable generate/edit support.

**Tech Stack:** Python 3.11+, standard library core, pytest; optional live extras only (`google-genai==2.20.0`, `anthropic==1.2.0`). BFL uses an injected HTTP transport and does not add a mandatory HTTP dependency.

**Spec:** `RESEARCH_SPEC.md`

## Global Constraints

- Zero hosted API calls and zero paid inference in this plan.
- No Datapoint jobs or credits.
- No production corpus freeze and no production result claims.
- Exact provider/model identities remain candidates until the live calibration gate passes.
- Keep the benchmark-owned normalized media interface; do not expose provider-native marketing/performance hints to controllers.
- Preserve the two-media-call budget and explicit failure states.
- Do not store or request hidden chain-of-thought.
- Secrets come only from runtime environment/configuration and never enter artifacts/tests/Git history.
- Existing OpenAI and offline paths must remain unchanged and green.
- Optional SDK extras must not become core dependencies.

---

### Task 1: Provider capability registry and normalization validator

**Files:**
- Create: `src/thrumely/capabilities.py`
- Create: `tests/test_capabilities.py`
- Modify: `docs/providers/INVENTORY.md`

**Interfaces:**
- `ProviderCapability` frozen dataclass: `backend_id`, `provider`, `model`, `operations`, `aspect_ratios`, `quality_tiers`, `pinned_snapshot`, `notes`.
- `candidate_capabilities() -> tuple[ProviderCapability, ...]`.
- `validate_candidate_matrix(capabilities=None) -> tuple[str, ...]`, returning human-readable blockers; empty tuple means static normalization compatibility only, not live readiness.

- [ ] Write tests that require three image candidates, unique backend IDs, generate/edit support, the five normalized aspect ratios (`1:1`, `3:2`, `2:3`, `16:9`, `9:16`), and all three normalized quality tiers (`draft`, `standard`, `high`).
- [ ] Verify RED because `thrumely.capabilities` does not exist.
- [ ] Implement the minimal registry for OpenAI `gpt-image-2-2026-04-21`, Google `gemini-3.1-flash-image`, and BFL `/flux-2-pro`.
- [ ] Make the validator explicitly report that static compatibility does not satisfy the live calibration gate.
- [ ] Run capability and existing schema tests.

### Task 2: Google Gemini image adapter under fake-client tests

**Files:**
- Create: `src/thrumely/google_provider.py`
- Create: `tests/test_google_provider.py`
- Modify: `pyproject.toml`

**Interfaces:**
- `GoogleImageProvider(model="gemini-3.1-flash-image", client=None)`.
- `execute(request, previous_media=None) -> ProviderMediaResult`.
- `quality_tier_to_resolution()` maps `draft -> 0.5K`, `standard -> 1K`, `high -> 2K` for calibration only.
- Aspect ratio passes through the five benchmark-owned ratios.

- [ ] Write fake-client tests that assert generation input contains text only, edit input contains previous image + text, no Search grounding/tool is enabled, and returned inline image bytes are decoded/stored separately from raw response metadata.
- [ ] Verify RED.
- [ ] Add optional `google = ["google-genai==2.20.0"]` extra only.
- [ ] Implement adapter with injected `client.interactions.create(...)`; live import is lazy.
- [ ] Parse actual PNG/JPEG dimensions from bytes and reject malformed media as typed provider execution failure.
- [ ] Verify provider tests and core dependency independence.

### Task 3: BFL FLUX.2 Pro adapter under fake-transport tests

**Files:**
- Create: `src/thrumely/bfl_provider.py`
- Create: `tests/test_bfl_provider.py`

**Interfaces:**
- `BFLImageProvider(model="flux-2-pro", transport=None, base_url="https://api.bfl.ai/v1")`.
- `execute(request, previous_media=None) -> ProviderMediaResult`.
- Injected transport exposes `post_json(url, headers, json)`, `get_json(url, headers)`, and `get_bytes(url)`.

- [ ] Write tests for submit -> poll -> download flow, fixed `/flux-2-pro` endpoint, exact dimensions from benchmark ratio mapping, edit `input_image` base64 data URL, terminal provider failure, bounded polling, and no `x-key` persistence in raw artifacts.
- [ ] Verify RED.
- [ ] Implement with no mandatory third-party HTTP package; default live transport may lazily use stdlib `urllib.request`.
- [ ] Preserve BFL `id`, `polling_url` host, reported cost credits, status, and downloaded artifact hashable bytes while excluding expiring signed sample URLs from artifact identity.
- [ ] Verify tests.

### Task 4: Anthropic controller adapter under fake-client tests

**Files:**
- Create: `src/thrumely/anthropic_controller.py`
- Create: `tests/test_anthropic_controller.py`
- Modify: `pyproject.toml`

**Interfaces:**
- `AnthropicController(config: ControllerConfig, client=None)` with candidate default `claude-opus-5` supplied by caller/config.
- `decide(task, environment, *, call_index, previous_artifact=None, previous_media=None) -> ControllerDecision`.
- Reuse the same semantic tool names/fields as OpenAI: `generate_or_edit` and `finish`.

- [ ] Write fake `messages.create()` tests asserting `tool_choice={"type":"any","disable_parallel_tool_use":True}`, strict client-tool schemas, backend enum derived only from `ToolEnvironment`, first-call finish rejection, second-call finish support, base64 previous-image input, and removal of thinking/text blocks from observable output unless scientifically needed.
- [ ] Verify RED.
- [ ] Add optional `anthropic = ["anthropic==1.2.0"]` extra.
- [ ] Implement defensive parser that requires exactly one recognized `tool_use` block and never requests server tools.
- [ ] Verify tests.

### Task 5: Offline cross-provider contract validation

**Files:**
- Create: `src/thrumely/validate_normalization.py`
- Create: `tests/test_validate_normalization.py`
- Modify: `README.md`
- Modify: `docs/providers/INVENTORY.md`

**Interfaces:**
- CLI: `python -m thrumely.validate_normalization`.
- Exits 0 only when static schemas/capabilities cover the benchmark-owned normalized action surface.
- Output must include `STATIC_ONLY` and state that live provider calibration remains required.

- [ ] Write CLI/helper tests.
- [ ] Verify RED.
- [ ] Implement deterministic validation only; no network imports/calls.
- [ ] Document current official model/API assumptions and explicit live-gate limitation.
- [ ] Run full suite and offline synthetic runner.

## Verification Gate

Before PR/merge:

```bash
python -m pytest -q
python -m thrumely.offline --output .verify-offline
python -m thrumely.validate_normalization
```

Expected: all tests pass; offline run completes; normalization command reports static compatibility and explicitly states the live gate is still pending.
