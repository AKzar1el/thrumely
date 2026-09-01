from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from thrumely.calibration import load_calibration_tasks, main, run_calibration
from thrumely.interfaces import ControllerDecision, ProviderMediaResult
from thrumely.openai_provider import ProviderExecutionError
from thrumely.schema import ControllerConfig, MediaOperation, NormalizedMediaRequest


class FakeController:
    def __init__(self) -> None:
        self.config = ControllerConfig(
            controller_id="fake-live-controller",
            provider="openai",
            model="gpt-5.6-sol",
            reasoning_effort="medium",
            max_output_tokens=1024,
            system_prompt_sha256="a" * 64,
            sdk_version="3.6.0",
        )
        self.calls = []

    def decide(self, task, environment, *, call_index, previous_artifact=None, previous_media=None):
        self.calls.append((task.task_id, call_index))
        if call_index == 2:
            return ControllerDecision(
                action="finish",
                request=None,
                response_id=f"resp-{task.task_id}-2",
                actual_model="gpt-5.6-sol",
                usage={"input_tokens": 12, "output_tokens": 1},
                observable_output=({"type": "function_call", "name": "finish", "arguments": "{}"},),
            )
        request = NormalizedMediaRequest(
            backend=environment.available_backends[0],
            prompt=task.instruction,
            operation=MediaOperation.GENERATE,
            aspect_ratio="1:1",
            quality_tier="standard",
            previous_artifact_id=None,
            environment=environment,
        )
        return ControllerDecision(
            action="media",
            request=request,
            response_id=f"resp-{task.task_id}-1",
            actual_model="gpt-5.6-sol",
            usage={"input_tokens": 10, "output_tokens": 5},
            observable_output=(
                {"type": "function_call", "name": "generate_or_edit", "arguments": {"prompt": task.instruction}},
            ),
        )


class FakeProvider:
    provider = "openai"
    model = "gpt-image-2-2026-04-21"
    backend_id = "openai:gpt-image-2"

    def execute(self, request, previous_media=None):
        return ProviderMediaResult(
            media_bytes=("fake:" + request.prompt).encode(),
            mime_type="image/png",
            width=1024,
            height=1024,
            provider=self.provider,
            model=self.model,
            raw_request={"prompt": request.prompt, "authorization": "Bearer fake-secret"},
            raw_response={"data": [{"b64_json": "[MEDIA_BYTES_STORED_SEPARATELY]"}]},
            request_id="img-test",
            latency_seconds=0.01,
            cost_usd=None,
            moderation_status=None,
            retry_count=0,
            usage={"output_tokens": 196},
        )


class FailingProvider(FakeProvider):
    def execute(self, request, previous_media=None):
        raise ProviderExecutionError("synthetic provider outage")


