from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .serialization import canonical_json_bytes


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def content_hash(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))
