from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pytest

from thrumely.hashing import content_hash, sha256_bytes, sha256_file
from thrumely.serialization import canonical_json_bytes, to_primitive


class ExampleEnum(str, Enum):
    VALUE = "value"


@dataclass(frozen=True)
class ExampleRecord:
    name: str
    kind: ExampleEnum


def test_mapping_order_does_not_change_content_hash() -> None:
    assert content_hash({"b": 2, "a": 1}) == content_hash({"a": 1, "b": 2})


def test_sha256_file_matches_bytes(tmp_path: Path) -> None:
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"thrumely")
    assert sha256_file(path) == sha256_bytes(b"thrumely")


def test_canonical_json_handles_dataclasses_enums_tuples_and_paths() -> None:
    value = {
        "record": ExampleRecord("x", ExampleEnum.VALUE),
        "items": (1, 2),
        "path": Path("a/b"),
    }
    assert to_primitive(value) == {
        "record": {"name": "x", "kind": "value"},
        "items": [1, 2],
        "path": "a/b",
    }
    assert canonical_json_bytes(value).decode("utf-8") == '{"items":[1,2],"path":"a/b","record":{"kind":"value","name":"x"}}'


def test_unsupported_values_raise_type_error() -> None:
    with pytest.raises(TypeError, match="Unsupported"):
        canonical_json_bytes(object())
