from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


def to_primitive(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return to_primitive(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_primitive(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    raise TypeError(f"Unsupported value for canonical serialization: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    primitive = to_primitive(value)
    return json.dumps(
        primitive,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
