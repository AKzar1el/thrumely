from __future__ import annotations

import json
import sys
from pathlib import Path

from thrumely.cloudflare_control_surface import (
    build_control_probes,
    main,
    run_cloudflare_control_surface,
)
from thrumely.cloudflare_provider import quality_tier_to_dimensions
from thrumely.hashing import sha256_bytes
from thrumely.interfaces import ProviderExecutionError, ProviderMediaResult
from thrumely.schema import MediaOperation


class FakeProvider:
    provider = "cloudflare"
    backend_id = "cloudflare:flux-2-klein-4b"
    model = "@cf/black-forest-labs/flux-2-klein-4b"

    def __init__(self, *, fail_on_call: int | None = None) -> None:
        self.calls = []
        self.fail_on_call = fail_on_call

    def execute(self, request, previous_media=None):
        self.calls.append((request, previous_media))
        call_index = len(self.calls)
        if self.fail_on_call == call_index:
            raise ProviderExecutionError("synthetic provider failure that must not leak")
        width, height = quality_tier_to_dimensions(request.aspect_ratio, request.quality_tier)
        media = (
            f"media-{call_index}-{request.operation.value}-{request.aspect_ratio}-{request.quality_tier}"
        ).encode("utf-8")
        return ProviderMediaResult(
            media_bytes=media,
            mime_type="image/png",
            width=width,
            height=height,
            provider=self.provider,
            model=self.model,
            raw_request={"operation": request.operation.value},
            raw_response={"success": True},
            request_id=f"req-{call_index}",
            latency_seconds=0.01 * call_index,
            cost_usd=None,
            moderation_status=None,
            retry_count=0,
            usage={},
        )


def _task_file(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "calibration_only": True,
                "tasks": [
                    {
                        "task_id": "cal-control-001",
                        "family": "control-surface",
                        "instruction": "Create three simple colored shapes on a plain background.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_control_probe_plan_is_fixed_and_exercises_edit_aspect_and_all_tiers() -> None:
    probes = build_control_probes("Create three simple colored shapes on a plain background.")

    assert [probe["operation"] for probe in probes] == [
        MediaOperation.GENERATE,
        MediaOperation.EDIT_PREVIOUS,
        MediaOperation.GENERATE,
        MediaOperation.GENERATE,
    ]
    assert [(probe["aspect_ratio"], probe["quality_tier"]) for probe in probes] == [
        ("1:1", "standard"),
        ("1:1", "standard"),
        ("16:9", "draft"),
        ("2:3", "high"),
    ]
    assert probes[1]["prompt"] != probes[0]["prompt"]


def test_control_surface_uses_exact_first_artifact_for_edit_and_records_dimensions(tmp_path: Path) -> None:
    tasks = _task_file(tmp_path / "tasks.json")
    provider = FakeProvider()

    run_dir = run_cloudflare_control_surface(
        tmp_path / "out",
        tasks,
        provider,
        task_id="cal-control-001",
        run_id="control-test",
    )

    assert len(provider.calls) == 4
    first_request, first_previous = provider.calls[0]
    edit_request, edit_previous = provider.calls[1]
    assert first_previous is None
    assert edit_previous == b"media-1-generate-1:1-standard"
    first_sha = sha256_bytes(edit_previous)
    assert edit_request.operation is MediaOperation.EDIT_PREVIOUS
    assert edit_request.previous_artifact_id == f"media:{first_sha}"
    assert provider.calls[2][1] is None
    assert provider.calls[3][1] is None

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["data_classification"] == "live-control-calibration"
    assert manifest["requested_provider_executions"] == 4
    assert manifest["completed_provider_executions"] == 4
    assert manifest["successful_provider_executions"] == 4
    assert manifest["maximum_transport_requests"] == 4
    assert manifest["benchmark_trajectory"] is False

    rows = [
        json.loads(line)
        for line in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 4
    assert all(row["status"] == "success" for row in rows)
    assert all(row["dimension_match"] is True for row in rows)
    assert all(row["retry_count"] == 0 for row in rows)
    assert [row["probe_id"] for row in rows] == [
        "standard-square-generate",
        "standard-square-edit",
        "draft-wide-generate",
        "high-portrait-generate",
    ]
    assert len(list((run_dir / "media").iterdir())) == 4


def test_control_surface_stops_on_first_provider_failure_without_retrying(tmp_path: Path) -> None:
    tasks = _task_file(tmp_path / "tasks.json")
    provider = FakeProvider(fail_on_call=2)

    run_dir = run_cloudflare_control_surface(
        tmp_path / "out",
        tasks,
        provider,
        task_id="cal-control-001",
        run_id="control-failure",
    )

    assert len(provider.calls) == 2
    rows = [
        json.loads(line)
        for line in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [row["status"] for row in rows] == ["success", "error"]
    assert rows[1]["error_type"] == "ProviderExecutionError"
    assert "synthetic provider failure" not in json.dumps(rows[1])

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["completed_provider_executions"] == 2
    assert manifest["successful_provider_executions"] == 1
    assert manifest["status"] == "error"


def test_cli_is_dry_run_by_default_without_credentials_or_output(tmp_path: Path, monkeypatch, capsys) -> None:
    tasks = _task_file(tmp_path / "tasks.json")
    output = tmp_path / "must-not-exist"
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cloudflare-control-surface",
            "--tasks",
            str(tasks),
            "--task-id",
            "cal-control-001",
            "--output",
            str(output),
        ],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "DRY_RUN_ONLY"
    assert payload["requested_provider_executions"] == 4
    assert payload["maximum_transport_requests"] == 4
    assert payload["benchmark_trajectory"] is False
    assert payload["live_execution_authorized"] is False
    assert not output.exists()
