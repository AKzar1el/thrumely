from __future__ import annotations

import base64
import json
import struct
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import thrumely.calibration as calibration
from thrumely.openai_controller import ControllerExecutionError, OpenAIController, system_prompt_sha256
from thrumely.openai_provider import OpenAIImageProvider, ProviderExecutionError
from thrumely.schema import ControllerConfig, MediaOperation, NormalizedMediaRequest, TaskSpec, ToolEnvironment


_GATEWAY_ONLY_OPENAI = {"providerOptions": {"gateway": {"only": ["openai"]}}}


def _routing_metadata(*, provider: str = "openai", provider_attempts: int = 1) -> dict:
    attempts = []
    for index in range(provider_attempts):
        attempts.append(
            {
                "provider": provider,
                "credentialType": "system",
                "success": index == provider_attempts - 1,
            }
        )
    return {
        "gateway": {
            "routing": {
                "resolvedProvider": provider,
                "finalProvider": provider,
                "modelAttemptCount": 1,
                "totalProviderAttemptCount": provider_attempts,
                "modelAttempts": [
                    {
                        "canonicalSlug": "openai/gpt-5.6-sol",
                        "providerAttempts": attempts,
                    }
                ],
            },
            "cost": "0.001",
        }
    }


def _controller_response(*, provider: str = "openai", provider_attempts: int = 1, finish: bool = False):
    if finish:
        name = "finish"
        arguments = {}
    else:
        name = "generate_or_edit"
        arguments = {
            "backend": "openai:gpt-image-2",
            "prompt": "Create a blue square.",
            "operation": "generate",
            "aspect_ratio": "1:1",
            "quality_tier": "standard",
            "previous_artifact_id": None,
        }
    return SimpleNamespace(
        id="resp_gateway",
        model="openai/gpt-5.6-sol",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5, total_tokens=15),
        provider_metadata=_routing_metadata(provider=provider, provider_attempts=provider_attempts),
        output=[
            SimpleNamespace(
                type="function_call",
                name=name,
                arguments=json.dumps(arguments),
                call_id="call_gateway",
            )
        ],
    )


class _FakeResponses:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class _FakeImages:
    def __init__(self, *, provider: str = "openai", provider_attempts: int = 1) -> None:
        self.provider = provider
        self.provider_attempts = provider_attempts
        self.generate_calls: list[dict] = []
        self.edit_calls: list[dict] = []

    def _result(self):
        return SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(_png_bytes()).decode("ascii"))],
            usage=SimpleNamespace(input_tokens=5, output_tokens=196, total_tokens=201),
            _request_id="img_gateway",
            model="openai/gpt-image-2",
            provider_metadata=_routing_metadata(
                provider=self.provider,
                provider_attempts=self.provider_attempts,
            ),
        )

    def generate(self, **kwargs):
        self.generate_calls.append(kwargs)
        return self._result()

    def edit(self, **kwargs):
        self.edit_calls.append(kwargs)
        return self._result()


class _FakeClient:
    def __init__(self, responses, *, provider: str = "openai", provider_attempts: int = 1) -> None:
        self.responses = _FakeResponses(responses)
        self.images = _FakeImages(provider=provider, provider_attempts=provider_attempts)


def _controller_config() -> ControllerConfig:
    return ControllerConfig(
        controller_id="openai-sol-vercel-calibration",
        provider="openai",
        model="openai/gpt-5.6-sol",
        reasoning_effort="medium",
        max_output_tokens=1024,
        system_prompt_sha256=system_prompt_sha256(),
        sdk_version="3.6.0",
    )


def _task() -> TaskSpec:
    return TaskSpec("cal-openai-001", "composition", "Create a blue square.")


def _environment() -> ToolEnvironment:
    return ToolEnvironment("fixed-openai", "fixed", ("openai:gpt-image-2",))


