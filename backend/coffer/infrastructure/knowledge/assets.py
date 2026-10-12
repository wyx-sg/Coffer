"""The pictures an uploaded source keeps, under its collection's ``assets/``
(ADR knowledge-sources-keep-their-images-and-originals-stay-on-this-mac; spec
knowledge "Keep the pictures of an upload beside its source").

Each upload gets a folder of its own, ``assets/<title-slug>-<hash>/``, named
before the source is written so the Markdown can link its pictures with a
plain relative path (``../assets/<folder>/image-1.png``) that any Markdown
reader, an agent's included, follows. The pictures are ordinary files of the
collection: they sync with the vault and keep their history like the Markdown.
"""

from __future__ import annotations

import os
import pathlib
import re

from coffer.domain.knowledge.converter import ConvertedImage
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

_LINK = re.compile(r"\]\((image-\d+\.[a-z]+)\)")


def folder_for(title: str, digest: str) -> str:
    """The folder one upload's pictures go in: readable, and unique per file."""
    return f"{slugify(title)[:60].strip('-') or 'upload'}-{digest[:8]}"


def link_pictures(markdown: str, folder: str, images: tuple[ConvertedImage, ...]) -> str:
    """``markdown`` with each kept picture's bare name pointed at where it is
    kept, relative to the source under ``sources/``."""
    names = {image.name for image in images}

    def _point(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in names:
            return match.group(0)
        return f"](../{paths.ASSETS_DIR_NAME}/{folder}/{name})"

    return _LINK.sub(_point, markdown)


def picture_paths(
    collection: str, folder: str, images: tuple[ConvertedImage, ...]
) -> dict[str, bytes]:
    """Each picture by its knowledge-root-relative path."""
    base = f"{collection}/{paths.ASSETS_DIR_NAME}/{folder}"
    return {f"{base}/{image.name}": image.data for image in images}


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
    "folder_for",
    "image_type",
    "link_pictures",
    "picture_at",
    "picture_paths",
    "read_picture",
    "write_bytes",
]
