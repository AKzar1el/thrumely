from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

FAMILIES = (
    "compositional constraints",
    "typography and layout",
    "styled visual brief",
    "product/editorial scene",
    "revision-sensitive multi-constraint brief",
)
ASPECT_RATIOS = ("1:1", "3:2", "2:3", "16:9", "9:16")


def _require_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_text_tuple(name: str, values: tuple[str, ...]) -> None:
    if not values or not all(isinstance(item, str) and item.strip() for item in values):
        raise ValueError(f"{name} must contain at least one non-empty string")


@dataclass(frozen=True)
class CandidateTaskSpec:
    task_id: str
    family: str
    instruction: str
    target_aspect_ratio: str
    atomic_requirements: tuple[str, ...]
    evaluation_questions: tuple[str, ...]
    human_rubric_notes: str
    deterministic_checks: tuple[str, ...]
    risk_flags: tuple[str, ...] = ()
    corpus_status: str = "candidate"

    def __post_init__(self) -> None:
        _require_text("task_id", self.task_id)
        if self.family not in FAMILIES:
            raise ValueError(f"unsupported family: {self.family}")
        _require_text("instruction", self.instruction)
        if self.target_aspect_ratio not in ASPECT_RATIOS:
            raise ValueError(f"unsupported target_aspect_ratio: {self.target_aspect_ratio}")
        _require_text_tuple("atomic_requirements", self.atomic_requirements)
        _require_text_tuple("evaluation_questions", self.evaluation_questions)
        _require_text("human_rubric_notes", self.human_rubric_notes)
        _require_text_tuple("deterministic_checks", self.deterministic_checks)
        if not all(isinstance(item, str) and item.strip() for item in self.risk_flags):
            raise ValueError("risk_flags must contain only non-empty strings")
        if self.corpus_status != "candidate":
            raise ValueError("corpus_status must remain 'candidate' before the production freeze gate")

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "family": self.family,
            "instruction": self.instruction,
            "target_aspect_ratio": self.target_aspect_ratio,
            "atomic_requirements": list(self.atomic_requirements),
            "evaluation_questions": list(self.evaluation_questions),
            "human_rubric_notes": self.human_rubric_notes,
            "deterministic_checks": list(self.deterministic_checks),
            "risk_flags": list(self.risk_flags),
            "corpus_status": self.corpus_status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "CandidateTaskSpec":
        def scalar(name: str, *, default: str | None = None) -> str:
            value = data.get(name, default) if default is not None else data[name]
            if not isinstance(value, str):
                raise ValueError(f"{name} must be a string")
            return value

        def sequence(name: str, *, default: tuple[str, ...] | None = None) -> tuple[str, ...]:
            value = data.get(name, default) if default is not None else data[name]
            if not isinstance(value, (list, tuple)):
                raise ValueError(f"{name} must be a JSON array")
            if not all(isinstance(item, str) for item in value):
                raise ValueError(f"{name} must contain only strings")
            return tuple(value)

        return cls(
            task_id=scalar("task_id"),
            family=scalar("family"),
            instruction=scalar("instruction"),
            target_aspect_ratio=scalar("target_aspect_ratio"),
            atomic_requirements=sequence("atomic_requirements"),
            evaluation_questions=sequence("evaluation_questions"),
            human_rubric_notes=scalar("human_rubric_notes"),
            deterministic_checks=sequence("deterministic_checks"),
            risk_flags=sequence("risk_flags", default=()),
            corpus_status=scalar("corpus_status", default="candidate"),
        )


def load_candidate_jsonl(path: str | Path) -> tuple[CandidateTaskSpec, ...]:
    source = Path(path)
    tasks: list[CandidateTaskSpec] = []
    with source.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {line_number}: {exc.msg}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"line {line_number} must contain a JSON object")
            try:
                tasks.append(CandidateTaskSpec.from_dict(payload))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid candidate on line {line_number}: {exc}") from exc
    return tuple(tasks)


def validate_candidate_corpus(
    tasks: Iterable[CandidateTaskSpec],
    *,
    expected_total: int = 150,
    expected_per_family: int = 30,
) -> tuple[str, ...]:
    materialized = tuple(tasks)
    issues: list[str] = []
    if len(materialized) != expected_total:
        issues.append(f"expected {expected_total} candidates, found {len(materialized)}")

    ids = [task.task_id for task in materialized]
    duplicates = sorted({task_id for task_id in ids if ids.count(task_id) > 1})
    if duplicates:
        issues.append("duplicate task_id values: " + ", ".join(duplicates))

    for family in FAMILIES:
        count = sum(task.family == family for task in materialized)
        if count != expected_per_family:
            issues.append(f"family {family!r} expected {expected_per_family}, found {count}")

    for task in materialized:
        if task.corpus_status != "candidate":
            issues.append(f"{task.task_id}: corpus_status must be candidate")
    return tuple(issues)


def canonical_candidate_corpus_hash(tasks: Iterable[CandidateTaskSpec]) -> str:
    payload = [task.to_dict() for task in tasks]
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
