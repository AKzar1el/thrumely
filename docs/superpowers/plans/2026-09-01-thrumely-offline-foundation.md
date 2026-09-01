# Thrumely Offline Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Thrumely's zero-cost, fully offline research foundation so one synthetic task can run through a mock controller, normalized mock image tool, artifact store, provenance manifest, scorer, redacted export, and CI without any live provider or Datapoint call.

**Architecture:** Use a small Python 3.11+ package with immutable dataclass-based research records and standard-library serialization/hashing. Keep provider/controller behavior behind minimal protocols, generate deterministic SVG media in the mock provider, preserve raw-vs-normalized request records, and write a self-contained public artifact bundle. The offline runner is intentionally not a generic evaluation framework; it exists only to validate Thrumely's v1 data contract and reproducibility assumptions before live integrations.

**Tech Stack:** Python 3.11+, standard library, `pytest` for tests, GitHub Actions for CI.

**Spec:** `RESEARCH_SPEC.md`

## Global Constraints

- No paid Datapoint jobs.
- No live OpenAI, Google, BFL, Anthropic, or other provider calls.
- No production task corpus or production benchmark results.
- No GodPrompt experimental condition or GodPrompt-specific scoring assumptions.
- Store observable controller/tool events only; never store hidden chain-of-thought, encrypted reasoning, or secrets.
- Failures are explicit terminal records; do not silently substitute successful outputs.
- Hosted-provider model IDs remain candidates until the later calibration gate; this plan has no provider SDK dependency.
- Python floor is `>=3.11`.
- Keep the implementation small and research-specific; do not extract a generic shared framework.

---

## File Structure

- `README.md` — public project identity, current research status, non-claims, local offline verification instructions.
- `LICENSE` — MIT license for benchmark code only.
- `CONTRIBUTING.md` — contribution and scientific-integrity rules.
- `pyproject.toml` — package/test configuration; no provider SDK dependencies.
- `src/thrumely/__init__.py` — package version/export surface.
- `src/thrumely/schema.py` — immutable enums/dataclasses for tasks, controllers, environments, tool calls, media, trajectories, scores, and manifests.
- `src/thrumely/serialization.py` — canonical JSON conversion/encoding for dataclasses and enums.
- `src/thrumely/hashing.py` — SHA-256 helpers for bytes, files, and canonical structured records.
- `src/thrumely/redaction.py` — recursive secret redaction and reasoning-field stripping for public artifacts.
- `src/thrumely/artifacts.py` — content-addressed media persistence and immutable `MediaArtifact` construction.
- `src/thrumely/mock.py` — deterministic mock controller, mock normalized image provider, and mock scorer.
- `src/thrumely/offline.py` — single synthetic end-to-end run and export orchestration.
- `tests/test_schema.py` — schema validation and immutability tests.
- `tests/test_hashing.py` — canonical hashing tests.
- `tests/test_redaction.py` — secret/reasoning sanitization tests.
- `tests/test_artifacts.py` — content-addressed artifact tests.
- `tests/test_offline.py` — full offline bundle integration test.
- `docs/decisions/0001-neutral-research-identity.md` — why Thrumely is separate and neutral to GodPrompt/vendors.
- `docs/methodology/THREATS_TO_VALIDITY.md` — pre-result validity threats and mitigations.
- `docs/providers/INVENTORY.md` — candidate-provider inventory with verification-date/source fields; records current candidates but deliberately does not freeze them.
- `.github/workflows/ci.yml` — offline CI only.

---

### Task 1: Repository Identity and Packaging

**Files:**
- Create: `README.md`
- Create: `LICENSE`
- Create: `CONTRIBUTING.md`
- Create: `pyproject.toml`
- Create: `src/thrumely/__init__.py`

**Interfaces:**
- Consumes: `RESEARCH_SPEC.md`
- Produces: installable package `thrumely`, `__version__ == "0.1.0"`, pytest configuration.

- [ ] **Step 1: Write the package smoke test**

Create `tests/test_package.py`:

```python
from thrumely import __version__


def test_package_exposes_version() -> None:
    assert __version__ == "0.1.0"
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
python -m pytest tests/test_package.py -q
```

Expected: collection/import failure because `thrumely` does not exist.

- [ ] **Step 3: Add minimal package/pyproject implementation**

Create `src/thrumely/__init__.py`:

```python
__version__ = "0.1.0"
```

Create `pyproject.toml` with:

