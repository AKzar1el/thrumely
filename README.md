# Thrumely

Thrumely is open research on how AI agents select and control generative-media tools.

The v1 study asks a narrow question:

> Holding user tasks, agent budget, and evaluation procedure constant, does giving an AI agent a choice among multiple image-generation tools improve human-rated instruction faithfulness compared with assigning it a single fixed image backend?

Thrumely is currently **pre-production research infrastructure**. The authoritative protocol is in [`RESEARCH_SPEC.md`](RESEARCH_SPEC.md).

## Status

The zero-cost offline foundation is complete and continuously tested. It validates the research data contract with deterministic mock components, including provenance, artifact hashing, public redaction, and end-to-end export.

A separate **live calibration path** now exists for one OpenAI controller candidate and one OpenAI image-backend candidate. Its purpose is to test whether the same research artifact contract survives real hosted APIs. Calibration output is **not benchmark evidence**, is not part of the future frozen v1 corpus, and must not be used to claim that one controller, model, provider, or policy performs better than another.

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
python -m thrumely.offline --output .offline-results
```

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

## OpenAI live calibration

The first hosted calibration slice uses a benchmark-owned controller/tool interface:

- controller candidate: `gpt-5.6-sol` through the Responses API;
- image candidate: pinned `gpt-image-2-2026-04-21` through the Images API;
- the controller receives only Thrumely's neutral `generate_or_edit` / `finish` function tools;
- OpenAI's native image-generation tool is **not** exposed to the controller;
- the five prompts in `calibration/tasks/openai-smoke.json` are calibration-only and are excluded from the future v1 task corpus;
- at most two image calls are allowed per trajectory.

Install the optional live dependency and run the calibration in an environment where `OPENAI_API_KEY` is already configured:

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
- `calibration/` — calibration-only prompts kept separate from future v1 tasks.
- `docs/decisions/` — pre-result architecture/methodology decisions.
- `docs/methodology/` — threats to validity and later analysis protocol.
- `docs/providers/` — dated provider/model candidate inventory.
- `src/thrumely/` — research data model, adapters, and execution code.
- `tests/` — offline and fake-client tests; CI does not require provider credentials.

## License

Benchmark code is MIT-licensed. That code license does **not** automatically apply to future task data, human annotations, trajectories, or generated-media bytes; those artifact classes require separate release treatment as documented in the research protocol.
