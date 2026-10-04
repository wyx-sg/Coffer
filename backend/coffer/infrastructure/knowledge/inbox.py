"""A collection's inbox: the drop zone where new material lands before it is a document.

The hidden ``.inbox/`` half of what ``fs.py`` writes (see "Promote submitted
material at once"). An item is ordinary frontmatter and Markdown;
:func:`promote` makes it a document of its own and removes it. Coffer's own
entrances promote at once, and the sweep adopts and promotes whatever an agent
outside Coffer, another machine or an older guide dropped there.
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

from coffer.domain.knowledge.entry import ACTOR_AGENT, KnowledgeFile
from coffer.domain.knowledge.errors import KnowledgeFileNotFound
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.catalogue import is_markdown
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter
from coffer.infrastructure.knowledge.fs import (
    atomic_write,
    decode,
    render,
    timestamp,
    write_file,
)
from coffer.infrastructure.knowledge.naming import opening_prose, slugify, unique_name

#: The keys every item a Coffer surface writes carries.
_SUBMITTED_KEYS = ("title", "description", "actor", "created_at", "updated_at")


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

    The item is ordinary frontmatter and Markdown. It is written under a name of its
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


def has_complete_frontmatter(collection: str, name: str) -> bool:
    """Whether an item carries every key a Coffer surface writes. A file that
    lacks one was written outside Coffer."""
    fm, _ = split_frontmatter(decode(_inbox_item(collection, name).read_bytes()))
    return all(fm.get(key) for key in _SUBMITTED_KEYS)


def _first_heading(body: str) -> str:
    for line in body.splitlines():
        if line.startswith("# ") and line[2:].strip():
            return line[2:].strip()
    return ""


def adopt_dropped(collection: str, name: str) -> tuple[str, str, bool]:
    """Fill the frontmatter of an item written outside Coffer, in place (spec
    knowledge "Adopt a file dropped into the inbox").

    ``title`` is kept, else the first ``# `` heading, else the file name's stem;
    ``description`` is kept, else the first prose paragraph, else the title;
    ``actor`` is kept as written (self-reported), else ``agent``; the two
    timestamps are kept, else now; every other key a writer set is kept, and the
    body is unchanged. Returns ``(title, actor, actor_reported)``.
    """
    path = _inbox_item(collection, name)
    fm, body = split_frontmatter(decode(path.read_bytes()))
    title = str(fm.get("title") or "").strip() or _first_heading(body) or path.stem
    description = str(fm.get("description") or "").strip() or opening_prose(body, fallback=title)
    reported = str(fm.get("actor") or "").strip()
    actor = reported or ACTOR_AGENT
    now = timestamp()
    atomic_write(
        path,
        render(
            {
                **fm,
                "title": title,
                "description": description,
                "actor": actor,
                "created_at": fm.get("created_at") or now,
                "updated_at": fm.get("updated_at") or now,
            },
            body,
        ),
    )
    return title, actor, bool(reported)


def non_markdown_items(collection: str) -> tuple[str, ...]:
    """Files in a collection's inbox that are not Markdown: never promoted."""
    directory = paths.inbox_dir(collection)
    if not directory.is_dir():
        return ()
    return tuple(
        sorted(e.name for e in directory.iterdir() if e.is_file() and not is_markdown(e.name))
    )


def _submitted_at(entry: pathlib.Path) -> float:
    """When an item was submitted: its own ``created_at``, else its file time.

    The file time is only a fallback. A checkout, a restore or a sync round
    rewrites every mtime at once and would scramble "oldest first" ("A modification
    time never decides"), whereas ``created_at`` travels with the item.
    """
    try:
        fm, _ = split_frontmatter(decode(entry.read_bytes()))
        stamp = datetime.fromisoformat(str(fm.get("created_at") or ""))
    except (OSError, ValueError):
        return entry.stat().st_mtime
    return (stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)).timestamp()


def inbox_items(collection: str) -> tuple[str, ...]:
    """The names of a collection's waiting items, oldest submitted first."""
    directory = paths.inbox_dir(collection)
    if not directory.is_dir():
        return ()
    found = [
        (_submitted_at(entry), entry.name)
        for entry in directory.iterdir()
        if entry.is_file() and is_markdown(entry.name)
    ]
    return tuple(name for _, name in sorted(found))


def promote(collection: str, name: str) -> KnowledgeFile:
    """Make an inbox item a document of its own, as it stands.

    The material is knowledge the moment it arrives, so it must not wait in a
    hidden directory: it lands at the collection root with its frontmatter, and
    the inbox file is removed.
    """
    path = _inbox_item(collection, name)
    if not path.is_file():
        raise KnowledgeFileNotFound(inbox_path(collection, name))
    fm, body = split_frontmatter(decode(path.read_bytes()))
    written = write_file(
        directory=collection,
        title=str(fm.get("title") or path.stem),
        description=str(fm.get("description") or ""),
        body=body,
        actor=str(fm.get("actor") or ACTOR_AGENT),
    )
    path.unlink(missing_ok=True)
    return written