def _request() -> NormalizedMediaRequest:
    return NormalizedMediaRequest(
        backend="openai:gpt-image-2",
        prompt="Create a blue square.",
        operation=MediaOperation.GENERATE,
        aspect_ratio="1:1",
        quality_tier="standard",
        previous_artifact_id=None,
        environment=_environment(),
    )


def _png_bytes(width: int = 128, height: int = 128) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x06\x00\x00\x00"
    )


def _write_tasks(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "calibration_only": True,
                "tasks": [
                    {
                        "task_id": "cal-openai-001",
                        "family": "compositional-constraints",
                        "instruction": "Create a blue square.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_controller_gateway_request_is_openai_only_and_records_routing_metadata() -> None:
    client = _FakeClient([_controller_response()])
    controller = OpenAIController(
        _controller_config(),
        client=client,
        request_extra_body=_GATEWAY_ONLY_OPENAI,
        required_gateway_provider="openai",
    )

    decision = controller.decide(_task(), _environment(), call_index=1)

    assert client.responses.calls[0]["extra_body"] == _GATEWAY_ONLY_OPENAI
    assert decision.provider_metadata["gateway"]["routing"]["finalProvider"] == "openai"
    assert decision.provider_metadata["gateway"]["routing"]["totalProviderAttemptCount"] == 1


def test_controller_gateway_rejects_multiple_provider_attempts() -> None:
    client = _FakeClient([_controller_response(provider_attempts=2)])
    controller = OpenAIController(
        _controller_config(),
        client=client,
        request_extra_body=_GATEWAY_ONLY_OPENAI,
        required_gateway_provider="openai",
    )

    with pytest.raises(ControllerExecutionError, match="routing contract"):
        controller.decide(_task(), _environment(), call_index=1)


def test_image_gateway_request_is_openai_only_and_records_routing_metadata() -> None:
    client = _FakeClient([])
    provider = OpenAIImageProvider(
        model="openai/gpt-image-2",
        client=client,
        request_extra_body=_GATEWAY_ONLY_OPENAI,
        required_gateway_provider="openai",
    )

    result = provider.execute(_request())

    assert client.images.generate_calls[0]["extra_body"] == _GATEWAY_ONLY_OPENAI
    assert result.model == "openai/gpt-image-2"
    assert result.raw_response["provider_metadata"]["gateway"]["routing"]["finalProvider"] == "openai"


def test_image_gateway_rejects_non_openai_routing() -> None:
    client = _FakeClient([], provider="azure")
    provider = OpenAIImageProvider(
        model="openai/gpt-image-2",
        client=client,
        request_extra_body=_GATEWAY_ONLY_OPENAI,
        required_gateway_provider="openai",
    )

    with pytest.raises(ProviderExecutionError, match="routing contract"):
        provider.execute(_request())


def test_vercel_credit_check_uses_gateway_credits_endpoint() -> None:
    captured: dict[str, object] = {}

    class FakeHTTPResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"balance":"5.00","total_used":"0.00"}'

    def opener(request, *, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return FakeHTTPResponse()

    credits = calibration.fetch_vercel_gateway_credits("gateway-secret", opener=opener)

    assert captured == {
        "url": "https://ai-gateway.vercel.sh/v1/credits",
        "authorization": "Bearer gateway-secret",
        "timeout": 15.0,
    }
    assert credits == {"balance": "5.00", "total_used": "0.00"}


def test_cli_vercel_live_requires_gateway_key_not_openai_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_path = _write_tasks(tmp_path / "tasks.json")
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "direct-key-that-must-not-be-used")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "thrumely.calibration",
            "--tasks",
            str(task_path),
            "--task-id",
            "cal-openai-001",
            "--transport",
            "vercel-gateway",
            "--execute-live",
        ],
    )

    with pytest.raises(SystemExit, match="AI_GATEWAY_API_KEY"):
        calibration.main()


