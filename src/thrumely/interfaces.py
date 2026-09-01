from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .schema import NormalizedMediaRequest


def _require_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


@dataclass(frozen=True)
class ProviderMediaResult:
    media_bytes: bytes
    mime_type: str
    width: int
    height: int
    provider: str
    model: str
    raw_request: Mapping[str, Any]
    raw_response: Mapping[str, Any]
    request_id: str | None
    latency_seconds: float | None
    cost_usd: float | None
    moderation_status: str | None
    retry_count: int = 0
    usage: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.media_bytes:
            raise ValueError("media_bytes must be non-empty")
        _require_text("mime_type", self.mime_type)
        _require_text("provider", self.provider)
        _require_text("model", self.model)
        if self.width <= 0 or self.height <= 0:
            raise ValueError("media dimensions must be positive")
        if self.latency_seconds is not None and self.latency_seconds < 0:
            raise ValueError("latency_seconds must be >= 0")
        if self.cost_usd is not None and self.cost_usd < 0:
            raise ValueError("cost_usd must be >= 0")
        if self.retry_count < 0:
            raise ValueError("retry_count must be >= 0")


@dataclass(frozen=True)
class ControllerDecision:
    action: str
    request: NormalizedMediaRequest | None
    response_id: str | None
    actual_model: str | None
    usage: Mapping[str, Any] = field(default_factory=dict)
    observable_output: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.action not in {"media", "finish"}:
            raise ValueError("action must be 'media' or 'finish'")
        if self.action == "media" and self.request is None:
            raise ValueError("media action requires request")
        if self.action == "finish" and self.request is not None:
            raise ValueError("finish action must not include request")
