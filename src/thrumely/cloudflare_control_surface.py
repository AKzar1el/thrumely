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
from .cloudflare_provider import CloudflareImageProvider, quality_tier_to_dimensions
from .hashing import sha256_file
from .redaction import sanitize_public_payload
from .schema import MediaOperation, MediaStage, NormalizedMediaRequest, TaskSpec, ToolEnvironment
from .serialization import to_primitive

_PROVIDER_EXECUTION_CEILING = 4
_EDIT_PROMPT = (
    "Using the previous image as the sole reference, preserve the main composition and all "
    "existing objects. Make exactly one visible calibration edit: change only the background "
    "to a very light neutral gray. Do not add text, logos, or new objects."
)


def _write_json(path: Path, payload: Any) -> None:
    sanitized = sanitize_public_payload(to_primitive(payload))
    path.write_text(json.dumps(sanitized, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            sanitized = sanitize_public_payload(to_primitive(row))
            handle.write(json.dumps(sanitized, sort_keys=True) + "\n")


def _select_task(task_path: Path, task_id: str) -> TaskSpec:
    tasks = load_calibration_tasks(task_path)
    selected = [task for task in tasks if task.task_id == task_id]
    if len(selected) != 1:
        raise ValueError(f"unknown calibration task_id: {task_id}")
    return selected[0]


def build_control_probes(base_prompt: str) -> list[dict[str, Any]]:
    return [
        {
            "probe_id": "standard-square-generate",
            "operation": MediaOperation.GENERATE,
            "aspect_ratio": "1:1",
            "quality_tier": "standard",
            "prompt": base_prompt,
        },
        {
            "probe_id": "standard-square-edit",
            "operation": MediaOperation.EDIT_PREVIOUS,
            "aspect_ratio": "1:1",
            "quality_tier": "standard",
            "prompt": _EDIT_PROMPT,
        },
        {
            "probe_id": "draft-wide-generate",
            "operation": MediaOperation.GENERATE,
            "aspect_ratio": "16:9",
            "quality_tier": "draft",
            "prompt": base_prompt,
        },
        {
            "probe_id": "high-portrait-generate",
            "operation": MediaOperation.GENERATE,
            "aspect_ratio": "2:3",
            "quality_tier": "high",
            "prompt": base_prompt,
        },
    ]


def _stage_for_probe(probe_id: str) -> MediaStage:
    if probe_id == "standard-square-generate":
        return MediaStage.FIRST
    if probe_id == "standard-square-edit":
        return MediaStage.REVISION
    return MediaStage.FINAL


def run_cloudflare_control_surface(
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
    if provider_name != "cloudflare" or not backend_id.startswith("cloudflare:") or not model:
        raise ValueError("Cloudflare control calibration requires an identified Cloudflare provider")

    probes = build_control_probes(task.instruction)
    if len(probes) != _PROVIDER_EXECUTION_CEILING:
        raise RuntimeError("Cloudflare control calibration probe plan escaped its fixed ceiling")

    resolved_run_id = run_id or (
        "cloudflare-controls-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    )
    run_dir = output_root / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    store = ArtifactStore(run_dir)

    environment = ToolEnvironment(
        environment_id="cloudflare-control-surface-calibration",
        mode="fixed",
        available_backends=(backend_id,),
        media_call_budget=1,
    )

    _write_json(run_dir / "task.json", task)
    _write_json(
        run_dir / "configuration.json",
        {
            "provider": provider_name,
            "backend_id": backend_id,
            "model": model,
            "task_id": task.task_id,
            "task_corpus_sha256": sha256_file(task_path),
            "benchmark_trajectory": False,
            "scientific_scope": "provider-control-surface-calibration-only",
            "requested_provider_executions": _PROVIDER_EXECUTION_CEILING,
            "maximum_transport_requests": _PROVIDER_EXECUTION_CEILING,
            "probes": probes,
        },
    )

    rows: list[dict[str, Any]] = []
    first_media: bytes | None = None
    first_artifact_id: str | None = None
    successful = 0

    for probe in probes:
        operation = probe["operation"]
        previous_artifact_id = first_artifact_id if operation is MediaOperation.EDIT_PREVIOUS else None
        request = NormalizedMediaRequest(
            backend=backend_id,
            prompt=probe["prompt"],
            operation=operation,
            aspect_ratio=probe["aspect_ratio"],
            quality_tier=probe["quality_tier"],
            previous_artifact_id=previous_artifact_id,
            environment=environment,
        )
        expected_width, expected_height = quality_tier_to_dimensions(
            request.aspect_ratio,
            request.quality_tier,
        )
        previous_media = first_media if operation is MediaOperation.EDIT_PREVIOUS else None

        try:
            provider_result = provider.execute(request, previous_media=previous_media)
            artifact = store.put_media(
                provider_result.media_bytes,
                mime_type=provider_result.mime_type,
                width=provider_result.width,
                height=provider_result.height,
                stage=_stage_for_probe(probe["probe_id"]),
            )
            dimension_match = (
                provider_result.width == expected_width and provider_result.height == expected_height
            )
            rows.append(
                {
                    "probe_id": probe["probe_id"],
                    "status": "success",
                    "normalized_request": request,
                    "expected_dimensions": {"width": expected_width, "height": expected_height},
                    "actual_dimensions": {
                        "width": provider_result.width,
                        "height": provider_result.height,
                    },
                    "dimension_match": dimension_match,
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
            )
            successful += 1
            if probe["probe_id"] == "standard-square-generate":
                first_media = provider_result.media_bytes
                first_artifact_id = artifact.artifact_id
        except Exception as exc:
            rows.append(
                {
                    "probe_id": probe["probe_id"],
                    "status": "error",
                    "normalized_request": request,
                    "expected_dimensions": {"width": expected_width, "height": expected_height},
                    "error_type": type(exc).__name__,
                }
            )
            break

    _write_jsonl(run_dir / "results.jsonl", rows)
    all_dimensions_match = all(row.get("dimension_match") is True for row in rows if row["status"] == "success")
    status = (
        "success"
        if len(rows) == _PROVIDER_EXECUTION_CEILING
        and successful == _PROVIDER_EXECUTION_CEILING
        and all_dimensions_match
        else "error"
    )
    _write_json(
        run_dir / "manifest.json",
        {
            "run_id": resolved_run_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "data_classification": "live-control-calibration",
            "scientific_scope": "provider-control-surface-calibration-only",
            "benchmark_trajectory": False,
            "provider": provider_name,
            "backend_id": backend_id,
            "model": model,
            "task_id": task.task_id,
            "task_corpus_sha256": sha256_file(task_path),
            "status": status,
            "requested_provider_executions": _PROVIDER_EXECUTION_CEILING,
            "completed_provider_executions": len(rows),
            "successful_provider_executions": successful,
            "maximum_provider_executions": _PROVIDER_EXECUTION_CEILING,
            "maximum_transport_requests": _PROVIDER_EXECUTION_CEILING,
            "all_dimensions_match": all_dimensions_match,
        },
    )
    return run_dir


def _dry_run_payload(task_id: str) -> dict[str, Any]:
    return {
        "status": "DRY_RUN_ONLY",
        "provider": "cloudflare",
        "model": "@cf/black-forest-labs/flux-2-klein-4b",
        "task_id": task_id,
        "requested_provider_executions": _PROVIDER_EXECUTION_CEILING,
        "maximum_provider_executions": _PROVIDER_EXECUTION_CEILING,
        "maximum_transport_requests": _PROVIDER_EXECUTION_CEILING,
        "benchmark_trajectory": False,
        "scientific_scope": "provider-control-surface-calibration-only",
        "live_execution_authorized": False,
        "probes": build_control_probes("[CALIBRATION_TASK_PROMPT]"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run a fixed four-probe Cloudflare image control-surface calibration; "
            "this is provider instrumentation, not a benchmark trajectory"
        )
    )
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--output", type=Path, default=Path("results/cloudflare-controls"))
    parser.add_argument(
        "--execute-live",
        action="store_true",
        help="Authorize exactly four fixed Cloudflare provider executions; omitted is dry-run only",
    )
    args = parser.parse_args()

    try:
        _select_task(args.tasks, args.task_id)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if not args.execute_live:
        print(json.dumps(to_primitive(_dry_run_payload(args.task_id)), sort_keys=True))
        return

    api_token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not api_token:
        raise SystemExit("CLOUDFLARE_API_TOKEN is required for live Cloudflare control calibration")
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if not account_id:
        raise SystemExit("CLOUDFLARE_ACCOUNT_ID is required for live Cloudflare control calibration")

    provider = CloudflareImageProvider(account_id=account_id, api_token=api_token)
    output = run_cloudflare_control_surface(
        args.output,
        args.tasks,
        provider,
        task_id=args.task_id,
    )
    print(output)


if __name__ == "__main__":
    main()
