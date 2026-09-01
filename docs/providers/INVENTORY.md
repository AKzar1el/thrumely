# Provider and Model Candidate Inventory

**Inventory date:** 2026-09-01  
**Status:** candidates only; nothing in this file freezes the v1 matrix.

The Week 3 calibration gate will reverify first-party API availability, exact IDs, pricing, rate limits, normalized-control fairness, and release terms before any provider/model is frozen.

| Role | Candidate | Verified | First-party source | Freeze status | Notes |
| --- | --- | --- | --- | --- | --- |
| Controller | OpenAI `gpt-5.6-sol` | 2026-09-01 | https://developers.openai.com/api/docs/models | Candidate | OpenAI currently lists GPT-5.6 Sol as its flagship model; supports image input and function/tool use. Exact reasoning/budget controls must be frozen later. |
| Controller | Anthropic `claude-opus-5` | 2026-09-01 | https://platform.claude.com/docs/en/models/overview | Candidate | Still positioned for complex agentic/enterprise work and remains a plausible cost/capability match. |
| Controller | Anthropic `claude-fable-5` | 2026-09-01 | https://platform.claude.com/docs/en/models/overview | Candidate alternative | Anthropic now calls Fable 5 its highest available/widely released capability. It is materially more expensive than Opus 5, so using it could worsen experimental cost comparability; Week 3 must decide deliberately. |
| Image backend | OpenAI `gpt-image-2-2026-04-21` | 2026-09-01 | https://developers.openai.com/api/docs/models/gpt-image-2 | Candidate | Official dated snapshot exists, giving the strongest current version-freeze story among planned image candidates. |
| Image backend | Google `gemini-3.1-flash-image` | 2026-09-01 | https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-image | Candidate | Google documents this as a stable image-generation/editing model with multiple output resolutions/aspect ratios. |
| Image backend | BFL `/flux-2-pro` | 2026-09-01 | https://docs.bfl.ai/llms.txt | Candidate | BFL's current docs say FLUX.2 remains fully supported; the API index calls `/flux-2-pro` the recommended default for image generation/editing and the text-to-image guide still recommends FLUX.2. FLUX 3 is the newest family, so current image applicability must be rechecked at freeze time rather than assumed. |

## Freeze checklist

A candidate may enter the production matrix only after all are true:

1. first-party API access is legitimate and available to this project;
2. the exact endpoint/model identifier is recorded;
3. the controller-visible normalized schema is materially fair across image backends;
4. model/version stability is documented honestly;
5. rate limits and expected generation cost fit the production matrix;
6. safety/moderation behavior is represented as data rather than hidden retries;
7. output/release terms have a documented treatment, including metadata/hash-only fallback if raw-byte redistribution remains unclear.
