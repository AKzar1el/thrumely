from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from thrumely.openai_controller import (
    SYSTEM_PROMPT,
    ControllerProtocolError,
    OpenAIController,
    system_prompt_sha256,
)
from thrumely.schema import ControllerConfig, MediaArtifact, MediaOperation, MediaStage, TaskSpec, ToolEnvironment


class FakeResponses:
    def __init__(self, response) -> None:
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response) -> None:
        self.responses = FakeResponses(response)


def response_with_call(name: str, arguments: dict, *, output_prefix=()):
    return SimpleNamespace(
        id="resp_test",
        model="gpt-5.6-sol",
        usage=SimpleNamespace(input_tokens=20, output_tokens=5, total_tokens=25),
        output=[
            *output_prefix,
            SimpleNamespace(
                type="function_call",
                name=name,
                arguments=json.dumps(arguments),
                call_id="call_test",
            ),
        ],
    )


def config() -> ControllerConfig:
    return ControllerConfig(
        controller_id="openai-sol-calibration",
        provider="openai",
        model="gpt-5.6-sol",
        reasoning_effort="medium",
        max_output_tokens=1024,
        system_prompt_sha256=system_prompt_sha256(),
        sdk_version="3.6.0",
    )


def task() -> TaskSpec:
    return TaskSpec("cal-openai-001", "composition", "Create a blue square.")


def environment() -> ToolEnvironment:
    return ToolEnvironment("fixed-openai", "fixed", ("openai:gpt-image-2",))


def artifact() -> MediaArtifact:
    return MediaArtifact(
        artifact_id="media-abc",
        sha256="a" * 64,
        mime_type="image/png",
        width=1024,
        height=1024,
        byte_length=3,
        stage=MediaStage.FIRST,
        relative_path="media/abc.png",
    )


def test_system_prompt_hash_is_stable_sha256() -> None:
    assert len(system_prompt_sha256()) == 64
    assert "native image" not in SYSTEM_PROMPT.lower()


def test_first_decision_uses_only_benchmark_owned_media_function() -> None:
    fake_response = response_with_call(
        "generate_or_edit",
        {
            "backend": "openai:gpt-image-2",
            "prompt": "Create a centered blue square on white.",
            "operation": "generate",
            "aspect_ratio": "1:1",
            "quality_tier": "standard",
            "previous_artifact_id": None,
        },
    )
    client = FakeClient(fake_response)
    controller = OpenAIController(config(), client=client)

    decision = controller.decide(task(), environment(), call_index=1)

    assert decision.action == "media"
    assert decision.request is not None
    assert decision.request.operation is MediaOperation.GENERATE
    kwargs = client.responses.calls[0]
    assert kwargs["model"] == "gpt-5.6-sol"
    assert kwargs["instructions"] == SYSTEM_PROMPT
    assert kwargs["tool_choice"] == {"type": "function", "name": "generate_or_edit"}
    assert kwargs["parallel_tool_calls"] is False
    assert kwargs["store"] is False
    assert [tool["name"] for tool in kwargs["tools"]] == ["generate_or_edit"]
    tool = kwargs["tools"][0]
    assert tool["type"] == "function"
    assert tool["strict"] is True
    assert tool["parameters"]["properties"]["backend"]["enum"] == ["openai:gpt-image-2"]
    assert tool["parameters"]["properties"]["operation"]["enum"] == ["generate"]
    assert tool["parameters"]["additionalProperties"] is False


def test_second_decision_can_finish_after_visual_review() -> None:
    fake_response = response_with_call("finish", {})
    client = FakeClient(fake_response)
    controller = OpenAIController(config(), client=client)

    decision = controller.decide(
        task(),
        environment(),
        call_index=2,
        previous_artifact=artifact(),
        previous_media=b"png",
    )

    assert decision.action == "finish"
    assert decision.request is None
    kwargs = client.responses.calls[0]
    assert kwargs["tool_choice"] == "required"
    assert [tool["name"] for tool in kwargs["tools"]] == ["generate_or_edit", "finish"]
    content = kwargs["input"][0]["content"]
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/png;base64,")


def test_private_reasoning_items_are_not_observable() -> None:
    reasoning = SimpleNamespace(type="reasoning", summary="private", encrypted_content="cipher")
    fake_response = response_with_call(
        "generate_or_edit",
        {
            "backend": "openai:gpt-image-2",
            "prompt": "Create a blue square.",
            "operation": "generate",
            "aspect_ratio": "1:1",
            "quality_tier": "standard",
            "previous_artifact_id": None,
        },
        output_prefix=(reasoning,),
    )
    decision = OpenAIController(config(), client=FakeClient(fake_response)).decide(
        task(), environment(), call_index=1
    )
    serialized = json.dumps(decision.observable_output)
    assert "private" not in serialized
    assert "cipher" not in serialized
    assert "reasoning" not in serialized


def test_first_decision_rejects_finish() -> None:
    controller = OpenAIController(config(), client=FakeClient(response_with_call("finish", {})))
    with pytest.raises(ControllerProtocolError, match="finish"):
        controller.decide(task(), environment(), call_index=1)


def test_rejects_multiple_function_calls() -> None:
    response = SimpleNamespace(
        id="resp_test",
        model="gpt-5.6-sol",
        usage=None,
        output=[
            SimpleNamespace(type="function_call", name="finish", arguments="{}", call_id="one"),
            SimpleNamespace(type="function_call", name="finish", arguments="{}", call_id="two"),
        ],
    )
    controller = OpenAIController(config(), client=FakeClient(response))
    with pytest.raises(ControllerProtocolError, match="exactly one"):
        controller.decide(
            task(), environment(), call_index=2, previous_artifact=artifact(), previous_media=b"png"
        )


def test_controller_wraps_sdk_failure_as_typed_execution_error() -> None:
    from thrumely.openai_controller import ControllerExecutionError

    class FailingResponses:
        def create(self, **kwargs):
            raise RuntimeError("rate limited")

    controller = OpenAIController(config(), client=SimpleNamespace(responses=FailingResponses()))
    with pytest.raises(ControllerExecutionError, match="rate limited"):
        controller.decide(task(), environment(), call_index=1)