```toml
[build-system]
requires = ["setuptools>=75,<76"]
build-backend = "setuptools.build_meta"

[project]
name = "thrumely"
version = "0.1.0"
description = "Open research on agent policies for generative-media tool selection and control"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
test = ["pytest>=8.3,<10"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 4: Add README/license/contribution documents**

README must state that Thrumely is in pre-production research status, summarize the chooser-vs-fixed question, say that no result claims exist yet, link `RESEARCH_SPEC.md`, and document the offline verification command.

`LICENSE` is the standard MIT license for code, with copyright year 2026 and Tomi Šeregi.

`CONTRIBUTING.md` must prohibit result-driven task rewriting, fabricated provenance/results, secrets in fixtures, and claims derived from mock/calibration output.

- [ ] **Step 5: Run package test and verify GREEN**

Run:

```bash
python -m pytest tests/test_package.py -q
```

Expected: `1 passed`.

- [ ] **Step 6: Commit**

```bash
git add README.md LICENSE CONTRIBUTING.md pyproject.toml src/thrumely/__init__.py tests/test_package.py
git commit -m "chore: initialize Thrumely research package"
```

---

### Task 2: Immutable Research Schemas

**Files:**
- Create: `src/thrumely/schema.py`
- Create: `tests/test_schema.py`

**Interfaces:**
- Produces:
  - `CompletionStatus(str, Enum)`
  - `MediaStage(str, Enum)`
  - `MediaOperation(str, Enum)`
  - `TaskSpec`
  - `ControllerConfig`
  - `ToolEnvironment`
  - `NormalizedMediaRequest`
  - `ToolCallRecord`
  - `MediaArtifact`
  - `TrajectoryRecord`
  - `ScorerResult`
  - `RunManifest`

All records are `@dataclass(frozen=True)` and reject structurally invalid values in `__post_init__`.

- [ ] **Step 1: Write schema tests first**

Create tests that prove:

```python
from dataclasses import FrozenInstanceError

import pytest

from thrumely.schema import (
    ControllerConfig,
    MediaOperation,
    NormalizedMediaRequest,
    TaskSpec,
    ToolEnvironment,
)


def test_task_requires_nonempty_instruction() -> None:
    with pytest.raises(ValueError, match="instruction"):
        TaskSpec(task_id="task-001", family="composition", instruction="")


def test_tool_environment_requires_available_backends() -> None:
    with pytest.raises(ValueError, match="backend"):
        ToolEnvironment(environment_id="chooser", mode="chooser", available_backends=())


def test_normalized_request_rejects_backend_outside_environment() -> None:
    environment = ToolEnvironment(
        environment_id="fixed-a",
        mode="fixed",
        available_backends=("provider-a",),
    )
    with pytest.raises(ValueError, match="available"):
        NormalizedMediaRequest(
            backend="provider-b",
            prompt="draw a blue square",
            operation=MediaOperation.GENERATE,
            aspect_ratio="1:1",
            quality_tier="standard",
            previous_artifact_id=None,
            environment=environment,
        )


def test_schema_records_are_immutable() -> None:
    controller = ControllerConfig(controller_id="mock-a", provider="mock", model="mock-v1")
    with pytest.raises(FrozenInstanceError):
        controller.model = "changed"  # type: ignore[misc]
```

- [ ] **Step 2: Verify RED**

Run:

```bash
python -m pytest tests/test_schema.py -q
```

Expected: import failure because `thrumely.schema` does not exist.

- [ ] **Step 3: Implement minimal immutable schemas**

Use frozen dataclasses, `Enum` string values, tuples rather than mutable lists, and explicit validation for identifiers, non-empty task instruction, valid environment mode (`fixed` or `chooser`), positive call indices, 64-character lowercase SHA-256 values, non-negative byte lengths/latencies/costs, and media-call budget `>=1`.

`NormalizedMediaRequest` includes the `ToolEnvironment` so it can validate that `backend` is available in the current environment.

`TrajectoryRecord` includes controller/environment IDs, task ID, replication, tuple of `ToolCallRecord`, final artifact ID or `None`, completion status, optional infrastructure error, and observable messages/events represented as tuples of mappings.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
python -m pytest tests/test_schema.py -q
```

