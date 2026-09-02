from __future__ import annotations

import base64
import time
from typing import Any, Mapping

from .interfaces import ProviderMediaResult
from .schema import MediaOperation, NormalizedMediaRequest

_MODEL = "gemini-3.1-flash-image"
_QUALITY_TO_RESOLUTION = {
    "draft": "512",
    "standard": "1K",
    "high": "2K",
}
_ALLOWED_ASPECTS = {"1:1", "3:2", "2:3", "16:9", "9:16"}


class GoogleProviderExecutionError(RuntimeError):
    pass


def quality_tier_to_resolution(quality_tier: str) -> str:
    try:
        return _QUALITY_TO_RESOLUTION[quality_tier]
    except KeyError as exc:
        raise ValueError(f"unsupported normalized quality tier: {quality_tier}") from exc


def _primitive(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_primitive(item) for item in value]
    if hasattr(value, "model_dump"):
        return _primitive(value.model_dump(mode="json", exclude_none=True))
    if hasattr(value, "__dict__"):
        return {
            str(key): _primitive(item)
            for key, item in vars(value).items()
            if not str(key).startswith("_")
        }
    return str(value)


def _redact_media_payload(payload: Any) -> Any:
    primitive = _primitive(payload)
    if not isinstance(primitive, dict):
        return primitive
    output_image = primitive.get("output_image")
    if isinstance(output_image, dict) and "data" in output_image:
        output_image["data"] = "[MEDIA_BYTES_STORED_SEPARATELY]"
    return primitive


def _usage_dict(result: Any) -> Mapping[str, Any]:
    usage = getattr(result, "usage_metadata", None) or getattr(result, "usage", None)
    primitive = _primitive(usage)
    return primitive if isinstance(primitive, dict) else {}


def _png_dimensions(media_bytes: bytes) -> tuple[int, int] | None:
    if len(media_bytes) >= 24 and media_bytes[:8] == b"\x89PNG\r\n\x1a\n" and media_bytes[12:16] == b"IHDR":
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
        segment_length = int.from_bytes(media_bytes[index:index + 2], "big")
        if segment_length < 2 or index + segment_length > len(media_bytes):
            break
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if segment_length >= 7:
                height = int.from_bytes(media_bytes[index + 3:index + 5], "big")
                width = int.from_bytes(media_bytes[index + 5:index + 7], "big")
                if width > 0 and height > 0:
                    return width, height
            break
        index += segment_length
    return None


def _input_image_mime_type(media_bytes: bytes) -> str:
    if _png_dimensions(media_bytes) is not None:
        return "image/png"
    if _jpeg_dimensions(media_bytes) is not None:
        return "image/jpeg"
    raise ValueError("previous_media must contain valid PNG or JPEG image data")


def _media_dimensions(media_bytes: bytes, mime_type: str) -> tuple[int, int]:
    dimensions = _png_dimensions(media_bytes)
    if dimensions is None and mime_type in {"image/jpeg", "image/jpg"}:
        dimensions = _jpeg_dimensions(media_bytes)
    if dimensions is None:
        raise GoogleProviderExecutionError("Google image response did not contain valid PNG/JPEG image data")
    return dimensions


class GoogleImageProvider:
    provider = "google"
    backend_id = "google:gemini-3.1-flash-image"

    def __init__(self, model: str = _MODEL, client: Any | None = None) -> None:
        self.model = model
        if client is None:
            try:
                from google import genai
                from google.genai import types
            except ImportError as exc:
                raise RuntimeError("Google live adapter requires the 'google' optional dependency") from exc
            client = genai.Client(
                http_options=types.HttpOptions(
                    retry_options=types.HttpRetryOptions(attempts=1),
                )
            )
        self.client = client

    def execute(
        self,
        request: NormalizedMediaRequest,
        previous_media: bytes | None = None,
    ) -> ProviderMediaResult:
        if not request.backend.startswith("google:"):
            raise ValueError(f"Google provider cannot execute backend {request.backend!r}")
        if request.aspect_ratio not in _ALLOWED_ASPECTS:
            raise ValueError(f"unsupported normalized aspect ratio: {request.aspect_ratio}")
        image_size = quality_tier_to_resolution(request.quality_tier)

        response_format = {
            "type": "image",
            "aspect_ratio": request.aspect_ratio,
            "image_size": image_size,
        }
        if request.operation is MediaOperation.GENERATE:
            interaction_input: Any = request.prompt
        else:
            if previous_media is None:
                raise ValueError("edit_previous requires previous_media bytes")
            previous_mime_type = _input_image_mime_type(previous_media)
            interaction_input = [
                {"type": "text", "text": request.prompt},
                {
                    "type": "image",
                    "data": base64.b64encode(previous_media).decode("ascii"),
                    "mime_type": previous_mime_type,
                },
            ]

        raw_request = {
            "model": self.model,
            "input": "[TEXT_AND_OPTIONAL_MEDIA]" if isinstance(interaction_input, list) else request.prompt,
            "response_format": response_format,
            "operation": request.operation.value,
        }

        started = time.perf_counter()
        try:
            result = self.client.interactions.create(
                model=self.model,
                input=interaction_input,
                response_format=response_format,
            )
        except Exception as exc:
            raise GoogleProviderExecutionError(f"Google image request failed ({type(exc).__name__})") from exc
        latency = time.perf_counter() - started

        output_image = getattr(result, "output_image", None)
        encoded = getattr(output_image, "data", None) if output_image is not None else None
        if not encoded:
            raise GoogleProviderExecutionError("Google image response did not contain image data")
        try:
            media_bytes = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise GoogleProviderExecutionError("Google image response media decode failed") from exc

        mime_type = str(getattr(output_image, "mime_type", None) or "image/png")
        width, height = _media_dimensions(media_bytes, mime_type)
        request_id = getattr(result, "id", None)
        actual_model = getattr(result, "model", None) or self.model

        return ProviderMediaResult(
            media_bytes=media_bytes,
            mime_type=mime_type,
            width=width,
            height=height,
            provider=self.provider,
            model=str(actual_model),
            raw_request=raw_request,
            raw_response=_redact_media_payload(result),
            request_id=str(request_id) if request_id else None,
            latency_seconds=latency,
            cost_usd=None,
            moderation_status=None,
            retry_count=0,
            usage=_usage_dict(result),
        )