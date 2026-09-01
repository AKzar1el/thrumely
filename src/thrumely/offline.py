from __future__ import annotations

import argparse
import json
import platform
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .artifacts import ArtifactStore
from .hashing import sha256_file
from .mock import MockController, MockImageProvider, MockScorer
from .redaction import sanitize_public_payload
from .schema import (
    CompletionStatus,
    ControllerConfig,
    MediaStage,
    RunManifest,
    TaskSpec,
    ToolCallRecord,
    ToolEnvironment,
    TrajectoryRecord,
)
from .serialization import to_primitive


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _git(repo_root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def _git_metadata(repo_root: Path) -> tuple[str | None, bool | None]:
    commit = _git(repo_root, "rev-parse", "HEAD")
    status = _git(repo_root, "status", "--porcelain")
    dirty = None if status is None else bool(status)
    return commit, dirty


def _write_json(path: Path, value: Any) -> None:
    payload = sanitize_public_payload(to_primitive(value))
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: Iterable[Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for value in values:
            payload = sanitize_public_payload(to_primitive(value))
            handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _synthetic_task() -> TaskSpec:
    return TaskSpec(
        task_id="synthetic-blue-square",
        family="synthetic-offline",
        instruction="Create a blue square centered on a white canvas.",
    )


def run_offline(output_root: Path, run_id: str | None = None) -> Path:
    repo_root = _repo_root()
    research_spec = repo_root / "RESEARCH_SPEC.md"
    if not research_spec.exists():
        raise FileNotFoundError(f"research specification not found: {research_spec}")

    resolved_run_id = run_id or f"offline-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    run_dir = output_root / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    store = ArtifactStore(run_dir)

    task = _synthetic_task()
    controller_config = ControllerConfig("mock-controller", "mock", "mock-v1")
    controller = MockController(controller_config)
    provider = MockImageProvider()
    scorer = MockScorer()
    environments = (
        ToolEnvironment("fixed-a", "fixed", ("mock-a",)),
        ToolEnvironment("chooser", "chooser", ("mock-a", "mock-b", "mock-c")),
    )

    trajectories: list[TrajectoryRecord] = []
    scores = []

    for environment in environments:
        trajectory_id = f"traj-{environment.environment_id}-r1"
        request = controller.decide(
            task,
            environment,
            call_index=1,
            previous_artifact_id=None,
        )
        if request is None:
            raise RuntimeError("mock controller unexpectedly stopped before first media call")

        media_bytes, metadata = provider.execute(request)
        artifact = store.put_media(
            media_bytes,
            mime_type=str(metadata["mime_type"]),
            width=int(metadata["width"]),
            height=int(metadata["height"]),
            stage=MediaStage.FINAL,
        )
        raw_request = dict(metadata["raw_request"])
        raw_request["authorization"] = "Bearer synthetic-secret"
        raw_response = dict(metadata["raw_response"])
        raw_response["encrypted_content"] = "synthetic-encrypted-reasoning"

        tool_call = ToolCallRecord(
            call_index=1,
            request=request,
            raw_request=raw_request,
            raw_response=raw_response,
            request_id=str(metadata["request_id"]),
            artifact_id=artifact.artifact_id,
            latency_seconds=float(metadata["latency_seconds"]),
            cost_usd=float(metadata["cost_usd"]),
            error=None,
            moderation_status=None,
        )

        second_decision = controller.decide(
            task,
            environment,
            call_index=2,
            previous_artifact_id=artifact.artifact_id,
        )
        if second_decision is not None:
            raise RuntimeError("default mock controller must stop after the first media call")

        trajectory = TrajectoryRecord(
            trajectory_id=trajectory_id,
            task_id=task.task_id,
            controller_id=controller_config.controller_id,
            environment_id=environment.environment_id,
            replication=1,
            tool_calls=(tool_call,),
            final_artifact_id=artifact.artifact_id,
            completion_status=CompletionStatus.SUCCESS,
            infrastructure_error=None,
            messages=(
                {"role": "user", "content": task.instruction},
                {
                    "role": "assistant",
                    "content": [
                        {"type": "reasoning", "text": "synthetic private reasoning"},
                        {"type": "text", "text": "mock image created"},
                    ],
                },
            ),
            events=(
                {"type": "tool", "request_id": metadata["request_id"]},
                {"type": "decision", "action": "stop"},
            ),
        )
        trajectories.append(trajectory)
        scores.append(scorer.score(task, trajectory_id=trajectory_id, artifact=artifact))

    commit_sha, working_tree_dirty = _git_metadata(repo_root)
    manifest = RunManifest(
        run_id=resolved_run_id,
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        package_version=__version__,
        python_version=platform.python_version(),
        benchmark_commit_sha=commit_sha,
        working_tree_dirty=working_tree_dirty,
        research_spec_sha256=sha256_file(research_spec),
        requested_trajectories=len(environments),
        completed_trajectories=sum(
            trajectory.completion_status is CompletionStatus.SUCCESS for trajectory in trajectories
        ),
        media_call_budget=2,
        controller_ids=(controller_config.controller_id,),
        environment_ids=tuple(environment.environment_id for environment in environments),
        data_classification="synthetic-offline",
    )

    _write_json(run_dir / "manifest.json", manifest)
    _write_jsonl(run_dir / "trajectories.jsonl", trajectories)
    _write_jsonl(run_dir / "scores.jsonl", scores)
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Thrumely's zero-cost synthetic offline research pipeline")
    parser.add_argument("--output", type=Path, default=Path("results/offline"))
    args = parser.parse_args()
    result = run_offline(args.output)
    print(result)


if __name__ == "__main__":
    main()
