# First Live OpenAI Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Thrumely's first real controller and image-provider calibration path using OpenAI while preserving the benchmark-owned tool interface, complete provenance, a calibration-only task set, and a hard separation from production benchmark data.

**Architecture:** Keep the existing offline mock pipeline unchanged as the permanent zero-cost contract test. Add small provider/controller adapters that depend on an optional pinned OpenAI SDK extra, use the Responses API only for controller decisions, and call the Images API separately for media generation/editing so the controller never receives a privileged native image-generation tool. A calibration runner composes the adapters with the existing artifact store and schemas, exports the same public bundle shape, and refuses to run without an explicit calibration task file and API key.

**Tech Stack:** Python 3.11+, standard library, `openai==3.6.0` as an optional live-calibration dependency, `pytest`, GitHub Actions.

**Spec:** `RESEARCH_SPEC.md`

## Global Constraints

- This is calibration infrastructure, not the v1 production benchmark.
- No Datapoint jobs or Datapoint credits.
- No production task corpus and no production result claims.
- GodPrompt is not an experimental condition.
- Use benchmark-owned function tools; do not use the Responses API native image-generation tool for the controller.
- Controller candidate for this calibration slice: `gpt-5.6-sol`; do not treat it as the final frozen v1 controller until the Week 3 model freeze.
- Image candidate for this calibration slice: pinned snapshot `gpt-image-2-2026-04-21` through the Images API.
- Store only observable controller outputs/tool calls; do not request or persist hidden chain-of-thought or encrypted reasoning.
- `OPENAI_API_KEY` is read only from process environment/SDK configuration and must never enter manifests, raw requests, test fixtures, or Git history.
- The first live calibration set is separate from future candidate/frozen v1 tasks.
- Maximum media calls per live calibration trajectory remains 2.
- Provider failures, refusals, and invalid controller outputs are explicit terminal records; never silently replace them.
- Existing offline tests and offline runner must continue to work without installing the OpenAI extra.
- Python floor remains `>=3.11`.

---

## Verified API assumptions on 2026-09-01

- OpenAI documents `gpt-5.6-sol` as its flagship model, with image input, Responses API support, and function calling.
- OpenAI recommends the Responses API for GPT-5.6 reasoning/tool workflows.
- OpenAI documents `gpt-image-2` as the state-of-the-art image model and exposes a pinned snapshot `gpt-image-2-2026-04-21`.
- The Images API supports `gpt-image-2` generation and edits and returns base64 image data.
- `gpt-image-2` supports flexible dimensions with edge, ratio, and total-pixel constraints; this plan uses a benchmark-owned mapping for five normalized aspect ratios rather than exposing arbitrary provider dimensions to the controller.
- OpenAI function tools in the Responses API support strict JSON schemas and `tool_choice="required"`.

These are calibration-time facts, not permanent benchmark assumptions. `docs/providers/INVENTORY.md` records the source URLs and verification date.

---

## File Structure

- Modify `pyproject.toml` — add pinned optional `openai` extra without affecting the zero-dependency core.
- Modify `src/thrumely/schema.py` — add calibration-relevant controller/provider provenance fields while preserving backwards-compatible defaults for the offline path.
- Create `src/thrumely/interfaces.py` — small runtime-only result/decision dataclasses shared by live adapters.
- Create `src/thrumely/openai_provider.py` — normalized OpenAI GPT-Image adapter; maps aspect/quality tiers to provider parameters and captures request/response metadata.
- Create `src/thrumely/openai_controller.py` — GPT-5.6 Sol Responses API controller using only benchmark-owned strict function tools.
- Create `src/thrumely/calibration.py` — end-to-end live calibration runner/exporter using existing artifact/provenance/redaction primitives.
- Create `calibration/tasks/openai-smoke.json` — five rights-clean, calibration-only prompts, one per intended v1 family.
- Modify `docs/providers/INVENTORY.md` — verification date, model IDs, snapshot, API surface, pricing notes, output-ownership/release notes, and source URLs.
- Modify `README.md` — explain calibration status and live command without presenting calibration output as benchmark results.
- Create `tests/test_live_schema.py` — provenance extension tests.
- Create `tests/test_openai_provider.py` — provider mapping/response parsing tests using a fake injected client.
- Create `tests/test_openai_controller.py` — strict tool-schema/decision parsing tests using a fake injected client.
- Create `tests/test_calibration.py` — end-to-end calibration runner test with fake live adapters; no network.
- Modify `.github/workflows/ci.yml` only if needed to explicitly prove core CI does not require OpenAI credentials.

