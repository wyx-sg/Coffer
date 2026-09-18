"""What the knowledge directory looks like, read at call time.

Nothing here is materialized (spec knowledge FR-001): a catalogue is produced
by walking the tree and reading frontmatter when someone asks, so it cannot
drift from what is on disk — there is no second copy to keep in sync.

Two rules decide what a walk sees, and keeping them apart is the point of this
module:

* :func:`is_listed` — what a **person** browsing the folder should see. Every
  visible file except a ``README.md``, deliberately including an uploaded
  document's original: a lane that showed the extracted text and hid the PDF
  the person actually sent would be lying about its own contents (FR-016).
* :func:`is_markdown` — what **this layer** can read, curate or catalogue. A
  ``.pdf`` in ``sources/`` is a thing a person can see and delete, not a thing
  curation or a skill's catalogue can use.
"""

from __future__ import annotations

import os
import pathlib

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
    """Excludes any dot-prefixed entry. Coffer itself writes none (FR-005)."""
    return not entry.name.startswith(".")


def is_listed(name: str) -> bool:
    """Whether a person browsing this folder should see the file.

    Everything visible except a ``README.md``, which describes the directory it
    sits in rather than being content in it. A collection's README lives
    outside both lanes (FR-007), but a person may put one inside a ``sources/``
    folder too, and it is a blurb there for the same reason.

    Deliberately NOT restricted to Markdown: an uploaded document's original
    lands in ``sources/`` beside the text extracted from it (FR-016), and a
    lane that shows the extraction but hides the PDF the person actually sent
    would be lying about its own contents.
    """
    return not name.startswith(".") and name != paths.README_NAME


def is_markdown(name: str) -> bool:
    """Whether a file is text this layer can read, curate or catalogue.

    The narrower of the two: curation reads bodies, and the catalogue a skill
    carries lists documents an agent can open. A ``.pdf`` in ``sources/`` is a
    thing a person can see and delete, not a thing either of those can use.
    """
    return name.endswith(MARKDOWN_SUFFIX) and is_listed(name)


def count_files(directory: pathlib.Path, *, markdown_only: bool = False) -> int:
    """Files under ``directory``, recursively, skipping hidden ones.

    ``markdown_only`` narrows it to what this layer can read — which is the
    right count for ``topics/``, where every file is a document, and the wrong
    one for ``sources/``, where a person's uploaded original counts as much as
    the text extracted from it.
    """
    if not directory.is_dir():
        return 0
    keep = is_markdown if markdown_only else is_listed
    total = 0
    for _root, dirnames, filenames in os.walk(directory):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        total += sum(1 for f in filenames if keep(f))
    return total


def readme_description(collection: str) -> str:
    """A collection's one-line description: its README's first paragraph.

    Deliberately read from the file rather than stored (FR-011) — the person
    browsing the folder must be able to see and change it in place, and it is
    what the delivered skill's own description is built from (FR-036).
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
    """Every collection directory present on disk, with both lanes counted."""
    root = paths.knowledge_root()
    if not root.is_dir():
        return ()
    found = [d for d in sorted(root.iterdir()) if d.is_dir() and visible(d)]
    return tuple(
        CollectionEntry(
            # Empty here by construction: this walks the DIRECTORY, which knows
            # names and counts and nothing about identity. The application layer
            # joins the registry in and fills it, and its enabled-rows filter is
            # what keeps an unclaimed folder out of the list a caller gets.
            uid="",
            name=d.name,
            description=readme_description(d.name),
            source_count=count_files(paths.sources_dir(d.name)),
            topic_count=count_files(paths.topics_dir(d.name), markdown_only=True),
        )
        for d in found
    )


def _file_entry(path: pathlib.Path) -> FileEntry:
    if not is_markdown(path.name):
        # An uploaded original: bytes, not prose. It has no frontmatter to read
        # and may be large, so it is described by its own name rather than
        # opened (FR-016).
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
    """One level of one lane: this directory's children and nothing deeper."""
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
        elif is_listed(child.name):
            files.append(_file_entry(child))
    return CatalogueLevel(
        path=relpath.strip("/"),
        directories=tuple(directories),
        files=tuple(files),
    )


def walk_files(directory: pathlib.Path) -> tuple[FileEntry, ...]:
    """Every content file under ``directory``, recursively, in path order.

    The catalogue a skill carries is the whole of one lane at once (FR-037),
    unlike the level-at-a-time listing a human surface pages through — so this
    is the shape that builds it, and the one curation reads a collection with.
    """
    if not directory.is_dir():
        return ()
    found: list[FileEntry] = []
    for root, dirnames, filenames in os.walk(directory):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            # The narrow rule: this feeds the catalogue and curation, both of
            # which need text.
            if is_markdown(name):
                found.append(_file_entry(pathlib.Path(root) / name))
    return tuple(sorted(found, key=lambda f: f.path))
