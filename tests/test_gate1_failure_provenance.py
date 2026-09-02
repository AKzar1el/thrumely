from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from thrumely.calibration import run_calibration
from thrumely.openai_controller import ControllerExecutionError, OpenAIController, system_prompt_sha256
from thrumely.schema import ControllerConfig


class NeverCalledProvider:
    provider = "openai"
    model = "gpt-image-2-2026-04-21"
    backend_id = "openai:gpt-image-2"

    def execute(self, request, previous_media=None):
        raise AssertionError("provider must not run when the controller fails")


class FailingResponses:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def create(self, **kwargs):
        raise self.error


class FakePermissionDeniedError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("raw SDK message with Authorization: Bearer sdk-secret")
        self.status_code = 403
        self.type = "access_denied"
        self.code = "gateway_denied"
        self.request_id = "req_safe_123"
        self.body = {
            "message": "Forbidden. Authorization: Bearer body-secret",
            "type": "access_denied",
            "code": "gateway_denied",
            "authorization": "Bearer body-secret",
        }
        self.response = SimpleNamespace(
            headers={
                "x-vercel-id": "iad1::safe-vercel-id",
                "x-request-id": "req_header_456",
                "authorization": "Bearer header-secret",
                "set-cookie": "session=secret-cookie",
            }
        )


def controller_config() -> ControllerConfig:
    return ControllerConfig(
        controller_id="openai-sol-calibration",
        provider="openai",
        model="openai/gpt-5.6-sol",
        reasoning_effort="medium",
        max_output_tokens=1024,
        system_prompt_sha256=system_prompt_sha256(),
        sdk_version="3.6.0",
    )


def write_tasks(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "calibration_only": True,
                "tasks": [
                    {"task_id": "cal-openai-001", "family": "a", "instruction": "one"},
                    {"task_id": "cal-openai-002", "family": "b", "instruction": "two"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_selected_calibration_bundle_contains_only_selected_task(tmp_path: Path) -> None:
    task_path = write_tasks(tmp_path / "tasks.json")
    controller = OpenAIController(
        controller_config(),
        client=SimpleNamespace(responses=FailingResponses(RuntimeError("stop"))),
    )

    output = run_calibration(
        tmp_path / "results",
        task_path,
        controller,
        NeverCalledProvider(),
        task_id="cal-openai-001",
        run_id="selected-task-bundle",
    )

    bundled = json.loads((output / "tasks.json").read_text(encoding="utf-8"))
    assert bundled == {
        "calibration_only": True,
        "tasks": [{"task_id": "cal-openai-001", "family": "a", "instruction": "one"}],
    }


def test_controller_failure_exposes_only_allowlisted_safe_diagnostics() -> None:
    controller = OpenAIController(
        controller_config(),
        client=SimpleNamespace(responses=FailingResponses(FakePermissionDeniedError())),
    )
    task_path = Path("unused")
    from thrumely.schema import TaskSpec, ToolEnvironment

    task = TaskSpec("cal-openai-001", "a", "one")
    environment = ToolEnvironment("fixed-openai", "fixed", ("openai:gpt-image-2",))

    with pytest.raises(ControllerExecutionError) as captured:
        controller.decide(task, environment, call_index=1)

    assert captured.value.diagnostics == {
        "exception_class": "FakePermissionDeniedError",
        "status_code": 403,
        "error_type": "access_denied",
        "error_code": "gateway_denied",
        "error_message": "Forbidden. Authorization: Bearer [REDACTED]",
        "request_id": "req_safe_123",
        "x_vercel_id": "iad1::safe-vercel-id",
    }
    serialized = json.dumps(captured.value.diagnostics)
    assert "sdk-secret" not in serialized
    assert "body-secret" not in serialized
    assert "header-secret" not in serialized
    assert "secret-cookie" not in serialized
    assert "set-cookie" not in serialized
    assert "authorization\"" not in serialized.lower()


def test_calibration_terminal_event_persists_controller_diagnostics(tmp_path: Path) -> None:
    task_path = write_tasks(tmp_path / "tasks.json")
    controller = OpenAIController(
        controller_config(),
        client=SimpleNamespace(responses=FailingResponses(FakePermissionDeniedError())),
    )

    output = run_calibration(
        tmp_path / "results",
        task_path,
        controller,
        NeverCalledProvider(),
        task_id="cal-openai-001",
        run_id="controller-diagnostics",
    )

    trajectory = json.loads((output / "trajectories.jsonl").read_text(encoding="utf-8"))
    terminal = trajectory["events"][-1]
    assert terminal["type"] == "terminal_error"
    assert terminal["diagnostics"]["status_code"] == 403
    assert terminal["diagnostics"]["error_type"] == "access_denied"
    assert terminal["diagnostics"]["x_vercel_id"] == "iad1::safe-vercel-id"
    serialized = json.dumps(terminal)
    assert "body-secret" not in serialized
    assert "header-secret" not in serialized
    assert "secret-cookie" not in serialized