---

### Task 1: Extend provenance records without breaking offline mode

**Files:**
- Modify: `src/thrumely/schema.py`
- Create: `src/thrumely/interfaces.py`
- Create: `tests/test_live_schema.py`

**Interfaces:**
- `ControllerConfig` gains optional fields: `reasoning_effort`, `max_output_tokens`, `system_prompt_sha256`, `sdk_version`.
- `ToolCallRecord` gains optional fields: `provider`, `model`, `retry_count`, `usage`.
- `ProviderMediaResult` is a frozen runtime dataclass containing media bytes plus provider metadata.
- `ControllerDecision` is a frozen runtime dataclass with `action`, optional normalized request, response ID/model/usage, and sanitized observable output items.

- [ ] **Step 1: Write failing provenance tests**

Add tests asserting that:

```python
from thrumely.interfaces import ControllerDecision, ProviderMediaResult
from thrumely.schema import ControllerConfig


def test_controller_config_accepts_frozen_live_provenance() -> None:
    config = ControllerConfig(
        controller_id="openai-sol-calibration",
        provider="openai",
        model="gpt-5.6-sol",
        reasoning_effort="medium",
        max_output_tokens=1024,
        system_prompt_sha256="a" * 64,
        sdk_version="3.6.0",
    )
    assert config.model == "gpt-5.6-sol"


def test_controller_decision_finish_has_no_media_request() -> None:
    decision = ControllerDecision(
        action="finish",
        request=None,
        response_id="resp_test",
        actual_model="gpt-5.6-sol",
        usage={"input_tokens": 10, "output_tokens": 2},
        observable_output=(),
    )
    assert decision.request is None
```

Also test negative retry counts and malformed system prompt hashes are rejected.

- [ ] **Step 2: Verify RED**

Run:

```bash
python -m pytest tests/test_live_schema.py -q
```

Expected: import/constructor failures because the live provenance interfaces/fields do not exist.

- [ ] **Step 3: Implement minimal schema extensions**

Keep all new schema fields optional/defaulted so `MockController`, `run_offline`, and existing tests do not need live-specific values.

`ControllerDecision.__post_init__` rules:

- `action` is exactly `media` or `finish`;
- `media` requires `request`;
- `finish` requires `request is None`.

`ProviderMediaResult.__post_init__` rules:

- non-empty provider/model/mime type;
- positive width/height;
- non-negative latency/retry count/cost when provided;
- media bytes must be non-empty.

- [ ] **Step 4: Verify GREEN and regression suite**

```bash
python -m pytest tests/test_live_schema.py tests/test_schema.py tests/test_offline.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/thrumely/schema.py src/thrumely/interfaces.py tests/test_live_schema.py
git commit -m "feat: extend live calibration provenance"
```

---

### Task 2: Add normalized GPT-Image provider adapter

**Files:**
- Modify: `pyproject.toml`
- Create: `src/thrumely/openai_provider.py`
- Create: `tests/test_openai_provider.py`

**Interfaces:**
- `OpenAIImageProvider(model="gpt-image-2-2026-04-21", client=None)`
- `execute(request: NormalizedMediaRequest, previous_media: bytes | None = None) -> ProviderMediaResult`
- `aspect_ratio_to_size(aspect_ratio: str) -> str`
- `quality_tier_to_openai(quality_tier: str) -> str`

