from __future__ import annotations

import base64
import json
import os
import re
import time
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .interfaces import ProviderExecutionError, ProviderMediaResult
from .schema import MediaOperation, NormalizedMediaRequest

MODEL_ID = "black-forest-labs/FLUX.2-klein-4B"
MODEL_REVISION = "e7b7dc27f91deacad38e78976d1f2b499d76a294"
BACKEND_ID = "modal:flux-2-klein-4b-reference"
_PROVIDER_NAME = "modal-reference"
_EVIDENCE_ENDPOINT = "[MODAL_PROXY_AUTHENTICATED_ENDPOINT]"
_SAFE_ERROR_CODE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")

_DIMENSIONS = {
    "draft": {
        "1:1": (512, 512),
        "3:2": (768, 512),
        "2:3": (512, 768),
        "16:9": (896, 512),
        "9:16": (512, 896),
    },
    "standard": {
        "1:1": (1024, 1024),
        "3:2": (1248, 832),
        "2:3": (832, 1248),
        "16:9": (1344, 768),
        "9:16": (768, 1344),
    },
    "high": {
        "1:1": (1536, 1536),
        "3:2": (1728, 1152),
        "2:3": (1152, 1728),
        "16:9": (1792, 1024),
        "9:16": (1024, 1792),
    },
}


class ModalProviderExecutionError(ProviderExecutionError):
    """Typed, redaction-safe failure from the Modal reference backend."""


def quality_tier_to_dimensions(aspect_ratio: str, quality_tier: str) -> tuple[int, int]:
    try:
        return _DIMENSIONS[quality_tier][aspect_ratio]
    except KeyError as exc:
        if quality_tier not in _DIMENSIONS:
            raise ValueError(f"unsupported normalized quality tier: {quality_tier}") from exc
        raise ValueError(f"unsupported normalized aspect ratio: {aspect_ratio}") from exc


def _png_dimensions(media_bytes: bytes) -> tuple[int, int] | None:
    if (
        len(media_bytes) >= 24
        and media_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        and media_bytes[12:16] == b"IHDR"
    ):
        width = int.from_bytes(media_bytes[16:20], "big")
        height = int.from_bytes(media_bytes[20:24], "big")
        if width > 0 and height > 0:
            return width, height
    return None


def _jpeg_dimensions(media_bytes: bytes) -> tuple[int, int] | None:
    if len(media_bytes) < 4 or media_bytes[:2] != b"\xff\xd8":
        return None
    index = 2
    while index + 4 <= len(media_bytes):
        if media_bytes[index] != 0xFF:
            index += 1
            continue
        marker = media_bytes[index + 1]
        index += 2
        while marker == 0xFF and index < len(media_bytes):
            marker = media_bytes[index]
            index += 1
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(media_bytes):
            break
        segment_length = int.from_bytes(media_bytes[index : index + 2], "big")
        if segment_length < 2 or index + segment_length > len(media_bytes):
            break
        if marker in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            if segment_length >= 7:
                height = int.from_bytes(media_bytes[index + 3 : index + 5], "big")
                width = int.from_bytes(media_bytes[index + 5 : index + 7], "big")
                if width > 0 and height > 0:
                    return width, height
            break
        index += segment_length
    return None


def _media_info(media_bytes: bytes) -> tuple[int, int, str]:
    dimensions = _png_dimensions(media_bytes)
    if dimensions is not None:
        return dimensions[0], dimensions[1], "image/png"
    dimensions = _jpeg_dimensions(media_bytes)
    if dimensions is not None:
        return dimensions[0], dimensions[1], "image/jpeg"
    raise ModalProviderExecutionError(
        "Modal reference response did not contain valid PNG/JPEG image data"
    )


def _redact_response(payload: Mapping[str, Any]) -> dict[str, Any]:
    output = json.loads(json.dumps(payload))
    if "image_base64" in output:
        output["image_base64"] = "[MEDIA_BYTES_STORED_SEPARATELY]"
    return output


def _safe_error_code(payload: object) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    error = payload.get("error")
    if not isinstance(error, Mapping):
        return None
    code = error.get("code")
    if isinstance(code, bool) or code is None:
        return None
    text = str(code).strip()
    if _SAFE_ERROR_CODE.fullmatch(text):
        return text
    return None


def _http_error_summary(exc: HTTPError) -> str:
    parts = [f"HTTP {exc.code}"]
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        payload = None

    code = _safe_error_code(payload)
    if code is not None:
        parts.append(f"code {code}")

    retry_after = None
    if exc.headers is not None:
        retry_after = exc.headers.get("Retry-After")
    if retry_after is not None:
        retry_after_text = str(retry_after).strip()
        if retry_after_text.isdigit():
            parts.append(f"retry-after {int(retry_after_text)}s")
    return ", ".join(parts)


class _UrllibTransport:
    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        request_headers = dict(headers)
        request_headers["Content-Type"] = "application/json"
        request_headers["Accept"] = "application/json"
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=request_headers,
            method="POST",
        )
        with urlopen(request, timeout=300) as response:
            decoded = json.loads(response.read().decode("utf-8"))
        if not isinstance(decoded, Mapping):
            raise ModalProviderExecutionError("Modal reference response must be a JSON object")
        return decoded


