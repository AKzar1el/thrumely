import json
from pathlib import Path

import pytest

from thrumely.corpus import (
    CandidateTaskSpec,
    FAMILIES,
    canonical_candidate_corpus_hash,
    load_candidate_jsonl,
    validate_candidate_corpus,
)


def make_task(task_id="comp-001", family="compositional constraints"):
    return CandidateTaskSpec(
        task_id=task_id,
        family=family,
        instruction="Create a square image with a red mug left of a blue book.",
        target_aspect_ratio="1:1",
        atomic_requirements=("red mug", "blue book", "mug left of book"),
        evaluation_questions=("Is there a red mug?", "Is the mug left of the blue book?"),
        human_rubric_notes="Prioritize object identity, color, and left-right relation.",
        deterministic_checks=("aspect_ratio",),
        risk_flags=(),
    )


def test_candidate_requires_supported_family_and_candidate_status():
    with pytest.raises(ValueError, match="unsupported family"):
        make_task(family="other")
    with pytest.raises(ValueError, match="corpus_status"):
        CandidateTaskSpec(**{**make_task().__dict__, "corpus_status": "frozen"})


def test_candidate_requires_authored_evaluation_material():
    base = make_task().__dict__
    for field in ("atomic_requirements", "evaluation_questions", "human_rubric_notes", "deterministic_checks"):
        bad = dict(base)
        bad[field] = () if field != "human_rubric_notes" else ""
        with pytest.raises(ValueError):
            CandidateTaskSpec(**bad)


def test_validate_corpus_checks_counts_and_unique_ids():
    tasks = []
    for family_index, family in enumerate(FAMILIES):
        prefix = ("comp", "type", "style", "editorial", "revision")[family_index]
        for i in range(30):
            tasks.append(make_task(f"{prefix}-{i+1:03d}", family))
    assert validate_candidate_corpus(tasks) == ()
    issues = validate_candidate_corpus(tasks + [tasks[0]])
    assert any("expected 150" in issue for issue in issues)
    assert any("duplicate task_id" in issue for issue in issues)


def test_canonical_hash_is_order_sensitive_but_mapping_stable(tmp_path: Path):
    first = make_task()
    second = make_task("comp-002")
    h1 = canonical_candidate_corpus_hash((first, second))
    h2 = canonical_candidate_corpus_hash((first, second))
    assert h1 == h2 and len(h1) == 64
    assert canonical_candidate_corpus_hash((second, first)) != h1

    path = tmp_path / "tasks.jsonl"
    path.write_text("\n".join(json.dumps(task.to_dict(), sort_keys=True) for task in (first, second)) + "\n", encoding="utf-8")
    loaded = load_candidate_jsonl(path)
    assert loaded == (first, second)


def test_from_dict_rejects_scalar_sequence_fields():
    payload = make_task().to_dict()
    payload["atomic_requirements"] = "redmug"
    with pytest.raises(ValueError, match="atomic_requirements"):
        CandidateTaskSpec.from_dict(payload)


def test_from_dict_rejects_non_string_scalar_fields():
    payload = make_task().to_dict()
    payload["task_id"] = None
    with pytest.raises(ValueError, match="task_id"):
        CandidateTaskSpec.from_dict(payload)

    payload = make_task().to_dict()
    payload["human_rubric_notes"] = 123
    with pytest.raises(ValueError, match="human_rubric_notes"):
        CandidateTaskSpec.from_dict(payload)


def test_from_dict_rejects_non_string_array_items():
    payload = make_task().to_dict()
    payload["atomic_requirements"] = [123]
    with pytest.raises(ValueError, match="atomic_requirements"):
        CandidateTaskSpec.from_dict(payload)
