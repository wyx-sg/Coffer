"""Reads and writes one partition's four files, with one writer each.

A partition holds ``MEMORY.md``, ``notes/``, ``RETIRED.md`` and ``.raw/``, and
keeping those apart is not tidiness — it is what makes "Keep distil out of the
raw directory" checkable. Every function here writes into exactly one of the
four, so "does the distil pass write ``.raw/``?" is answered by reading which
functions the pass calls rather than by trusting it, and there is deliberately
no helper that writes a note and its raw entry in one go however convenient that
would be.

Notes and raw entries are one Markdown file each — frontmatter, then a body that
comes back byte for byte (:mod:`coffer.infrastructure.memory.frontmatter` argues
why that exactness is load-bearing for ``.raw/``, and writes atomically too).

``.raw/`` is not here: it is :mod:`coffer.infrastructure.memory.raw_store`,
so that the one directory only aggregation may write is the one module only
aggregation imports. That is the same argument one level up.

``MEMORY.md`` is written and read as **opaque text**. "Write each index line to
stand on its own" requires one function to render both that file and the
delivered line, and it lives in ``application/memory/index.py``; a second
renderer hiding in the storage layer is how those two surfaces became two
definitions of "newest" and drifted last time. ``RETIRED.md``'s format is argued
at :func:`write_retired`.
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from typing import Any

from coffer.domain.error_base import CofferError
from coffer.domain.memory.note import Note, Origin
from coffer.domain.memory.retired import RetiredNote
from coffer.infrastructure.memory import paths
from coffer.infrastructure.memory.frontmatter import (
    atomic_write,
    read_text,
    render_frontmatter,
    split_frontmatter,
    text_list,
)

_RETIRED_HEADER = (
    "# Retired\n\n"
    "Notes Coffer removed from this partition, and why — also the next distil "
    "pass's exclusion list, so a subject recorded here is not re-opened from the "
    "same unchanged raw entry (spec memory, 'Record retirements so they stick'). "
    "The record above the fence is read back; the prose below it is rendered from "
    "it, to be read not parsed.\n"
)


class NoteNotFound(CofferError):  # noqa: N818
    code = "MEMORY_NOTE_NOT_FOUND"

    def __init__(self, partition: str, slug: str) -> None:
        super().__init__(f"no note {slug!r} in partition {partition!r}")
        self.partition = partition
        self.slug = slug


def _origins_frontmatter(origins: Sequence[Origin]) -> list[dict[str, str]]:
    return [
        {
            "agent": o.agent,
            "native_path": o.native_path,
            "anchor": o.anchor,
            "captured_at": o.captured_at,
            "source_written_at": o.source_written_at,
        }
        for o in origins
    ]


def _origins_from_frontmatter(raw: Any) -> tuple[Origin, ...]:
    return tuple(
        Origin(
            agent=str(o.get("agent", "")),
            native_path=str(o.get("native_path", "")),
            anchor=str(o.get("anchor", "")),
            captured_at=str(o.get("captured_at", "")),
            source_written_at=str(o.get("source_written_at", "")),
        )
        for o in (raw or [])
        if isinstance(o, dict)
    )


# --- notes: written by the distil pass, and by nothing else ------------------


def write_note(note: Note) -> str:
    """Write one note file, atomically. Returns the memory-root-relative path."""
    frontmatter: dict[str, Any] = {
        "title": note.title,
        "description": note.description,
        "type": note.type,
        "origins": _origins_frontmatter(note.origins),
        "created_at": note.created_at,
        "updated_at": note.updated_at,
        "search_terms": list(note.search_terms),
    }
    path = paths.note_path(note.partition, note.slug)
    atomic_write(path, render_frontmatter(frontmatter, note.body))
    return paths.relative_of(path)


def read_note(partition: str, slug: str) -> Note:
    """Read one note back. Raises :class:`NoteNotFound` when the file is absent."""
    path = paths.note_path(partition, slug)
    if not path.is_file():
        raise NoteNotFound(partition, slug)
    fm, body = split_frontmatter(read_text(path))
    return Note(
        slug=slug,
        title=str(fm.get("title", "")),
        description=str(fm.get("description", "")),
        type=str(fm.get("type", "")),
        body=body,
        partition=partition,
        origins=_origins_from_frontmatter(fm.get("origins")),
        created_at=str(fm.get("created_at", "")),
        updated_at=str(fm.get("updated_at", "")),
        search_terms=text_list(fm.get("search_terms")),
    )


def list_notes(partition: str) -> tuple[Note, ...]:
    """Every note in ``partition``, by slug — not by ``updated_at``.

    "Write each index line to stand on its own" requires *one* definition of
    "newest" behind the index and the delivered lines, and it is the index
    renderer's; a second ordering here is how those two surfaces drifted apart
    before.
    """
    directory = paths.notes_dir(partition)
    if not directory.is_dir():
        return ()
    slugs = sorted(p.stem for p in directory.glob("*.md"))
    return tuple(read_note(partition, slug) for slug in slugs)


def delete_note(partition: str, slug: str) -> bool:
    """Remove one note's file; ``True`` when there was one to remove.

    Only the file half of a retirement: :func:`write_retired` is the half that
    makes it stick, and deleting without recording writes a deletion the next
    aggregation undoes (see "Record retirements so they stick").
    """
    path = paths.note_path(partition, slug)
    if not path.is_file():
        return False
    path.unlink()
    return True


# --- the retirement record ---------------------------------------------------


def write_retired(partition: str, retired: Sequence[RetiredNote]) -> str:
    """Rewrite ``RETIRED.md`` from ``retired``. Returns the relative path.

    **Why this file has two halves.** Two readers, whose needs conflict. The
    developer opens the partition as a folder and wants prose — what Coffer
    decided was no longer true, and on what grounds. The next distil pass takes
    the same file as its exclusion list, and a record it mis-parses is a note
    re-opened from an unchanged raw entry: the precise failure "Record
    retirements so they stick" exists to prevent, repeating every pass
    thereafter.

    One format cannot serve both, because ``reason`` is free prose Coffer
    writes: any heading, bullet or delimiter chosen to separate records is a
    string a reason may legitimately contain, and every fix for that —
    escaping, indenting, forbidding — makes the prose worse for the parser's
    sake. So the records go down **once as YAML frontmatter**, which quotes
    anything, and **once as rendered prose** below the fence.
    :func:`read_retired` reads only the fence, and the prose is regenerated
    from the same list on every write, so the two cannot disagree.

    An empty ``retired`` **removes** the file rather than writing an empty one:
    "Present partitions as a table and a file tree" shows it in the tree when
    something has been retired, and a "nothing yet" file in every partition is
    noise in the surface meant to make a retirement visible.
    """
    path = paths.retired_path(partition)
    if not retired:
        if path.is_file():
            path.unlink()
        return paths.relative_of(path)
    frontmatter: dict[str, Any] = {"retired": [_retired_record(r) for r in retired]}
    atomic_write(path, render_frontmatter(frontmatter, _render_retired_prose(retired)))
    return paths.relative_of(path)


def _retired_record(r: RetiredNote) -> dict[str, Any]:
    """One record as the fence stores it. ``sources_gone`` is written only when
    set, so a file with none of those records reads exactly as it always has."""
    record: dict[str, Any] = {
        "slug": r.slug,
        "title": r.title,
        "reason": r.reason,
        "replaced_by": r.replaced_by,
        "retired_at": r.retired_at,
        "entry_ids": list(r.entry_ids),
    }
    if r.sources_gone:
        record["sources_gone"] = True
    return record


def _render_retired_prose(retired: Sequence[RetiredNote]) -> str:
    """The half of ``RETIRED.md`` a human reads. Never parsed back."""
    chunks = [_RETIRED_HEADER]
    for r in retired:
        details = []
        if r.slug:
            details.append(f"was `notes/{r.slug}.md`")
            if r.sources_gone:
                details.append("its sources are gone")
        else:
            # No slug means this record accounts for entries a pass kept
            # nothing from: there was never a note and never a file, so
            # naming one would print a path that has never existed.
            count = len(r.entry_ids) or 1
            details.append(f"never became a note ({count} entry(s) read and not carried)")
        if r.replaced_by:
            details.append(f"replaced by `notes/{r.replaced_by}.md`")
        if r.retired_at:
            details.append(f"retired {r.retired_at}")
        heading = r.title or r.slug or "Untitled"
        chunks.append(f"\n## {heading}\n\n{' · '.join(details)}\n\n{r.reason}\n")
    return "".join(chunks)


def read_retired(partition: str) -> tuple[RetiredNote, ...]:
    """What has been retired from ``partition``, in the order it was written.

    Not sorted: a caller appending a retirement rewrites the whole list, so
    re-sorting here would silently reorder a file a human reads.
    """
    path = paths.retired_path(partition)
    if not path.is_file():
        return ()
    fm, _ = split_frontmatter(read_text(path))
    return tuple(
        RetiredNote(
            slug=str(r.get("slug", "")),
            title=str(r.get("title", "")),
            reason=str(r.get("reason", "")),
            replaced_by=str(r.get("replaced_by", "")),
            retired_at=str(r.get("retired_at", "")),
            entry_ids=text_list(r.get("entry_ids")),
            sources_gone=r.get("sources_gone") is True,
        )
        for r in (fm.get("retired") or [])
        if isinstance(r, dict)
    )


# --- the index, as opaque bytes ----------------------------------------------


def write_index(partition: str, text: str) -> str:
    """Put ``text`` at the partition's ``MEMORY.md``. Returns the relative path."""
    path = paths.index_path(partition)
    atomic_write(path, text)
    return paths.relative_of(path)