def test_cli_vercel_zero_balance_stops_before_sdk_or_inference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_path = _write_tasks(tmp_path / "tasks.json")
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "gateway-secret")
    monkeypatch.setattr(
        calibration,
        "fetch_vercel_gateway_credits",
        lambda api_key, opener=None: {"balance": "0.00", "total_used": "5.00"},
        raising=False,
    )

    class ForbiddenOpenAI:
        def __init__(self, **kwargs) -> None:
            raise AssertionError("SDK must not be constructed with zero Gateway balance")

    module = ModuleType("openai")
    module.OpenAI = ForbiddenOpenAI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", module)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "thrumely.calibration",
            "--tasks",
            str(task_path),
            "--task-id",
            "cal-openai-001",
            "--transport",
            "vercel-gateway",
            "--execute-live",
        ],
    )

    with pytest.raises(SystemExit, match="positive AI Gateway credit"):
        calibration.main()


def test_cli_vercel_live_uses_gateway_models_and_records_credit_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    task_path = _write_tasks(tmp_path / "tasks.json")
    output_root = tmp_path / "results"
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "gateway-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "direct-key-that-must-not-be-used")
    monkeypatch.setattr(calibration, "_openai_sdk_version", lambda: "3.6.0")

    balances = iter(
        [
            {"balance": "5.00", "total_used": "0.00"},
            {"balance": "4.90", "total_used": "0.10"},
        ]
    )
    credit_keys: list[str] = []

    def fake_credits(api_key, opener=None):
        credit_keys.append(api_key)
        return next(balances)

    monkeypatch.setattr(calibration, "fetch_vercel_gateway_credits", fake_credits, raising=False)

    constructed: list[dict] = []
    fake_client = _FakeClient([_controller_response(), _controller_response(finish=True)])

    class FakeOpenAI:
        def __new__(cls, **kwargs):
            constructed.append(kwargs)
            return fake_client

    module = ModuleType("openai")
    module.OpenAI = FakeOpenAI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", module)
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
            str(output_root),
            "--transport",
            "vercel-gateway",
            "--execute-live",
        ],
    )

    calibration.main()

    assert constructed == [
        {
            "api_key": "gateway-secret",
            "base_url": "https://ai-gateway.vercel.sh/v1",
            "max_retries": 0,
        }
    ]
    assert credit_keys == ["gateway-secret", "gateway-secret"]
    assert fake_client.responses.calls[0]["model"] == "openai/gpt-5.6-sol"
    assert fake_client.responses.calls[0]["extra_body"] == _GATEWAY_ONLY_OPENAI
    assert fake_client.images.generate_calls[0]["model"] == "openai/gpt-image-2"
    assert fake_client.images.generate_calls[0]["extra_body"] == _GATEWAY_ONLY_OPENAI

    run_dir = Path(capsys.readouterr().out.strip())
    configuration = json.loads((run_dir / "configuration.json").read_text(encoding="utf-8"))
    transport = configuration["transport"]
    assert transport["kind"] == "vercel-ai-gateway"
    assert transport["upstream_provider_required"] == "openai"
    assert transport["controller_gateway_model"] == "openai/gpt-5.6-sol"
    assert transport["image_gateway_model"] == "openai/gpt-image-2"
    assert transport["image_gateway_release_date"] == "2026-04-21"
    assert transport["exact_snapshot_equivalence_established"] is False
    assert transport["credits_before"] == {"balance": "5.00", "total_used": "0.00"}
    assert transport["credits_after"] == {"balance": "4.90", "total_used": "0.10"}
    assert transport["observed_credit_delta_usd"] == "0.10"

    trajectory = json.loads((run_dir / "trajectories.jsonl").read_text(encoding="utf-8").splitlines()[0])
    first_controller_message = next(
        message for message in trajectory["messages"] if message.get("role") == "controller"
    )
    assert first_controller_message["provider_metadata"]["gateway"]["routing"]["finalProvider"] == "openai"
    assert "gateway-secret" not in json.dumps(configuration)