Expected: all schema tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/thrumely/schema.py tests/test_schema.py
git commit -m "feat: define immutable research schemas"
```

---

### Task 3: Canonical Serialization and Hashing

**Files:**
- Create: `src/thrumely/serialization.py`
- Create: `src/thrumely/hashing.py`
- Create: `tests/test_hashing.py`

**Interfaces:**
- Produces:
  - `to_primitive(value: Any) -> Any`
  - `canonical_json_bytes(value: Any) -> bytes`
  - `sha256_bytes(data: bytes) -> str`
  - `sha256_file(path: Path) -> str`
  - `content_hash(value: Any) -> str`

- [ ] **Step 1: Write deterministic hashing tests**

```python
from pathlib import Path

from thrumely.hashing import content_hash, sha256_bytes, sha256_file


def test_mapping_order_does_not_change_content_hash() -> None:
    assert content_hash({"b": 2, "a": 1}) == content_hash({"a": 1, "b": 2})


def test_sha256_file_matches_bytes(tmp_path: Path) -> None:
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"thrumely")
    assert sha256_file(path) == sha256_bytes(b"thrumely")
```

- [ ] **Step 2: Verify RED**

Run `python -m pytest tests/test_hashing.py -q`; expect missing-module failure.

- [ ] **Step 3: Implement canonical serialization/hashing**

Canonical JSON must use UTF-8, sorted keys, compact separators, `ensure_ascii=False`, enum `.value`, dataclass fields recursively, tuples as JSON arrays, and `Path` as POSIX/string path. Unsupported values raise `TypeError` rather than silently stringifying arbitrary objects.

- [ ] **Step 4: Verify GREEN**

Run `python -m pytest tests/test_hashing.py -q`; expect all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/thrumely/serialization.py src/thrumely/hashing.py tests/test_hashing.py
git commit -m "feat: add canonical provenance hashing"
```

---

### Task 4: Public-Artifact Redaction

**Files:**
- Create: `src/thrumely/redaction.py`
- Create: `tests/test_redaction.py`

**Interfaces:**
- Produces:
  - `redact_secrets(value: Any) -> Any`
  - `strip_private_reasoning(value: Any) -> Any`
  - `sanitize_public_payload(value: Any) -> Any`

- [ ] **Step 1: Write redaction tests**

```python
from thrumely.redaction import sanitize_public_payload


def test_public_payload_redacts_secret_keys_and_removes_reasoning() -> None:
    payload = {
        "authorization": "Bearer secret",
        "nested": {"api_key": "abc", "safe": "keep"},
        "reasoning": "private",
        "encrypted_content": "ciphertext",
        "blocks": [
            {"type": "reasoning", "text": "hidden"},
            {"type": "text", "text": "visible"},
        ],
    }
    assert sanitize_public_payload(payload) == {
        "authorization": "[REDACTED]",
        "nested": {"api_key": "[REDACTED]", "safe": "keep"},
        "blocks": [{"type": "text", "text": "visible"}],
    }
```

- [ ] **Step 2: Verify RED**

Run `python -m pytest tests/test_redaction.py -q`; expect missing-module failure.

- [ ] **Step 3: Implement recursive sanitization**

Secret-key detection must be case-insensitive and cover `api_key`, `apikey`, `authorization`, `access_token`, `refresh_token`, `secret`, and `password`. Reasoning stripping removes mapping keys `reasoning` and `encrypted_content`, and removes list items whose `type` is `reasoning` or `redacted_reasoning`.

- [ ] **Step 4: Verify GREEN**

Run `python -m pytest tests/test_redaction.py -q`; expect pass.

- [ ] **Step 5: Commit**

```bash
git add src/thrumely/redaction.py tests/test_redaction.py
git commit -m "feat: sanitize public research artifacts"
```

---

### Task 5: Content-Addressed Media Artifact Store

**Files:**
- Create: `src/thrumely/artifacts.py`
- Create: `tests/test_artifacts.py`

**Interfaces:**
- Consumes: `MediaArtifact`, `MediaStage`, hashing helpers.
- Produces: `ArtifactStore(root: Path)` with `put_media(...) -> MediaArtifact`.

- [ ] **Step 1: Write artifact-store tests**

Test that identical media bytes produce the same artifact ID/hash/path and are not duplicated; differing bytes produce differing IDs. Assert the stored path exists and its hash matches the `MediaArtifact.sha256` field.

- [ ] **Step 2: Verify RED**

Run `python -m pytest tests/test_artifacts.py -q`; expect missing-module failure.

- [ ] **Step 3: Implement content-addressed storage**

