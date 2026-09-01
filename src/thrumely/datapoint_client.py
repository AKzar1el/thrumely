from __future__ import annotations

import json
import mimetypes
import re
import secrets
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Mapping

from .redaction import sanitize_public_payload

BASE_URL = "https://api.trydatapoint.com/data-labelling/v1"
MAX_MEDIA_BYTES = 20_971_520
USER_AGENT = "Thrumely/0.1 (+https://github.com/AKzar1el/thrumely)"
Transport = Callable[[str, str, Mapping[str, str], bytes | None, str | None], tuple[int, bytes]]
_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class DatapointClientError(RuntimeError):
    pass


def _urllib_transport(method: str, url: str, headers: Mapping[str, str], body: bytes | None, content_type: str | None) -> tuple[int, bytes]:
    request_headers = dict(headers)
    if content_type:
        request_headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=body, method=method, headers=request_headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read()


def _safe_error_message(api_key: str, exc: BaseException) -> str:
    return str(exc).replace(api_key, "[REDACTED]")[:500]


def _safe_payload_text(api_key: str, value: object) -> str:
    return str(sanitize_public_payload(value)).replace(api_key, "[REDACTED]")[:1000]


def _job_id(value: str) -> str:
    if not isinstance(value, str) or not _JOB_ID_RE.fullmatch(value):
        raise ValueError("job_id must contain only letters, digits, underscores, or hyphens")
    return value


def _headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key, "Accept": "application/json", "User-Agent": USER_AGENT}


class DatapointClient:
    def __init__(self, api_key: str, *, transport: Transport | None = None, base_url: str = BASE_URL):
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key must be a non-empty string")
        normalized_base = base_url.rstrip("/")
        if normalized_base != BASE_URL:
            raise ValueError("base_url must be the official Datapoint API endpoint")
        self._api_key = api_key
        self._transport = transport or _urllib_transport
        self._base_url = normalized_base

    def _request_json(self, method: str, path: str, *, payload: Mapping[str, object] | None = None) -> dict[str, object]:
        body = None
        content_type = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            content_type = "application/json"
        headers = _headers(self._api_key)
        try:
            status, raw = self._transport(method, self._base_url + path, headers, body, content_type)
        except Exception as exc:
            raise DatapointClientError(f"Datapoint transport failed: {_safe_error_message(self._api_key, exc)}") from None
        try:
            decoded = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            decoded = {"error": "non-json response"}
        if not isinstance(decoded, dict):
            decoded = {"error": "unexpected response shape"}
        if not 200 <= status < 300:
            raise DatapointClientError(f"Datapoint HTTP {status}: {_safe_payload_text(self._api_key, decoded)}")
        return decoded

    def upload_media(self, path: str | Path) -> dict[str, object]:
        source = Path(path)
        if not source.is_file():
            raise ValueError("media path must be an existing file")
        if source.stat().st_size > MAX_MEDIA_BYTES:
            raise ValueError(f"media file exceeds Datapoint {MAX_MEDIA_BYTES}-byte limit")
        suffix = source.suffix.lower()
        allowed = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif", ".svg", ".heic", ".heif"}
        if suffix not in allowed:
            raise ValueError("upload_media currently supports Datapoint image formats only")
        if any(char in source.name for char in ("\r", "\n", '"', "\\")):
            raise ValueError("media filename contains header-unsafe characters")
        mime = mimetypes.types_map.get(suffix, "application/octet-stream")
        boundary = "thrumely-" + secrets.token_hex(12)
        body = b"".join([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="files"; filename="{source.name}"\r\n'.encode(),
            f"Content-Type: {mime}\r\n\r\n".encode(),
            source.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ])
        headers = _headers(self._api_key)
        try:
            status, raw = self._transport("POST", self._base_url + "/media", headers, body, f"multipart/form-data; boundary={boundary}")
        except Exception as exc:
            raise DatapointClientError(f"Datapoint transport failed: {_safe_error_message(self._api_key, exc)}") from None
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = {"error": "non-json response"}
        if not 200 <= status < 300:
            raise DatapointClientError(f"Datapoint HTTP {status}: {_safe_payload_text(self._api_key, payload)}")
        media = payload.get("media") if isinstance(payload, dict) else None
        if not isinstance(media, list) or len(media) != 1 or not isinstance(media[0], dict):
            raise DatapointClientError("Datapoint upload returned unexpected media envelope")
        if not isinstance(media[0].get("media_ref"), str) or not media[0]["media_ref"].startswith("dp://"):
            raise DatapointClientError("Datapoint upload response missing media_ref")
        return media[0]

    def create_sandbox_job(self, payload: Mapping[str, object]) -> dict[str, object]:
        if payload.get("serving_environment") != "sandbox":
            raise ValueError("Datapoint client refuses non-sandbox job creation")
        return self._request_json("POST", "/jobs", payload=payload)

    def get_job(self, job_id: str) -> dict[str, object]:
        safe_id = _job_id(job_id)
        return self._request_json("GET", f"/jobs/{safe_id}")

    def get_results(self, job_id: str, *, page: int = 1, per_page: int = 100) -> dict[str, object]:
        safe_id = _job_id(job_id)
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            raise ValueError("page must be an integer >= 1")
        if not isinstance(per_page, int) or isinstance(per_page, bool) or per_page < 1:
            raise ValueError("per_page must be an integer >= 1")
        return self._request_json("GET", f"/jobs/{safe_id}/results?page={page}&per_page={per_page}")

    def get_all_results(self, job_id: str, *, per_page: int = 1000) -> dict[str, object]:
        page = 1
        merged: dict[str, object] | None = None
        rows: list[object] = []
        while True:
            payload = self.get_results(job_id, page=page, per_page=per_page)
            current = payload.get("results")
            total = payload.get("total_results")
            if not isinstance(current, list):
                raise DatapointClientError("Datapoint results response missing results list")
            if not isinstance(total, int) or isinstance(total, bool) or total < 0:
                raise DatapointClientError("Datapoint results response missing total_results")
            if merged is None:
                merged = dict(payload)
            rows.extend(current)
            if len(rows) >= total:
                break
            if not current:
                raise DatapointClientError("Datapoint results pagination made no progress")
            page += 1
        assert merged is not None
        merged["page"] = 1
        merged["per_page"] = per_page
        merged["results"] = rows
        return merged

    def get_responses(self, job_id: str, *, page: int = 1, per_page: int = 100) -> dict[str, object]:
        safe_id = _job_id(job_id)
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            raise ValueError("page must be an integer >= 1")
        if not isinstance(per_page, int) or isinstance(per_page, bool) or not 1 <= per_page <= 1000:
            raise ValueError("per_page must be an integer in [1, 1000]")
        return self._request_json("GET", f"/jobs/{safe_id}/responses?page={page}&per_page={per_page}")

    def get_all_responses(self, job_id: str, *, per_page: int = 1000) -> dict[str, object]:
        page = 1
        merged: dict[str, object] | None = None
        rows: list[object] = []
        while True:
            payload = self.get_responses(job_id, page=page, per_page=per_page)
            current = payload.get("responses")
            total_pages = payload.get("total_pages")
            if not isinstance(current, list):
                raise DatapointClientError("Datapoint responses response missing responses list")
            if not isinstance(total_pages, int) or isinstance(total_pages, bool) or total_pages < 1:
                raise DatapointClientError("Datapoint responses response missing total_pages")
            if merged is None:
                merged = dict(payload)
            rows.extend(current)
            if page >= total_pages:
                break
            page += 1
        assert merged is not None
        merged["page"] = 1
        merged["per_page"] = per_page
        merged["responses"] = rows
        return merged
