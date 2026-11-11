"""Reading a linked folder: a collection the person keeps with their own tools.

A linked folder (ADR linked-knowledge-folders-are-read-only-and-machine-local)
is any folder on this disk, an Obsidian vault say, that Coffer only **shares**
with the agents. Coffer never writes into it, keeps no history of it and
checks nothing in it: the folder has its own layout and its own rules, read the
same way as a collection Coffer keeps (``collection_settings``), and the agents
follow those. So this module only reads, and it has its
own path guard because the folder lies outside the knowledge root that
``paths`` guards.

Paths a surface sees are still name-led, ``<collection>/<path inside the
folder>``, so the tree and file routes address a linked folder the way they
address any collection. File names in a person's own folder are whatever their
tools wrote, so the guard here refuses only what could escape the folder or
reach a hidden entry, not every character ``paths`` refuses.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
from datetime import UTC, datetime

from coffer.domain.knowledge.entry import (
    ACTOR_USER,
    CatalogueLevel,
    CollectionEntry,
    DirectoryEntry,
    FileEntry,
    KnowledgeFile,
)
from coffer.domain.knowledge.errors import (
    KnowledgeFileNotFound,
    LinkedFolderRefused,
    UnsafeKnowledgePath,
)
from coffer.infrastructure.knowledge import collection_settings
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter
from coffer.infrastructure.vault.home import coffer_home

#: Folders no knowledge lives in, skipped on every walk besides hidden ones.
_SKIPPED_DIRS = frozenset({"node_modules", "__pycache__"})

#: A walk stops after this many Markdown files: a folder this large is a
#: different design (the knowledge spec's own assumption is hundreds of files).
MAX_WALKED_FILES = 5000

#: A file larger than this is described but not read into the page: a linked
#: folder can hold attachments of any size.
MAX_READ_BYTES = 2_000_000

_MARKDOWN = ".md"


def check_folder(folder: str) -> pathlib.Path:
    """The folder to link, refused when it cannot be one.

    Coffer's own home is refused, and so is any folder holding it, the home
    directory or the disk root: the vault already holds Coffer's knowledge,
    and a walk of the whole home would read everything on it.
    """
    path = pathlib.Path(folder).expanduser()
    if not path.is_absolute():
        raise LinkedFolderRefused(folder, "not an absolute path")
    if not path.is_dir():
        raise LinkedFolderRefused(folder, "no such folder")
    resolved = path.resolve()
    home = coffer_home().resolve()
    if resolved.is_relative_to(home) or home.is_relative_to(resolved):
        raise LinkedFolderRefused(folder, "Coffer's own folder, or a folder holding it")
    return path


def _segments(relpath: str) -> list[str]:
    cleaned = (relpath or "").strip().strip("/")
    segments = [s for s in cleaned.split("/") if s]
    for segment in segments:
        if segment.startswith(".") or "\\" in segment or "\x00" in segment:
            raise UnsafeKnowledgePath(relpath, "hidden or unsafe entry")
    return segments


def resolve(folder: str, relpath: str) -> pathlib.Path:
    """An absolute path inside ``folder`` for a folder-relative path, refused
    when a segment is hidden or the result resolves outside the folder (a
    symlink pointing out of it, for one)."""
    base = pathlib.Path(folder)
    candidate = base.joinpath(*_segments(relpath))
    if not candidate.resolve().is_relative_to(base.resolve()):
        raise UnsafeKnowledgePath(relpath, "escapes the linked folder")
    return candidate


def rules_file(folder: str) -> str:
    """The folder's own rules file: what its README declares as ``rules``,
    else the first of ``collection_settings.RULES_FILES`` at its root; empty when none."""
    return collection_settings.read(pathlib.Path(folder)).rules


def _title(path: pathlib.Path) -> str:
    """A note's title: its frontmatter ``title``, else its first ``#``
    heading, else its file name without ``.md``."""
    return collection_settings.head_title(path)[0]


def _walk(folder: str) -> tuple[list[pathlib.Path], float]:
    """Every Markdown file under ``folder`` in path order, up to
    :data:`MAX_WALKED_FILES`, and the newest one's write time."""
    found: list[pathlib.Path] = []
    newest = 0.0
    for root, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(
            d for d in dirnames if not d.startswith(".") and d not in _SKIPPED_DIRS
        )
        for name in sorted(filenames):
            if name.startswith(".") or not name.endswith(_MARKDOWN):
                continue
            path = pathlib.Path(root) / name
            found.append(path)
            with contextlib.suppress(OSError):
                newest = max(newest, path.stat().st_mtime)
            if len(found) >= MAX_WALKED_FILES:
                return found, newest
    return found, newest


