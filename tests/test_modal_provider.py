from __future__ import annotations

import base64
import io
import json
from urllib.error import HTTPError

import pytest

from thrumely.modal_provider import (
    BACKEND_ID,
    MODEL_ID,
    MODEL_REVISION,
    ModalImageProvider,
    ModalProviderExecutionError,
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
            "image_base64": base64.b64encode(png_bytes(1024, 1024)).decode("ascii"),
            "mime_type": "image/png",
            "width": 1024,
            "height": 1024,
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "seed": 0,
            "steps": 4,
            "guidance_scale": 1.0,
            "inference_seconds": 1.25,
        }
        self.error = error
        self.calls = []

    def post_json(self, url, headers, payload):
        self.calls.append((url, dict(headers), json.loads(json.dumps(payload))))
        if self.error is not None:
            raise self.error
        return self.response


def make_request(
    operation: MediaOperation = MediaOperation.GENERATE,
    *,
    aspect_ratio: str = "1:1",
    quality_tier: str = "standard",
) -> NormalizedMediaRequest:
    env = ToolEnvironment("modal-reference", "fixed", (BACKEND_ID,))
    return NormalizedMediaRequest(
        backend=BACKEND_ID,
        prompt="Create a simple blue square",
        operation=operation,
        aspect_ratio=aspect_ratio,
        quality_tier=quality_tier,
        previous_artifact_id="artifact-1" if operation is MediaOperation.EDIT_PREVIOUS else None,
        environment=env,
    )


def test_quality_mapping_matches_reference_pixel_budget() -> None:
    assert quality_tier_to_dimensions("1:1", "standard") == (1024, 1024)
    assert quality_tier_to_dimensions("16:9", "draft") == (896, 512)
    assert quality_tier_to_dimensions("2:3", "high") == (1152, 1728)
    with pytest.raises(ValueError):
        quality_tier_to_dimensions("4:3", "standard")
    with pytest.raises(ValueError):
        quality_tier_to_dimensions("1:1", "ultra")


def test_generation_uses_one_authenticated_json_request_and_redacts_evidence() -> None:
    transport = FakeTransport()
    provider = ModalImageProvider(
        endpoint_url="https://example.modal.run/infer",
        proxy_key="wk-secret",
        proxy_secret="ws-secret",
        transport=transport,
    )

    result = provider.execute(make_request(), seed=0)

    assert len(transport.calls) == 1
    url, headers, payload = transport.calls[0]
    assert url == "https://example.modal.run/infer"
    assert headers == {"Modal-Key": "wk-secret", "Modal-Secret": "ws-secret"}
    assert payload == {
        "prompt": "Create a simple blue square",
        "operation": "generate",
        "width": 1024,
        "height": 1024,
        "seed": 0,
        "previous_image_base64": None,
    }
    assert result.provider == "modal-reference"
    assert result.model == MODEL_ID
    assert result.retry_count == 0
    assert (result.width, result.height) == (1024, 1024)
    assert result.usage["model_revision"] == MODEL_REVISION
    assert result.usage["seed"] == 0
    assert result.raw_response["image_base64"] == "[MEDIA_BYTES_STORED_SEPARATELY]"
    serialized = json.dumps({"request": result.raw_request, "response": result.raw_response})
    assert "wk-secret" not in serialized
    assert "ws-secret" not in serialized
    assert result.raw_request["endpoint"] == "[MODAL_PROXY_AUTHENTICATED_ENDPOINT]"


def test_edit_sends_only_exact_previous_image_and_requires_bytes() -> None:
    transport = FakeTransport()
    provider = ModalImageProvider(
        endpoint_url="https://example.modal.run/infer",
        proxy_key="wk-a",
        proxy_secret="ws-b",
        transport=transport,
    )
    previous = png_bytes(480, 480)

    provider.execute(make_request(MediaOperation.EDIT_PREVIOUS), previous_media=previous, seed=7)

    payload = transport.calls[0][2]
    assert payload["operation"] == "edit_previous"
    assert payload["seed"] == 7
    assert base64.b64decode(payload["previous_image_base64"]) == previous

    second = FakeTransport()
    provider2 = ModalImageProvider(
        endpoint_url="https://example.modal.run/infer",
        proxy_key="wk-a",
        proxy_secret="ws-b",
        transport=second,
    )
    with pytest.raises(ValueError, match="previous_media"):
        provider2.execute(make_request(MediaOperation.EDIT_PREVIOUS), seed=7)
    assert second.calls == []


def test_model_revision_mismatch_is_rejected() -> None:
    response = FakeTransport().response.copy()
    response["model_revision"] = "unexpected"
    provider = ModalImageProvider(
        endpoint_url="https://example.modal.run/infer",
        proxy_key="wk-a",
        proxy_secret="ws-b",
        transport=FakeTransport(response),
    )
    with pytest.raises(ModalProviderExecutionError, match="revision"):
        provider.execute(make_request(), seed=0)


def test_http_error_reports_only_safe_status_code_and_retry_after() -> None:
    body = io.BytesIO(
        json.dumps(
            {"error": {"code": "INVALID_INPUT", "message": "secret upstream detail must not leak"}}
        ).encode("utf-8")
    )
    error = HTTPError(
        "https://workspace.modal.run/infer",
        400,
        "provider detail must not leak",
        {"Retry-After": "9"},
        body,
    )
    provider = ModalImageProvider(
        endpoint_url="https://example.modal.run/infer",
        proxy_key="wk-secret",
        proxy_secret="ws-secret",
        transport=FakeTransport(error=error),
    )

    with pytest.raises(ModalProviderExecutionError) as caught:
        provider.execute(make_request(), seed=0)

    message = str(caught.value)
    assert message == "Modal reference request failed (HTTP 400, code INVALID_INPUT, retry-after 9s)"
    assert "secret upstream" not in message
    assert "provider detail" not in message
    assert "wk-secret" not in message
    assert "ws-secret" not in message


def test_wrong_backend_and_invalid_seed_fail_before_network() -> None:
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
    provider = ModalImageProvider(
        endpoint_url="https://example.modal.run/infer",
        proxy_key="wk-a",
        proxy_secret="ws-b",
        transport=transport,
    )
    with pytest.raises(ValueError, match="cannot execute backend"):
        provider.execute(request, seed=0)
    with pytest.raises(ValueError, match="seed"):
        provider.execute(make_request(), seed=-1)
    assert transport.calls == []
