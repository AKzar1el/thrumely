from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from .corpus import canonical_candidate_corpus_hash, load_candidate_jsonl, validate_candidate_corpus


def validate_path(path: str | Path) -> tuple[int, str]:
    source = Path(path)
    if not source.exists():
        return 2, f"Candidate corpus not found: {source}"
    try:
        tasks = load_candidate_jsonl(source)
    except ValueError as exc:
        return 2, f"Candidate corpus parse error: {exc}"
    issues = validate_candidate_corpus(tasks)
    if issues:
        return 1, "Candidate corpus validation: FAIL\n" + "\n".join(f"- {issue}" for issue in issues)
    counts = Counter(task.family for task in tasks)
    lines = [
        "Candidate corpus validation: PASS",
        "Status: UNFROZEN_CANDIDATE_POOL",
        f"Candidates: {len(tasks)}",
        f"Development SHA-256: {canonical_candidate_corpus_hash(tasks)}",
    ]
    lines.extend(f"{family}: {count}" for family, count in sorted(counts.items()))
    return 0, "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an unfrozen Thrumely candidate-task JSONL file.")
    parser.add_argument("path")
    args = parser.parse_args(argv)
    code, text = validate_path(args.path)
    print(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
