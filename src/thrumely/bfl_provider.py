from __future__ import annotations

import base64
import json
import os
import time
from typing import Any, Mapping
from urllib.request import Request, urlopen

from .interfaces import ProviderMediaResult
from .schema import MediaOperation, NormalizedMediaRequest

_MODEL = "flux-2-pro"
_BASE_URL = "https://api.bfl.ai/v1"
_DIMENSIONS = {
    "draft": {
        "1:1": (704, 704),
        "3:2": (864, 576),
        "2:3": (576, 864),
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
        "1:1": (1408, 1408),
        "3:2": (1728, 1152),
        "2:3": (1152, 1728),
        "16:9": (1792, 1024),
        "9:16": (1024, 1792),
    },
}


class BFLProviderExecutionError(RuntimeError):
    pass


def quality_tier_to_dimensions(aspect_ratio: str, quality_tier: str) -> tuple[int, int]:
    try:
        return _DIMENSIONS[quality_tier][aspect_ratio]
    except KeyError as exc:
        if quality_tier not in _DIMENSIONS:
            raise ValueError(f"unsupported normalized quality tier: {quality_tier}") from exc
        raise ValueError(f"unsupported normalized aspect ratio: {aspect_ratio}") from exc


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
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(media_bytes):
            break
        segment_length = int.from_bytes(media_bytes[index:index + 2], "big")
        if segment_length < 2 or index + segment_length > len(media_bytes):
            break
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF} and segment_length >= 7:
            height = int.from_bytes(media_bytes[index + 3:index + 5], "big")
            width = int.from_bytes(media_bytes[index + 5:index + 7], "big")
            if width > 0 and height > 0:
                return width, height
        index += segment_length
    return None


def _media_dimensions(media_bytes: bytes) -> tuple[int, int]:
    dimensions = _png_dimensions(media_bytes) or _jpeg_dimensions(media_bytes)
    if dimensions is None:
        raise BFLProviderExecutionError("BFL delivery response was not a valid PNG/JPEG artifact")
    return dimensions


def _redact_final_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    cleaned = dict(payload)
    result = cleaned.get("result")
    if isinstance(result, Mapping):
        result_copy = dict(result)
        if "sample" in result_copy:
            result_copy["sample"] = "[EPHEMERAL_DELIVERY_URL]"
        cleaned["result"] = result_copy
    return cleaned


class _UrllibTransport:
    def post_json(self, url: str, headers: Mapping[str, str], json: Mapping[str, Any]) -> Mapping[str, Any]:
        body = __import__("json").dumps(json).encode("utf-8")
        request = Request(url, data=body, headers=dict(headers), method="POST")
        with urlopen(request, timeout=120) as response:
            return __import__("json").loads(response.read().decode("utf-8"))

    def get_json(self, url: str, headers: Mapping[str, str]) -> Mapping[str, Any]:
        request = Request(url, headers=dict(headers), method="GET")
        with urlopen(request, timeout=120) as response:
            return __import__("json").loads(response.read().decode("utf-8"))

    def get_bytes(self, url: str) -> bytes:
        request = Request(url, method="GET")
        with urlopen(request, timeout=120) as response:
            return response.read()


