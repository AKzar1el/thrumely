from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from thrumely.interfaces import ProviderMediaResult
from thrumely.provider_canary import main, run_provider_canary


class FakeProvider:
    provider = "google"
    model = "gemini-3.1-flash-image"
    backend_id = "google:gemini-3.1-flash-image"

    def __init__(self) -> None:
        self.calls = []

    def execute(self, request, previous_media=None):
        self.calls.append((request, previous_media))
        return ProviderMediaResult(
            media_bytes=("provider-canary:" + request.prompt).encode(),
            mime_type="image/png",
            width=1024,
            height=1024,
            provider=self.provider,
            model=self.model,
            raw_request={
                "prompt": request.prompt,
                "authorization": "Bearer fake-provider-secret",
            },
            raw_response={"id": "provider-response-1", "output_image": "[MEDIA_BYTES_STORED_SEPARATELY]"},
            request_id="provider-response-1",
            latency_seconds=0.01,
            cost_usd=0.067,
            moderation_status=None,
            retry_count=0,
            usage={"image_size": "1K"},
        )


class FailingProvider(FakeProvider):
    def execute(self, request, previous_media=None):
        self.calls.append((request, previous_media))
        raise RuntimeError("Authorization: Bearer fake-failure-secret")


def write_tasks(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "calibration_only": True,
                "tasks": [
                    {
                        "task_id": "cal-openai-001",
                        "family": "compositional-constraints",
                        "instruction": "Create a blue square centered on white.",
                    },
                    {
                        "task_id": "cal-openai-002",
                        "family": "typography-and-layout",
                        "instruction": "Create a simple poster reading TEST.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_provider_canary_executes_exactly_one_generation_and_exports_auditable_bundle(tmp_path: Path) -> None:
    task_path = write_tasks(tmp_path / "tasks.json")
    provider = FakeProvider()

    output = run_provider_canary(
        tmp_path / "results",
        task_path,
        provider,
        task_id="cal-openai-001",
        run_id="provider-canary-test",
    )

    assert len(provider.calls) == 1
    request, previous_media = provider.calls[0]
    assert request.operation.value == "generate"
    assert request.aspect_ratio == "1:1"
    assert request.quality_tier == "standard"
    assert previous_media is None

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["data_classification"] == "live-provider-canary"
    assert manifest["provider"] == "google"
    assert manifest["task_id"] == "cal-openai-001"
    assert manifest["requested_provider_executions"] == 1
    assert manifest["completed_provider_executions"] == 1
    assert manifest["successful_provider_executions"] == 1
    assert manifest["maximum_provider_executions"] == 1
    assert manifest["maximum_transport_requests"] == 1

    task = json.loads((output / "task.json").read_text(encoding="utf-8"))
    assert task["task_id"] == "cal-openai-001"
    assert "cal-openai-002" not in json.dumps(task)

    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "success"
    assert result["provider"] == "google"
    assert result["request_id"] == "provider-response-1"
    assert result["retry_count"] == 0
    assert result["raw_request"]["authorization"] == "[REDACTED]"
    assert result["artifact"]["stage"] == "final"
    assert (output / result["artifact"]["relative_path"]).exists()

    serialized = "\n".join(path.read_text(errors="ignore") for path in output.glob("*.json"))
    assert "fake-provider-secret" not in serialized


def test_provider_canary_records_terminal_failure_without_leaking_exception_text(tmp_path: Path) -> None:
    task_path = write_tasks(tmp_path / "tasks.json")
    provider = FailingProvider()

    output = run_provider_canary(
        tmp_path / "results",
        task_path,
        provider,
        task_id="cal-openai-001",
        run_id="provider-canary-failure",
    )

    assert len(provider.calls) == 1
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["completed_provider_executions"] == 1
    assert manifest["successful_provider_executions"] == 0

    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result == {
        "error_type": "RuntimeError",
        "provider": "google",
        "status": "error",
    }
    serialized = "\n".join(path.read_text(errors="ignore") for path in output.glob("*.json"))
    assert "fake-failure-secret" not in serialized


def test_provider_canary_rejects_unknown_task_before_provider_call(tmp_path: Path) -> None:
    task_path = write_tasks(tmp_path / "tasks.json")
    provider = FakeProvider()

    with pytest.raises(ValueError, match="unknown calibration task_id"):
        run_provider_canary(
            tmp_path / "results",
            task_path,
            provider,
            task_id="cal-openai-999",
        )

    assert provider.calls == []
    assert not (tmp_path / "results").exists()


def test_cli_google_is_dry_run_by_default_without_key_sdk_or_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    task_path = write_tasks(tmp_path / "tasks.json")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "thrumely.provider_canary",
            "--provider",
            "google",
            "--tasks",
            str(task_path),
            "--task-id",
            "cal-openai-001",
            "--output",
            str(tmp_path / "results"),
        ],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "aspect_ratio": "1:1",
        "live_execution_authorized": False,
        "maximum_provider_executions": 1,
        "maximum_transport_requests": 1,
        "operation": "generate",
        "provider": "google",
        "quality_tier": "standard",
        "status": "DRY_RUN_ONLY",
        "task_id": "cal-openai-001",
    }
    assert not (tmp_path / "results").exists()


def test_cli_bfl_is_dry_run_by_default_without_key_or_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    task_path = write_tasks(tmp_path / "tasks.json")
    monkeypatch.delenv("BFL_API_KEY", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "thrumely.provider_canary",
            "--provider",
            "bfl",
            "--tasks",
            str(task_path),
            "--task-id",
            "cal-openai-001",
        ],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "DRY_RUN_ONLY"
    assert payload["provider"] == "bfl"
    assert payload["maximum_provider_executions"] == 1
    assert payload["maximum_transport_requests"] == 62


def test_cli_google_execute_live_requires_api_key_before_sdk_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_path = write_tasks(tmp_path / "tasks.json")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "thrumely.provider_canary",
            "--provider",
            "google",
            "--tasks",
            str(task_path),
            "--task-id",
            "cal-openai-001",
            "--execute-live",
        ],
    )

    with pytest.raises(SystemExit, match="GEMINI_API_KEY or GOOGLE_API_KEY"):
        main()


def test_cli_bfl_execute_live_requires_api_key_before_transport_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_path = write_tasks(tmp_path / "tasks.json")
    monkeypatch.delenv("BFL_API_KEY", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "thrumely.provider_canary",
            "--provider",
            "bfl",
            "--tasks",
            str(task_path),
            "--task-id",
            "cal-openai-001",
            "--execute-live",
        ],
    )

    with pytest.raises(SystemExit, match="BFL_API_KEY"):
        main()
