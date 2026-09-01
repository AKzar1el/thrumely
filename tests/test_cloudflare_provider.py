from __future__ import annotations

import base64

import pytest

from thrumely.cloudflare_provider import (
    CloudflareImageProvider,
    CloudflareProviderExecutionError,
    quality_tier_to_dimensions,
)
from thrumely.schema import MediaOperation, NormalizedMediaRequest, ToolEnvironment


def png_bytes(width: int = 64, height: int = 48) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
    )


class FakeTransport:
    def __init__(self, response=None, *, error: Exception | None = None) -> None:
        self.response = response or {
            "success": True,
            "result": {"image": base64.b64encode(png_bytes(1024, 1024)).decode("ascii")},
            "errors": [],
            "messages": [],
        }
        self.error = error
        self.calls = []

    def post_multipart(self, url, headers, fields, files):
        self.calls.append((url, dict(headers), dict(fields), dict(files)))
        if self.error is not None:
            raise self.error
        return self.response


def make_request(
    operation: MediaOperation = MediaOperation.GENERATE,
    *,
    aspect_ratio: str = "1:1",
    quality_tier: str = "standard",
) -> NormalizedMediaRequest:
    env = ToolEnvironment(
        "cloudflare-fixed",
        "fixed",
        ("cloudflare:flux-2-klein-4b",),
    )
    return NormalizedMediaRequest(
        backend="cloudflare:flux-2-klein-4b",
        prompt="Create a simple blue square",
        operation=operation,
        aspect_ratio=aspect_ratio,
        quality_tier=quality_tier,
        previous_artifact_id="artifact-1" if operation is MediaOperation.EDIT_PREVIOUS else None,
        environment=env,
    )


def test_quality_mapping_stays_within_cloudflare_model_limits() -> None:
    assert quality_tier_to_dimensions("1:1", "draft") == (512, 512)
    assert quality_tier_to_dimensions("1:1", "standard") == (1024, 1024)
    assert quality_tier_to_dimensions("1:1", "high") == (1536, 1536)
    assert quality_tier_to_dimensions("16:9", "standard") == (1344, 768)
    assert quality_tier_to_dimensions("9:16", "standard") == (768, 1344)
    with pytest.raises(ValueError):
        quality_tier_to_dimensions("4:3", "standard")
    with pytest.raises(ValueError):
        quality_tier_to_dimensions("1:1", "ultra")


def test_generation_uses_one_multipart_request_and_redacts_media() -> None:
    response = {
        "success": True,
        "result": {
            "image": base64.b64encode(png_bytes(1024, 1024)).decode("ascii"),
            "seed": 42,
        },
        "errors": [],
        "messages": [],
    }
    transport = FakeTransport(response)
    provider = CloudflareImageProvider(
        account_id="account-test",
        api_token="secret-token",
        transport=transport,
    )

    result = provider.execute(make_request())

    assert len(transport.calls) == 1
    url, headers, fields, files = transport.calls[0]
    assert url.endswith("/accounts/account-test/ai/run/@cf/black-forest-labs/flux-2-klein-4b")
    assert headers["Authorization"] == "Bearer secret-token"
    assert fields == {
        "prompt": "Create a simple blue square",
        "width": "1024",
        "height": "1024",
    }
    assert files == {}
    assert result.provider == "cloudflare"
    assert result.model == "@cf/black-forest-labs/flux-2-klein-4b"
    assert result.retry_count == 0
    assert (result.width, result.height) == (1024, 1024)
    assert "Authorization" not in result.raw_request
    assert result.raw_response["result"]["image"] == "[MEDIA_BYTES_STORED_SEPARATELY]"
    assert "secret-token" not in str(result.raw_request)
    assert "secret-token" not in str(result.raw_response)


def test_edit_sends_previous_image_as_binary_multipart_file() -> None:
    response = {
        "success": True,
        "result": {"image": base64.b64encode(png_bytes(1024, 1024)).decode("ascii")},
        "errors": [],
        "messages": [],
    }
    transport = FakeTransport(response)
    provider = CloudflareImageProvider(
        account_id="account-test",
        api_token="secret-token",
        transport=transport,
    )
    previous = png_bytes(480, 480)

    provider.execute(make_request(MediaOperation.EDIT_PREVIOUS), previous_media=previous)

    _, _, fields, files = transport.calls[0]
    assert fields["prompt"] == "Create a simple blue square"
    assert files == {"input_image_0": ("previous.png", previous, "image/png")}


def test_large_edit_input_uses_injected_resizer_before_transport() -> None:
    response = {
        "success": True,
        "result": {"image": base64.b64encode(png_bytes(1024, 1024)).decode("ascii")},
        "errors": [],
        "messages": [],
    }
    transport = FakeTransport(response)
    resized = png_bytes(480, 480)
    seen = []

    def resizer(data: bytes) -> tuple[bytes, str]:
        seen.append(data)
        return resized, "image/png"

    provider = CloudflareImageProvider(
        account_id="account-test",
        api_token="secret-token",
        transport=transport,
        edit_resizer=resizer,
    )
    previous = png_bytes(1024, 1024)

    provider.execute(make_request(MediaOperation.EDIT_PREVIOUS), previous_media=previous)

    assert seen == [previous]
    assert transport.calls[0][3]["input_image_0"] == ("previous.png", resized, "image/png")


def test_edit_requires_previous_media_before_network() -> None:
    transport = FakeTransport()
    provider = CloudflareImageProvider(account_id="a", api_token="t", transport=transport)
    with pytest.raises(ValueError, match="previous_media"):
        provider.execute(make_request(MediaOperation.EDIT_PREVIOUS))
    assert transport.calls == []


def test_unsuccessful_cloudflare_envelope_is_typed_failure_without_error_echo() -> None:
    transport = FakeTransport(
        {
            "success": False,
            "result": None,
            "errors": [{"code": 10000, "message": "Bearer do-not-persist-this"}],
            "messages": [],
        }
    )
    provider = CloudflareImageProvider(account_id="a", api_token="t", transport=transport)
    with pytest.raises(CloudflareProviderExecutionError, match="unsuccessful response") as caught:
        provider.execute(make_request())
    assert "do-not-persist-this" not in str(caught.value)


def test_wrong_backend_is_rejected_before_network() -> None:
    env = ToolEnvironment("other", "fixed", ("openai:gpt-image-2",))
    request = NormalizedMediaRequest(
        backend="openai:gpt-image-2",
        prompt="x",
        operation=MediaOperation.GENERATE,
        aspect_ratio="1:1",
        quality_tier="standard",
        previous_artifact_id=None,
        environment=env,
    )
    transport = FakeTransport()
    provider = CloudflareImageProvider(account_id="a", api_token="t", transport=transport)
    with pytest.raises(ValueError, match="cannot execute backend"):
        provider.execute(request)
    assert transport.calls == []