def _relative(name: str, folder: str, path: pathlib.Path) -> str:
    return f"{name}/{path.relative_to(folder).as_posix()}"


def _file_entry(name: str, folder: str, path: pathlib.Path) -> FileEntry:
    markdown = path.name.endswith(_MARKDOWN)
    return FileEntry(
        path=_relative(name, folder, path),
        title=_title(path) if markdown else path.name,
        description="",
        actor=ACTOR_USER,
        updated_at="",
    )


def walk_files(name: str, folder: str) -> tuple[FileEntry, ...]:
    """Every Markdown file of the linked folder, each with its title."""
    if not pathlib.Path(folder).is_dir():
        return ()
    found, _ = _walk(folder)
    return tuple(_file_entry(name, folder, path) for path in found)


def collection_entry(uid: str, name: str, folder: str) -> CollectionEntry:
    """The linked folder as the collection list shows it. A folder that has
    gone missing lists with no files rather than failing the whole list."""
    present = pathlib.Path(folder).is_dir()
    found, newest = _walk(folder) if present else ([], 0.0)
    settings = collection_settings.read(pathlib.Path(folder)) if present else None
    return CollectionEntry(
        uid=uid,
        name=name,
        description=collection_settings.description(pathlib.Path(folder)) if present else "",
        folder_path=folder,
        updated_at=datetime.fromtimestamp(newest, tz=UTC).isoformat() if newest else None,
        linked=True,
        note_count=len(found),
        rules_file=settings.rules if settings else "",
        entry_file=settings.entry if settings else "",
    )


def _count(directory: pathlib.Path) -> int:
    total = 0
    for _root, dirnames, filenames in os.walk(directory):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in _SKIPPED_DIRS]
        total += sum(1 for f in filenames if not f.startswith("."))
    return total


def list_level(name: str, folder: str, relpath: str) -> CatalogueLevel:
    """One level of the linked folder: its visible children and nothing deeper.
    ``relpath`` is name-led, like every tree path."""
    inner = relpath.strip("/").split("/", 1)[1] if "/" in relpath.strip("/") else ""
    directory = resolve(folder, inner)
    if not directory.is_dir():
        raise KnowledgeFileNotFound(relpath)
    directories: list[DirectoryEntry] = []
    files: list[FileEntry] = []
    for child in sorted(directory.iterdir(), key=lambda c: c.name.lower()):
        if child.name.startswith("."):
            continue
        if child.is_dir():
            if child.name in _SKIPPED_DIRS:
                continue
            directories.append(
                DirectoryEntry(
                    path=_relative(name, folder, child),
                    name=child.name,
                    file_count=_count(child),
                )
            )
        elif child.is_file():
            files.append(_file_entry(name, folder, child))
    return CatalogueLevel(
        path=relpath.strip("/"), directories=tuple(directories), files=tuple(files)
    )


def read_file(name: str, folder: str, relpath: str) -> KnowledgeFile:
    """One file of the linked folder with its absolute paths, read as it is:
    nothing is checked in it, so it carries no resolved links."""
    inner = relpath.strip("/").split("/", 1)[1] if "/" in relpath.strip("/") else ""
    if not inner:
        raise KnowledgeFileNotFound(relpath)
    path = resolve(folder, inner)
    if not path.is_file():
        raise KnowledgeFileNotFound(relpath)
    large = path.stat().st_size > MAX_READ_BYTES
    text = "" if large else path.read_bytes().decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    fm, body = split_frontmatter(text)
    return KnowledgeFile(
        path=_relative(name, folder, path),
        title=_title(path) if path.name.endswith(_MARKDOWN) else path.name,
        description=str(fm.get("description") or ""),
        actor=ACTOR_USER,
        created_at="",
        updated_at=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(),
        body=body,
        file_path=str(path),
        folder_path=str(path.parent),
    )
