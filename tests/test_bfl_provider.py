from __future__ import annotations

import base64

import pytest

from thrumely.bfl_provider import (
    BFLImageProvider,
    BFLProviderExecutionError,
    quality_tier_to_dimensions,
)
from thrumely.schema import MediaOperation, NormalizedMediaRequest, ToolEnvironment


def png_bytes(width: int = 64, height: int = 48) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x06\x00\x00\x00"


class FakeTransport:
    def __init__(self, polls, media=None):
        self.polls = list(polls)
        self.media = media or png_bytes()
        self.post_calls = []
        self.get_json_calls = []
        self.get_bytes_calls = []

    def post_json(self, url, headers, json):
        self.post_calls.append((url, headers, json))
        return {
            "id": "req-1",
            "polling_url": "https://api.bfl.ai/v1/get_result?id=req-1",
            "cost": 4.5,
            "input_mp": 0.0,
            "output_mp": 1.0,
        }

    def get_json(self, url, headers):
        self.get_json_calls.append((url, headers))
        return self.polls.pop(0)

    def get_bytes(self, url):
        self.get_bytes_calls.append(url)
        return self.media


def make_request(operation: MediaOperation = MediaOperation.GENERATE, quality="standard") -> NormalizedMediaRequest:
    env = ToolEnvironment("bfl-fixed", "fixed", ("bfl:flux-2-pro",))
    return NormalizedMediaRequest(
        backend="bfl:flux-2-pro",
        prompt="Create a clean product photo",
        operation=operation,
        aspect_ratio="16:9",
        quality_tier=quality,
        previous_artifact_id="artifact-1" if operation is MediaOperation.EDIT_PREVIOUS else None,
        environment=env,
    )


def test_quality_tier_dimensions_are_supported_and_multiple_of_16() -> None:
    for tier in ("draft", "standard", "high"):
        width, height = quality_tier_to_dimensions("16:9", tier)
        assert width % 16 == 0 and height % 16 == 0
        assert width > height
    with pytest.raises(ValueError):
        quality_tier_to_dimensions("4:3", "standard")


def test_submit_poll_download_flow_uses_fixed_flux2_pro_endpoint() -> None:
    transport = FakeTransport([
        {"status": "Pending"},
        {"status": "Ready", "result": {"sample": "https://delivery.eu.bfl.ai/signed.png"}},
    ], media=png_bytes(80, 45))
    result = BFLImageProvider(transport=transport, api_key="test-key", poll_interval=0).execute(make_request())

    url, headers, payload = transport.post_calls[0]
    assert url == "https://api.bfl.ai/v1/flux-2-pro"
    assert headers["x-key"] == "test-key"
    assert payload["prompt"] == "Create a clean product photo"
    assert payload["output_format"] == "png"
    assert "input_image" not in payload
    assert (payload["width"], payload["height"]) == quality_tier_to_dimensions("16:9", "standard")
    assert (result.width, result.height) == (80, 45)
    assert result.request_id == "req-1"
    assert result.cost_usd == pytest.approx(0.045)
    assert result.raw_request.get("x-key") is None
    assert result.raw_response["final"]["result"]["sample"] == "[EPHEMERAL_DELIVERY_URL]"


def test_edit_sends_base64_input_image_without_secret_persistence() -> None:
    previous = png_bytes(20, 20)
    transport = FakeTransport([
        {"status": "Ready", "result": {"sample": "https://delivery.us.bfl.ai/x.png"}},
    ])
    BFLImageProvider(transport=transport, api_key="secret", poll_interval=0).execute(
        make_request(MediaOperation.EDIT_PREVIOUS), previous_media=previous
    )
    payload = transport.post_calls[0][2]
    assert base64.b64decode(payload["input_image"]) == previous
    assert "secret" not in repr(payload)


@pytest.mark.parametrize(
    "status",
    ["Error", "Failed", "Request Moderated", "Content Moderated", "Task not found"],
)
def test_documented_terminal_provider_statuses_fail_immediately(status: str) -> None:
    transport = FakeTransport([{"status": status, "error": "provider terminal state"}])
    with pytest.raises(BFLProviderExecutionError, match=f"terminal status {status}"):
        BFLImageProvider(transport=transport, api_key="x", max_polls=3, poll_interval=0).execute(make_request())
    assert len(transport.get_json_calls) == 1


def test_polling_is_bounded() -> None:
    transport = FakeTransport([{"status": "Pending"}] * 3)
    with pytest.raises(BFLProviderExecutionError, match="poll limit"):
        BFLImageProvider(transport=transport, api_key="x", max_polls=2, poll_interval=0).execute(make_request())
    assert len(transport.get_json_calls) == 2


def test_edit_requires_previous_media_before_submit() -> None:
    transport = FakeTransport([])
    with pytest.raises(ValueError, match="previous_media"):
        BFLImageProvider(transport=transport, api_key="x", poll_interval=0).execute(make_request(MediaOperation.EDIT_PREVIOUS))
    assert transport.post_calls == []
