"""What the knowledge directory looks like, read at call time.

Nothing here is materialized (spec knowledge "Store each collection as one
tree of Markdown files"): a catalogue is produced by walking the tree and
reading frontmatter when someone asks, so it cannot drift from what is on
disk — there is no second copy to keep in sync.

A walk sees every visible Markdown document under a collection. It never sees
the hidden ``.inbox/`` — material there is not knowledge yet — and it never lists a ``README.md``,
which describes the directory it sits in rather than being content in it (see
"Keep the collection README out of the corpus").
"""

from __future__ import annotations

import os
import pathlib
from datetime import UTC, datetime

from coffer.domain.knowledge.entry import (
    ACTOR_AGENT,
    ACTOR_USER,
    CatalogueLevel,
    CollectionEntry,
    DirectoryEntry,
    FileEntry,
)
from coffer.domain.knowledge.errors import KnowledgeFileNotFound
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter

MARKDOWN_SUFFIX = ".md"


def visible(entry: pathlib.Path) -> bool:
    """Excludes any dot-prefixed entry — the inbox included."""
    return not entry.name.startswith(".")


def is_listed(name: str) -> bool:
    """Whether a file of this name can be listed at all: any visible one.

    Not restricted to Markdown: a file a person drops in by hand is theirs to see
    and delete, whatever it is. The one file this hides is decided by where it
    sits, not by its name — see :func:`is_collection_readme`.
    """
    return not name.startswith(".")


def is_collection_readme(path: pathlib.Path) -> bool:
    """Whether ``path`` is a collection's own ``README.md`` — at the collection root.

    It describes the collection rather than being content in it, so it is kept out
    of listings and counts ("Keep the collection README out of the
    corpus"). A ``README.md`` in a subfolder is an ordinary document.
    """
    return path.name == paths.README_NAME and path.parent.parent == paths.knowledge_root()


def is_markdown(name: str) -> bool:
    """Whether a file is a document this layer can read or catalogue."""
    return name.endswith(MARKDOWN_SUFFIX) and is_listed(name)


def count_files(directory: pathlib.Path, *, markdown_only: bool = False) -> int:
    """Files under ``directory``, recursively, skipping hidden ones.

    ``markdown_only`` narrows it to the documents this layer can read.
    """
    if not directory.is_dir():
        return 0
    keep = is_markdown if markdown_only else is_listed
    total = 0
    for root, dirnames, filenames in os.walk(directory):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        total += sum(
            1 for f in filenames if keep(f) and not is_collection_readme(pathlib.Path(root) / f)
        )
    return total


def latest_edit(directory: pathlib.Path) -> str | None:
    """When the newest document under ``directory`` was written (ISO 8601,
    UTC), by file time; ``None`` when it holds none."""
    newest = 0.0
    for root, dirnames, filenames in os.walk(directory):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for f in filenames:
            path = pathlib.Path(root) / f
            if is_markdown(f) and not is_collection_readme(path):
                newest = max(newest, path.stat().st_mtime)
    if not newest:
        return None
    return datetime.fromtimestamp(newest, tz=UTC).isoformat()


def readme_description(collection: str) -> str:
    """A collection's one-line description: its README's first paragraph.

    Deliberately read from the file rather than stored (see "Read a collection's
    description from its README") — the person browsing the folder must be
    able to see and change it in place, and it is what the delivered skill's
    own description is built from (see "Describe Coffer and the collections'
    subjects in the skill description").
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
    """Every collection directory present on disk, with its documents counted."""
    root = paths.knowledge_root()
    if not root.is_dir():
        return ()
    found = [d for d in sorted(root.iterdir()) if d.is_dir() and visible(d)]
    return tuple(
        CollectionEntry(
            # Empty here by construction: this walks the DIRECTORY, which knows
            # names and counts and nothing about identity. The application layer
            # joins the registry in and fills it, and that join is
            # what keeps an unclaimed folder out of the list a caller gets.
            uid="",
            name=d.name,
            description=readme_description(d.name),
            document_count=count_files(d, markdown_only=True),
            folder_path=str(d),
            updated_at=latest_edit(d),
        )
        for d in found
    )


def _file_entry(path: pathlib.Path) -> FileEntry:
    if not is_markdown(path.name):
        # A file a person dropped in that is not Markdown: bytes, not prose. It
        # has no frontmatter to read and may be large, so it is described by
        # its own name rather than opened.
        return FileEntry(
            path=paths.relative_of(path),
            title=path.name,
            description="",
            actor=ACTOR_USER,
            updated_at="",
        )
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
    """One level of one collection: this directory's children and nothing deeper."""
    directory = paths.resolve(relpath)
    if not directory.is_dir():
        raise KnowledgeFileNotFound(relpath)
    directories: list[DirectoryEntry] = []
    files: list[FileEntry] = []
    for child in sorted(directory.iterdir()):
        if not visible(child):
            continue
        if child.is_dir():
            directories.append(
                DirectoryEntry(
                    path=paths.relative_of(child),
                    name=child.name,
                    file_count=count_files(child),
                )
            )
        elif is_listed(child.name) and not is_collection_readme(child):
            files.append(_file_entry(child))
    return CatalogueLevel(
        path=relpath.strip("/"),
        directories=tuple(directories),
        files=tuple(files),
    )


def walk_files(directory: pathlib.Path) -> tuple[FileEntry, ...]:
    """Every content file under ``directory``, recursively, in path order.

    The catalogue a skill carries is a whole collection at once (see "Merge the
    manual and the catalogue in the skill body"), unlike the level-at-a-time
    listing a human surface pages through — so this is the shape that builds
    it.
    """
    if not directory.is_dir():
        return ()
    found: list[FileEntry] = []
    for root, dirnames, filenames in os.walk(directory):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            # The narrow rule: this feeds the catalogue, which needs text.
            if is_markdown(name) and not is_collection_readme(pathlib.Path(root) / name):
                found.append(_file_entry(pathlib.Path(root) / name))
    return tuple(sorted(found, key=lambda f: f.path))
