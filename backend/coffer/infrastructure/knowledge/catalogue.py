"""What the knowledge directory looks like, read at call time.

Nothing here is materialized (spec knowledge "Store each collection as one
tree of Markdown files"): a catalogue is produced by walking the tree and
reading frontmatter when someone asks, so it cannot drift from what is on
disk — there is no second copy to keep in sync.

A walk sees every visible file under a collection, each with its title and
description as its own frontmatter or first heading gives them; no folder and
no key means anything to it (spec knowledge "Let each collection declare its
own rules"). It never sees a hidden entry. A level lists the collection's
``README.md`` like any other root file, but no count or catalogue walk
includes it, because it describes the collection rather than being content
in it (see "Keep the collection README out of the corpus").
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
from coffer.infrastructure.knowledge import collection_settings, link_graph, paths
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter

MARKDOWN_SUFFIX = ".md"


def visible(entry: pathlib.Path) -> bool:
    """Excludes any dot-prefixed entry."""
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
    """A collection's one-line description: its README's first paragraph,
    before its first section (``##``).

    Deliberately read from the file rather than stored (see "Read a collection's
    description from its README") — the person browsing the folder must be
    able to see and change it in place, and it is what the delivered skill's
    own description is built from (see "Describe Coffer and the collections'
    subjects in the skill description").
    """
    return collection_settings.description(paths.collection_dir(collection))


def list_collections() -> tuple[CollectionEntry, ...]:
    """Every collection directory present on disk, with its documents counted."""
    root = paths.knowledge_root()
    if not root.is_dir():
        return ()
    found = [d for d in sorted(root.iterdir()) if d.is_dir() and visible(d)]
    return tuple(collection_entry(d) for d in found)


def collection_entry(
    directory: pathlib.Path, graph: link_graph.LinkGraph | None = None
) -> CollectionEntry:
    """One collection directory with its counts, its declarations and its
    broken links."""
    graph = graph if graph is not None else link_graph.build(directory.name)
    findings = tuple(graph.findings())
    settings = collection_settings.read(directory, bound=paths.knowledge_root())
    return CollectionEntry(
        # Empty here by construction: this walks the DIRECTORY, which knows
        # names and counts and nothing about identity. The application layer
        # joins the registry in and fills it, and that join is
        # what keeps an unclaimed folder out of the list a caller gets.
        uid="",
        name=directory.name,
        description=readme_description(directory.name),
        finding_count=len(findings),
        findings=findings,
        folder_path=str(directory),
        updated_at=latest_edit(directory),
        note_count=count_files(directory, markdown_only=True),
        rules_file=settings.rules,
        entry_file=settings.entry,
        uploads_dir=settings.uploads,
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
    fm, body = split_frontmatter(text)
    described = fm.get("description")
    return FileEntry(
        path=paths.relative_of(path),
        title=collection_settings.title_of(fm, body, path.stem),
        description=" ".join(str(described).split()) if described else "",
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
    # Folders first, then files, each by name: no folder means more than another.
    children = sorted(directory.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower()))
    for child in children:
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
        elif is_listed(child.name):
            # The README is listed too, as the plain file it is: a person browses
            # and opens a collection's own files where they are.
            files.append(_file_entry(child))
    return CatalogueLevel(
        path=relpath.strip("/"),
        directories=tuple(directories),
        files=tuple(files),
    )


def walk_files(directory: pathlib.Path) -> tuple[FileEntry, ...]:
    """Every Markdown file under a collection ``directory`` but its README,
    recursively, in path order, each with its title and description.

    The catalogue a skill carries is a whole collection at once when the
    collection names no entry page (see "Merge the manual and the catalogue in
    the skill body"), unlike the level-at-a-time listing a human surface pages
    through — so this is the shape that builds it.
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