Store media as `media/<sha256>.<extension>` where extension is derived from a small explicit MIME mapping (`image/svg+xml -> svg`, `image/png -> png`, `image/jpeg -> jpg`, `image/webp -> webp`). Unsupported MIME types raise `ValueError`.

Artifact IDs are `media:<sha256>`. Do not use provider URLs as artifact identity.

- [ ] **Step 4: Verify GREEN**

Run `python -m pytest tests/test_artifacts.py -q`; expect pass.

- [ ] **Step 5: Commit**

```bash
git add src/thrumely/artifacts.py tests/test_artifacts.py
git commit -m "feat: add content-addressed media store"
```

---

### Task 6: Deterministic Mock Controller, Provider, and Scorer

**Files:**
- Create: `src/thrumely/mock.py`
- Create: `tests/test_mock.py`

**Interfaces:**
- Produces:
  - `MockController.decide(task, environment, call_index, previous_artifact_id) -> NormalizedMediaRequest | None`
  - `MockImageProvider.execute(request) -> tuple[bytes, dict[str, object]]`
  - `MockScorer.score(task, artifact) -> ScorerResult`

- [ ] **Step 1: Write behavior tests**

Tests must prove:

- fixed environment always selects its only backend;
- chooser deterministically selects the first declared backend for the mock path;
- call 1 generates; call 2 returns `None` so the mock controller stops after one image unless a dedicated test subclass asks for a revision;
- provider returns deterministic SVG bytes for the same normalized request;
- provider metadata includes a mock request ID and zero monetary cost;
- scorer returns a deterministic non-human placeholder score explicitly named `mock_artifact_present`, never `faithfulness`.

- [ ] **Step 2: Verify RED**

Run `python -m pytest tests/test_mock.py -q`; expect missing-module failure.

- [ ] **Step 3: Implement minimal mock components**

SVG generation must escape user text before embedding it. The provider has no network access and performs no random I/O.

- [ ] **Step 4: Verify GREEN**

Run `python -m pytest tests/test_mock.py -q`; expect pass.

- [ ] **Step 5: Commit**

```bash
git add src/thrumely/mock.py tests/test_mock.py
git commit -m "feat: add deterministic mock research components"
```

---

### Task 7: Offline End-to-End Runner and Exports

**Files:**
- Create: `src/thrumely/offline.py`
- Create: `tests/test_offline.py`

**Interfaces:**
- Consumes all earlier schema/hash/redaction/artifact/mock interfaces.
- Produces:
  - `run_offline(output_root: Path, run_id: str | None = None) -> Path`
  - CLI: `python -m thrumely.offline --output <dir>`

The public bundle contains:

```text
<run-id>/
├── manifest.json
├── trajectories.jsonl
├── scores.jsonl
└── media/
    └── <sha256>.svg
```

- [ ] **Step 1: Write the integration test**

The test runs one synthetic task in exactly two fake environments (`fixed-a`, `chooser`), asserts two trajectory rows and two score rows, verifies every referenced final media artifact exists, verifies every media hash, verifies the manifest includes the research-spec SHA-256 and Python/package versions, and verifies exported JSON contains no raw secret fixture or reasoning fixture.

- [ ] **Step 2: Verify RED**

Run `python -m pytest tests/test_offline.py -q`; expect missing-runner failure.

- [ ] **Step 3: Implement minimal offline runner**

Use a synthetic task such as `"Create a blue square centered on a white canvas."`. The two mock environments are:

```python
ToolEnvironment("fixed-a", "fixed", ("mock-a",))
ToolEnvironment("chooser", "chooser", ("mock-a", "mock-b", "mock-c"))
```

No production task IDs or real provider names are required.

Manifest fields include run ID, UTC timestamp, package version, Python version, benchmark commit SHA when available, dirty-tree state when available, research-spec SHA-256, requested/completed trajectory counts, media-call budget, controller IDs, environment IDs, and explicit `data_classification="synthetic-offline"`.

If Git metadata is unavailable, record `null` rather than failing the synthetic run.

All exported structured data goes through `sanitize_public_payload` before writing.

- [ ] **Step 4: Verify GREEN and full suite**

Run:

```bash
python -m pytest -q
python -m thrumely.offline --output /tmp/thrumely-offline
```

Expected: all tests pass and CLI prints the generated bundle path.

- [ ] **Step 5: Commit**