Normalized mappings for this calibration slice:

```text
1:1  -> 1024x1024
3:2  -> 1536x1024
2:3  -> 1024x1536
16:9 -> 1536x864
9:16 -> 864x1536

draft    -> low
standard -> medium
high     -> high
```

- [ ] **Step 1: Write failing provider tests**

Use an injected fake client whose `images.generate()` returns an object with `data[0].b64_json`, `id`, `model`, and `usage`; test exact provider kwargs for generation.

Test that:

```python
assert aspect_ratio_to_size("16:9") == "1536x864"
assert quality_tier_to_openai("standard") == "medium"
```

Test unsupported ratio/tier raises `ValueError` before any API call.

Test `EDIT_PREVIOUS` without `previous_media` fails before any API call.

Test generated base64 bytes are decoded and reported as `image/png` with the expected configured dimensions.

- [ ] **Step 2: Verify RED**

```bash
python -m pytest tests/test_openai_provider.py -q
```

Expected: missing module.

- [ ] **Step 3: Add pinned optional SDK dependency**

In `pyproject.toml`:

```toml
[project.optional-dependencies]
test = ["pytest>=8.3,<10"]
openai = ["openai==3.6.0"]
```

The core package remains dependency-free unless the `openai` extra is installed.

- [ ] **Step 4: Implement generation path**

Generation calls:

```python
client.images.generate(
    model=self.model,
    prompt=request.prompt,
    size=aspect_ratio_to_size(request.aspect_ratio),
    quality=quality_tier_to_openai(request.quality_tier),
    output_format="png",
)
```

Capture only a redaction-safe raw request mapping; never add authorization headers/API keys.

- [ ] **Step 5: Implement edit path**

Use `client.images.edit(...)` with the pinned model, the previous media bytes exposed as a named binary file object, the same benchmark-owned prompt/size/quality mapping, and PNG output.

Do not expose OpenAI-only `input_fidelity` to the controller; current GPT-Image-2 applies high fidelity automatically.

- [ ] **Step 6: Verify provider tests**

```bash
python -m pytest tests/test_openai_provider.py -q
```

