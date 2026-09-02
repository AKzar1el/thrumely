from __future__ import annotations

import json
import sys
from pathlib import Path

from thrumely.hashing import sha256_bytes
from thrumely.interfaces import ProviderExecutionError, ProviderMediaResult
from thrumely.modal_control_surface import build_control_probes, main, run_modal_control_surface
from thrumely.modal_provider import BACKEND_ID, MODEL_ID, MODEL_REVISION, quality_tier_to_dimensions
from thrumely.schema import MediaOperation


class FakeProvider:
    provider = "modal-reference"
    backend_id = BACKEND_ID
    model = MODEL_ID

    def __init__(self, *, fail_on_call: int | None = None, mismatch_on_call: int | None = None) -> None:
        self.calls = []
        self.fail_on_call = fail_on_call
        self.mismatch_on_call = mismatch_on_call

    def execute(self, request, previous_media=None, *, seed=0):
        self.calls.append((request, previous_media, seed))
        call_index = len(self.calls)
        if self.fail_on_call == call_index:
            raise ProviderExecutionError("synthetic provider detail must not leak")
        width, height = quality_tier_to_dimensions(request.aspect_ratio, request.quality_tier)
        if self.mismatch_on_call == call_index:
            width += 16
        media = f"modal-media-{call_index}-{seed}-{request.operation.value}".encode()
        return ProviderMediaResult(
            media_bytes=media,
            mime_type="image/png",
            width=width,
            height=height,
            provider=self.provider,
            model=self.model,
            raw_request={"operation": request.operation.value, "seed": seed},
            raw_response={"model_revision": MODEL_REVISION},
            request_id=None,
            latency_seconds=0.02 * call_index,
            cost_usd=None,
            moderation_status=None,
            retry_count=0,
            usage={"model_revision": MODEL_REVISION, "seed": seed},
        )


def _task_file(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "calibration_only": True,
                "tasks": [
                    {
                        "task_id": "cal-modal-001",
                        "family": "reference-control",
                        "instruction": "Create three simple colored shapes on a plain background.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_probe_plan_is_fixed_seeded_and_exercises_edit_aspect_and_tiers() -> None:
    probes = build_control_probes("Create shapes")
    assert [probe["operation"] for probe in probes] == [
        MediaOperation.GENERATE,
        MediaOperation.EDIT_PREVIOUS,
        MediaOperation.GENERATE,
        MediaOperation.GENERATE,
    ]
    assert [(probe["aspect_ratio"], probe["quality_tier"], probe["seed"]) for probe in probes] == [
        ("1:1", "standard", 0),
        ("1:1", "standard", 1),
        ("16:9", "draft", 2),
        ("2:3", "high", 3),
    ]


def test_runner_uses_exact_first_artifact_for_edit_and_records_reference_provenance(tmp_path: Path) -> None:
    tasks = _task_file(tmp_path / "tasks.json")
    provider = FakeProvider()

    run_dir = run_modal_control_surface(
        tmp_path / "out",
        tasks,
        provider,
        task_id="cal-modal-001",
        run_id="modal-controls-test",
    )

    assert len(provider.calls) == 4
    assert [call[2] for call in provider.calls] == [0, 1, 2, 3]
    first_request, first_previous, _ = provider.calls[0]
    edit_request, edit_previous, _ = provider.calls[1]
    assert first_previous is None
    assert edit_previous == b"modal-media-1-0-generate"
    assert edit_request.operation is MediaOperation.EDIT_PREVIOUS
    assert edit_request.previous_artifact_id == f"media:{sha256_bytes(edit_previous)}"
    assert provider.calls[2][1] is None
    assert provider.calls[3][1] is None

    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["data_classification"] == "live-reference-control-calibration"
    assert manifest["scientific_scope"] == "open-weight-reference-control-calibration-only"
    assert manifest["benchmark_trajectory"] is False
    assert manifest["requested_provider_executions"] == 4
    assert manifest["successful_provider_executions"] == 4
    assert manifest["maximum_transport_requests"] == 4
    assert manifest["model_revision"] == MODEL_REVISION

    rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text().splitlines() if line]
    assert len(rows) == 4
    assert all(row["status"] == "success" for row in rows)
    assert all(row["dimension_match"] is True for row in rows)
    assert all(row["retry_count"] == 0 for row in rows)
    assert [row["seed"] for row in rows] == [0, 1, 2, 3]
    assert all(row["usage"]["model_revision"] == MODEL_REVISION for row in rows)
    assert len(list((run_dir / "media").iterdir())) == 4


def test_runner_stops_on_first_provider_failure_without_retrying_or_echoing_detail(tmp_path: Path) -> None:
    tasks = _task_file(tmp_path / "tasks.json")
    provider = FakeProvider(fail_on_call=2)
    run_dir = run_modal_control_surface(
        tmp_path / "out", tasks, provider, task_id="cal-modal-001", run_id="modal-failure"
    )

    assert len(provider.calls) == 2
    rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text().splitlines() if line]
    assert [row["status"] for row in rows] == ["success", "error"]
    assert rows[1]["error_type"] == "ProviderExecutionError"
    assert "synthetic provider detail" not in json.dumps(rows[1])
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["status"] == "error"
    assert manifest["completed_provider_executions"] == 2
    assert manifest["successful_provider_executions"] == 1


def test_runner_stops_immediately_on_dimension_mismatch_to_avoid_extra_compute(tmp_path: Path) -> None:
    tasks = _task_file(tmp_path / "tasks.json")
    provider = FakeProvider(mismatch_on_call=1)
    run_dir = run_modal_control_surface(
        tmp_path / "out", tasks, provider, task_id="cal-modal-001", run_id="modal-mismatch"
    )

    assert len(provider.calls) == 1
    rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text().splitlines() if line]
    assert len(rows) == 1
    assert rows[0]["status"] == "success"
    assert rows[0]["dimension_match"] is False
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["status"] == "error"
    assert manifest["completed_provider_executions"] == 1
    assert manifest["successful_provider_executions"] == 1
    assert manifest["all_dimensions_match"] is False


def test_cli_is_dry_run_by_default_without_modal_credentials_or_output(tmp_path: Path, monkeypatch, capsys) -> None:
    tasks = _task_file(tmp_path / "tasks.json")
    output = tmp_path / "must-not-exist"
    for name in (
        "THRUMELY_MODAL_ENDPOINT_URL",
        "THRUMELY_MODAL_PROXY_KEY",
        "THRUMELY_MODAL_PROXY_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "modal-control-surface",
            "--tasks",
            str(tasks),
            "--task-id",
            "cal-modal-001",
            "--output",
            str(output),
        ],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "DRY_RUN_ONLY"
    assert payload["provider"] == "modal-reference"
    assert payload["model"] == MODEL_ID
    assert payload["model_revision"] == MODEL_REVISION
    assert payload["requested_provider_executions"] == 4
    assert payload["maximum_transport_requests"] == 4
    assert payload["benchmark_trajectory"] is False
    assert payload["scientific_scope"] == "open-weight-reference-control-calibration-only"
    assert payload["live_execution_authorized"] is False
    assert not output.exists()