class BFLImageProvider:
    provider = "bfl"
    backend_id = "bfl:flux-2-pro"

    def __init__(
        self,
        model: str = _MODEL,
        transport: Any | None = None,
        base_url: str = _BASE_URL,
        api_key: str | None = None,
        max_polls: int = 120,
        poll_interval: float = 0.5,
    ) -> None:
        self.model = model.strip("/")
        self.base_url = base_url.rstrip("/")
        self.transport = transport or _UrllibTransport()
        self.api_key = api_key if api_key is not None else os.environ.get("BFL_API_KEY")
        self.max_polls = max_polls
        self.poll_interval = poll_interval
        if self.max_polls < 1:
            raise ValueError("max_polls must be >= 1")
        if self.poll_interval < 0:
            raise ValueError("poll_interval must be >= 0")
        if not self.api_key:
            raise RuntimeError("BFL live adapter requires BFL_API_KEY")

    def execute(
        self,
        request: NormalizedMediaRequest,
        previous_media: bytes | None = None,
    ) -> ProviderMediaResult:
        if not request.backend.startswith("bfl:"):
            raise ValueError(f"BFL provider cannot execute backend {request.backend!r}")
        if request.operation is MediaOperation.EDIT_PREVIOUS and previous_media is None:
            raise ValueError("edit_previous requires previous_media bytes")

        width, height = quality_tier_to_dimensions(request.aspect_ratio, request.quality_tier)
        payload: dict[str, Any] = {
            "prompt": request.prompt,
            "width": width,
            "height": height,
            "output_format": "png",
        }
        if request.operation is MediaOperation.EDIT_PREVIOUS:
            payload["input_image"] = base64.b64encode(previous_media or b"").decode("ascii")

        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "x-key": self.api_key,
        }
        endpoint = f"{self.base_url}/{self.model}"
        raw_request = {
            "model": self.model,
            "endpoint": endpoint,
            "prompt": request.prompt,
            "width": width,
            "height": height,
            "output_format": "png",
            "operation": request.operation.value,
        }
        if request.operation is MediaOperation.EDIT_PREVIOUS:
            raw_request["input_image"] = "[MEDIA_BYTES_STORED_SEPARATELY]"

        started = time.perf_counter()
        try:
            submitted = self.transport.post_json(endpoint, headers, payload)
        except Exception as exc:
            raise BFLProviderExecutionError(f"BFL submit request failed ({type(exc).__name__})") from exc

        request_id = submitted.get("id") if isinstance(submitted, Mapping) else None
        polling_url = submitted.get("polling_url") if isinstance(submitted, Mapping) else None
        if not request_id or not polling_url:
            raise BFLProviderExecutionError("BFL submit response missing id or polling_url")

        final: Mapping[str, Any] | None = None
        for _ in range(self.max_polls):
            if self.poll_interval:
                time.sleep(self.poll_interval)
            try:
                polled = self.transport.get_json(str(polling_url), headers)
            except Exception as exc:
                raise BFLProviderExecutionError(f"BFL poll request failed ({type(exc).__name__})") from exc
            status = str(polled.get("status", "")) if isinstance(polled, Mapping) else ""
            if status == "Ready":
                final = polled
                break
            if status in {"Error", "Failed"}:
                raise BFLProviderExecutionError(f"BFL generation ended with terminal status {status}")
        if final is None:
            raise BFLProviderExecutionError("BFL generation exceeded poll limit")

        result_block = final.get("result") if isinstance(final, Mapping) else None
        sample_url = result_block.get("sample") if isinstance(result_block, Mapping) else None
        if not sample_url:
            raise BFLProviderExecutionError("BFL ready response missing delivery sample URL")
        try:
            media_bytes = self.transport.get_bytes(str(sample_url))
        except Exception as exc:
            raise BFLProviderExecutionError(f"BFL media download failed ({type(exc).__name__})") from exc
        width_actual, height_actual = _media_dimensions(media_bytes)
        latency = time.perf_counter() - started

        credits = submitted.get("cost") if isinstance(submitted, Mapping) else None
        cost_usd = float(credits) * 0.01 if isinstance(credits, (int, float)) else None
        usage = {
            key: submitted[key]
            for key in ("cost", "input_mp", "output_mp")
            if isinstance(submitted, Mapping) and key in submitted
        }

        return ProviderMediaResult(
            media_bytes=media_bytes,
            mime_type="image/png",
            width=width_actual,
            height=height_actual,
            provider=self.provider,
            model=self.model,
            raw_request=raw_request,
            raw_response={
                "submit": dict(submitted) if isinstance(submitted, Mapping) else {},
                "final": _redact_final_payload(final),
                "polling_url": str(polling_url),
            },
            request_id=str(request_id),
            latency_seconds=latency,
            cost_usd=cost_usd,
            moderation_status=None,
            retry_count=0,
            usage=usage,
        )
