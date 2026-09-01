from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .calibration import load_calibration_tasks, run_calibration
from .cloudflare_controller import CloudflareController
from .cloudflare_provider import CloudflareImageProvider
from .openai_controller import system_prompt_sha256
from .schema import ControllerConfig

_CONTROLLER_MODEL = "@cf/google/gemma-4-26b-a4b-it"
_IMAGE_MODEL = "@cf/black-forest-labs/flux-2-klein-4b"


def _require_task(task_path: Path, task_id: str) -> None:
    tasks = load_calibration_tasks(task_path)
    if sum(task.task_id == task_id for task in tasks) != 1:
        raise ValueError(f"unknown calibration task_id: {task_id}")


def _dry_run_payload(task_id: str) -> dict[str, object]:
    return {
        "status": "DRY_RUN_ONLY",
        "task_id": task_id,
        "controller_model": _CONTROLLER_MODEL,
        "image_model": _IMAGE_MODEL,
        "maximum_controller_calls": 2,
        "maximum_media_calls": 2,
        "maximum_transport_requests": 4,
        "live_execution_authorized": False,
        "scientific_scope": "zero-cost-live-calibration-only",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one guarded zero-cost Cloudflare Workers AI calibration trajectory"
    )
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--task-id", required=True, help="Execute exactly one calibration-only task ID")
    parser.add_argument("--output", type=Path, default=Path("results/cloudflare-calibration"))
    parser.add_argument("--replication", type=int, default=1)
    parser.add_argument(
        "--execute-live",
        action="store_true",
        help="Authorize Cloudflare Workers AI calls; omitted means zero-cost dry-run only",
    )
    args = parser.parse_args()

    try:
        _require_task(args.tasks, args.task_id)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if not args.execute_live:
        print(json.dumps(_dry_run_payload(args.task_id), sort_keys=True))
        return

    api_token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not api_token:
        raise SystemExit("CLOUDFLARE_API_TOKEN is required for live Cloudflare calibration")
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if not account_id:
        raise SystemExit("CLOUDFLARE_ACCOUNT_ID is required for live Cloudflare calibration")

    config = ControllerConfig(
        controller_id="cloudflare-gemma4-calibration",
        provider="cloudflare",
        model=_CONTROLLER_MODEL,
        reasoning_effort="medium",
        max_output_tokens=1024,
        system_prompt_sha256=system_prompt_sha256(),
        sdk_version=None,
    )
    controller = CloudflareController(
        config,
        account_id=account_id,
        api_token=api_token,
    )
    provider = CloudflareImageProvider(
        model=_IMAGE_MODEL,
        account_id=account_id,
        api_token=api_token,
    )
    output = run_calibration(
        args.output,
        args.tasks,
        controller,
        provider,
        task_id=args.task_id,
        replication=args.replication,
    )
    print(output)


if __name__ == "__main__":
    main()
