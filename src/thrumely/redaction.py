from __future__ import annotations

import re
from typing import Any, Mapping

_SECRET_KEY = re.compile(
    r"(?:api_?key|authorization|access_?token|refresh_?token|secret|password)",
    re.IGNORECASE,
)
_PRIVATE_KEYS = {"reasoning", "encrypted_content"}
_PRIVATE_BLOCK_TYPES = {"reasoning", "redacted_reasoning"}


def redact_secrets(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: "[REDACTED]" if _SECRET_KEY.search(str(key)) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_secrets(item) for item in value]
    return value


def strip_private_reasoning(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: strip_private_reasoning(item)
            for key, item in value.items()
            if key not in _PRIVATE_KEYS
        }
    if isinstance(value, (list, tuple)):
        output = []
        for item in value:
            if isinstance(item, Mapping) and str(item.get("type", "")).lower() in _PRIVATE_BLOCK_TYPES:
                continue
            output.append(strip_private_reasoning(item))
        return output
    return value


def sanitize_public_payload(value: Any) -> Any:
    return redact_secrets(strip_private_reasoning(value))
