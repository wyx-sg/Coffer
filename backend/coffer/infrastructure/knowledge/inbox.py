"""A collection's inbox: the drop zone where new material lands before it is a source.

The hidden ``.inbox/`` half of what ``fs.py`` writes (see "Promote submitted
material at once"). An item is ordinary frontmatter and Markdown;
:func:`promote` keeps it as a source under ``sources/`` — with the original
file beside it when an upload brought one ("Keep every upload as a source with
its original") — and removes it. Coffer's own entrances promote at once, and the
sweep adopts and promotes whatever an agent outside Coffer, another machine or
an older guide dropped there.
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


#: The key naming a source's kept original file, beside it in ``sources/``.
ORIGINAL_KEY = "original"


def _free_stem(directory: pathlib.Path, slug: str, suffix: str | None) -> str:
    """``slug``, or ``slug-2``, ``slug-3``… — the first stem whose Markdown and,
    when there is one, whose original are both free, so the pair shares a name."""
    for n in range(1, 1000):
        stem = slug if n == 1 else f"{slug}-{n}"
        taken = (directory / f"{stem}.md").exists()
        if suffix is not None:
            taken = taken or (directory / f"{stem}{suffix}").exists()
        if not taken:
            return stem
    raise ValueError(f"cannot find a free name for {slug!r}")


def promote(
    collection: str, name: str, *, original: tuple[str, bytes] | None = None
) -> tuple[KnowledgeFile, str | None]:
    """Keep an inbox item as a source, as it stands; returns the source and the
    knowledge-root-relative path of the original kept beside it, if any.

    The material must not wait in a hidden directory: it lands under the
    collection's ``sources/`` with its frontmatter — every key a writer set
    kept — and the inbox file is removed. ``original`` is the upload's own file
    name and bytes, kept under the same stem with its own extension.
    """
    path = _inbox_item(collection, name)
    if not path.is_file():
        raise KnowledgeFileNotFound(inbox_path(collection, name))
    fm, body = split_frontmatter(decode(path.read_bytes()))
    title = str(fm.get("title") or path.stem)
    directory = paths.sources_dir(collection)
    directory.mkdir(parents=True, exist_ok=True)
    suffix = pathlib.Path(original[0]).suffix.lower() if original else None
    if suffix is not None:
        paths.check_segment(f"x{suffix}", original[0] if original else "")
    stem = _free_stem(directory, slugify(title), suffix)
    extra = dict(fm)
    kept: str | None = None
    if original is not None and suffix is not None:
        target = directory / f"{stem}{suffix}"
        paths.assert_inside_root(target, paths.relative_of(target))
        target.write_bytes(original[1])
        kept = paths.relative_of(target)
        extra[ORIGINAL_KEY] = target.name
    written = write_file(
        directory=f"{collection}/{paths.SOURCES_DIR_NAME}",
        relpath=f"{collection}/{paths.SOURCES_DIR_NAME}/{stem}.md",
        title=title,
        description=str(fm.get("description") or ""),
        body=body,
        actor=str(fm.get("actor") or ACTOR_AGENT),
        extra=extra,
    )
    path.unlink(missing_ok=True)
    return written, kept
