from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import urllib.error
import urllib.request
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Iterable, Mapping

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
from .vercel_gateway import (
    VERCEL_CONTROLLER_MODEL,
    VERCEL_GATEWAY_BASE_URL,
    VERCEL_GATEWAY_TIMEOUT_SECONDS,
    VERCEL_IMAGE_MODEL,
    VERCEL_IMAGE_RELEASE_DATE,
    openai_only_extra_body,
)


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


def fetch_vercel_gateway_credits(
    api_key: str,
    *,
    opener: Any | None = None,
) -> dict[str, str]:
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("AI Gateway API key must be a non-empty string")
    request = urllib.request.Request(
        f"{VERCEL_GATEWAY_BASE_URL}/credits",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    open_request = opener or urllib.request.urlopen
    try:
        with open_request(request, timeout=VERCEL_GATEWAY_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Vercel AI Gateway credit check failed ({type(exc).__name__})") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Vercel AI Gateway credit check returned an invalid payload")

    credits: dict[str, str] = {}
    for field in ("balance", "total_used"):
        if field not in payload:
            raise RuntimeError("Vercel AI Gateway credit check returned an incomplete payload")
        value = str(payload[field])
        try:
            amount = Decimal(value)
        except InvalidOperation as exc:
            raise RuntimeError("Vercel AI Gateway credit check returned an invalid amount") from exc
        if not amount.is_finite() or amount < 0:
            raise RuntimeError("Vercel AI Gateway credit check returned an invalid amount")
        credits[field] = value
    return credits


def _credit_amount(credits: Mapping[str, str], field: str) -> Decimal:
    try:
        amount = Decimal(credits[field])
    except (KeyError, InvalidOperation) as exc:
        raise RuntimeError("Vercel AI Gateway credit provenance is invalid") from exc
    if not amount.is_finite() or amount < 0:
        raise RuntimeError("Vercel AI Gateway credit provenance is invalid")
    return amount


def _update_transport_metadata(run_dir: Path, transport: Mapping[str, Any]) -> None:
    path = run_dir / "configuration.json"
    configuration = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(configuration, dict):
        raise RuntimeError("calibration configuration is invalid")
    configuration["transport"] = dict(transport)
    _write_json(path, configuration)


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


def _select_calibration_task(tasks: tuple[TaskSpec, ...], task_id: str) -> tuple[TaskSpec, ...]:
    selected = tuple(task for task in tasks if task.task_id == task_id)
    if len(selected) != 1:
        raise ValueError(f"unknown calibration task_id: {task_id}")
    return selected


def _public_task_path(task_path: Path, repo_root: Path) -> str:
    try:
        return task_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return task_path.name


def _controller_message(turn: int, decision: Any) -> dict[str, Any]:
    message = {
        "role": "controller",
        "turn": turn,
        "response_id": decision.response_id,
        "actual_model": decision.actual_model,
        "usage": dict(decision.usage),
        "observable_output": list(decision.observable_output),
        "action": decision.action,
    }
    provider_metadata = getattr(decision, "provider_metadata", None)
    if provider_metadata:
        message["provider_metadata"] = dict(provider_metadata)
    return message


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
    task_id: str | None = None,
    replication: int = 1,
    run_id: str | None = None,
    transport_metadata: Mapping[str, Any] | None = None,
) -> Path:
    if replication < 1:
        raise ValueError("replication must be >= 1")
    tasks = load_calibration_tasks(task_path)
    if task_id is not None:
        tasks = _select_calibration_task(tasks, task_id)
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
    if transport_metadata is not None:
        configuration["transport"] = dict(transport_metadata)

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


def _run_direct_openai(args: argparse.Namespace, sdk_version: str) -> Path:
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
    return run_calibration(
        args.output,
        args.tasks,
        controller,
        provider,
        task_id=args.task_id,
        replication=args.replication,
        transport_metadata={
            "kind": "openai-direct",
            "controller_model": "gpt-5.6-sol",
            "image_model": "gpt-image-2-2026-04-21",
        },
    )