Expected: all pass with no network.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/thrumely/openai_provider.py tests/test_openai_provider.py
git commit -m "feat: add OpenAI image calibration adapter"
```

---

### Task 3: Add GPT-5.6 Sol benchmark-owned controller adapter

**Files:**
- Create: `src/thrumely/openai_controller.py`
- Create: `tests/test_openai_controller.py`

**Interfaces:**
- `OpenAIController(config: ControllerConfig, client=None)`
- `decide(task, environment, *, call_index, previous_artifact=None, previous_media=None) -> ControllerDecision`
- module-level `SYSTEM_PROMPT`
- internal strict tool builders `_media_tool(environment, allow_edit)` and `_finish_tool()`

Controller rules:

- first decision: only the benchmark-owned `generate_or_edit` function is available and is required;
- second decision: `generate_or_edit` and benchmark-owned `finish` are available and one is required;
- controller never receives OpenAI's native image-generation tool;
- chooser/fixed behavior is expressed only through the `backend` enum derived from `ToolEnvironment.available_backends`;
- no provider marketing/performance claims are shown to the controller;
- system prompt states only the task, normalized controls, two-call budget, and stop/revise behavior.

- [ ] **Step 1: Write failing controller tests**

Use an injected fake `responses.create()` implementation and assert the outgoing tool schema is flat Responses API function-tool format:

```python
{
    "type": "function",
    "name": "generate_or_edit",
    "strict": True,
    "parameters": {..., "additionalProperties": False},
}
```

Test a fake `function_call` output is parsed into `NormalizedMediaRequest`.

Test first call rejects a fake `finish` output.

Test second call parses `finish` into `ControllerDecision(action="finish", request=None, ...)`.

Test private reasoning/encrypted content is not copied into `observable_output`.

- [ ] **Step 2: Verify RED**

```bash
python -m pytest tests/test_openai_controller.py -q
```

Expected: missing module.

- [ ] **Step 3: Implement visible system/tool contract**

Hash `SYSTEM_PROMPT` using the existing canonical SHA-256 helper when constructing the live `ControllerConfig`; never request a reasoning summary or encrypted reasoning include field.

Use:

```python
client.responses.create(
    model=config.model,
    instructions=SYSTEM_PROMPT,
    input=...,
    tools=tools,
    tool_choice="required",
    reasoning={"effort": config.reasoning_effort or "medium"},
    max_output_tokens=config.max_output_tokens or 1024,
    store=False,
)
```

For the second decision, include the first generated image as an `input_image` data URL plus a concise benchmark-owned instruction asking whether to finish or make one final media call.

- [ ] **Step 4: Implement defensive output parsing**

Require exactly one recognized function call. Unknown tools, malformed JSON, multiple function calls, backend outside the environment, or invalid operation/artifact combinations raise a typed `ControllerProtocolError` and become explicit trajectory errors in the runner.

- [ ] **Step 5: Verify GREEN**

```bash
python -m pytest tests/test_openai_controller.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/thrumely/openai_controller.py tests/test_openai_controller.py
git commit -m "feat: add OpenAI calibration controller"
```

---

### Task 4: Add calibration-only task corpus and live runner

**Files:**
- Create: `calibration/tasks/openai-smoke.json`
- Create: `src/thrumely/calibration.py`
- Create: `tests/test_calibration.py`

**Interfaces:**
- `load_calibration_tasks(path: Path) -> tuple[TaskSpec, ...]`
- `run_calibration(output_root, task_path, controller, provider, *, replication=1) -> Path`
- CLI: `python -m thrumely.calibration --tasks calibration/tasks/openai-smoke.json --output results/calibration`

Calibration task file contains exactly five newly authored prompts, one per working task family, explicitly marked `calibration_only: true`. They are not candidates for the later 100-task frozen v1 corpus.

Tasks:

1. compositional: three colored geometric objects with unambiguous spatial relations;
2. typography/layout: a simple poster with one short exact phrase and two layout constraints;
3. styled visual brief: a rights-clean fictional botanical travel-poster brief;
4. product/editorial: a generic unbranded reusable bottle editorial scene;
5. revision-sensitive: a multi-constraint fictional café menu-board scene designed to make visual review meaningful.

- [ ] **Step 1: Write failing loader/runner tests**

Test loader rejects:

- missing `calibration_only: true`;
- duplicate IDs;
- empty tasks;
- files containing a task ID prefix reserved for production.

Test fake end-to-end runner creates:

- `manifest.json`;
- `trajectories.jsonl`;
- stored media artifacts;
- explicit controller/provider identifiers;
- `data_classification="live-calibration"`;
- no secret values.

- [ ] **Step 2: Verify RED**

```bash
python -m pytest tests/test_calibration.py -q
```

Expected: missing runner/fixture.

- [ ] **Step 3: Implement five calibration tasks**

Use IDs `cal-openai-001` through `cal-openai-005`; no copyrighted characters, real people, trademarks, politics, minors, or reference images.

- [ ] **Step 4: Implement runner**

For every task:

1. ask controller for first normalized media decision;
2. execute provider call;
3. store the returned media in `ArtifactStore`;
4. record the first `ToolCallRecord`;
5. show the first artifact to the controller;
6. if controller finishes, mark first artifact final;
7. if controller requests a second media call, execute/store/record it and mark the second artifact final;
8. export a sanitized trajectory bundle;
9. on provider/controller protocol failure, persist an explicit non-success trajectory with the observed safe metadata available up to failure.

No automatic faithfulness score is computed in this increment; calibration is testing instrumentation, not claiming image quality.

- [ ] **Step 5: Verify GREEN and full offline regression**

```bash
python -m pytest -q
python -m thrumely.offline --output /tmp/thrumely-offline-check
```

Expected: full suite green and offline bundle still works without API credentials.

- [ ] **Step 6: Commit**

```bash
git add calibration/tasks/openai-smoke.json src/thrumely/calibration.py tests/test_calibration.py
git commit -m "feat: add calibration-only live runner"
```

---

### Task 5: Freeze the current provider inventory and live-run documentation

**Files:**
- Modify: `docs/providers/INVENTORY.md`
- Modify: `README.md`

**Interfaces:** documentation only; no production behavior.

- [ ] **Step 1: Update provider inventory with verified 2026-09-01 facts**

Record:

- controller candidate `gpt-5.6-sol`;
- image alias `gpt-image-2` and calibration snapshot `gpt-image-2-2026-04-21`;
- Responses API + function-calling support for controller;
- Images API generation/edit endpoints for image backend;
- OpenAI's current GPT-Image organization-verification caveat;
- output-ownership statement and service-terms caveats;
- current documented example image prices for common 1024/1536 sizes as observation-only, not a frozen budget;
- source URLs and verification date.

- [ ] **Step 2: Update README**

State clearly:

- offline foundation is complete;
- first live OpenAI calibration adapter exists;
- calibration output is not benchmark evidence;
- production corpus/Datapoint remain locked;
- live setup uses the optional `openai` extra and `OPENAI_API_KEY`;
- exact command for five-task calibration.

- [ ] **Step 3: Verify docs do not overclaim**

Search repository text and ensure no wording claims the chooser improves quality, that Thrumely has completed the benchmark, or that calibration tasks are production tasks.

- [ ] **Step 4: Commit**

```bash
git add docs/providers/INVENTORY.md README.md
git commit -m "docs: document first live calibration candidate"
```

---

### Task 6: Live credentialed smoke run and integration gate

**Files:** no required source changes unless a live-run defect is reproduced first in a failing test.

- [ ] **Step 1: Run complete local/CI-safe verification**

```bash
python -m pytest -q
python -m thrumely.offline --output /tmp/thrumely-offline-final
```

Expected: all tests pass; no API key required.

- [ ] **Step 2: Install pinned live extra in the trusted live environment**

```bash
python -m pip install -e '.[test,openai]'
```

Confirm runtime SDK version is `3.6.0` and record it in live manifest/controller config.

- [ ] **Step 3: Run the five-task live calibration once**

```bash
python -m thrumely.calibration \
  --tasks calibration/tasks/openai-smoke.json \
  --output results/calibration
