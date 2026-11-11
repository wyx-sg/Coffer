"""The pictures and attachments an upload keeps, in a folder of its own under
the uploads folder with the source beside them (ADR
knowledge-sources-keep-their-images-and-originals-stay-on-this-mac; spec
knowledge "Keep the pictures of an upload beside its source").

An upload that keeps files is a folder, ``<uploads>/<title-slug>/``, holding
its Markdown and every file it links by bare name (``image-1.png``) — a plain
relative path any Markdown reader, an agent's included, follows, and one that
stays right when the folder is moved or renamed as a whole. The files are
ordinary files of the collection: they sync with the vault and keep their
history like the Markdown.
"""

from __future__ import annotations

import os
import pathlib

from coffer.domain.knowledge.errors import KnowledgeFileNotFound
from coffer.infrastructure.knowledge import linked, paths
from coffer.infrastructure.knowledge.naming import slugify

#: What a picture's extension says it is, for the read route.
IMAGE_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "svg": "image/svg+xml",
}

#: The largest picture the read route hands back.
MAX_ASSET_BYTES = 10 * 1024 * 1024


def folder_for(title: str) -> str:
    """The name an upload's own folder wants: its title as a slug."""
    return slugify(title)[:60].strip("-") or "upload"


def bundle_paths(collection: str, folder: str, files: dict[str, bytes]) -> dict[str, bytes]:
    """Each kept file by its knowledge-root-relative path in the upload's folder."""
    base = f"{paths.relative_of(paths.uploads_dir(collection))}/{folder}"
    return {f"{base}/{name}": data for name, data in files.items()}


def write_bytes(relpath: str, data: bytes) -> None:
    """Write ``data`` at a knowledge-root-relative path, guarded like a
    document and through one rename."""
    path = paths.resolve(relpath)
    path.parent.mkdir(parents=True, exist_ok=True)
    paths.assert_inside_root(path, relpath)
    tmp = path.with_name(f".{path.name}.tmp")
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(tmp, flags, 0o644)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(path)


def image_type(name: str) -> str | None:
    """The media type of a picture by its name; ``None`` for anything else."""
    return IMAGE_TYPES.get(pathlib.PurePosixPath(name).suffix.lstrip(".").lower())


def read_picture(path: pathlib.Path, relpath: str) -> tuple[bytes, str]:
    """A picture's bytes and media type. Anything that is not a picture, is
    missing or is too large reads as not found."""
    media = image_type(path.name)
    if media is None or not path.is_file() or path.stat().st_size > MAX_ASSET_BYTES:
        raise KnowledgeFileNotFound(relpath)
    return path.read_bytes(), media


def picture_at(relpath: str, folder: str | None) -> tuple[bytes, str]:
    """The picture at a knowledge path — in a collection Coffer keeps, or in
    the linked ``folder`` the path's collection names — guarded like a read."""
    if folder is None:
        return read_picture(paths.resolve(relpath), relpath)
    inner = relpath.strip("/").split("/", 1)[1] if "/" in relpath.strip("/") else ""
    if not inner:
        raise KnowledgeFileNotFound(relpath)
    return read_picture(linked.resolve(folder, inner), relpath)


__all__ = [
    "IMAGE_TYPES",
    "MAX_ASSET_BYTES",
    "bundle_paths",
    "folder_for",
    "image_type",
    "picture_at",
    "read_picture",
    "write_bytes",
]
