"""Reading and writing the knowledge directory.

Every operation here is a filesystem operation and nothing else: no index is
updated, because there is none (spec knowledge FR-001). That is what lets a
human's edit in their own editor and an agent's ``write`` reach the same bytes
with nothing in between.
"""

from __future__ import annotations

import os
import pathlib
import shutil
from datetime import UTC, datetime

from coffer.domain.knowledge.entry import (
    ACTOR_AGENT,
    CatalogueLevel,
    CollectionEntry,
    DirectoryEntry,
    FileEntry,
    KnowledgeFile,
)
from coffer.domain.knowledge.errors import KnowledgeFileNotFound
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.frontmatter import (
    render_frontmatter,
    split_frontmatter,
)
from coffer.infrastructure.knowledge.naming import slugify, unique_name

MARKDOWN_SUFFIX = ".md"


def _visible(entry: pathlib.Path) -> bool:
    """Excludes any dot-prefixed entry — ``.history/`` and ``.raw/`` included,
    with nothing naming either specifically (FR-005, FR-024)."""
    return not entry.name.startswith(".")


def _is_content(name: str) -> bool:
    """Whether a file name is knowledge rather than a folder's own description.

    ``README.md`` describes the directory it sits in (FR-010). Listing it as
    content would put a folder's blurb in the same list as the files it
    introduces, and counting it would inflate every count by one.
    """
    return name.endswith(MARKDOWN_SUFFIX) and not name.startswith(".") and name != paths.README_NAME


def _now() -> str:
    return datetime.now(UTC).isoformat()


def count_files(directory: pathlib.Path) -> int:
    """Markdown files under ``directory``, recursively, skipping hidden ones.

    The dot-prefix filter walks past ``.history/`` and ``.raw/`` alike, so a
    collection's converted-document originals never inflate its count.
    """
    if not directory.is_dir():
        return 0
    total = 0
    for _root, dirnames, filenames in os.walk(directory):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        total += sum(1 for f in filenames if _is_content(f))
    return total


def readme_description(collection: str) -> str:
    """A collection's one-line description: its README's first paragraph.

    Deliberately read from the file rather than stored (FR-010) — the person
    browsing the folder must be able to see and change it in place.
    """
    readme = paths.readme_path(collection)
    if not readme.is_file():
        return ""
    _, body = split_frontmatter(readme.read_text(encoding="utf-8", errors="replace"))
    paragraph: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if not stripped:
            if paragraph:
                break
            continue
        paragraph.append(stripped)
    return " ".join(paragraph)


def list_collections() -> tuple[CollectionEntry, ...]:
    """Every collection directory present on disk."""
    root = paths.knowledge_root()
    if not root.is_dir():
        return ()
    found = [d for d in sorted(root.iterdir()) if d.is_dir() and _visible(d)]
    return tuple(
        CollectionEntry(
            name=d.name,
            description=readme_description(d.name),
            file_count=count_files(d),
        )
        for d in found
    )


def _file_entry(path: pathlib.Path) -> FileEntry:
    text = path.read_text(encoding="utf-8", errors="replace")
    fm, _ = split_frontmatter(text)
    relpath = paths.relative_of(path)
    return FileEntry(
        path=relpath,
        title=str(fm.get("title") or path.stem),
        description=str(fm.get("description") or ""),
        actor=str(fm.get("actor") or ACTOR_AGENT),
        updated_at=str(fm.get("updated_at") or ""),
    )


def list_level(relpath: str) -> CatalogueLevel:
    """One level of the catalogue: this directory's children and nothing deeper."""
    directory = paths.resolve(relpath)
    if not directory.is_dir():
        raise KnowledgeFileNotFound(relpath)
    directories: list[DirectoryEntry] = []
    files: list[FileEntry] = []
    for child in sorted(directory.iterdir()):
        if not _visible(child):
            continue
        if child.is_dir():
            directories.append(
                DirectoryEntry(
                    path=paths.relative_of(child),
                    name=child.name,
                    file_count=count_files(child),
                )
            )
        elif _is_content(child.name):
            files.append(_file_entry(child))
    return CatalogueLevel(
        path=relpath.strip("/"),
        directories=tuple(directories),
        files=tuple(files),
    )


