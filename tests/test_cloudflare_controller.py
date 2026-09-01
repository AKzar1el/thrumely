from __future__ import annotations

import json

import pytest

from thrumely.cloudflare_controller import CloudflareController
from thrumely.interfaces import ControllerProtocolError
from thrumely.schema import ControllerConfig, MediaArtifact, MediaStage, TaskSpec, ToolEnvironment


MODEL = "@cf/google/gemma-4-26b-a4b-it"
BACKEND = "cloudflare:flux-2-klein-4b"


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_json(self, url, headers, json_payload):
        self.calls.append((url, dict(headers), json.loads(json.dumps(json_payload))))
        return self.response


def config() -> ControllerConfig:
    return ControllerConfig(
        controller_id="cloudflare-gemma4-calibration",
        provider="cloudflare",
        model=MODEL,
        reasoning_effort="medium",
        max_output_tokens=1024,
        system_prompt_sha256="a" * 64,
        sdk_version=None,
    )


def task() -> TaskSpec:
    return TaskSpec("cal-cloudflare-001", "composition", "Create a blue square on white.")


def environment() -> ToolEnvironment:
    return ToolEnvironment("cloudflare-fixed", "fixed", (BACKEND,))


def tool_response(name: str, arguments: dict, *, response_id: str = "chat-1") -> dict:
    return {
        "id": response_id,
        "object": "chat.completion",
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "reasoning": "private chain that must not be persisted",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(arguments),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
    }


def media_args(*, operation: str = "generate", previous_artifact_id=None) -> dict:
    return {
        "backend": BACKEND,
        "prompt": "Create a blue square on white.",
        "operation": operation,
        "aspect_ratio": "1:1",
        "quality_tier": "standard",
        "previous_artifact_id": previous_artifact_id,
    }


def artifact() -> MediaArtifact:
    return MediaArtifact(
        artifact_id="media:" + "b" * 64,
        sha256="b" * 64,
        mime_type="image/png",
        width=1024,
        height=1024,
        byte_length=32,
        stage=MediaStage.FIRST,
        relative_path="media/test.png",
    )


def test_first_decision_requires_generate_tool_and_uses_exact_backend_enum() -> None:
    transport = FakeTransport(tool_response("generate_or_edit", media_args()))
    controller = CloudflareController(
        config(),
        account_id="account-test",
        api_token="secret-token",
        transport=transport,
    )

    decision = controller.decide(task(), environment(), call_index=1)

    assert decision.action == "media"
    assert decision.request is not None
    assert decision.request.backend == BACKEND
    assert decision.request.operation.value == "generate"
    assert decision.observable_output[0]["type"] == "function_call"
    assert "reasoning" not in json.dumps(decision.observable_output).lower()

    assert len(transport.calls) == 1
    url, headers, payload = transport.calls[0]
    assert url.endswith("/accounts/account-test/ai/v1/chat/completions")
    assert headers["Authorization"] == "Bearer secret-token"
    assert payload["model"] == MODEL
    assert payload["parallel_tool_calls"] is False
    assert payload["stream"] is False
    assert payload["tool_choice"] == {
        "type": "function",
        "function": {"name": "generate_or_edit"},
    }
    assert [tool["function"]["name"] for tool in payload["tools"]] == ["generate_or_edit"]
    backend_schema = payload["tools"][0]["function"]["parameters"]["properties"]["backend"]
    assert backend_schema["enum"] == [BACKEND]
    serialized = json.dumps(payload)
    assert "secret-token" not in serialized


def test_second_decision_can_finish_after_reviewing_previous_image() -> None:
    transport = FakeTransport(tool_response("finish", {}, response_id="chat-2"))
    controller = CloudflareController(
        config(),
        account_id="account-test",
        api_token="secret-token",
        transport=transport,
    )
    previous = artifact()
    media = b"png-like-current-media"

    decision = controller.decide(
        task(),
        environment(),
        call_index=2,
        previous_artifact=previous,
        previous_media=media,
    )

    assert decision.action == "finish"
    payload = transport.calls[0][2]
    assert [tool["function"]["name"] for tool in payload["tools"]] == ["generate_or_edit", "finish"]
    user_content = payload["messages"][-1]["content"]
    assert user_content[0]["type"] == "text"
    assert previous.artifact_id in user_content[0]["text"]
    assert user_content[1]["type"] == "image_url"
    assert user_content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_second_decision_can_edit_only_current_artifact() -> None:
    previous = artifact()
    transport = FakeTransport(
        tool_response(
            "generate_or_edit",
            media_args(operation="edit_previous", previous_artifact_id=previous.artifact_id),
        )
    )
    controller = CloudflareController(
        config(),
        account_id="a",
        api_token="t",
        transport=transport,
    )

    decision = controller.decide(
        task(),
        environment(),
        call_index=2,
        previous_artifact=previous,
        previous_media=b"media",
    )

    assert decision.action == "media"
    assert decision.request is not None
    assert decision.request.operation.value == "edit_previous"
    assert decision.request.previous_artifact_id == previous.artifact_id


def test_first_call_finish_is_rejected() -> None:
    transport = FakeTransport(tool_response("finish", {}))
    controller = CloudflareController(config(), account_id="a", api_token="t", transport=transport)
    with pytest.raises(ControllerProtocolError, match="finish is not allowed"):
        controller.decide(task(), environment(), call_index=1)


def test_malformed_or_multiple_tool_calls_are_rejected() -> None:
    response = tool_response("generate_or_edit", media_args())
    response["choices"][0]["message"]["tool_calls"].append(
        response["choices"][0]["message"]["tool_calls"][0].copy()
    )
    transport = FakeTransport(response)
    controller = CloudflareController(config(), account_id="a", api_token="t", transport=transport)
    with pytest.raises(ControllerProtocolError, match="exactly one"):
        controller.decide(task(), environment(), call_index=1)


def test_second_decision_requires_previous_media_before_network() -> None:
    transport = FakeTransport(tool_response("finish", {}))
    controller = CloudflareController(config(), account_id="a", api_token="t", transport=transport)
    with pytest.raises(ValueError, match="previous_artifact and previous_media"):
        controller.decide(task(), environment(), call_index=2)
    assert transport.calls == []