def read_index(partition: str) -> str:
    """The partition's ``MEMORY.md`` as text, or ``""`` when it has none yet."""
    path = paths.index_path(partition)
    if not path.is_file():
        return ""
    return read_text(path)


# --- partitions --------------------------------------------------------------


def list_partitions() -> tuple[str, ...]:
    """Every partition directory present on disk, ``global`` included.

    This module creates none of them — "Create partitions only by aggregation"
    gives that to aggregation, so an agent's working directory cannot bring a
    partition into existence merely by being read. Dot-prefixed directories are
    the layer's own state.
    """
    root = paths.memory_root()
    if not root.is_dir():
        return ()
    return tuple(sorted(d.name for d in root.iterdir() if d.is_dir() and d.name[0] != "."))


def delete_partition(name: str) -> None:
    """Remove a partition entirely — index, notes, retirements and ``.raw/``.

    Safe by construction, which is what "Keep the memory tree derived and local"
    means by derived: the agents still hold everything it was built from.
    """
    directory = paths.partition_dir(name)
    if directory.is_dir():
        shutil.rmtree(directory)


def rename_partition(old: str, new: str) -> None:
    """Move a partition's whole directory when its Resource is renamed.

    The mirror of ``knowledge``'s ``rename_collection_dir``, and for the same
    reason: a partition's name is its directory, so the label and the folder
    have to move together. One move takes the index, ``notes/``, ``RETIRED.md``
    and ``.raw/`` with it, which is what keeps a rename from costing the layer
    the entries the distil pass has not been back to yet.

    **A target that already exists is refused rather than merged into.** The
    framework has checked that no ``memory`` *row* holds the new name; it has
    not checked the filesystem, and it cannot — a directory can be there with no
    row behind it, left by a partition whose cleanup failed. The check has to be
    explicit because ``rename(2)`` makes the wrong call quietly: it fails on a
    non-empty target but succeeds over an empty one. Merging would file two
    repositories' raw entries into one partition, which is the one thing the
    keying of "Identify a partition by its repository" exists to prevent, and it
    would not be undone by the tree being derived — the next pass would happily
    re-fill the merged directory.

    A missing source is tolerated: a row whose directory is gone still renames,
    and the next aggregation pass writes the directory under the new name.
    """
    target = paths.partition_dir(new)
    if target.exists() or target.is_symlink():
        raise FileExistsError(str(target))
    source = paths.partition_dir(old)
    if not source.is_dir():
        return
    source.rename(target)
