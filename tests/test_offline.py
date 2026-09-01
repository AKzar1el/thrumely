import json
from pathlib import Path

from thrumely.hashing import sha256_file
from thrumely.offline import run_offline


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_offline_run_exports_two_synthetic_trajectories_with_verified_media(tmp_path: Path) -> None:
    run_dir = run_offline(tmp_path, run_id="offline-test")

    manifest_path = run_dir / "manifest.json"
    trajectories_path = run_dir / "trajectories.jsonl"
    scores_path = run_dir / "scores.jsonl"
    assert manifest_path.exists()
    assert trajectories_path.exists()
    assert scores_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    trajectories = _jsonl(trajectories_path)
    scores = _jsonl(scores_path)

    assert manifest["run_id"] == "offline-test"
    assert manifest["data_classification"] == "synthetic-offline"
    assert manifest["requested_trajectories"] == 2
    assert manifest["completed_trajectories"] == 2
    assert manifest["package_version"] == "0.1.0"
    assert len(manifest["research_spec_sha256"]) == 64
    assert len(trajectories) == 2
    assert len(scores) == 2

    for trajectory in trajectories:
        artifact_id = trajectory["final_artifact_id"]
        assert isinstance(artifact_id, str)
        digest = artifact_id.removeprefix("media:")
        media_path = run_dir / "media" / f"{digest}.svg"
        assert media_path.exists()
        assert sha256_file(media_path) == digest

    public_text = manifest_path.read_text(encoding="utf-8") + trajectories_path.read_text(encoding="utf-8") + scores_path.read_text(encoding="utf-8")
    assert "Bearer synthetic-secret" not in public_text
    assert "synthetic private reasoning" not in public_text
    assert "encrypted_content" not in public_text
    assert "[REDACTED]" in public_text


def test_offline_run_uses_only_mock_backends(tmp_path: Path) -> None:
    trajectories = _jsonl(run_offline(tmp_path, run_id="mock-only") / "trajectories.jsonl")
    backends = {
        tool_call["request"]["backend"]
        for trajectory in trajectories
        for tool_call in trajectory["tool_calls"]
    }
    assert backends == {"mock-a"}