def write_tasks(path: Path, *, calibration_only=True, tasks=None) -> Path:
    payload = {
        "calibration_only": calibration_only,
        "tasks": tasks
        or [
            {
                "task_id": "cal-openai-001",
                "family": "compositional-constraints",
                "instruction": "Create a blue square centered on white.",
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_loader_requires_explicit_calibration_only_flag(tmp_path: Path) -> None:
    path = write_tasks(tmp_path / "tasks.json", calibration_only=False)
    with pytest.raises(ValueError, match="calibration_only"):
        load_calibration_tasks(path)


def test_loader_rejects_duplicate_task_ids(tmp_path: Path) -> None:
    path = write_tasks(
        tmp_path / "tasks.json",
        tasks=[
            {"task_id": "cal-openai-001", "family": "a", "instruction": "one"},
            {"task_id": "cal-openai-001", "family": "b", "instruction": "two"},
        ],
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_calibration_tasks(path)


def test_loader_rejects_non_calibration_task_prefix(tmp_path: Path) -> None:
    path = write_tasks(
        tmp_path / "tasks.json",
        tasks=[{"task_id": "v1-001", "family": "a", "instruction": "one"}],
    )
    with pytest.raises(ValueError, match="calibration task_id"):
        load_calibration_tasks(path)


def test_fake_live_runner_exports_hashed_redacted_bundle(tmp_path: Path) -> None:
    task_path = write_tasks(tmp_path / "tasks.json")
    output = run_calibration(
        tmp_path / "results",
        task_path,
        FakeController(),
        FakeProvider(),
        run_id="calibration-test",
    )

    assert (output / "manifest.json").exists()
    assert (output / "configuration.json").exists()
    assert (output / "trajectories.jsonl").exists()
    assert (output / "media.jsonl").exists()

    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["data_classification"] == "live-calibration"
    assert manifest["requested_trajectories"] == 1
    assert manifest["completed_trajectories"] == 1
    assert len(manifest["task_corpus_sha256"]) == 64
    assert (output / "tasks.json").exists()
    configuration = json.loads((output / "configuration.json").read_text())
    assert configuration["task_file"] == "tasks.json"
    assert str(tmp_path) not in json.dumps(configuration)

    trajectories = read_jsonl(output / "trajectories.jsonl")
    assert len(trajectories) == 1
    trajectory = trajectories[0]
    assert trajectory["completion_status"] == "success"
    assert trajectory["final_artifact_id"].startswith("media:")
    assert trajectory["tool_calls"][0]["provider"] == "openai"
    assert trajectory["tool_calls"][0]["model"] == "gpt-image-2-2026-04-21"
    assert trajectory["tool_calls"][0]["raw_request"]["authorization"] == "[REDACTED]"

    media = read_jsonl(output / "media.jsonl")
    assert len(media) == 1
    assert media[0]["stage"] == "final"
    media_path = output / media[0]["relative_path"]
    assert media_path.exists()
    assert media[0]["byte_length"] == len(media_path.read_bytes())

    serialized = "\n".join(path.read_text(errors="ignore") for path in output.glob("*.json*"))
    assert "fake-secret" not in serialized


def test_provider_failure_becomes_explicit_error_trajectory(tmp_path: Path) -> None:
    task_path = write_tasks(tmp_path / "tasks.json")
    output = run_calibration(
        tmp_path / "results",
        task_path,
        FakeController(),
        FailingProvider(),
        run_id="calibration-failure",
    )
    trajectory = read_jsonl(output / "trajectories.jsonl")[0]
    assert trajectory["completion_status"] == "error"
    assert "synthetic provider outage" in trajectory["infrastructure_error"]
    assert trajectory["final_artifact_id"] is None
    assert trajectory["tool_calls"] == []


def test_runner_can_hard_select_one_calibration_task(tmp_path: Path) -> None:
    task_path = write_tasks(
        tmp_path / "tasks.json",
        tasks=[
            {"task_id": "cal-openai-001", "family": "a", "instruction": "one"},
            {"task_id": "cal-openai-002", "family": "b", "instruction": "two"},
        ],
    )
    controller = FakeController()
    output = run_calibration(
        tmp_path / "results",
        task_path,
        controller,
        FakeProvider(),
        task_id="cal-openai-002",
        run_id="calibration-one-task",
    )

    manifest = json.loads((output / "manifest.json").read_text())
    trajectories = read_jsonl(output / "trajectories.jsonl")
    assert manifest["requested_trajectories"] == 1
    assert [row["task_id"] for row in trajectories] == ["cal-openai-002"]
    assert controller.calls == [("cal-openai-002", 1), ("cal-openai-002", 2)]


def test_cli_is_dry_run_by_default_without_api_key_or_sdk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    task_path = write_tasks(tmp_path / "tasks.json")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "thrumely.calibration",
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
    assert payload["status"] == "DRY_RUN_ONLY"
    assert payload["task_id"] == "cal-openai-001"
    assert payload["maximum_media_calls"] == 2
    assert payload["live_execution_authorized"] is False
    assert not (tmp_path / "results").exists()


def test_cli_execute_live_still_requires_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_path = write_tasks(tmp_path / "tasks.json")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "thrumely.calibration",
            "--tasks",
            str(task_path),
            "--task-id",
            "cal-openai-001",
            "--execute-live",
        ],
    )

    with pytest.raises(SystemExit, match="OPENAI_API_KEY"):
        main()
