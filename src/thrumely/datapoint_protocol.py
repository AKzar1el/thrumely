from __future__ import annotations

from typing import Iterable, Mapping

PAIRWISE_INSTRUCTION = (
    "Imagine that you submitted the request shown for this item. Which result would you prefer to receive overall? "
    "Consider whether it satisfies the requested content, composition, text, style, and other constraints, as well as overall visual quality."
)
RATING_INSTRUCTION = "How faithfully does this image satisfy the user's request?\n\nUser request: {context}"
RATING_LABELS = {
    "1": "Major requirements are absent, contradicted, or badly wrong.",
    "2": "Several important requirements are missed or materially incorrect.",
    "3": "The request is partly satisfied, but there are notable omissions or errors.",
    "4": "Nearly all important requirements are satisfied; remaining problems are minor.",
    "5": "All observable important requirements are satisfied with no material contradiction.",
}


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _media_ref(value: object) -> str:
    ref = _require_text("media reference", value)
    if not (ref.startswith("dp://") or ref.startswith("https://")):
        raise ValueError("media reference must use dp:// or https://")
    return ref


def _response_count(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 10000:
        raise ValueError("max_responses_per_datapoint must be an integer in [1, 10000]")
    return value


def build_pairwise_sandbox_job(
    name: str,
    pairs: Iterable[Mapping[str, object]],
    *,
    max_responses_per_datapoint: int = 5,
) -> dict[str, object]:
    _require_text("name", name)
    count = _response_count(max_responses_per_datapoint)
    datapoints: list[dict[str, object]] = []
    for index, pair in enumerate(pairs):
        if not isinstance(pair, Mapping):
            raise ValueError(f"pair {index} must be a mapping")
        context = _require_text("context", pair.get("context"))
        a = _media_ref(pair.get("candidate_a"))
        b = _media_ref(pair.get("candidate_b"))
        if a == b:
            raise ValueError("pair candidates must be distinct media references")
        datapoints.append({
            "context": context,
            "media": {
                "candidates": [
                    {"url": a, "type": "image"},
                    {"url": b, "type": "image"},
                ]
            },
        })
    if not datapoints:
        raise ValueError("pairs must contain at least one datapoint")
    return {
        "name": name,
        "instruction": PAIRWISE_INSTRUCTION,
        "task_type": "comparison",
        "max_responses_per_datapoint": count,
        "serving_environment": "sandbox",
        "datapoints": datapoints,
    }


def build_rating_sandbox_job(
    name: str,
    items: Iterable[Mapping[str, object]],
    *,
    max_responses_per_datapoint: int = 5,
) -> dict[str, object]:
    _require_text("name", name)
    count = _response_count(max_responses_per_datapoint)
    datapoints: list[dict[str, object]] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise ValueError(f"rating item {index} must be a mapping")
        context = _require_text("context", item.get("context"))
        subject = _media_ref(item.get("subject"))
        datapoints.append({
            "context": context,
            "media": {"subject": [{"url": subject, "type": "image"}]},
        })
    if not datapoints:
        raise ValueError("items must contain at least one datapoint")
    return {
        "name": name,
        "instruction": RATING_INSTRUCTION,
        "task_type": "rating",
        "response_options": {"scale": [1, 2, 3, 4, 5], "labels": RATING_LABELS},
        "max_responses_per_datapoint": count,
        "serving_environment": "sandbox",
        "datapoints": datapoints,
    }
