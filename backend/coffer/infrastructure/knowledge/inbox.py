"""A collection's inbox: where new material waits to be merged.

The hidden ``.inbox/`` half of what ``fs.py`` writes (see "Submit every
entrance's input as material"). An item is ordinary frontmatter and Markdown,
so a pass reads it exactly as it reads a document; it is deleted when that pass
completes, and with no model to fold it, :func:`promote` makes it a document of
its own (see "Promote material directly when no model is configured"). A person
may read an item (see "Hide dot-prefixed entries except the inbox"); nothing
but this module writes or deletes one.
"""

from __future__ import annotations

import pathlib

from coffer.domain.knowledge.entry import ACTOR_AGENT, KnowledgeFile
from coffer.domain.knowledge.errors import KnowledgeFileNotFound
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.catalogue import is_markdown
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter
from coffer.infrastructure.knowledge.fs import (
    atomic_write,
    decode,
    fingerprint,
    render,
    timestamp,
    write_file,
)
from coffer.infrastructure.knowledge.naming import slugify, unique_name


def _inbox_item(collection: str, name: str) -> pathlib.Path:
    """One inbox item by its file name, guarded like any other segment."""
    paths.check_segment(name, f"{collection}/{paths.INBOX_DIR_NAME}/{name}")
    return paths.inbox_dir(collection) / name


def inbox_path(collection: str, name: str) -> str:
    """An inbox item's knowledge-root-relative path — what its history records."""
    return f"{collection}/{paths.INBOX_DIR_NAME}/{name}"


def submit_material(
    collection: str,
    *,
    title: str,
    description: str,
    body: str,
    actor: str = ACTOR_AGENT,
) -> str:
    """Put new material in the collection's inbox. Returns the item's name.

    The item is ordinary frontmatter and Markdown, so the pass that merges it
    reads it exactly as it reads a document. It is written under a name of its
    own — never onto an existing item — because two submissions of the same
    title are two pieces of material.
    """
    directory = paths.inbox_dir(collection)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / unique_name(directory, slugify(title))
    now = timestamp()
    atomic_write(
        target,
        render(
            {
                "title": title,
                "description": description,
                "actor": actor,
                "created_at": now,
                "updated_at": now,
            },
            body,
        ),
    )
    return target.name


def inbox_items(collection: str) -> tuple[str, ...]:
    """The names of a collection's unmerged items, oldest first."""
    directory = paths.inbox_dir(collection)
    if not directory.is_dir():
        return ()
    found = [
        (entry.stat().st_mtime, entry.name)
        for entry in directory.iterdir()
        if entry.is_file() and is_markdown(entry.name)
    ]
    return tuple(name for _, name in sorted(found))


def read_material(collection: str, name: str) -> KnowledgeFile:
    """One inbox item, read the way a document is."""
    path = _inbox_item(collection, name)
    if not path.is_file():
        raise KnowledgeFileNotFound(f"{collection}/{paths.INBOX_DIR_NAME}/{name}")
    raw = path.read_bytes()
    fm, body = split_frontmatter(decode(raw))
    return KnowledgeFile(
        path=f"{collection}/{paths.INBOX_DIR_NAME}/{name}",
        title=str(fm.get("title") or path.stem),
        description=str(fm.get("description") or ""),
        actor=str(fm.get("actor") or ACTOR_AGENT),
        created_at=str(fm.get("created_at") or ""),
        updated_at=str(fm.get("updated_at") or ""),
        body=body,
        file_path=str(path),
        folder_path=str(path.parent),
        fingerprint=fingerprint(raw),
        inbox=True,
    )


def discard_material(collection: str, name: str) -> None:
    """Delete an inbox item a pass has folded in."""
    _inbox_item(collection, name).unlink(missing_ok=True)


def promote(collection: str, name: str) -> KnowledgeFile:
    """Make an inbox item a document of its own, as it stands.

    The path with no model to merge it: the material is knowledge the moment it
    arrives, so it must not wait in a hidden directory for a connection that
    may never be configured. It lands at the collection root, recorded as
    settled by curation — nothing is going to curate it, and an unsettled
    document would only be handed back by every sweep.
    """
    material = read_material(collection, name)
    written = write_file(
        directory=collection,
        title=material.title,
        description=material.description,
        body=material.body,
        actor=material.actor,
        curated=True,
    )
    discard_material(collection, name)
    return written
