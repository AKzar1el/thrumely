from __future__ import annotations

import base64
import io
import json
import os
import time
import uuid
from typing import Any, Callable, Mapping
from urllib.request import Request, urlopen

from .interfaces import ProviderExecutionError, ProviderMediaResult
from .schema import MediaOperation, NormalizedMediaRequest

_MODEL = "@cf/black-forest-labs/flux-2-klein-4b"
_BACKEND_ID = "cloudflare:flux-2-klein-4b"
_BASE_URL = "https://api.cloudflare.com/client/v4"
_EDIT_MAX_DIMENSION = 480

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


class CloudflareProviderExecutionError(ProviderExecutionError):
    pass


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


def _media_info(media_bytes: bytes) -> tuple[int, int, str, str]:
    dimensions = _png_dimensions(media_bytes)
    if dimensions is not None:
        return dimensions[0], dimensions[1], "image/png", "png"
    dimensions = _jpeg_dimensions(media_bytes)
    if dimensions is not None:
        return dimensions[0], dimensions[1], "image/jpeg", "jpg"
    raise CloudflareProviderExecutionError(
        "Cloudflare image response did not contain valid PNG/JPEG image data"
    )


def _redact_response(payload: Mapping[str, Any]) -> dict[str, Any]:
    output = json.loads(json.dumps(payload))
    result = output.get("result")
    if isinstance(result, dict) and "image" in result:
        result["image"] = "[MEDIA_BYTES_STORED_SEPARATELY]"
    return output


def _pillow_resize_for_edit(media_bytes: bytes) -> tuple[bytes, str]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise CloudflareProviderExecutionError(
            "Cloudflare edit of images >=512px requires `pip install -e '.[cloudflare]'`"
        ) from exc

    try:
        with Image.open(io.BytesIO(media_bytes)) as image:
            image.load()
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGB")
            image.thumbnail((_EDIT_MAX_DIMENSION, _EDIT_MAX_DIMENSION), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            return buffer.getvalue(), "image/png"
    except Exception as exc:
        raise CloudflareProviderExecutionError(
            f"Cloudflare edit image resize failed ({type(exc).__name__})"
        ) from exc


class _UrllibTransport:
    def post_multipart(
        self,
        url: str,
        headers: Mapping[str, str],
        fields: Mapping[str, str],
        files: Mapping[str, tuple[str, bytes, str]],
    ) -> Mapping[str, Any]:
        boundary = f"----thrumely-{uuid.uuid4().hex}"
        body = bytearray()

        for name, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode("ascii"))
            body.extend(
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8")
            )
            body.extend(str(value).encode("utf-8"))
            body.extend(b"\r\n")

        for name, (filename, data, mime_type) in files.items():
            body.extend(f"--{boundary}\r\n".encode("ascii"))
            body.extend(
                (
                    f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                    f"Content-Type: {mime_type}\r\n\r\n"
                ).encode("utf-8")
            )
            body.extend(data)
            body.extend(b"\r\n")

        body.extend(f"--{boundary}--\r\n".encode("ascii"))
        request_headers = dict(headers)
        request_headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        request_headers["Accept"] = "application/json"
        request = Request(url, data=bytes(body), headers=request_headers, method="POST")
        with urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))


