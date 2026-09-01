from __future__ import annotations

from typing import Mapping


def _require_envelope(payload: Mapping[str, object], task_type: str, list_key: str) -> tuple[str, list[object]]:
    if payload.get("task_type") != task_type:
        raise ValueError(f"task_type must be {task_type!r}")
    job_id = payload.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("job_id must be a non-empty string")
    rows = payload.get(list_key)
    if not isinstance(rows, list):
        raise ValueError(f"{list_key} must be a list")
    return job_id, rows


def _require_int(name: str, value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    return value


def normalize_comparison_results(payload: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    job_id, rows = _require_envelope(payload, "comparison", "results")
    output: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("comparison result row must be an object")
        votes = row.get("votes")
        if not isinstance(votes, Mapping):
            raise ValueError("comparison votes must be an object")
        media = row.get("media")
        if not isinstance(media, list):
            raise ValueError("comparison media must be a list")
        candidates = [item for item in media if isinstance(item, Mapping) and item.get("role") == "candidates"]
        if len(candidates) != 2:
            raise ValueError("comparison result must expose two candidate media items")
        media_ids = [item.get("media_id") for item in candidates]
        if not all(isinstance(item, str) and item for item in media_ids):
            raise ValueError("comparison candidate media_id values must be strings")
        output.append({
            "job_id": job_id,
            "datapoint_index": _require_int("datapoint_index", row.get("datapoint_index")),
            "votes_a": _require_int("votes.A", votes.get("A")),
            "votes_b": _require_int("votes.B", votes.get("B")),
            "consensus": row.get("consensus"),
            "total_responses": _require_int("total_responses", row.get("total_responses")),
            "confidence": row.get("confidence"),
            "agreement_rate": row.get("agreement_rate"),
            "media_id_a": media_ids[0],
            "media_id_b": media_ids[1],
        })
    return tuple(output)


def normalize_rating_results(payload: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    job_id, rows = _require_envelope(payload, "rating", "results")
    output: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("rating result row must be an object")
        distribution = row.get("distribution")
        if not isinstance(distribution, Mapping):
            raise ValueError("rating distribution must be an object")
        output.append({
            "job_id": job_id,
            "datapoint_index": _require_int("datapoint_index", row.get("datapoint_index")),
            "mean": row.get("mean"),
            "median": row.get("median"),
            "distribution": dict(distribution),
            "total_responses": _require_int("total_responses", row.get("total_responses")),
            "weighted_mean": row.get("weighted_mean"),
            "weighted_distribution": dict(row["weighted_distribution"]) if isinstance(row.get("weighted_distribution"), Mapping) else None,
        })
    return tuple(output)


def normalize_public_responses(payload: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    job_id = payload.get("job_id")
    task_type = payload.get("task_type")
    responses = payload.get("responses")
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("job_id must be a non-empty string")
    if not isinstance(task_type, str) or not task_type:
        raise ValueError("task_type must be a non-empty string")
    if not isinstance(responses, list):
        raise ValueError("responses must be a list")
    allowed = ("datapoint_index", "response", "response_label", "response_labels", "response_time_ms", "annotator_id", "annotator_country", "timestamp", "step_index", "task_type")
    output: list[dict[str, object]] = []
    for row in responses:
        if not isinstance(row, Mapping):
            raise ValueError("raw response row must be an object")
        normalized = {"job_id": job_id, "job_task_type": task_type}
        for key in allowed:
            if key in row:
                normalized[key] = row[key]
        output.append(normalized)
    return tuple(output)
