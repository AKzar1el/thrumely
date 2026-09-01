from pathlib import Path

from thrumely.corpus import FAMILIES, load_candidate_jsonl, validate_candidate_corpus

ROOT = Path(__file__).resolve().parents[1]


def test_candidate_dataset_is_balanced_valid_and_unfrozen():
    tasks = load_candidate_jsonl(ROOT / "candidates/tasks-v0.1.jsonl")
    assert len(tasks) == 150
    assert validate_candidate_corpus(tasks) == ()
    assert {task.family for task in tasks} == set(FAMILIES)
    assert len({task.task_id for task in tasks}) == 150
    assert all(task.corpus_status == "candidate" for task in tasks)
    assert all(3 <= len(task.atomic_requirements) <= 7 for task in tasks)
    assert all(2 <= len(task.evaluation_questions) <= 6 for task in tasks)
    assert all("aspect_ratio" in task.deterministic_checks for task in tasks)
