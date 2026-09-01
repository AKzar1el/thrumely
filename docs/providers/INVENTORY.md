# Provider and Model Candidate Inventory

**Inventory date:** 2026-09-01  
**Status:** candidates/calibration only; nothing in this file freezes the v1 matrix.

The Week 3 calibration gate will reverify first-party API availability, exact IDs, pricing, rate limits, normalized-control fairness, and release terms before any provider/model is frozen.

| Role | Candidate | Verified | First-party source | Freeze status | Notes |
| --- | --- | --- | --- | --- | --- |
| Controller | OpenAI `gpt-5.6-sol` | 2026-09-01 | https://developers.openai.com/api/docs/models/gpt-5.6-sol | **Calibration candidate** | OpenAI currently positions GPT-5.6 Sol as its flagship model. It supports image input, the Responses API, and function calling. Thrumely uses benchmark-owned strict function tools rather than OpenAI's native image-generation tool. |
| Controller | Anthropic `claude-opus-5` | 2026-09-01 | https://platform.claude.com/docs/en/models/overview | Candidate | Still a plausible complex agentic/enterprise controller. Exact cost/capability matching remains a Week 3 decision. |
| Controller | Anthropic `claude-fable-5` | 2026-09-01 | https://platform.claude.com/docs/en/models/overview | Candidate alternative | Anthropic now positions Fable 5 above Opus 5 on capability. It is materially more expensive, so experimental cost comparability must be considered deliberately. |
| Image backend | OpenAI `gpt-image-2-2026-04-21` | 2026-09-01 | https://developers.openai.com/api/docs/models/gpt-image-2 | **Calibration candidate** | Official dated snapshot used by the first live slice. Generation/editing run through the Images API, outside the controller. |
| Image backend | Google `gemini-3.1-flash-image` | 2026-09-01 | https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-image | Candidate | Google documents this as a stable image-generation/editing model with multiple output resolutions/aspect ratios. |
| Image backend | BFL `/flux-2-pro` | 2026-09-01 | https://docs.bfl.ai/llms.txt | Candidate | BFL's current docs say FLUX.2 remains supported and still recommend it for image-generation workflows, while FLUX 3 is the newest family. Recheck image applicability at freeze time. |

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

## Cost notes (observation only)

OpenAI's 2026-09-01 image documentation lists example GPT Image 2 output prices around **$0.006 / $0.053 / $0.211** for a `1024x1024` low/medium/high image, with landscape/portrait prices varying by pixel count. These values are **not frozen budget constants**. Production budgeting will use measured/quoted prices at the Week 3/Week 8 gates and record actual usage/cost fields where exposed.

The controller cost is also not hard-coded into the benchmark; provider pricing is external, time-varying metadata.

Sources:

- https://developers.openai.com/api/docs/guides/image-generation
- https://developers.openai.com/api/docs/models/gpt-5.6-sol

## Access, ownership, and release notes

- OpenAI documents that access to GPT Image models may require API Organization Verification. This is an account/access gate, not a benchmark failure.
- OpenAI's Services Agreement states that, as between the customer and OpenAI and to the extent permitted by applicable law, the customer owns Output. That does not eliminate obligations arising from prompts, third-party rights, or other provider terms.
- OpenAI's service terms impose additional restrictions around visual capabilities, including real-person likeness use. Core v1 already excludes real-person/deepfake tasks.
- Generated-media release treatment remains an artifact-class decision. Thrumely does not blanket-apply the MIT code license to generated image bytes.

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
7. output/release terms have a documented treatment, including metadata/hash-only fallback if raw-byte redistribution remains unclear.
