# Provider and Model Candidate Inventory

**Inventory date:** 2026-09-01  
**Status:** candidates/calibration only; nothing in this file freezes the v1 matrix.

The Week 3 calibration gate will reverify first-party API availability, exact IDs, pricing, rate limits, normalized-control fairness, and release terms before any provider/model is frozen.

| Role | Candidate | Verified | First-party source | Freeze status | Notes |
| --- | --- | --- | --- | --- | --- |
| Controller | OpenAI `gpt-5.6-sol` | 2026-09-01 | https://developers.openai.com/api/docs/models/gpt-5.6-sol | **Calibration candidate** | OpenAI currently positions GPT-5.6 Sol as its flagship model. It supports image input, the Responses API, and function calling. Thrumely uses benchmark-owned strict function tools rather than OpenAI's native image-generation tool. |
| Controller | Anthropic `claude-opus-5` | 2026-09-01 | https://platform.claude.com/docs/en/models/overview | Candidate / zero-cost scaffold | Still a plausible complex agentic/enterprise controller. Exact cost/capability matching remains a Week 3 decision. The current adapter is fake-client tested only. |
| Controller | Anthropic `claude-fable-5` | 2026-09-01 | https://platform.claude.com/docs/en/models/overview | Candidate alternative | Anthropic now positions Fable 5 above Opus 5 on capability. It is materially more expensive, so experimental cost comparability must be considered deliberately. |
| Image backend | OpenAI `gpt-image-2-2026-04-21` | 2026-09-01 | https://developers.openai.com/api/docs/models/gpt-image-2 | **Calibration candidate** | Official dated snapshot used by the first live slice. Generation/editing run through the Images API, outside the controller. |
| Image backend | Google `gemini-3.1-flash-image` | 2026-09-01 | https://ai.google.dev/gemini-api/docs/image-generation | Candidate / zero-cost scaffold | Google documents generation/editing through the Interactions API, multiple aspect ratios, and 0.5K/1K/2K/4K output sizes. Thrumely does not enable Google Search grounding. |
| Image backend | BFL `/flux-2-pro` | 2026-09-01 | https://docs.bfl.ai/llms.txt | Candidate / zero-cost scaffold | BFL documents FLUX.2 Pro as a fixed endpoint and an asynchronous submit/poll/download flow. Exact editing payload behavior remains a live-calibration check. |

## First live calibration: OpenAI

The first hosted slice deliberately validates **one** controller/provider path before adding the remaining candidates.

### Controller

- requested model: `gpt-5.6-sol`;
- API surface: Responses API;
- visible tools: Thrumely-owned `generate_or_edit` and, after the first image, `finish`;
- function schemas use strict JSON Schema and `tool_choice` is constrained so the controller must return an explicit benchmark action;
- first generated media is returned to the controller as an image input for the second/stop decision;
- no reasoning summaries, encrypted reasoning, or private chain-of-thought are requested or stored;
- OpenAI SDK calibration pin: `openai==3.6.0` (PyPI release verified 2026-09-01).

Sources:

- https://developers.openai.com/api/docs/models/gpt-5.6-sol
- https://developers.openai.com/api/docs/guides/function-calling
- https://developers.openai.com/api/docs/guides/images-vision
- https://pypi.org/project/openai/

### Image backend

- logical benchmark backend ID: `openai:gpt-image-2`;
- requested provider model: `gpt-image-2-2026-04-21`;
- API surface: Images API `generate` / `edit`;
- response media: base64 image data decoded to content-addressed PNG artifacts;
- provider media bytes are never duplicated into public JSON metadata;
- high-input-fidelity is not exposed as a provider-specific controller knob;
- provider request/response IDs, model, usage, latency, and errors are recorded when exposed by the SDK/API.

Benchmark-owned normalized mappings for this calibration slice:

| Normalized aspect | OpenAI size |
| --- | --- |
| `1:1` | `1024x1024` |
| `3:2` | `1536x1024` |
| `2:3` | `1024x1536` |
| `16:9` | `1536x864` |
| `9:16` | `864x1536` |

| Normalized quality | OpenAI quality |
| --- | --- |
| `draft` | `low` |
| `standard` | `medium` |
| `high` | `high` |

Sources:

- https://developers.openai.com/api/docs/models/gpt-image-2
- https://developers.openai.com/api/docs/guides/image-generation

## Zero-cost static scaffolding

The remaining candidate adapters are implemented behind injected clients/transports and tested without credentials or network calls. This is **engineering preparation only**. It does not satisfy the live-provider calibration gate.

Run the static contract check with:

```bash
python -m thrumely.validate_normalization
```

A zero exit code means only that each candidate adapter declares the benchmark-owned `generate` / `edit_previous`, aspect-ratio, and quality-tier surface. The command prints `STATIC_ONLY` deliberately. It does not establish empirical quality-tier equivalence, API behavior, cost, latency, safety behavior, or output comparability.

### Google Gemini 3.1 Flash Image

