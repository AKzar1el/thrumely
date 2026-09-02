from __future__ import annotations

import base64
import time
from typing import Any, Mapping

from .interfaces import ProviderMediaResult
from .schema import MediaOperation, NormalizedMediaRequest
from .vercel_gateway import GatewayRoutingError, extract_provider_metadata, validate_gateway_routing

_MODEL = "gpt-image-2-2026-04-21"
_SIZE_BY_ASPECT = {
    "1:1": "1024x1024",
    "3:2": "1536x1024",
    "2:3": "1024x1536",
    "16:9": "1536x864",
    "9:16": "864x1536",
}
_QUALITY_BY_TIER = {
    "draft": "low",
    "standard": "medium",
    "high": "high",
}


def aspect_ratio_to_size(aspect_ratio: str) -> str:
    try:
        return _SIZE_BY_ASPECT[aspect_ratio]
    except KeyError as exc:
        raise ValueError(f"unsupported normalized aspect ratio: {aspect_ratio}") from exc


def quality_tier_to_openai(quality_tier: str) -> str:
    try:
        return _QUALITY_BY_TIER[quality_tier]
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
    data = primitive.get("data")
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "b64_json" in item:
                item["b64_json"] = "[MEDIA_BYTES_STORED_SEPARATELY]"
    return primitive


def _usage_dict(result: Any) -> Mapping[str, Any]:
    usage = getattr(result, "usage", None)
    primitive = _primitive(usage)
    return primitive if isinstance(primitive, dict) else {}


def _edit_media_descriptor(media_bytes: bytes) -> tuple[str, str]:
    if media_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "previous.png", "image/png"
    if media_bytes.startswith(b"\xff\xd8\xff"):
        return "previous.jpg", "image/jpeg"
    if len(media_bytes) >= 12 and media_bytes[:4] == b"RIFF" and media_bytes[8:12] == b"WEBP":
        return "previous.webp", "image/webp"
    raise ValueError("unsupported previous_media image format: expected PNG, JPEG, or WebP")


def _png_dimensions(media_bytes: bytes) -> tuple[int, int]:
    if len(media_bytes) < 24 or media_bytes[:8] != b"\x89PNG\r\n\x1a\n" or media_bytes[12:16] != b"IHDR":
        raise ProviderExecutionError("OpenAI image response was not a valid PNG artifact")
    width = int.from_bytes(media_bytes[16:20], "big")
    height = int.from_bytes(media_bytes[20:24], "big")
    if width <= 0 or height <= 0:
        raise ProviderExecutionError("OpenAI image response contained invalid PNG dimensions")
    return width, height


class ProviderExecutionError(RuntimeError):
    pass


class OpenAIImageProvider:
    provider = "openai"
    backend_id = "openai:gpt-image-2"

    def __init__(
        self,
        model: str = _MODEL,
        client: Any | None = None,
        *,
        request_extra_body: Mapping[str, Any] | None = None,
        required_gateway_provider: str | None = None,
    ) -> None:
        self.model = model
        self.request_extra_body = request_extra_body
        self.required_gateway_provider = required_gateway_provider
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError("OpenAI live adapter requires the 'openai' optional dependency") from exc
            client = OpenAI(max_retries=0)
        self.client = client

    def execute(
        self,
        request: NormalizedMediaRequest,
        previous_media: bytes | None = None,
    ) -> ProviderMediaResult:
        if not request.backend.startswith("openai:"):
            raise ValueError(f"OpenAI provider cannot execute backend {request.backend!r}")

        size = aspect_ratio_to_size(request.aspect_ratio)
        quality = quality_tier_to_openai(request.quality_tier)
        raw_request: dict[str, Any] = {
            "model": self.model,
            "prompt": request.prompt,
            "size": size,
            "quality": quality,
            "output_format": "png",
            "operation": request.operation.value,
        }
        if self.request_extra_body is not None:
            raw_request["transport_options"] = _primitive(self.request_extra_body)

        common_kwargs: dict[str, Any] = {
            "model": self.model,
            "prompt": request.prompt,
            "size": size,
            "quality": quality,
            "output_format": "png",
        }
        if self.request_extra_body is not None:
            common_kwargs["extra_body"] = self.request_extra_body

        started = time.perf_counter()
        try:
            if request.operation is MediaOperation.GENERATE:
                result = self.client.images.generate(**common_kwargs)
            else:
                if previous_media is None:
                    raise ValueError("edit_previous requires previous_media bytes")
                filename, mime_type = _edit_media_descriptor(previous_media)
                raw_request["previous_media_mime_type"] = mime_type
                result = self.client.images.edit(
                    image=(filename, previous_media, mime_type),
                    **common_kwargs,
                )
        except ValueError:
            raise
        except Exception as exc:
            raise ProviderExecutionError(f"OpenAI image request failed ({type(exc).__name__})") from exc
        latency = time.perf_counter() - started

        provider_metadata = extract_provider_metadata(result)
        if self.required_gateway_provider is not None:
            try:
                validate_gateway_routing(
                    provider_metadata,
                    required_provider=self.required_gateway_provider,
                )
            except GatewayRoutingError as exc:
                raise ProviderExecutionError("OpenAI image Gateway routing contract failed") from exc

        data = getattr(result, "data", None) or []
        if not data or not getattr(data[0], "b64_json", None):
            raise ProviderExecutionError("OpenAI image response did not contain base64 media data")
        try:
            media_bytes = base64.b64decode(data[0].b64_json, validate=True)
        except ValueError as exc:
            raise ProviderExecutionError("OpenAI image response media decode failed") from exc
        width, height = _png_dimensions(media_bytes)
        request_id = getattr(result, "_request_id", None) or getattr(result, "id", None)
        actual_model = getattr(result, "model", None) or self.model

        return ProviderMediaResult(
            media_bytes=media_bytes,
            mime_type="image/png",
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
