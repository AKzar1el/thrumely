from __future__ import annotations

from pathlib import Path

from .hashing import sha256_bytes
from .schema import MediaArtifact, MediaStage

_MIME_EXTENSIONS = {
    "image/svg+xml": "svg",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.media_root = root / "media"
        self.media_root.mkdir(parents=True, exist_ok=True)

    def put_media(
        self,
        data: bytes,
        *,
        mime_type: str,
        width: int,
        height: int,
        stage: MediaStage,
    ) -> MediaArtifact:
        extension = _MIME_EXTENSIONS.get(mime_type)
        if extension is None:
            raise ValueError(f"Unsupported MIME type: {mime_type}")
        digest = sha256_bytes(data)
        relative = Path("media") / f"{digest}.{extension}"
        path = self.root / relative
        if not path.exists():
            path.write_bytes(data)
        return MediaArtifact(
            artifact_id=f"media:{digest}",
            sha256=digest,
            mime_type=mime_type,
            width=width,
            height=height,
            byte_length=len(data),
            stage=stage,
            relative_path=relative.as_posix(),
        )