def read_file(relpath: str) -> KnowledgeFile:
    """A file's frontmatter and body, plus the absolute paths a surface shows."""
    path = paths.resolve(relpath)
    if not path.is_file():
        raise KnowledgeFileNotFound(relpath)
    text = path.read_text(encoding="utf-8", errors="replace")
    fm, body = split_frontmatter(text)
    return KnowledgeFile(
        path=paths.relative_of(path),
        title=str(fm.get("title") or path.stem),
        description=str(fm.get("description") or ""),
        actor=str(fm.get("actor") or ACTOR_AGENT),
        created_at=str(fm.get("created_at") or ""),
        updated_at=str(fm.get("updated_at") or ""),
        body=body,
        file_path=str(path),
        folder_path=str(path.parent),
    )


def _atomic_write(path: pathlib.Path, text: str) -> None:
    """Write ``text`` to ``path`` through a sibling temp file and one rename.

    The guard is re-run here, on the parent that exists by now, because this
    is the last step before bytes land: ``resolve`` checked the path when the
    caller named it, and nothing between then and now may have redirected the
    directory out of the root. The temp file is opened ``O_NOFOLLOW`` and
    ``O_EXCL`` so a planted symlink under its name cannot carry the bytes
    elsewhere, and the final rename never follows a link (FR-006).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    paths.assert_inside_root(path, paths.relative_of(path))
    tmp = path.with_name(f".{path.name}.tmp")
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(tmp, flags, 0o644)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(path)


def write_file(
    *,
    directory: str,
    title: str,
    description: str,
    body: str,
    actor: str = ACTOR_AGENT,
    relpath: str | None = None,
) -> KnowledgeFile:
    """Create a file under ``directory``, or replace the one at ``relpath``.

    Replacing preserves ``created_at`` so the file keeps its own history even
    though nothing but the file records it.
    """
    now = _now()
    created = now
    if relpath is not None:
        target = paths.resolve(relpath)
        if target.is_file():
            existing, _ = split_frontmatter(target.read_text(encoding="utf-8", errors="replace"))
            created = str(existing.get("created_at") or now)
    else:
        parent = paths.resolve(directory)
        parent.mkdir(parents=True, exist_ok=True)
        name = unique_name(parent, slugify(title))
        target = parent / name
    text = render_frontmatter(
        {
            "title": title,
            "description": description,
            "actor": actor,
            "created_at": created,
            "updated_at": now,
        },
        body,
    )
    _atomic_write(target, text)
    return read_file(paths.relative_of(target))


def delete_file(relpath: str) -> None:
    path = paths.resolve(relpath)
    if not path.is_file():
        raise KnowledgeFileNotFound(relpath)
    path.unlink()


def remove_raw_original(relpath: str) -> None:
    """Remove the ``.raw/`` original behind a converted file, if any (FR-024).

    ``.raw/`` mirrors a converted file's directory structure but keeps the
    original's own extension, not ``.md`` (see ``paths.raw_path``), so the
    match is by stem rather than by full name. A file that was hand-written
    rather than ingested has no original — that is the common case, and it
    stays a clean no-op rather than an error.
    """
    segments = paths.split(relpath)
    if len(segments) < 2:
        return
    collection, rest = segments[0], segments[1:]
    *dirs, name = rest
    stem = pathlib.Path(name).stem
    raw_directory = paths.raw_dir(collection).joinpath(*dirs)
    if not raw_directory.is_dir():
        return
    for candidate in raw_directory.iterdir():
        if candidate.is_file() and candidate.stem == stem:
            candidate.unlink()


def archive(relpath: str) -> pathlib.Path:
    """Copy a file's current contents into its collection's ``.history/``.

    Called before tidy overwrites or merges anything: the pass runs with no
    review step, so this copy is the entire safety net (FR-030).
    """
    source = paths.resolve(relpath)
    if not source.is_file():
        raise KnowledgeFileNotFound(relpath)
    destination = paths.history_path(relpath)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def create_collection_dir(name: str) -> pathlib.Path:
    directory = paths.collection_dir(name)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def remove_collection_dir(name: str) -> None:
    directory = paths.collection_dir(name)
    if directory.is_dir():
        shutil.rmtree(directory)
