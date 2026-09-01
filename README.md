# Thrumely

Thrumely is open research on how AI agents select and control generative-media tools.

The v1 study asks a narrow question:

> Holding user tasks, agent budget, and evaluation procedure constant, does giving an AI agent a choice among multiple image-generation tools improve human-rated instruction faithfulness compared with assigning it a single fixed image backend?

Thrumely is currently **pre-production research infrastructure**. The authoritative protocol is in [`RESEARCH_SPEC.md`](RESEARCH_SPEC.md).

## Status

The zero-cost offline foundation is complete and continuously tested. It validates the research data contract with deterministic mock components, including provenance, artifact hashing, public redaction, and end-to-end export.

A separate **live calibration path** exists for one OpenAI controller candidate and one OpenAI image-backend candidate. Its purpose is to test whether the same research artifact contract survives real hosted APIs. The credentialed hosted smoke is currently postponed; calibration output is **not benchmark evidence**, is not part of the future frozen v1 corpus, and must not be used to claim that one controller, model, provider, or policy performs better than another.

Zero-cost scaffolding also exists for the remaining current candidates: Google `gemini-3.1-flash-image`, BFL `flux-2-pro`, and Anthropic `claude-opus-5`. These adapters are exercised only through fake clients/transports at this stage. Static schema compatibility is useful engineering evidence, but it is **not** evidence that the providers are scientifically equivalent or production-ready.

A separate unfrozen development pool now contains **150 newly authored candidate tasks, 30 per planned family**. Each candidate includes observable atomic requirements, pre-output image-answerable evaluation questions, human-rubric notes, and deterministic-check descriptors. This is deliberately broader than the planned 100-task production corpus; it is **not** the frozen v1 task set, and final selection remains blocked by live provider-normalization calibration.

The planned v1 experiment still targets:

- 100 frozen tasks across five task families;
- two controller LLMs;
- three image backends;
- three fixed-backend environments plus one multi-tool chooser environment;
- two stochastic replications;
- at most two media calls per trajectory;
- human pairwise preference and instruction-faithfulness evaluation.

Exact production provider/model identities remain intentionally unfrozen until the calibration gate.

## Research integrity

Thrumely is independent of GodPrompt's primary benchmark conditions. GodPrompt is not a v1 treatment. Null and negative results are first-class outcomes.

The project is designed to be **artifact-auditable and procedurally reproducible**. Hosted APIs may change and may not offer deterministic seeds, so future API calls are not claimed to reproduce historical image bytes exactly. Historical artifacts, hashes, configuration, observable tool decisions, and provider metadata are preserved instead.

## Offline verification

The core requires Python 3.11+ and no API credentials or provider SDKs.

```bash
python -m pip install -e '.[test]'
python -m pytest -q
python -m thrumely.validate_candidates candidates/tasks-v0.1.jsonl
python -m thrumely.power --tasks 100 --effect 0.20 --simulations 2000 --seed 20260901
python -m thrumely.validate_normalization
python -m thrumely.offline --output .offline-results
```

The candidate validator reports corpus balance and a canonical development SHA-256. A successful result is labeled `UNFROZEN_CANDIDATE_POOL`; it must not be interpreted as a production-corpus freeze.

The power command is a **synthetic planning simulation only**. Its default variance parameters are placeholders until pilot data exists, and its output is not achieved power or the final confirmatory analysis. The production analysis still requires the task-clustered contract in `RESEARCH_SPEC.md`.

The normalization validator is intentionally labeled `STATIC_ONLY`. A successful exit means that the candidate adapters cover Thrumely's benchmark-owned operations, aspect ratios, and quality-tier labels at the schema level. It does **not** establish equivalent quality, API behavior, cost, latency, safety behavior, or output comparability; those remain live-calibration questions.

The synthetic run writes:

```text
<run-id>/
├── manifest.json
├── trajectories.jsonl
├── scores.jsonl
└── media/
    └── <sha256>.svg
```

Synthetic output is explicitly marked `synthetic-offline`. The mock score only checks that an artifact exists; it is not a faithfulness or preference score.

## Candidate task pool

`candidates/tasks-v0.1.jsonl` contains 150 development candidates across the five families in `RESEARCH_SPEC.md`:

1. compositional constraints;
2. typography and layout;
3. styled visual brief;
4. product/editorial scene;
5. revision-sensitive multi-constraint brief.

All records remain `corpus_status: candidate`. Calibration prompts live separately under `calibration/` and are guarded against accidental promotion or exact reuse. Candidate tasks may be removed for ambiguity, redundancy, safety, provider incompatibility, or methodology reasons before the final 100-task freeze; they must not be rewritten after production-condition outputs are observed in order to increase separation.

## Automated-evaluation scaffolding

Human instruction-faithfulness remains the primary endpoint. The current zero-cost scorer layer implements only deterministic primitives such as aspect-ratio compliance, normalized required-text matching against externally supplied OCR text, and atomic-requirement coverage bookkeeping.

Model-backed metrics are registered as **future optional validation adapters**, not run by CI and not eligible to become the primary endpoint by configuration drift. Candidate families include:

- TIFA-style frozen visual-question answering for fine-grained faithfulness: https://github.com/Yushi-Hu/tifa
- VQAScore-style semantic image-text faithfulness;
- CLIPScore as a historical reference-free embedding baseline: https://github.com/jmhessel/clipscore
- HPSv2 as a human-preference prediction baseline: https://github.com/tgxs002/HPSv2
- a pairwise VLM judge that must be run in both A/B and B/A order when implemented.

Automatic metrics will be validated against held-out human judgments rather than tuned on production labels and then reported as confirmatory.

## Candidate provider scaffolding

All provider SDKs remain optional. Installing the core test extra does not install or call hosted providers.

- OpenAI: `openai==3.6.0`
- Google: `google-genai==2.20.0`
- Anthropic: `anthropic==1.2.0`
- BFL: no mandatory third-party HTTP dependency; the adapter has an injectable transport and a standard-library fallback for a future live run.

The current static mappings are calibration hypotheses, not frozen scientific equivalences. In particular, a normalized `quality_tier` maps to different native controls across providers and must be checked empirically before the production matrix is frozen.

## OpenAI live calibration

The first hosted calibration slice uses a benchmark-owned controller/tool interface:

- controller candidate: `gpt-5.6-sol` through the Responses API;
- image candidate: pinned `gpt-image-2-2026-04-21` through the Images API;
- the controller receives only Thrumely's neutral `generate_or_edit` / `finish` function tools;
- OpenAI's native image-generation tool is **not** exposed to the controller;
- the five prompts in `calibration/tasks/openai-smoke.json` are calibration-only and are excluded from the future v1 task corpus;
- at most two image calls are allowed per trajectory.

When paid API access is deliberately enabled in a suitable environment, the existing calibration command is:

```bash
python -m pip install -e '.[test,openai]'
python -m thrumely.calibration \
  --tasks calibration/tasks/openai-smoke.json \
  --output results/calibration
```

A live calibration bundle writes:

```text
<run-id>/
├── manifest.json
├── configuration.json
├── tasks.json
├── trajectories.jsonl
├── media.jsonl
└── media/
    └── <sha256>.png
```

The bundle is classified `live-calibration`. There is deliberately no automatic quality score in this slice: its purpose is instrumentation/provenance calibration, not model ranking.

## Datapoint grant

Human annotation for the planned core study is supported by a Datapoint Data Grant. **No Datapoint production annotation or paid Datapoint pilot is part of the current calibration stage.**

The release protocol records the required paper acknowledgment, dataset-card attribution, public tag, and final grant outcome summary in `RESEARCH_SPEC.md`.

## Repository map

- `RESEARCH_SPEC.md` — authoritative pre-production research protocol.
- `candidates/` — unfrozen development task pool; never assume this is the production corpus.
- `calibration/` — calibration-only prompts kept separate from future v1 tasks.
- `docs/decisions/` — pre-result architecture/methodology decisions.
- `docs/methodology/` — threats to validity, power-planning boundaries, and later analysis protocol.
- `docs/providers/` — dated provider/model candidate inventory.
- `src/thrumely/` — research data model, adapters, scoring scaffolds, and execution code.
- `tests/` — offline and fake-client tests; CI does not require provider credentials.

## License

Benchmark code is MIT-licensed. That code license does **not** automatically apply to future task data, human annotations, trajectories, or generated-media bytes; those artifact classes require separate release treatment as documented in the research protocol.
