from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from thrumely.google_provider import (
    GoogleImageProvider,
    GoogleProviderExecutionError,
    quality_tier_to_resolution,
)
from thrumely.schema import MediaOperation, NormalizedMediaRequest, ToolEnvironment


def png_bytes(width: int = 32, height: int = 24) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x06\x00\x00\x00"


class FakeInteractions:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response):
        self.interactions = FakeInteractions(response)


def make_request(operation: MediaOperation = MediaOperation.GENERATE) -> NormalizedMediaRequest:
    env = ToolEnvironment("google-fixed", "fixed", ("google:gemini-3.1-flash-image",))
    return NormalizedMediaRequest(
        backend="google:gemini-3.1-flash-image",
        prompt="Create a simple blue square",
        operation=operation,
        aspect_ratio="16:9",
        quality_tier="standard",
        previous_artifact_id="artifact-1" if operation is MediaOperation.EDIT_PREVIOUS else None,
        environment=env,
    )


def fake_response(media: bytes | None = None, mime_type: str = "image/png"):
    image = None if media is None else SimpleNamespace(data=base64.b64encode(media).decode(), mime_type=mime_type)
    return SimpleNamespace(
        id="interaction-1",
        model="gemini-3.1-flash-image",
        output_image=image,
        usage_metadata=SimpleNamespace(prompt_token_count=10, candidates_token_count=20),
    )


def test_quality_tier_mapping() -> None:
    assert quality_tier_to_resolution("draft") == "0.5K"
    assert quality_tier_to_resolution("standard") == "1K"
    assert quality_tier_to_resolution("high") == "2K"
    with pytest.raises(ValueError):
        quality_tier_to_resolution("ultra")


def test_generation_uses_neutral_image_response_format_without_tools() -> None:
    client = FakeClient(fake_response(png_bytes(64, 36)))
    result = GoogleImageProvider(client=client).execute(make_request())

    call = client.interactions.calls[0]
    assert call["model"] == "gemini-3.1-flash-image"
    assert call["input"] == "Create a simple blue square"
    assert call["response_format"] == {
        "type": "image",
        "mime_type": "image/png",
        "aspect_ratio": "16:9",
        "image_size": "1K",
    }
    assert "tools" not in call
    assert (result.width, result.height) == (64, 36)
    assert result.raw_response["output_image"]["data"] == "[MEDIA_BYTES_STORED_SEPARATELY]"


def test_edit_includes_previous_image_but_no_grounding_tools() -> None:
    client = FakeClient(fake_response(png_bytes()))
    previous = png_bytes(20, 20)
    GoogleImageProvider(client=client).execute(make_request(MediaOperation.EDIT_PREVIOUS), previous_media=previous)

    call = client.interactions.calls[0]
    assert "tools" not in call
    assert call["input"][0] == {"type": "text", "text": "Create a simple blue square"}
    assert call["input"][1]["type"] == "image"
    assert call["input"][1]["mime_type"] == "image/png"
    assert base64.b64decode(call["input"][1]["data"]) == previous


def test_edit_requires_previous_media() -> None:
    client = FakeClient(fake_response(png_bytes()))
    with pytest.raises(ValueError, match="previous_media"):
        GoogleImageProvider(client=client).execute(make_request(MediaOperation.EDIT_PREVIOUS))
    assert client.interactions.calls == []


def test_missing_image_is_typed_provider_failure() -> None:
    client = FakeClient(fake_response(None))
    with pytest.raises(GoogleProviderExecutionError, match="image data"):
        GoogleImageProvider(client=client).execute(make_request())


def test_wrong_backend_is_rejected_before_call() -> None:
    env = ToolEnvironment("other", "fixed", ("openai:gpt-image-2",))
    request = NormalizedMediaRequest(
        backend="openai:gpt-image-2",
        prompt="x",
        operation=MediaOperation.GENERATE,
        aspect_ratio="1:1",
        quality_tier="draft",
        previous_artifact_id=None,
        environment=env,
    )
    client = FakeClient(fake_response(png_bytes()))
    with pytest.raises(ValueError, match="cannot execute backend"):
        GoogleImageProvider(client=client).execute(request)
    assert client.interactions.calls == []
