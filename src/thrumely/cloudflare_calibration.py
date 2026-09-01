from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .calibration import load_calibration_tasks, run_calibration
from .cloudflare_controller import CloudflareController
from .cloudflare_provider import CloudflareImageProvider
from .interfaces import (
    ControllerExecutionError as GenericControllerExecutionError,
    ControllerProtocolError as GenericControllerProtocolError,
    ProviderExecutionError as GenericProviderExecutionError,
)
from .openai_controller import (
    ControllerExecutionError as CalibrationControllerExecutionError,
    ControllerProtocolError as CalibrationControllerProtocolError,
    system_prompt_sha256,
)
from .openai_provider import ProviderExecutionError as CalibrationProviderExecutionError
from .schema import ControllerConfig

_CONTROLLER_MODEL = "@cf/google/gemma-4-26b-a4b-it"
_IMAGE_MODEL = "@cf/black-forest-labs/flux-2-klein-4b"


class _ControllerCalibrationAdapter:
    def __init__(self, controller: CloudflareController) -> None:
        self._controller = controller
        self.config = controller.config

    def decide(self, *args: Any, **kwargs: Any):
        try:
            return self._controller.decide(*args, **kwargs)
        except GenericControllerProtocolError as exc:
            raise CalibrationControllerProtocolError(str(exc)) from exc
        except GenericControllerExecutionError as exc:
            raise CalibrationControllerExecutionError(str(exc)) from exc


class _ProviderCalibrationAdapter:
    def __init__(self, provider: CloudflareImageProvider) -> None:
        self._provider = provider
        self.provider = provider.provider
        self.model = provider.model
        self.backend_id = provider.backend_id

    def execute(self, *args: Any, **kwargs: Any):
        try:
            return self._provider.execute(*args, **kwargs)
        except GenericProviderExecutionError as exc:
            raise CalibrationProviderExecutionError(str(exc)) from exc


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
    controller = _ControllerCalibrationAdapter(
        CloudflareController(
            config,
            account_id=account_id,
            api_token=api_token,
        )
    )
    provider = _ProviderCalibrationAdapter(
        CloudflareImageProvider(
            model=_IMAGE_MODEL,
            account_id=account_id,
            api_token=api_token,
        )
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
