import json
from pathlib import Path

from thrumely.corpus import load_candidate_jsonl
from thrumely.scoring import candidate_metric_registry

ROOT = Path(__file__).resolve().parents[1]


def test_candidate_pool_stays_separate_from_calibration_and_unfrozen():
    candidates = load_candidate_jsonl(ROOT / "candidates/tasks-v0.1.jsonl")
    calibration = json.loads((ROOT / "calibration/tasks/openai-smoke.json").read_text(encoding="utf-8"))["tasks"]
    candidate_ids = {task.task_id for task in candidates}
    calibration_ids = {task["task_id"] for task in calibration}
    candidate_instructions = {task.instruction.strip().casefold() for task in candidates}
    calibration_instructions = {task["instruction"].strip().casefold() for task in calibration}
    assert len(candidates) == 150
    assert candidate_ids.isdisjoint(calibration_ids)
    assert candidate_instructions.isdisjoint(calibration_instructions)
    assert all(task.corpus_status == "candidate" for task in candidates)


def test_no_model_backed_metric_is_primary_eligible():
    metrics = candidate_metric_registry()
    assert all(not metric.primary_eligible for metric in metrics if metric.requires_model)
