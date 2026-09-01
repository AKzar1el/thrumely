from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifacts import ArtifactStore
from .calibration import load_calibration_tasks
from .hashing import sha256_file
from .redaction import sanitize_public_payload
from .schema import MediaOperation, MediaStage, NormalizedMediaRequest, TaskSpec, ToolEnvironment
from .serialization import to_primitive

_BFL_CANARY_MAX_POLLS = 60
_BFL_CANARY_POLL_INTERVAL_SECONDS = 0.5


def _write_json(path: Path, payload: Any) -> None:
    sanitized = sanitize_public_payload(to_primitive(payload))
    path.write_text(json.dumps(sanitized, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _select_task(task_path: Path, task_id: str) -> TaskSpec:
    tasks = load_calibration_tasks(task_path)
    selected = [task for task in tasks if task.task_id == task_id]
    if len(selected) != 1:
        raise ValueError(f"unknown calibration task_id: {task_id}")
    return selected[0]


def _maximum_transport_requests(provider: Any) -> int:
    if str(getattr(provider, "provider", "")) == "bfl":
        max_polls = int(getattr(provider, "max_polls", _BFL_CANARY_MAX_POLLS))
        return max_polls + 2  # one submit + bounded polls + one media download
    return 1


def run_provider_canary(
    output_root: Path,
    task_path: Path,
    provider: Any,
    *,
    task_id: str,
    run_id: str | None = None,
) -> Path:
    task = _select_task(task_path, task_id)
    provider_name = str(getattr(provider, "provider", "")).strip()
    backend_id = str(getattr(provider, "backend_id", "")).strip()
    model = str(getattr(provider, "model", "")).strip()
    if not provider_name or not backend_id or not model:
        raise ValueError("provider canary requires provider, backend_id, and model identities")

    environment = ToolEnvironment(
        environment_id=f"provider-canary-{provider_name}",
        mode="fixed",
        available_backends=(backend_id,),
        media_call_budget=1,
    )
    request = NormalizedMediaRequest(
        backend=backend_id,
        prompt=task.instruction,
        operation=MediaOperation.GENERATE,
        aspect_ratio="1:1",
        quality_tier="standard",
        previous_artifact_id=None,
        environment=environment,
    )

    resolved_run_id = run_id or (
        f"provider-canary-{provider_name}-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    )
    run_dir = output_root / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    store = ArtifactStore(run_dir)

    _write_json(run_dir / "task.json", task)
    _write_json(
        run_dir / "configuration.json",
        {
            "provider": provider_name,
            "backend_id": backend_id,
            "model": model,
            "task_id": task.task_id,
            "task_corpus_sha256": sha256_file(task_path),
            "normalized_request": request,
            "maximum_provider_executions": 1,
            "maximum_transport_requests": _maximum_transport_requests(provider),
        },
    )

    successful = 0
    try:
        provider_result = provider.execute(request, previous_media=None)
        artifact = store.put_media(
            provider_result.media_bytes,
            mime_type=provider_result.mime_type,
            width=provider_result.width,
            height=provider_result.height,
            stage=MediaStage.FINAL,
        )
        result_payload: dict[str, Any] = {
            "status": "success",
            "provider": provider_result.provider,
            "model": provider_result.model,
            "request_id": provider_result.request_id,
            "latency_seconds": provider_result.latency_seconds,
            "cost_usd": provider_result.cost_usd,
            "moderation_status": provider_result.moderation_status,
            "retry_count": provider_result.retry_count,
            "usage": provider_result.usage,
            "raw_request": provider_result.raw_request,
            "raw_response": provider_result.raw_response,
            "artifact": artifact,
        }
        successful = 1
    except Exception as exc:
        result_payload = {
            "status": "error",
            "provider": provider_name,
            "error_type": type(exc).__name__,
        }

    _write_json(run_dir / "result.json", result_payload)
    _write_json(
        run_dir / "manifest.json",
        {
            "run_id": resolved_run_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "data_classification": "live-provider-canary",
            "provider": provider_name,
            "backend_id": backend_id,
            "model": model,
            "task_id": task.task_id,
            "task_corpus_sha256": sha256_file(task_path),
            "operation": MediaOperation.GENERATE.value,
            "aspect_ratio": "1:1",
            "quality_tier": "standard",
            "requested_provider_executions": 1,
            "completed_provider_executions": 1,
            "successful_provider_executions": successful,
            "maximum_provider_executions": 1,
            "maximum_transport_requests": _maximum_transport_requests(provider),
        },
    )
    return run_dir


def _dry_run_payload(provider_name: str, task_id: str) -> dict[str, Any]:
    maximum_transport_requests = 62 if provider_name == "bfl" else 1
    return {
        "status": "DRY_RUN_ONLY",
        "provider": provider_name,
        "task_id": task_id,
        "operation": MediaOperation.GENERATE.value,
        "aspect_ratio": "1:1",
        "quality_tier": "standard",
        "maximum_provider_executions": 1,
        "maximum_transport_requests": maximum_transport_requests,
        "live_execution_authorized": False,
    }


def _live_provider(provider_name: str) -> Any:
    if provider_name == "google":
        if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
            raise SystemExit("GEMINI_API_KEY or GOOGLE_API_KEY is required for live Google provider calibration")
        from .google_provider import GoogleImageProvider

        return GoogleImageProvider()

    if provider_name == "bfl":
        if not os.environ.get("BFL_API_KEY"):
            raise SystemExit("BFL_API_KEY is required for live BFL provider calibration")
        from .bfl_provider import BFLImageProvider

        return BFLImageProvider(
            max_polls=_BFL_CANARY_MAX_POLLS,
            poll_interval=_BFL_CANARY_POLL_INTERVAL_SECONDS,
        )

    raise ValueError(f"unsupported provider canary: {provider_name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a single fail-closed Google or BFL provider transport canary"
    )
    parser.add_argument("--provider", choices=("google", "bfl"), required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--output", type=Path, default=Path("results/provider-canary"))
    parser.add_argument(
        "--execute-live",
        action="store_true",
        help="Authorize exactly one live provider execution; omitted means zero-cost dry-run only",
    )
    args = parser.parse_args()

    try:
        _select_task(args.tasks, args.task_id)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if not args.execute_live:
        print(json.dumps(_dry_run_payload(args.provider, args.task_id), sort_keys=True))
        return

    provider = _live_provider(args.provider)
    output = run_provider_canary(
        args.output,
        args.tasks,
        provider,
        task_id=args.task_id,
    )
    print(output)


if __name__ == "__main__":
    main()