```

Expected maximum for this smoke: 5 controller-first decisions + up to 5 controller-review decisions + at most 10 GPT-Image calls. This is an engineering calibration, not a statistical experiment.

- [ ] **Step 4: Audit the generated bundle before any further provider integration**

Verify:

- all task/trajectory/controller/environment IDs resolve;
- actual response IDs/models are recorded when exposed;
- raw request/response fields contain no API key;
- media SHA-256 values match bytes;
- every failed/refused call is explicit;
- first/final artifact identities are unambiguous;
- no hidden reasoning or encrypted reasoning is present;
- costs/usage are recorded when exposed and otherwise explicitly null/available in raw usage;
- the run is classified `live-calibration`.

- [ ] **Step 5: Stop at the gate**

Do not add Google, BFL, Anthropic/Fable/Opus, candidate v1 tasks, or Datapoint in the same implementation pass. The next roadmap increment begins only after this first real provider path proves the artifact contract survives a hosted API.

---

## Completion criteria

This increment is complete only when:

1. all existing offline tests remain green without OpenAI installed;
2. all new adapter/runner tests are green with fake injected clients;
3. GitHub Actions is green;
4. one five-task credentialed OpenAI calibration run has been completed or, if account/API access blocks it, the exact external blocker is documented without pretending the live run occurred;
5. the generated bundle passes the provenance/redaction audit;
6. calibration tasks remain excluded from the future v1 corpus;
7. no Datapoint credits have been used;
8. the feature branch is merged by PR and removed after verification.
