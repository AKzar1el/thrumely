from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from thrumely.interfaces import ProviderExecutionError as GenericProviderExecutionError
from thrumely.modal_reference_calibration import _ProviderCalibrationAdapter, main
from thrumely.openai_provider import ProviderExecutionError as CalibrationProviderExecutionError


def write_tasks(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "calibration_only": True,
                "tasks": [
                    {
                        "task_id": "cal-openai-005",
                        "family": "reference-replay",
                        "instruction": "Create a simple rights-clean cafe menu card.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


class FailingProvider:
    provider = "modal-reference"
    model = "black-forest-labs/FLUX.2-klein-4B"
    backend_id = "modal:flux-2-klein-4b-reference"

    def execute(self, *args, **kwargs):
        raise GenericProviderExecutionError("safe synthetic provider failure")


def test_cli_is_zero_cost_dry_run_without_any_credentials_or_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tasks = write_tasks(tmp_path / "tasks.json")
    for name in (
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "THRUMELY_MODAL_ENDPOINT_URL",
        "THRUMELY_MODAL_PROXY_KEY",
        "THRUMELY_MODAL_PROXY_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    output = tmp_path / "must-not-exist"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "thrumely.modal_reference_calibration",
            "--tasks",
            str(tasks),
            "--task-id",
            "cal-openai-005",
            "--output",
            str(output),
        ],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "controller_model": "@cf/google/gemma-4-26b-a4b-it",
        "image_backend": "modal:flux-2-klein-4b-reference",
        "image_model": "black-forest-labs/FLUX.2-klein-4B",
        "image_model_revision": "e7b7dc27f91deacad38e78976d1f2b499d76a294",
        "live_execution_authorized": False,
        "maximum_controller_calls": 2,
        "maximum_media_calls": 2,
        "maximum_transport_requests": 4,
        "scientific_scope": "open-weight-reference-agent-calibration-only",
        "status": "DRY_RUN_ONLY",
        "task_id": "cal-openai-005",
    }
    assert not output.exists()


@pytest.mark.parametrize(
    ("missing_name", "expected"),
    [
        ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_API_TOKEN"),
        ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_ACCOUNT_ID"),
        ("THRUMELY_MODAL_ENDPOINT_URL", "THRUMELY_MODAL_ENDPOINT_URL"),
        ("THRUMELY_MODAL_PROXY_KEY", "THRUMELY_MODAL_PROXY_KEY"),
        ("THRUMELY_MODAL_PROXY_SECRET", "THRUMELY_MODAL_PROXY_SECRET"),
    ],
)
def test_execute_live_fails_closed_on_each_missing_runtime_credential(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing_name: str,
    expected: str,
) -> None:
    tasks = write_tasks(tmp_path / "tasks.json")
    values = {
        "CLOUDFLARE_API_TOKEN": "cf-test",
        "CLOUDFLARE_ACCOUNT_ID": "account-test",
        "THRUMELY_MODAL_ENDPOINT_URL": "https://example.modal.run/infer",
        "THRUMELY_MODAL_PROXY_KEY": "wk-test",
        "THRUMELY_MODAL_PROXY_SECRET": "ws-test",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv(missing_name, raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "thrumely.modal_reference_calibration",
            "--tasks",
            str(tasks),
            "--task-id",
            "cal-openai-005",
            "--execute-live",
        ],
    )

    with pytest.raises(SystemExit, match=expected):
        main()


def test_unknown_task_is_rejected_before_runtime_credential_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks = write_tasks(tmp_path / "tasks.json")
    for name in (
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "THRUMELY_MODAL_ENDPOINT_URL",
        "THRUMELY_MODAL_PROXY_KEY",
        "THRUMELY_MODAL_PROXY_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "thrumely.modal_reference_calibration",
            "--tasks",
            str(tasks),
            "--task-id",
            "cal-openai-999",
            "--execute-live",
        ],
    )

    with pytest.raises(SystemExit, match="unknown calibration task_id"):
        main()


def test_provider_adapter_translates_generic_error_into_shared_calibration_error() -> None:
    adapter = _ProviderCalibrationAdapter(FailingProvider())
    assert adapter.provider == "modal-reference"
    assert adapter.backend_id == "modal:flux-2-klein-4b-reference"
    with pytest.raises(CalibrationProviderExecutionError, match="safe synthetic provider failure"):
        adapter.execute(object())
