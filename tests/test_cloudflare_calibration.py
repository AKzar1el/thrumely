from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from thrumely.cloudflare_calibration import main


def write_tasks(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "calibration_only": True,
                "tasks": [
                    {
                        "task_id": "cal-cloudflare-001",
                        "family": "compositional-constraints",
                        "instruction": "Create a blue square centered on white.",
                    },
                    {
                        "task_id": "cal-cloudflare-002",
                        "family": "typography-and-layout",
                        "instruction": "Create a simple poster reading TEST.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_cli_is_zero_cost_dry_run_by_default_without_credentials_or_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tasks = write_tasks(tmp_path / "tasks.json")
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "thrumely.cloudflare_calibration",
            "--tasks",
            str(tasks),
            "--task-id",
            "cal-cloudflare-001",
            "--output",
            str(tmp_path / "results"),
        ],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "controller_model": "@cf/google/gemma-4-26b-a4b-it",
        "image_model": "@cf/black-forest-labs/flux-2-klein-4b",
        "live_execution_authorized": False,
        "maximum_controller_calls": 2,
        "maximum_media_calls": 2,
        "maximum_transport_requests": 4,
        "scientific_scope": "zero-cost-live-calibration-only",
        "status": "DRY_RUN_ONLY",
        "task_id": "cal-cloudflare-001",
    }
    assert not (tmp_path / "results").exists()


def test_execute_live_requires_token_before_constructing_clients(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks = write_tasks(tmp_path / "tasks.json")
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account-test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "thrumely.cloudflare_calibration",
            "--tasks",
            str(tasks),
            "--task-id",
            "cal-cloudflare-001",
            "--execute-live",
        ],
    )
    with pytest.raises(SystemExit, match="CLOUDFLARE_API_TOKEN"):
        main()


def test_execute_live_requires_account_id_before_constructing_clients(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks = write_tasks(tmp_path / "tasks.json")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "secret-token")
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "thrumely.cloudflare_calibration",
            "--tasks",
            str(tasks),
            "--task-id",
            "cal-cloudflare-001",
            "--execute-live",
        ],
    )
    with pytest.raises(SystemExit, match="CLOUDFLARE_ACCOUNT_ID"):
        main()


def test_unknown_task_is_rejected_before_credential_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks = write_tasks(tmp_path / "tasks.json")
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "thrumely.cloudflare_calibration",
            "--tasks",
            str(tasks),
            "--task-id",
            "cal-cloudflare-999",
            "--execute-live",
        ],
    )
    with pytest.raises(SystemExit, match="unknown calibration task_id"):
        main()
