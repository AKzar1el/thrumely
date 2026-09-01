from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .artifacts import ArtifactStore
from .hashing import sha256_file
from .openai_controller import (
    ControllerExecutionError,
    ControllerProtocolError,
    OpenAIController,
    system_prompt_sha256,
)
from .openai_provider import OpenAIImageProvider, ProviderExecutionError
from .redaction import sanitize_public_payload
from .schema import (
    CompletionStatus,
    ControllerConfig,
    MediaArtifact,
    MediaOperation,
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
    return commit, None if status is None else bool(status)


def _write_json(path: Path, value: Any) -> None:
    payload = sanitize_public_payload(to_primitive(value))
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: Iterable[Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for value in values:
            payload = sanitize_public_payload(to_primitive(value))
            handle.write(json.dumps(payload, sort_keys=True) + "\n")


def load_calibration_tasks(path: Path) -> tuple[TaskSpec, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("calibration task file must contain a JSON object")
    if raw.get("calibration_only") is not True:
        raise ValueError("calibration task file requires calibration_only=true")
    rows = raw.get("tasks")
    if not isinstance(rows, list) or not rows:
        raise ValueError("calibration task file requires a non-empty tasks list")

    tasks: list[TaskSpec] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each calibration task must be a JSON object")
        required = {"task_id", "family", "instruction"}
        if set(row) != required:
            raise ValueError("calibration task must contain exactly task_id, family, and instruction")
        task_id = str(row["task_id"])
        if not task_id.startswith("cal-"):
            raise ValueError("calibration task_id must start with 'cal-'")
        if task_id in seen:
            raise ValueError(f"duplicate calibration task_id: {task_id}")
        seen.add(task_id)
        tasks.append(
            TaskSpec(
                task_id=task_id,
                family=str(row["family"]),
                instruction=str(row["instruction"]),
            )
        )
    return tuple(tasks)


def _public_task_path(task_path: Path, repo_root: Path) -> str:
    try:
        return task_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return task_path.name


def _controller_message(turn: int, decision: Any) -> dict[str, Any]:
    return {
        "role": "controller",
        "turn": turn,
        "response_id": decision.response_id,
        "actual_model": decision.actual_model,
        "usage": dict(decision.usage),
        "observable_output": list(decision.observable_output),
        "action": decision.action,
    }


def _tool_record(call_index: int, request: Any, result: Any, artifact: MediaArtifact) -> ToolCallRecord:
    return ToolCallRecord(
        call_index=call_index,
        request=request,
        raw_request=result.raw_request,
        raw_response=result.raw_response,
        request_id=result.request_id,
        artifact_id=artifact.artifact_id,
        latency_seconds=result.latency_seconds,
        cost_usd=result.cost_usd,
        error=None,
        moderation_status=result.moderation_status,
        provider=result.provider,
        model=result.model,
        retry_count=result.retry_count,
        usage=result.usage,
    )


def run_calibration(
    output_root: Path,
    task_path: Path,
    controller: Any,
    provider: Any,
    *,
    replication: int = 1,
    run_id: str | None = None,
) -> Path:
    if replication < 1:
        raise ValueError("replication must be >= 1")
    tasks = load_calibration_tasks(task_path)
    repo_root = _repo_root()
    research_spec = repo_root / "RESEARCH_SPEC.md"
    if not research_spec.exists():
        raise FileNotFoundError(f"research specification not found: {research_spec}")

    resolved_run_id = run_id or f"calibration-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    run_dir = output_root / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(task_path, run_dir / "tasks.json")
    store = ArtifactStore(run_dir)

    backend_id = str(provider.backend_id)
    environment = ToolEnvironment(
        environment_id=f"fixed-{provider.provider}",
        mode="fixed",
        available_backends=(backend_id,),
        media_call_budget=2,
    )

    trajectories: list[TrajectoryRecord] = []
    media_records: list[MediaArtifact] = []

    for task in tasks:
        trajectory_id = f"traj-{task.task_id}-r{replication}"
        tool_calls: list[ToolCallRecord] = []
        messages: list[dict[str, Any]] = [{"role": "user", "content": task.instruction}]
        events: list[dict[str, Any]] = []
        final_artifact_id: str | None = None
        infrastructure_error: str | None = None
        completion_status = CompletionStatus.ERROR
        first_artifact: MediaArtifact | None = None
        first_media: bytes | None = None

        try:
            first_decision = controller.decide(task, environment, call_index=1)
            messages.append(_controller_message(1, first_decision))
            if first_decision.action != "media" or first_decision.request is None:
                raise ControllerProtocolError("first controller decision must be a media action")

            first_result = provider.execute(first_decision.request)
            first_media = first_result.media_bytes
            first_artifact = store.put_media(
                first_media,
                mime_type=first_result.mime_type,
                width=first_result.width,
                height=first_result.height,
                stage=MediaStage.FIRST,
            )
            tool_calls.append(_tool_record(1, first_decision.request, first_result, first_artifact))
            events.append({"type": "media_artifact", "call_index": 1, "artifact": to_primitive(first_artifact)})

            second_decision = controller.decide(
                task,
                environment,
                call_index=2,
                previous_artifact=first_artifact,
                previous_media=first_media,
            )
            messages.append(_controller_message(2, second_decision))

            if second_decision.action == "finish":
                final_artifact = replace(first_artifact, stage=MediaStage.FINAL)
                media_records.append(final_artifact)
                final_artifact_id = final_artifact.artifact_id
                events.append({"type": "decision", "action": "finish", "final_artifact_id": final_artifact_id})
            else:
                if second_decision.request is None:
                    raise ControllerProtocolError("second media action is missing request")
                previous_media = (
                    first_media
                    if second_decision.request.operation is MediaOperation.EDIT_PREVIOUS
                    else None
                )
                second_result = provider.execute(second_decision.request, previous_media=previous_media)
                second_artifact = store.put_media(
                    second_result.media_bytes,
                    mime_type=second_result.mime_type,
                    width=second_result.width,
                    height=second_result.height,
                    stage=MediaStage.FINAL,
                )
                media_records.extend((first_artifact, second_artifact))
                tool_calls.append(_tool_record(2, second_decision.request, second_result, second_artifact))
                final_artifact_id = second_artifact.artifact_id
                events.append({"type": "media_artifact", "call_index": 2, "artifact": to_primitive(second_artifact)})
                events.append({"type": "decision", "action": "finish_after_second_call", "final_artifact_id": final_artifact_id})

            completion_status = CompletionStatus.SUCCESS
        except (ControllerExecutionError, ControllerProtocolError, ProviderExecutionError) as exc:
            infrastructure_error = f"{type(exc).__name__}: {exc}"
            if first_artifact is not None and not any(
                artifact.artifact_id == first_artifact.artifact_id and artifact.stage is MediaStage.FIRST
                for artifact in media_records
            ):
                media_records.append(first_artifact)
            events.append({"type": "terminal_error", "error_type": type(exc).__name__, "message": str(exc)})

        trajectories.append(
            TrajectoryRecord(
                trajectory_id=trajectory_id,
                task_id=task.task_id,
                controller_id=controller.config.controller_id,
                environment_id=environment.environment_id,
                replication=replication,
                tool_calls=tuple(tool_calls),
                final_artifact_id=final_artifact_id,
                completion_status=completion_status,
                infrastructure_error=infrastructure_error,
                messages=tuple(messages),
                events=tuple(events),
            )
        )

    commit_sha, working_tree_dirty = _git_metadata(repo_root)
    manifest = RunManifest(
        run_id=resolved_run_id,
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        package_version=__version__,
        python_version=platform.python_version(),
        benchmark_commit_sha=commit_sha,
        working_tree_dirty=working_tree_dirty,
        research_spec_sha256=sha256_file(research_spec),
        requested_trajectories=len(tasks),
        completed_trajectories=sum(
            trajectory.completion_status is CompletionStatus.SUCCESS for trajectory in trajectories
        ),
        media_call_budget=environment.media_call_budget,
        controller_ids=(controller.config.controller_id,),
        environment_ids=(environment.environment_id,),
        data_classification="live-calibration",
        task_corpus_sha256=sha256_file(task_path),
    )
    configuration = {
        "calibration_only": True,
        "controller": controller.config,
        "environment": environment,
        "provider": {
            "provider": provider.provider,
            "logical_backend_id": backend_id,
            "model": provider.model,
        },
        "task_file": _public_task_path(task_path, repo_root),
        "task_corpus_sha256": sha256_file(task_path),
    }

    _write_json(run_dir / "manifest.json", manifest)
    _write_json(run_dir / "configuration.json", configuration)
    _write_jsonl(run_dir / "trajectories.jsonl", trajectories)
    _write_jsonl(run_dir / "media.jsonl", media_records)
    return run_dir


def _openai_sdk_version() -> str:
    try:
        return version("openai")
    except PackageNotFoundError as exc:
        raise RuntimeError("OpenAI live calibration requires `pip install -e '.[openai]'`") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Thrumely's calibration-only OpenAI live pipeline")
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("results/calibration"))
    parser.add_argument("--replication", type=int, default=1)
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required for live calibration")

    sdk_version = _openai_sdk_version()
    config = ControllerConfig(
        controller_id="openai-sol-calibration",
        provider="openai",
        model="gpt-5.6-sol",
        reasoning_effort="medium",
        max_output_tokens=1024,
        system_prompt_sha256=system_prompt_sha256(),
        sdk_version=sdk_version,
    )
    controller = OpenAIController(config)
    provider = OpenAIImageProvider()
    result = run_calibration(
        args.output,
        args.tasks,
        controller,
        provider,
        replication=args.replication,
    )
    print(result)


if __name__ == "__main__":
    main()
