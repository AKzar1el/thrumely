# Thrumely

Thrumely is open research on how AI agents select and control generative-media tools.

The v1 study asks a narrow question:

> Holding user tasks, agent budget, and evaluation procedure constant, does giving an AI agent a choice among multiple image-generation tools improve human-rated instruction faithfulness compared with assigning it a single fixed image backend?

Thrumely is currently **pre-production research infrastructure**. The scientific protocol is frozen before live-provider integration in [`RESEARCH_SPEC.md`](RESEARCH_SPEC.md).

## Status

The current implementation validates the research data contract entirely offline with synthetic mock components. It does **not** contain production benchmark results and must not be used to claim that one controller, model, provider, or policy performs better than another.

The planned v1 experiment targets:

- 100 frozen tasks across five task families;
- two controller LLMs;
- three image backends;
- three fixed-backend environments plus one multi-tool chooser environment;
- two stochastic replications;
- at most two media calls per trajectory;
- human pairwise preference and instruction-faithfulness evaluation.

Exact provider/model identities are intentionally not frozen until the calibration gate.

## Research integrity

Thrumely is independent of GodPrompt's primary benchmark conditions. GodPrompt is not a v1 treatment. Null and negative results are first-class outcomes.

The project is designed to be **artifact-auditable and procedurally reproducible**. Hosted APIs may change and may not offer deterministic seeds, so future API calls are not claimed to reproduce historical image bytes exactly. Historical artifacts, hashes, configuration, and observable tool decisions are preserved instead.

## Offline verification

The current foundation requires Python 3.11+ and no API credentials.

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

## Datapoint grant

Human annotation for the planned core study is supported by a Datapoint Data Grant. No production annotation is collected by the offline foundation.

The release protocol records the required paper acknowledgment, dataset-card attribution, public tag, and final grant outcome summary in `RESEARCH_SPEC.md`.

## Repository map

- `RESEARCH_SPEC.md` — authoritative pre-production research protocol.
- `docs/decisions/` — pre-result architecture/methodology decisions.
- `docs/methodology/` — threats to validity and later analysis protocol.
- `docs/providers/` — dated provider/model candidate inventory.
- `src/thrumely/` — research data model and execution code.
- `tests/` — offline tests only at this stage.

## License

Benchmark code is MIT-licensed. That code license does **not** automatically apply to future task data, human annotations, trajectories, or generated-media bytes; those artifact classes require separate release treatment as documented in the research protocol.