class CloudflareImageProvider:
    provider = "cloudflare"
    backend_id = _BACKEND_ID

    def __init__(
        self,
        model: str = _MODEL,
        *,
        account_id: str | None = None,
        api_token: str | None = None,
        transport: Any | None = None,
        base_url: str = _BASE_URL,
        edit_resizer: Callable[[bytes], tuple[bytes, str]] | None = None,
    ) -> None:
        self.model = model
        self.account_id = account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        self.api_token = api_token or os.environ.get("CLOUDFLARE_API_TOKEN")
        self.base_url = base_url.rstrip("/")
        self.transport = transport or _UrllibTransport()
        self.edit_resizer = edit_resizer or _pillow_resize_for_edit
        if not self.account_id:
            raise RuntimeError("Cloudflare live adapter requires CLOUDFLARE_ACCOUNT_ID")
        if not self.api_token:
            raise RuntimeError("Cloudflare live adapter requires CLOUDFLARE_API_TOKEN")

    def _prepare_previous(self, previous_media: bytes) -> tuple[bytes, str, str]:
        try:
            width, height, mime_type, extension = _media_info(previous_media)
        except CloudflareProviderExecutionError:
            resized, mime_type = self.edit_resizer(previous_media)
            _, _, _, extension = _media_info(resized)
            return resized, mime_type, extension

        if width < 512 and height < 512:
            return previous_media, mime_type, extension

        resized, resized_mime = self.edit_resizer(previous_media)
        resized_width, resized_height, _, extension = _media_info(resized)
        if resized_width >= 512 or resized_height >= 512:
            raise CloudflareProviderExecutionError(
                "Cloudflare edit resizer must produce an image smaller than 512x512"
            )
        return resized, resized_mime, extension

    def execute(
        self,
        request: NormalizedMediaRequest,
        previous_media: bytes | None = None,
    ) -> ProviderMediaResult:
        if not request.backend.startswith("cloudflare:"):
            raise ValueError(f"Cloudflare provider cannot execute backend {request.backend!r}")
        if request.operation is MediaOperation.EDIT_PREVIOUS and previous_media is None:
            raise ValueError("edit_previous requires previous_media bytes")

        width, height = quality_tier_to_dimensions(request.aspect_ratio, request.quality_tier)
        fields = {
            "prompt": request.prompt,
            "width": str(width),
            "height": str(height),
        }
        files: dict[str, tuple[str, bytes, str]] = {}
        if request.operation is MediaOperation.EDIT_PREVIOUS:
            assert previous_media is not None
            prepared, mime_type, extension = self._prepare_previous(previous_media)
            files["input_image_0"] = (f"previous.{extension}", prepared, mime_type)

        endpoint = (
            f"{self.base_url}/accounts/{self.account_id}/ai/run/{self.model}"
        )
        headers = {"Authorization": f"Bearer {self.api_token}"}
        raw_request: dict[str, Any] = {
            "model": self.model,
            "endpoint": endpoint,
            "prompt": request.prompt,
            "width": width,
            "height": height,
            "quality_tier": request.quality_tier,
            "operation": request.operation.value,
        }
        if files:
            raw_request["input_image_0"] = "[MEDIA_BYTES_STORED_SEPARATELY]"

        started = time.perf_counter()
        try:
            response = self.transport.post_multipart(endpoint, headers, fields, files)
        except Exception as exc:
            raise CloudflareProviderExecutionError(
                f"Cloudflare image request failed ({type(exc).__name__})"
            ) from exc
        latency = time.perf_counter() - started

        if not isinstance(response, Mapping) or response.get("success") is not True:
            raise CloudflareProviderExecutionError("Cloudflare image API returned unsuccessful response")
        result = response.get("result")
        if not isinstance(result, Mapping):
            raise CloudflareProviderExecutionError("Cloudflare image API response missing result object")
        encoded = result.get("image")
        if not isinstance(encoded, str) or not encoded:
            raise CloudflareProviderExecutionError("Cloudflare image API response missing image data")
        try:
            media_bytes = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise CloudflareProviderExecutionError("Cloudflare image response media decode failed") from exc

        actual_width, actual_height, mime_type, _ = _media_info(media_bytes)
        request_id = result.get("id") or response.get("request_id")
        usage = result.get("usage") if isinstance(result.get("usage"), Mapping) else {}

        return ProviderMediaResult(
            media_bytes=media_bytes,
            mime_type=mime_type,
            width=actual_width,
            height=actual_height,
            provider=self.provider,
            model=self.model,
            raw_request=raw_request,
            raw_response=_redact_response(response),
            request_id=str(request_id) if request_id else None,
            latency_seconds=latency,
            cost_usd=None,
            moderation_status=None,
            retry_count=0,
            usage=dict(usage),
        )