class ModalImageProvider:
    provider = _PROVIDER_NAME
    backend_id = BACKEND_ID
    model = MODEL_ID

    def __init__(
        self,
        *,
        endpoint_url: str | None = None,
        proxy_key: str | None = None,
        proxy_secret: str | None = None,
        transport: Any | None = None,
    ) -> None:
        self.endpoint_url = endpoint_url or os.environ.get("THRUMELY_MODAL_ENDPOINT_URL")
        self.proxy_key = proxy_key or os.environ.get("THRUMELY_MODAL_PROXY_KEY")
        self.proxy_secret = proxy_secret or os.environ.get("THRUMELY_MODAL_PROXY_SECRET")
        self.transport = transport or _UrllibTransport()

        if not self.endpoint_url:
            raise RuntimeError("Modal reference adapter requires THRUMELY_MODAL_ENDPOINT_URL")
        if not self.proxy_key:
            raise RuntimeError("Modal reference adapter requires THRUMELY_MODAL_PROXY_KEY")
        if not self.proxy_secret:
            raise RuntimeError("Modal reference adapter requires THRUMELY_MODAL_PROXY_SECRET")

    def execute(
        self,
        request: NormalizedMediaRequest,
        previous_media: bytes | None = None,
        *,
        seed: int = 0,
    ) -> ProviderMediaResult:
        if request.backend != BACKEND_ID:
            raise ValueError(f"Modal provider cannot execute backend {request.backend!r}")
        if isinstance(seed, bool) or not isinstance(seed, int) or not (0 <= seed <= 2**32 - 1):
            raise ValueError("seed must be an integer in [0, 2^32-1]")
        if request.operation is MediaOperation.EDIT_PREVIOUS and previous_media is None:
            raise ValueError("edit_previous requires previous_media bytes")

        width, height = quality_tier_to_dimensions(request.aspect_ratio, request.quality_tier)
        previous_image_base64 = None
        if request.operation is MediaOperation.EDIT_PREVIOUS:
            assert previous_media is not None
            previous_image_base64 = base64.b64encode(previous_media).decode("ascii")

        payload = {
            "prompt": request.prompt,
            "operation": request.operation.value,
            "width": width,
            "height": height,
            "seed": seed,
            "previous_image_base64": previous_image_base64,
        }
        headers = {"Modal-Key": self.proxy_key, "Modal-Secret": self.proxy_secret}
        raw_request: dict[str, Any] = {
            "endpoint": _EVIDENCE_ENDPOINT,
            "backend": BACKEND_ID,
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "prompt": request.prompt,
            "operation": request.operation.value,
            "width": width,
            "height": height,
            "seed": seed,
            "previous_artifact_id": request.previous_artifact_id,
            "previous_image_base64": (
                "[MEDIA_BYTES_STORED_SEPARATELY]" if previous_image_base64 is not None else None
            ),
        }

        started = time.perf_counter()
        try:
            response = self.transport.post_json(self.endpoint_url, headers, payload)
        except HTTPError as exc:
            raise ModalProviderExecutionError(
                f"Modal reference request failed ({_http_error_summary(exc)})"
            ) from exc
        except ModalProviderExecutionError:
            raise
        except Exception as exc:
            raise ModalProviderExecutionError(
                f"Modal reference request failed ({type(exc).__name__})"
            ) from exc
        latency = time.perf_counter() - started

        if not isinstance(response, Mapping):
            raise ModalProviderExecutionError("Modal reference response must be a JSON object")
        actual_model = response.get("model_id")
        actual_revision = response.get("model_revision")
        if actual_model != MODEL_ID:
            raise ModalProviderExecutionError("Modal reference response model identity mismatch")
        if actual_revision != MODEL_REVISION:
            raise ModalProviderExecutionError("Modal reference response model revision mismatch")

        encoded = response.get("image_base64")
        if not isinstance(encoded, str) or not encoded:
            raise ModalProviderExecutionError("Modal reference response missing image data")
        try:
            media_bytes = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise ModalProviderExecutionError("Modal reference response media decode failed") from exc

        actual_width, actual_height, mime_type = _media_info(media_bytes)
        declared_width = response.get("width")
        declared_height = response.get("height")
        if declared_width != actual_width or declared_height != actual_height:
            raise ModalProviderExecutionError("Modal reference response dimension metadata mismatch")

        usage: dict[str, Any] = {
            "model_revision": MODEL_REVISION,
            "seed": seed,
        }
        for key in ("steps", "guidance_scale", "inference_seconds"):
            value = response.get(key)
            if value is not None:
                usage[key] = value

        request_id = response.get("request_id")
        return ProviderMediaResult(
            media_bytes=media_bytes,
            mime_type=mime_type,
            width=actual_width,
            height=actual_height,
            provider=self.provider,
            model=MODEL_ID,
            raw_request=raw_request,
            raw_response=_redact_response(response),
            request_id=str(request_id) if request_id else None,
            latency_seconds=latency,
            cost_usd=None,
            moderation_status=None,
            retry_count=0,
            usage=usage,
        )
