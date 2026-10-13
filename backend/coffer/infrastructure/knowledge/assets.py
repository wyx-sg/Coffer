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
from collections.abc import Mapping
from typing import Any

from coffer.domain.knowledge.converter import ASSET_LINK_PREFIX, ConvertedImage
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

#: A converter's placeholder for a file it hands over: ``coffer-asset:<name>``.
_ASSET_LINK = re.compile(re.escape(ASSET_LINK_PREFIX) + r"([^\s()<>\"'\[\]]+)")

#: How many suffixed folders are tried before an upload's files are refused.
_MAX_FOLDER_TRIES = 100


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


def link_assets(text: str, folder: str, names: frozenset[str]) -> str:
    """``text`` with each ``coffer-asset:<name>`` of a kept file pointed at
    where it is kept, relative to the source under ``sources/``. A name the
    upload did not keep is left as written."""

    def _point(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in names:
            return match.group(0)
        return f"../{paths.ASSETS_DIR_NAME}/{folder}/{name}"

    return _ASSET_LINK.sub(_point, text)


def link_values(value: Any, folder: str, names: frozenset[str]) -> Any:
    """:func:`link_assets` over every string inside ``value``, recursively —
    a source's frontmatter names its kept files the way its body does."""
    if isinstance(value, str):
        return link_assets(value, folder, names)
    if isinstance(value, Mapping):
        return {k: link_values(v, folder, names) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [link_values(v, folder, names) for v in value]
    return value


def _clashes(directory: pathlib.Path, kept: Mapping[str, bytes]) -> bool:
    """Whether ``directory`` holds any of ``kept``'s names with other bytes."""
    for name, data in kept.items():
        path = directory / name
        if path.is_symlink() or (path.exists() and not path.is_file()):
            return True
        if path.is_file() and path.read_bytes() != data:
            return True
    return False


def place(
    collection: str, folder: str, kept: Mapping[str, bytes], digest: str
) -> tuple[str, dict[str, bytes]]:
    """The folder an upload's files go in, and those still to write, by their
    knowledge-root-relative path.

    A folder already holding the same bytes under the same names is reused and
    nothing is written again; one holding other bytes is left alone and the
    upload's files go in ``<folder>-<sha8>`` (then ``-2``, ``-3`` …).
    """
    if not kept:
        return folder, {}
    base = paths.collection_dir(collection) / paths.ASSETS_DIR_NAME
    suffixed = f"{folder}-{digest[:8]}"
    candidates = [folder, suffixed] + [f"{suffixed}-{n}" for n in range(2, _MAX_FOLDER_TRIES)]
    for candidate in candidates:
        directory = base / candidate
        if not _clashes(directory, kept):
            prefix = f"{collection}/{paths.ASSETS_DIR_NAME}/{candidate}"
            fresh = {
                f"{prefix}/{name}": data
                for name, data in kept.items()
                if not (directory / name).is_file()
            }
            return candidate, fresh
    raise ValueError(f"cannot find a free assets folder for {folder!r}")


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
    "link_assets",
    "link_pictures",
    "link_values",
    "picture_at",
    "picture_paths",
    "place",
    "read_picture",
    "write_bytes",
]
