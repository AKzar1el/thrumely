from pathlib import Path

from thrumely.validate_candidates import validate_path


def test_validate_path_reports_missing_file(tmp_path: Path):
    code, text = validate_path(tmp_path / "missing.jsonl")
    assert code == 2
    assert "not found" in text.lower()