- logical backend ID: `google:gemini-3.1-flash-image`;
- candidate model: `gemini-3.1-flash-image` stable alias;
- API surface scaffolded: Interactions API;
- generation uses text input only;
- editing uses text plus the previous image as inline base64 image input;
- Google Search/Image Search grounding is deliberately not enabled because it would add an asymmetric capability to one backend;
- media bytes are stored separately from public response metadata;
- current optional SDK pin: `google-genai==2.20.0`, whose release history shows 2.20.0 on 2026-08-25.

Current calibration-only mapping:

| Normalized quality | Google output size |
| --- | --- |
| `draft` | `0.5K` |
| `standard` | `1K` |
| `high` | `2K` |

This mapping is **not frozen as scientifically equivalent** to OpenAI's `low`/`medium`/`high`. Google exposes output resolution as a native control, while OpenAI exposes a provider-defined quality level. The live calibration must determine whether the normalized label should remain, be redefined, or be removed from the primary experimental surface.

Sources:

- https://ai.google.dev/gemini-api/docs/image-generation
- https://ai.google.dev/api/interactions-api
- https://pypi.org/project/google-genai/

### Black Forest Labs FLUX.2 Pro

- logical backend ID: `bfl:flux-2-pro`;
- fixed endpoint scaffold: `https://api.bfl.ai/v1/flux-2-pro`;
- asynchronous flow: submit request, poll provider `polling_url`, then download the ready result;
- signed delivery URLs are treated as ephemeral transport metadata and are not artifact identities;
- output bytes are parsed for actual dimensions before provenance is written;
- API key headers never enter raw public request artifacts;
- the zero-cost adapter uses explicit width/height presets in multiples of 16 for the five normalized aspect ratios;
- no mandatory HTTP package is added to the core; tests use an injected fake transport.

The BFL quality mapping currently changes requested pixel dimensions to approximate three output budgets. This is a **calibration hypothesis only**, not evidence that BFL's pixel budget is equivalent to OpenAI or Google's native quality controls. The exact FLUX.2 Pro edit payload, returned cost fields, and live response shape must be verified before this adapter is eligible for the matrix.

Sources:

- https://docs.bfl.ai/llms.txt
- https://docs.bfl.ai/

### Anthropic controller

- candidate model in the current scaffold: `claude-opus-5`;
- API surface: Messages API client tools only;
- visible tool semantics match the OpenAI controller: benchmark-owned `generate_or_edit` and second-turn `finish`;
- `tool_choice={"type":"any","disable_parallel_tool_use":true}` is used so exactly one client-tool decision is expected;
- no Anthropic server tools are enabled;
- the second decision receives the current generated image as base64 image input;
- only observable `tool_use` blocks enter Thrumely's public decision record; text/thinking blocks are excluded from the benchmark artifact;
- current optional SDK pin: `anthropic==1.2.0`, released 2026-08-27.

Sources:

- https://platform.claude.com/docs/en/api/http/messages
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/parallel-tool-use
- https://platform.claude.com/docs/en/build-with-claude/vision
- https://pypi.org/project/anthropic/

## Cost notes (observation only)

OpenAI's 2026-09-01 image documentation lists example GPT Image 2 output prices around **$0.006 / $0.053 / $0.211** for a `1024x1024` low/medium/high image, with landscape/portrait prices varying by pixel count. These values are **not frozen budget constants**. Production budgeting will use measured/quoted prices at the Week 3/Week 8 gates and record actual usage/cost fields where exposed.

Google's current pricing page lists no free API tier for `gemini-3.1-flash-image`; therefore no Google hosted smoke is part of the zero-cost phase. BFL and Anthropic hosted calls are likewise postponed until paid calibration is deliberately authorized.

The controller cost is not hard-coded into the benchmark; provider pricing is external, time-varying metadata.

Sources:

- https://developers.openai.com/api/docs/guides/image-generation
- https://developers.openai.com/api/docs/models/gpt-5.6-sol
- https://ai.google.dev/gemini-api/docs/pricing

## Access, ownership, and release notes

- OpenAI documents that access to GPT Image models may require API Organization Verification. This is an account/access gate, not a benchmark failure.
- OpenAI's Services Agreement states that, as between the customer and OpenAI and to the extent permitted by applicable law, the customer owns Output. That does not eliminate obligations arising from prompts, third-party rights, or other provider terms.
- OpenAI's service terms impose additional restrictions around visual capabilities, including real-person likeness use. Core v1 already excludes real-person/deepfake tasks.
- Generated-media release treatment remains an artifact-class decision. Thrumely does not blanket-apply the MIT code license to generated image bytes.
- Equivalent provider-specific output/release review remains required for Google and BFL before production media is published.

Sources:

- https://developers.openai.com/api/docs/guides/image-generation
- https://openai.com/policies/business-terms/
- https://openai.com/policies/service-terms/

## Freeze checklist

A candidate may enter the production matrix only after all are true:

1. first-party API access is legitimate and available to this project;
2. the exact endpoint/model identifier is recorded;
3. the controller-visible normalized schema is materially fair across image backends;
4. model/version stability is documented honestly;
5. rate limits and expected generation cost fit the production matrix;
6. safety/moderation behavior is represented as data rather than hidden retries;
7. output/release terms have a documented treatment, including metadata/hash-only fallback if raw-byte redistribution remains unclear;
8. live calibration confirms that provider request/response shapes match the tested adapters and that the chosen normalized controls are empirically defensible.
