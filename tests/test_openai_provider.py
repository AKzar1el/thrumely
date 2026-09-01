from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from thrumely.openai_provider import OpenAIImageProvider, aspect_ratio_to_size, quality_tier_to_openai
from thrumely.schema import MediaOperation, NormalizedMediaRequest, ToolEnvironment


class FakeImages:
    def __init__(self) -> None:
        self.generate_kwargs = None
        self.edit_kwargs = None

    def generate(self, **kwargs):
        self.generate_kwargs = kwargs
        return SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(b"fake-png").decode("ascii"))],
            usage=SimpleNamespace(input_tokens=5, output_tokens=196, total_tokens=201),
            _request_id="req_generate",
            model="gpt-image-2-2026-04-21",
        )

    def edit(self, **kwargs):
        self.edit_kwargs = kwargs
        return SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(b"edited-png").decode("ascii"))],
            usage=SimpleNamespace(input_tokens=15, output_tokens=196, total_tokens=211),
            _request_id="req_edit",
            model="gpt-image-2-2026-04-21",
        )


class FakeClient:
    def __init__(self) -> None:
        self.images = FakeImages()


def request(*, operation: MediaOperation = MediaOperation.GENERATE, previous_artifact_id: str | None = None):
    env = ToolEnvironment("fixed-openai", "fixed", ("openai:gpt-image-2",))
    return NormalizedMediaRequest(
        backend="openai:gpt-image-2",
        prompt="Create a blue square.",
        operation=operation,
        aspect_ratio="1:1",
        quality_tier="standard",
        previous_artifact_id=previous_artifact_id,
        environment=env,
    )


def test_aspect_ratio_mapping_is_benchmark_owned() -> None:
    assert aspect_ratio_to_size("1:1") == "1024x1024"
    assert aspect_ratio_to_size("16:9") == "1536x864"
    assert aspect_ratio_to_size("9:16") == "864x1536"
    with pytest.raises(ValueError, match="aspect ratio"):
        aspect_ratio_to_size("4:1")


def test_quality_mapping_is_benchmark_owned() -> None:
    assert quality_tier_to_openai("draft") == "low"
    assert quality_tier_to_openai("standard") == "medium"
    assert quality_tier_to_openai("high") == "high"
    with pytest.raises(ValueError, match="quality tier"):
        quality_tier_to_openai("ultra")


def test_generation_maps_normalized_request_and_decodes_media() -> None:
    client = FakeClient()
    provider = OpenAIImageProvider(client=client)

    result = provider.execute(request())

    assert client.images.generate_kwargs == {
        "model": "gpt-image-2-2026-04-21",
        "prompt": "Create a blue square.",
        "size": "1024x1024",
        "quality": "medium",
        "output_format": "png",
    }
    assert result.media_bytes == b"fake-png"
    assert result.mime_type == "image/png"
    assert result.width == 1024
    assert result.height == 1024
    assert result.provider == "openai"
    assert result.model == "gpt-image-2-2026-04-21"
    assert result.request_id == "req_generate"
    assert result.usage["output_tokens"] == 196
    assert result.raw_response["data"][0]["b64_json"] == "[MEDIA_BYTES_STORED_SEPARATELY]"


def test_edit_requires_previous_media_bytes() -> None:
    provider = OpenAIImageProvider(client=FakeClient())
    with pytest.raises(ValueError, match="previous_media"):
        provider.execute(
            request(operation=MediaOperation.EDIT_PREVIOUS, previous_artifact_id="artifact-1"),
            previous_media=None,
        )


def test_edit_uses_previous_media_and_same_normalized_controls() -> None:
    client = FakeClient()
    provider = OpenAIImageProvider(client=client)
    result = provider.execute(
        request(operation=MediaOperation.EDIT_PREVIOUS, previous_artifact_id="artifact-1"),
        previous_media=b"prior-png",
    )

    kwargs = client.images.edit_kwargs
    assert kwargs["model"] == "gpt-image-2-2026-04-21"
    assert kwargs["prompt"] == "Create a blue square."
    assert kwargs["size"] == "1024x1024"
    assert kwargs["quality"] == "medium"
    assert kwargs["output_format"] == "png"
    assert kwargs["image"].read() == b"prior-png"
    assert result.media_bytes == b"edited-png"
    assert result.request_id == "req_edit"


def test_provider_wraps_sdk_failure_as_typed_execution_error() -> None:
    from thrumely.openai_provider import ProviderExecutionError

    class FailingImages:
        def generate(self, **kwargs):
            raise RuntimeError("network down")

    failing_client = SimpleNamespace(images=FailingImages())
    provider = OpenAIImageProvider(client=failing_client)
    with pytest.raises(ProviderExecutionError, match="network down"):
        provider.execute(request())


def test_provider_exposes_logical_backend_id_separate_from_snapshot() -> None:
    provider = OpenAIImageProvider(client=FakeClient())
    assert provider.backend_id == "openai:gpt-image-2"
    assert provider.model == "gpt-image-2-2026-04-21"
