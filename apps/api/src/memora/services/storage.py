"""Content-addressed blob storage.

Files live at ``<blob_root>/<user_id>/<sha256>``. Three properties follow from that
layout, and all three are deliberate.

**The path comes from a hash, never from a filename.** An uploaded filename is data:
it is displayed, and it is never joined onto a path. There is no traversal to defend
against because user input never reaches the path at all.

**The database stores a hash, not a path.** Deriving the path from three values the
server already trusts means there is no filesystem path in a row for later code to join,
and moving the blob root is a config change rather than a data migration.

**Two users never share a blob.** The user id is a path component, so byte-identical
files from different owners land in different directories. A shared blob would be a
cross-user inference channel: user B uploads a file, sees it deduplicate, and has learned
that user A holds it.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from memora.config import get_settings
from memora.paths import repo_root

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")

THUMBNAIL_SUFFIX = ".thumb.jpg"
# 320px longest edge: enough to recognise a document in a result grid, small enough
# that a grid of them is a few hundred kilobytes.
THUMBNAIL_EDGE = 320


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class StoredBlob:
    content_hash: str
    byte_size: int
    deduplicated: bool


class BlobStore:
    def __init__(self, root: Path | None = None) -> None:
        # Resolved against the repo root, not the working directory. A relative
        # blob_root plus a command run from apps/api put personal documents in
        # apps/api/data/blobs, outside the ignore rule that expected them at the
        # top level. Where files land must not depend on where you were standing.
        if root is not None:
            self._root = Path(root)
        else:
            configured = Path(get_settings().blob_root)
            # Anchored to the repo root, never to the working directory, and never
            # "whichever happens to exist" - resolve() prefers a cwd-relative match,
            # which is how a second blob tree appeared under apps/api in the first
            # place. Where documents land must be one deterministic location.
            self._root = configured if configured.is_absolute() else repo_root() / configured

    def _user_dir(self, user_id: UUID) -> Path:
        if not isinstance(user_id, UUID):
            raise TypeError(f"user_id must be a UUID, got {type(user_id).__name__}")
        return self._root / str(user_id)

    def path(self, user_id: UUID, content_hash: str) -> Path:
        """The only way a blob path is ever produced."""
        if not _HASH_RE.match(content_hash):
            # Belt and braces: hashes come from sha256_of, but a validated path
            # component cannot be talked into containing a separator.
            raise ValueError("content_hash must be 64 lowercase hex characters")
        return self._user_dir(user_id) / content_hash

    def thumbnail_path(self, user_id: UUID, content_hash: str) -> Path:
        return self.path(user_id, content_hash).with_name(content_hash + THUMBNAIL_SUFFIX)

    def put(self, user_id: UUID, data: bytes) -> StoredBlob:
        content_hash = sha256_of(data)
        target = self.path(user_id, content_hash)
        if target.exists():
            return StoredBlob(content_hash, target.stat().st_size, deduplicated=True)

        target.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temporary name and rename, so a crash mid-write cannot leave a
        # truncated file sitting at the address of its own hash.
        staging = target.with_name(content_hash + ".partial")
        staging.write_bytes(data)
        staging.replace(target)
        return StoredBlob(content_hash, len(data), deduplicated=False)

    def read(self, user_id: UUID, content_hash: str) -> bytes:
        return self.path(user_id, content_hash).read_bytes()

    def exists(self, user_id: UUID, content_hash: str) -> bool:
        return self.path(user_id, content_hash).exists()

    def put_thumbnail(self, user_id: UUID, content_hash: str, data: bytes) -> None:
        target = self.thumbnail_path(user_id, content_hash)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def delete(self, user_id: UUID, content_hash: str) -> None:
        """Remove the blob and its thumbnail. Missing files are not an error."""
        self.path(user_id, content_hash).unlink(missing_ok=True)
        self.thumbnail_path(user_id, content_hash).unlink(missing_ok=True)

    def purge_user(self, user_id: UUID) -> None:
        """Account deletion. PRODUCT.md requires this to be demonstrable."""
        shutil.rmtree(self._user_dir(user_id), ignore_errors=True)


def make_thumbnail(data: bytes, mime_type: str) -> bytes | None:
    """A 320px JPEG preview, or None when the source cannot be previewed.

    Generated at ingest rather than on request. The result grid is the product's face -
    the user recognises the document by looking at it - so paying N renders on first
    paint of every search is the wrong latency in the wrong place. Ingest already pays
    for OCR, which dwarfs a resize.
    """
    import io

    from PIL import Image

    try:
        if mime_type == "application/pdf":
            import pymupdf

            with pymupdf.open(stream=data, filetype="pdf") as doc:
                if not len(doc):
                    return None
                data = doc[0].get_pixmap(dpi=72).tobytes("png")

        with Image.open(io.BytesIO(data)) as img:
            img = img.convert("RGB")
            img.thumbnail((THUMBNAIL_EDGE, THUMBNAIL_EDGE))
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=80)
            return buffer.getvalue()
    except Exception:  # noqa: BLE001 - a missing preview must not fail an upload
        return None


def build_blob_store() -> BlobStore:
    return BlobStore()
