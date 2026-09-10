"""On-disk I/O for the ``notes/`` lane — everything an agent or a person wrote.

One flat lane: a note is a note whether it was written a minute ago or has been
merged and rewritten since. There is no staging inbox, no promotion into a
separate topic-doc lane, and no review index — so this module has exactly the
six operations a lane needs (list, read, exists, write, archive, delete) and
nothing that existed only to move a file from one lane to the next.

The archive is the point of the module. The tidy pass runs unattended and lets
an LLM merge and rewrite text the user never re-reads, so every write over an
existing note first moves the prior revision into ``.history/``. That copy is
the whole safety net: there is no review step and no diff to approve, so an
archive failure must abort the write rather than be swallowed.

Frontmatter parse/render is delegated to the shared
``infrastructure.knowledge.frontmatter`` (the PyYAML owner) and the write goes
through ``infrastructure.knowledge.fs`` so a crash never leaves half a note.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from coffer.infrastructure.knowledge.frontmatter import (
    render_frontmatter,
    split_frontmatter,
)
from coffer.infrastructure.knowledge.fs import atomic_write_text
from coffer.infrastructure.knowledge.paths import history_path, note_path, notes_dir

#: ``documents.kind`` for every file in a knowledge scope; the lane a row
#: belongs to is the directory it sits in, not this header.
_KIND = "knowledge"


@dataclass(frozen=True)
class NoteDoc:
    """One note read from disk.

    ``summary`` is the frontmatter ``description`` — ``""`` when the file has
    none, rather than a guess, so a caller can tell "no summary" from one that
    happens to repeat the first line. ``updated_at`` is ``None`` only when the
    file carries no timestamp and its mtime cannot be read.
    """

    slug: str
    title: str
    summary: str
    body: str
    path: Path
    updated_at: datetime | None


def list_notes(store_dir: Path) -> list[NoteDoc]:
    """Every note in the store's ``notes/`` lane, sorted by slug.

    The lane may not exist yet (a scope nobody has written to) → an empty list,
    never an error. Dot-prefixed files are skipped: ``pathlib`` globs match them
    (unlike the shell), and the atomic writer parks its temp files alongside the
    real ones.
    """
    lane = notes_dir(store_dir)
    if not lane.exists():
        return []
    notes: list[NoteDoc] = []
    for path in sorted(lane.glob("*.md")):
        if path.name.startswith("."):
            continue
        note = _read_path(path)
        if note is not None:
            notes.append(note)
    return notes


def read_note(store_dir: Path, slug: str) -> NoteDoc | None:
    """Read one note, or ``None`` when there is no such file."""
    return _read_path(note_path(store_dir, slug))


def note_exists(store_dir: Path, slug: str) -> bool:
    """Whether ``notes/<slug>.md`` is already there (created-vs-updated
    accounting for the tidy pass)."""
    return note_path(store_dir, slug).exists()


def write_note(
    store_dir: Path,
    slug: str,
    *,
    title: str,
    summary: str,
    body: str,
    now: datetime,
) -> Path:
    """(Over)write ``notes/<slug>.md``, archiving whatever was there first.

    The archive is not best-effort: if it fails, this raises and the old note is
    still on disk, because losing an unattended rewrite's input is worse than
    failing the pass. The write itself is atomic, so a crash leaves either the
    old note or the new one.
    """
    path = note_path(store_dir, slug)
    if path.exists():
        archive_note(store_dir, slug, now=now)
    text = render_frontmatter(
        {
            "kind": _KIND,
            "title": title,
            "description": summary,
            "updated_at": _as_utc(now).isoformat(),
        },
        body,
    )
    atomic_write_text(path, text)
    return path


def archive_note(store_dir: Path, slug: str, *, now: datetime) -> Path | None:
    """Move ``notes/<slug>.md`` into ``.history/<slug>-<UTC stamp>.md``.

    Returns the archive path, or ``None`` when there was no such note. The bytes
    are read from disk (so a hand edit is captured, not the caller's idea of the
    content) and written to the archive BEFORE the original is unlinked, so an
    interrupted archive loses nothing. A second archive of the same slug within
    the same second gets a ``-2``/``-3``/… suffix rather than overwriting the
    first.
    """
    src = note_path(store_dir, slug)
    if not src.exists():
        return None
    content = src.read_text(encoding="utf-8")
    dest = _free_history_path(store_dir, f"{slug}-{_as_utc(now).strftime('%Y%m%dT%H%M%S')}")
    atomic_write_text(dest, content)
    src.unlink()
    return dest


def delete_note(store_dir: Path, slug: str) -> bool:
    """Delete one note. Returns whether it existed.

    A delete archives like a rewrite does — the file leaves the lane, and the
    ``.history/`` copy is what makes an over-eager tidy pass (or a mistaken
    ``coffer__delete``) recoverable.
    """
    return archive_note(store_dir, slug, now=datetime.now(UTC)) is not None


# --- internals --------------------------------------------------------------


def _read_path(path: Path) -> NoteDoc | None:
    """Parse one note file, degrading over missing frontmatter.

    A note may have been written by hand or by an agent that skipped the header,
    so ``title`` falls back to the filename stem, ``summary`` to ``""``, and
    ``updated_at`` to the file mtime.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    meta, body = split_frontmatter(text)
    return NoteDoc(
        slug=path.stem,
        title=str(meta.get("title") or path.stem),
        summary=str(meta.get("description") or ""),
        body=body.strip("\n"),
        path=path,
        updated_at=_parse_updated_at(meta.get("updated_at"), default=_mtime(path)),
    )


def _free_history_path(store_dir: Path, base: str) -> Path:
    path = history_path(store_dir, base)
    n = 2
    while path.exists():
        path = history_path(store_dir, f"{base}-{n}")
        n += 1
    return path


def _mtime(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except OSError:  # pragma: no cover - the read above already succeeded
        return None


def _as_utc(value: datetime) -> datetime:
    """A naive timestamp is read as UTC — the archive name claims to be UTC."""
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _parse_updated_at(value: object, *, default: datetime | None) -> datetime | None:
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, str):
        try:
            return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return default
    return default
