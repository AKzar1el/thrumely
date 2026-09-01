# Contributing to Thrumely

Thrumely is a research repository. Contributions are welcome, but scientific integrity takes precedence over improving an observed score.

## Before contributing

Read `RESEARCH_SPEC.md`. Changes that alter the research question, primary endpoint, production task corpus, treatment definitions, exclusion rules, or analysis contract require an explicit versioned methodology decision before production data is collected.

## Hard rules

Do not:

- rewrite or add production tasks after seeing condition results in order to increase separation;
- fabricate provider metadata, costs, model versions, human responses, provenance, or benchmark results;
- commit API keys, tokens, passwords, authorization headers, or other credentials;
- store or publish hidden chain-of-thought, encrypted reasoning, or equivalent private model reasoning;
- present mock, calibration, or sandbox output as a production benchmark result;
- silently retry or replace provider failures in a way that erases the original terminal state;
- add GodPrompt as a privileged v1 treatment.

## Development

The current foundation is intentionally offline:

```bash
python -m pip install -e '.[test]'
python -m pytest -q
python -m thrumely.offline --output .offline-results
```

New behavioral code should be developed test-first. Provider integrations must not enter CI with credentials or paid model calls.

## Data and media

The MIT license applies to code. Future benchmark tasks, annotation tables, trajectories, and generated-media artifacts may have separate licenses or provider-specific redistribution restrictions. Do not assume repository-level code licensing grants rights over those artifacts.
