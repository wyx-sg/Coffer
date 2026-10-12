"""The uploaded file itself, kept on the Mac it was uploaded from only (ADR
knowledge-sources-keep-their-images-and-originals-stay-on-this-mac; spec
knowledge "Keep an upload's original on this Mac only").

The source carries the Markdown and the pictures everywhere; the original is
for the person who wants to look at the PDF or slides as they were. It lives
under the machine-local root, never in the vault, named by its SHA-256 so the
same file uploaded twice is kept once. The source records the name and the
hash (``original``, ``original_sha256``), so another Mac knows an original
exists and says where it is. Nothing deletes an original when its source
goes: it is the person's own file, and a later restore of the source finds it
again.
"""

from __future__ import annotations

import hashlib
import os
import pathlib

from coffer.infrastructure.vault.home import local_root

#: Frontmatter keys Coffer writes on an uploaded source.
ORIGINAL_KEY = "original"
ORIGINAL_SHA_KEY = "original_sha256"

_HEX = frozenset("0123456789abcdef")


def originals_dir() -> pathlib.Path:
    """Where this Mac keeps uploaded files."""
    return local_root() / "knowledge-originals"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _suffix(filename: str) -> str:
    ext = pathlib.PurePosixPath(filename).suffix.lower()
    return ext if ext[1:].isalnum() and len(ext) <= 10 else ""


def _path(sha: str, filename: str) -> pathlib.Path | None:
    if len(sha) != 64 or not set(sha) <= _HEX:
        return None
    return originals_dir() / f"{sha}{_suffix(filename)}"


def keep(data: bytes, filename: str) -> str:
    """Keep ``data`` on this Mac; returns its SHA-256."""
    sha = digest(data)
    target = _path(sha, filename)
    assert target is not None
    if target.is_file():
        return sha
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    tmp.unlink(missing_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    tmp.replace(target)
    return sha


def local_copy(sha: str, filename: str) -> str | None:
    """The absolute path of the original on this Mac, when it is here."""
    path = _path(sha.strip().lower(), filename)
    return str(path) if path is not None and path.is_file() else None


__all__ = ["ORIGINAL_KEY", "ORIGINAL_SHA_KEY", "digest", "keep", "local_copy", "originals_dir"]
