from pathlib import Path

import pytest

from thrumely.artifacts import ArtifactStore
from thrumely.hashing import sha256_file
from thrumely.schema import MediaStage


def test_identical_media_is_content_addressed_once(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    first = store.put_media(
        b"<svg>same</svg>",
        mime_type="image/svg+xml",
        width=1024,
        height=1024,
        stage=MediaStage.FIRST,
    )
    second = store.put_media(
        b"<svg>same</svg>",
        mime_type="image/svg+xml",
        width=1024,
        height=1024,
        stage=MediaStage.FINAL,
    )
    assert first.artifact_id == second.artifact_id
    assert first.relative_path == second.relative_path
    path = tmp_path / first.relative_path
    assert path.exists()
    assert sha256_file(path) == first.sha256
    assert len(list((tmp_path / "media").iterdir())) == 1


def test_different_media_gets_different_artifact_ids(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    first = store.put_media(b"a", mime_type="image/png", width=1, height=1, stage=MediaStage.FINAL)
    second = store.put_media(b"b", mime_type="image/png", width=1, height=1, stage=MediaStage.FINAL)
    assert first.artifact_id != second.artifact_id


def test_unsupported_mime_type_is_rejected(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    with pytest.raises(ValueError, match="Unsupported MIME"):
        store.put_media(b"x", mime_type="image/gif", width=1, height=1, stage=MediaStage.FINAL)