```bash
git add src/thrumely/offline.py tests/test_offline.py
git commit -m "feat: run fully offline synthetic experiment"
```

---

### Task 8: Methodology Decision Records and Provider Inventory

**Files:**
- Create: `docs/decisions/0001-neutral-research-identity.md`
- Create: `docs/methodology/THREATS_TO_VALIDITY.md`
- Create: `docs/providers/INVENTORY.md`

**Interfaces:**
- Consumes: `RESEARCH_SPEC.md`, current official provider research.
- Produces: auditable pre-result decisions; no executable API integration.

- [ ] **Step 1: Add neutral-research ADR**

Document that Thrumely is standalone because coupling to GodPrompt would create methodological/reputational bias and because the software-engineering benchmark's deterministic/no-network assumptions do not transfer. Record that GodPrompt may become a later external policy submission, not a v1 primary condition.

- [ ] **Step 2: Add threats-to-validity register**

At minimum cover backend dominance, normalized-schema unfairness, controller/provider coupling, silent hosted-model updates, missing generation seeds, moderation effects, low human agreement, geographic preference skew, automated-judge provider bias, task leakage, provider-media redistribution restrictions, and solo-researcher schedule risk. Each threat gets mitigation and detection stage.

- [ ] **Step 3: Add provider inventory**

Use a dated table with columns: role, provider/model candidate, verified date, first-party source, freeze status, notes.

Record current candidates without freezing them. At minimum include:

- OpenAI image candidate: `gpt-image-2-2026-04-21` dated snapshot;
- Google image candidate: `gemini-3.1-flash-image`;
- BFL image candidate: `flux-2-pro`, with a note that FLUX 3 is now the provider's current leading generation family and must be compared at Week 3 before the final backend freeze;
- OpenAI controller candidate: current GPT-5.6 family candidate, to be reverified at Week 3;
- Anthropic controller candidate: do **not** freeze Opus 5 from the August report; current official docs now identify Claude Fable 5 as the most capable widely released model, so the controller choice requires a Week 3 fairness/cost/capability review.

- [ ] **Step 4: Verify docs contain no frozen unsupported claim**

Run a grep/read review ensuring every model row is marked `candidate`, not `frozen`, and every time-sensitive row includes a verification date/source.

- [ ] **Step 5: Commit**

```bash
git add docs/decisions docs/methodology docs/providers
git commit -m "docs: record methodology and provider candidates"
```

---

### Task 9: Offline GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: Python package/tests.
- Produces: pull-request/push CI that performs no paid/network model calls.

- [ ] **Step 1: Add CI workflow**

Workflow requirements:

```yaml
name: CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: python -m pip install --upgrade pip
      - run: python -m pip install -e '.[test]'
      - run: python -m pytest -q
      - run: python -m thrumely.offline --output .ci-offline
```

No API secrets, provider SDKs, external model calls, or Datapoint calls are permitted in CI.

- [ ] **Step 2: Validate workflow semantics locally by running the same commands**

Run:

```bash
python -m pip install -e '.[test]'
python -m pytest -q
python -m thrumely.offline --output .ci-offline
```

Expected: all commands succeed without credentials.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: verify offline research foundation"
```

---

### Task 10: Final Week-1 Verification

**Files:**
- Modify only if verification exposes a defect.

**Interfaces:**
- Produces a green, inspectable feature branch ready for review.

- [ ] **Step 1: Run complete verification**

```bash
python -m pip install -e '.[test]'
python -m pytest -q
python -m thrumely.offline --output /tmp/thrumely-final-check
```

- [ ] **Step 2: Inspect generated bundle**

Verify manually/programmatically:

- exactly two synthetic trajectories;
- exactly two synthetic score records;
- every final artifact exists and hashes correctly;
- no `authorization`, `api_key`, `access_token`, `refresh_token`, `password`, `reasoning`, or `encrypted_content` values leak into public structured files;
- manifest marks data `synthetic-offline`;
- no real provider SDK dependency exists;
- no Datapoint production configuration exists;
- no benchmark result claim appears in README.

- [ ] **Step 3: Check repository diff for scope**

The feature branch should contain only the research foundation described in this plan. No live-provider adapter, final task corpus, leaderboard, web app, product router, or paid annotation code belongs in this slice.

- [ ] **Step 4: Record verification evidence in the pull request description**

Include exact commands and test counts. Do not claim GitHub-hosted CI passed until the actual Actions result is observed.