def _run_vercel_gateway(args: argparse.Namespace, api_key: str) -> Path:
    credits_before = fetch_vercel_gateway_credits(api_key)
    if _credit_amount(credits_before, "balance") <= 0:
        raise SystemExit("positive AI Gateway credit balance is required for live Vercel calibration")

    sdk_version = _openai_sdk_version()
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Vercel Gateway calibration requires `pip install -e '.[openai]'`") from exc

    client = OpenAI(
        api_key=api_key,
        base_url=VERCEL_GATEWAY_BASE_URL,
        max_retries=0,
    )
    request_extra_body = openai_only_extra_body()
    config = ControllerConfig(
        controller_id="openai-sol-vercel-calibration",
        provider="openai",
        model=VERCEL_CONTROLLER_MODEL,
        reasoning_effort="medium",
        max_output_tokens=1024,
        system_prompt_sha256=system_prompt_sha256(),
        sdk_version=sdk_version,
    )
    controller = OpenAIController(
        config,
        client=client,
        request_extra_body=request_extra_body,
        required_gateway_provider="openai",
    )
    provider = OpenAIImageProvider(
        model=VERCEL_IMAGE_MODEL,
        client=client,
        request_extra_body=request_extra_body,
        required_gateway_provider="openai",
    )
    transport: dict[str, Any] = {
        "kind": "vercel-ai-gateway",
        "base_url": VERCEL_GATEWAY_BASE_URL,
        "upstream_provider_required": "openai",
        "controller_gateway_model": VERCEL_CONTROLLER_MODEL,
        "image_gateway_model": VERCEL_IMAGE_MODEL,
        "image_gateway_release_date": VERCEL_IMAGE_RELEASE_DATE,
        "exact_snapshot_equivalence_established": False,
        "provider_fallback_allowed": False,
        "model_fallback_allowed": False,
        "credits_before": credits_before,
    }
    result = run_calibration(
        args.output,
        args.tasks,
        controller,
        provider,
        task_id=args.task_id,
        replication=args.replication,
        transport_metadata=transport,
    )

    credits_after = fetch_vercel_gateway_credits(api_key)
    transport["credits_after"] = credits_after
    transport["observed_credit_delta_usd"] = str(
        _credit_amount(credits_before, "balance") - _credit_amount(credits_after, "balance")
    )
    _update_transport_metadata(result, transport)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Thrumely's calibration-only OpenAI live pipeline")
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--task-id", required=True, help="Execute exactly one calibration-only task ID")
    parser.add_argument("--output", type=Path, default=Path("results/calibration"))
    parser.add_argument("--replication", type=int, default=1)
    parser.add_argument(
        "--transport",
        choices=("openai-direct", "vercel-gateway"),
        default="openai-direct",
        help="Calibration transport. Direct OpenAI remains the default.",
    )
    parser.add_argument(
        "--execute-live",
        action="store_true",
        help="Authorize the selected calibration transport to make live API calls; omitted means zero-cost dry-run only",
    )
    args = parser.parse_args()

    tasks = load_calibration_tasks(args.tasks)
    try:
        _select_calibration_task(tasks, args.task_id)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if not args.execute_live:
        print(
            json.dumps(
                {
                    "status": "DRY_RUN_ONLY",
                    "task_id": args.task_id,
                    "transport": args.transport,
                    "maximum_media_calls": 2,
                    "live_execution_authorized": False,
                },
                sort_keys=True,
            )
        )
        return

    if args.transport == "openai-direct":
        if not os.environ.get("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY is required for live calibration")
        result = _run_direct_openai(args, _openai_sdk_version())
    else:
        gateway_key = os.environ.get("AI_GATEWAY_API_KEY")
        if not gateway_key:
            raise SystemExit("AI_GATEWAY_API_KEY is required for live Vercel calibration")
        result = _run_vercel_gateway(args, gateway_key)

    print(result)


if __name__ == "__main__":
    main()
