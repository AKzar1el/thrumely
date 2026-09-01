from __future__ import annotations

import re
from dataclasses import dataclass

_ASPECTS = {
    "1:1": 1.0,
    "3:2": 3 / 2,
    "2:3": 2 / 3,
    "16:9": 16 / 9,
    "9:16": 9 / 16,
}


@dataclass(frozen=True)
class MetricDescriptor:
    name: str
    role: str
    implementation_status: str
    requires_model: bool
    primary_eligible: bool
    notes: str

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.role.strip() or not self.notes.strip():
            raise ValueError("metric descriptor text fields must be non-empty")
        if self.implementation_status not in {"implemented", "future_optional"}:
            raise ValueError("unsupported implementation_status")
        if self.requires_model and self.primary_eligible:
            raise ValueError("model-backed automatic metrics cannot be primary-eligible in v1")


def aspect_ratio_score(target: str, width: int, height: int, *, tolerance: float = 0.02) -> float:
    if target not in _ASPECTS:
        raise ValueError(f"unsupported aspect ratio: {target}")
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")
    expected = _ASPECTS[target]
    actual = width / height
    relative_error = abs(actual - expected) / expected
    return 1.0 if relative_error <= tolerance else 0.0


def normalize_ocr_text(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    normalized = re.sub(r"[^0-9a-z]+", " ", text.casefold())
    return " ".join(normalized.split())


def required_text_score(required: tuple[str, ...], observed_ocr_text: str) -> float | None:
    if not required:
        return None
    if not all(isinstance(item, str) and item.strip() for item in required):
        raise ValueError("required strings must be non-empty")
    observed = normalize_ocr_text(observed_ocr_text)
    matches = sum(normalize_ocr_text(item) in observed for item in required)
    return matches / len(required)


def atomic_coverage(requirement_ids: tuple[str, ...], satisfied_ids: set[str]) -> float | None:
    if not requirement_ids:
        return None
    if len(set(requirement_ids)) != len(requirement_ids):
        raise ValueError("requirement_ids must be unique")
    unknown = sorted(satisfied_ids.difference(requirement_ids))
    if unknown:
        raise ValueError("unknown satisfied requirement IDs: " + ", ".join(unknown))
    return len(satisfied_ids) / len(requirement_ids)


def candidate_metric_registry() -> tuple[MetricDescriptor, ...]:
    return (
        MetricDescriptor("aspect_ratio", "deterministic output geometry compliance", "implemented", False, False, "Checks final media dimensions against the task-authored target aspect ratio."),
        MetricDescriptor("required_text", "deterministic OCR string compliance", "implemented", False, False, "Scores exact required strings against externally supplied OCR text after fixed normalization."),
        MetricDescriptor("tool_validity", "process telemetry", "implemented", False, False, "Uses recorded provider/tool execution states rather than image judgment."),
        MetricDescriptor("tifa_style_qa", "fine-grained instruction faithfulness", "future_optional", True, False, "Uses task-authored frozen image-answerable questions; no inference is run in the zero-cost slice."),
        MetricDescriptor("vqascore", "semantic image-text faithfulness", "future_optional", True, False, "Candidate model-backed semantic faithfulness metric; optional adapter only."),
        MetricDescriptor("clipscore", "historical embedding baseline", "future_optional", True, False, "Historical reference-free embedding baseline, not a primary endpoint."),
        MetricDescriptor("hpsv2", "human-preference prediction baseline", "future_optional", True, False, "Preference/reward baseline for later validation against human judgments."),
        MetricDescriptor("pairwise_vlm_judge", "pairwise automated judge", "future_optional", True, False, "Must be run in both A/B and B/A order when implemented."),
    )
