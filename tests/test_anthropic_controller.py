from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from thrumely.anthropic_controller import (
    AnthropicController,
    AnthropicControllerProtocolError,
)
from thrumely.schema import (
    ControllerConfig,
    MediaArtifact,
    MediaOperation,
    MediaStage,
    TaskSpec,
    ToolEnvironment,
)


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response):
        self.messages = FakeMessages(response)


def config() -> ControllerConfig:
    return ControllerConfig(
        controller_id="anthropic-opus-calibration",
        provider="anthropic",
        model="claude-opus-5",
        max_output_tokens=1024,
    )


def env() -> ToolEnvironment:
    return ToolEnvironment(
        "chooser",
        "chooser",
        (
            "openai:gpt-image-2",
            "google:gemini-3.1-flash-image",
            "bfl:flux-2-pro",
        ),
    )


def task() -> TaskSpec:
    return TaskSpec("t1", "synthetic", "Create a blue square on white.")


def tool_use(name="generate_or_edit", input=None):
    if input is None:
        input = {
            "backend": "bfl:flux-2-pro",
            "prompt": "A blue square centered on a white background",
            "operation": "generate",
            "aspect_ratio": "1:1",
            "quality_tier": "draft",
            "previous_artifact_id": None,
        }
    return SimpleNamespace(type="tool_use", name=name, input=input, id="toolu_1")


def response(blocks):
    return SimpleNamespace(
        id="msg_1",
        model="claude-opus-5",
        content=blocks,
        usage=SimpleNamespace(input_tokens=100, output_tokens=30),
        stop_reason="tool_use",
    )


def artifact() -> MediaArtifact:
    return MediaArtifact(
        artifact_id="artifact-1",
        sha256="a" * 64,
        mime_type="image/png",
        width=32,
        height=32,
        byte_length=24,
        stage=MediaStage.FIRST,
        relative_path="media/a.png",
    )


def png_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (32).to_bytes(4, "big") + (32).to_bytes(4, "big") + b"\x08\x06\x00\x00\x00"


def test_first_call_forces_one_neutral_media_tool() -> None:
    client = FakeClient(response([tool_use()]))
    decision = AnthropicController(config(), client=client).decide(task(), env(), call_index=1)

    call = client.messages.calls[0]
    assert call["model"] == "claude-opus-5"
    assert call["tool_choice"] == {"type": "any", "disable_parallel_tool_use": True}
    assert len(call["tools"]) == 1
    media_tool = call["tools"][0]
    assert media_tool["name"] == "generate_or_edit"
    assert media_tool["strict"] is True
    assert media_tool["input_schema"]["properties"]["backend"]["enum"] == list(env().available_backends)
    assert decision.action == "media"
    assert decision.request is not None
    assert decision.request.operation is MediaOperation.GENERATE


def test_second_call_includes_image_and_finish_tool() -> None:
    client = FakeClient(response([tool_use("finish", {})]))
    previous = png_bytes()
    decision = AnthropicController(config(), client=client).decide(
        task(), env(), call_index=2, previous_artifact=artifact(), previous_media=previous
    )

    call = client.messages.calls[0]
    assert {tool["name"] for tool in call["tools"]} == {"generate_or_edit", "finish"}
    content = call["messages"][0]["content"]
    image_block = next(block for block in content if block["type"] == "image")
    assert image_block["source"]["type"] == "base64"
    assert base64.b64decode(image_block["source"]["data"]) == previous
    assert decision.action == "finish"


def test_first_call_rejects_finish() -> None:
    client = FakeClient(response([tool_use("finish", {})]))
    with pytest.raises(AnthropicControllerProtocolError, match="finish"):
        AnthropicController(config(), client=client).decide(task(), env(), call_index=1)


def test_exactly_one_tool_use_is_required() -> None:
    client = FakeClient(response([tool_use(), tool_use()]))
    with pytest.raises(AnthropicControllerProtocolError, match="exactly one"):
        AnthropicController(config(), client=client).decide(task(), env(), call_index=1)


def test_observable_output_excludes_text_and_thinking_blocks() -> None:
    blocks = [
        SimpleNamespace(type="thinking", thinking="private"),
        SimpleNamespace(type="text", text="I considered several options"),
        tool_use(),
    ]
    decision = AnthropicController(config(), client=FakeClient(response(blocks))).decide(task(), env(), call_index=1)
    assert len(decision.observable_output) == 1
    assert decision.observable_output[0]["type"] == "tool_use"
    assert "private" not in repr(decision.observable_output)
    assert "considered" not in repr(decision.observable_output)


def test_second_call_edit_must_reference_current_artifact() -> None:
    bad = {
        "backend": "google:gemini-3.1-flash-image",
        "prompt": "Fix the square",
        "operation": "edit_previous",
        "aspect_ratio": "1:1",
        "quality_tier": "standard",
        "previous_artifact_id": "wrong",
    }
    client = FakeClient(response([tool_use(input=bad)]))
    with pytest.raises(AnthropicControllerProtocolError, match="current artifact"):
        AnthropicController(config(), client=client).decide(
            task(), env(), call_index=2, previous_artifact=artifact(), previous_media=png_bytes()
        )
