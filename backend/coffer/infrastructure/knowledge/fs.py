"""Writing the knowledge directory, and reading one file out of it.

What the directory *looks like* — the counts, the levels, the walks a
catalogue is built from — is ``catalogue.py``. This module is the half that
changes bytes.

Every operation here is a filesystem operation and nothing else: no index is
updated, because there is none (spec knowledge FR-001). That is what lets a
person's edit in their own editor and a curation pass reach the same bytes
with nothing in between.

Two kinds of file live under a collection, and this module is where they meet:

* **Documents** — the visible tree. A person edits them in their own editor;
  a curation pass writes them through :func:`write_file`. Each carries
  ``coffer_curated_at``, the moment curation last had it in front of it, and an
  edit made since is what the sweep comes back for (FR-022).
* **Material** — the hidden ``.inbox/``. New knowledge waits here until a pass
  folds it into the documents, and is deleted when that pass completes; with no
  model to fold it, :func:`promote` makes it a document of its own (FR-029).
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import shutil
from datetime import UTC, datetime
from typing import Any

from coffer.domain.knowledge.entry import ACTOR_AGENT, KnowledgeFile
from coffer.domain.knowledge.errors import KnowledgeFileNotFound
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.catalogue import is_markdown
from coffer.infrastructure.knowledge.frontmatter import (
    render_frontmatter,
    split_frontmatter,
)
from coffer.infrastructure.knowledge.naming import slugify, unique_name

#: Frontmatter key carrying when curation last had a document in front of it
#: (FR-028). Written into a file a person also edits, deliberately: it is
#: feedback the person can see in their own editor, and it means the watermark
#: needs no state file, no table and nothing to keep level with the disk.
CURATED_AT_KEY = "coffer_curated_at"

#: The frontmatter keys this layer writes, in render order (FR-003). Anything
#: else a person put in the file is kept and rendered after them: FR-003 says
#: what Coffer writes, not what a person may not.
_ORDERED_KEYS = ("title", "description", "actor", "created_at", "updated_at", CURATED_AT_KEY)


def _now() -> str:
    return datetime.now(UTC).isoformat()


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
        curated_at=str(fm.get(CURATED_AT_KEY) or ""),
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


def _render(frontmatter: dict[str, Any], body: str) -> str:
    """The known keys in their fixed order, then anything else, unharmed.

    The tail matters. ``mark_curated`` rewrites a file a *person* also edits to
    add one stamp, unattended — so dropping a key it does not recognise would
    quietly delete their own `tags:` or `reviewed_by:` from a document.
    """
    ordered = {k: frontmatter[k] for k in _ORDERED_KEYS if frontmatter.get(k)}
    extra = {k: v for k, v in frontmatter.items() if k not in _ORDERED_KEYS and v}
    return render_frontmatter({**ordered, **extra}, body)


def write_file(
    *,
    directory: str,
    title: str,
    description: str,
    body: str,
    actor: str = ACTOR_AGENT,
    relpath: str | None = None,
    curated: bool = False,
) -> KnowledgeFile:
    """Create a document under ``directory``, or replace the one at ``relpath``.

    Both are knowledge-root-relative. ``directory`` is a collection or a folder
    inside one; ``relpath`` must name a document (``paths.require_document``).
    Replacing preserves ``created_at`` so the file keeps its own history even
    though nothing but the file records it.

    ``curated`` is the curation pass's own write: it stamps
    ``coffer_curated_at`` so the sweep does not hand the pass its own output
    back. Any other write leaves the stamp off, which is exactly what makes the
    sweep look at it.
    """
    now = _now()
    created = now
    if relpath is not None:
        paths.require_document(relpath)
        target = paths.resolve(relpath)
        if target.is_file():
            existing, _ = split_frontmatter(target.read_text(encoding="utf-8", errors="replace"))
            created = str(existing.get("created_at") or now)
    else:
        parent = paths.resolve(directory)
        parent.mkdir(parents=True, exist_ok=True)
        name = unique_name(parent, slugify(title))
        target = parent / name
        paths.require_document(paths.relative_of(target))
    frontmatter: dict[str, Any] = {
        "title": title,
        "description": description,
        "actor": actor,
        "created_at": created,
        "updated_at": now,
    }
    if curated:
        frontmatter[CURATED_AT_KEY] = now
    _atomic_write(target, _render(frontmatter, body))
    if curated:
        _align_mtime(target, now)
    return read_file(paths.relative_of(target))


def delete_file(relpath: str) -> None:
    paths.require_document(relpath)
    path = paths.resolve(relpath)
    if not path.is_file():
        raise KnowledgeFileNotFound(relpath)
    path.unlink()


def _align_mtime(path: pathlib.Path, stamp: str) -> None:
    """Make the file's mtime the stamp it now carries.

    Writing a stamp is itself a modification, so without this the file's mtime
    would land just after the stamp and the sweep would hand the same document
    back forever. Setting it to the stamp makes the file say the true thing —
    its last modification *was* curation — and any later edit by a person moves
    mtime past it again, which is the whole comparison.
    """
    with contextlib.suppress(OSError):
        seconds = _parse(stamp)
        if seconds:
            os.utime(path, (seconds, seconds))


def mark_curated(relpath: str, *, when: str | None = None) -> None:
    """Stamp a document as seen by curation, changing nothing else (FR-028).

    Called only after a pass over that document completes. A pass that fails
    leaves the stamp as it was, so the document comes back on a later sweep
    rather than being lost to one that half-ran.
    """
    paths.require_document(relpath)
    path = paths.resolve(relpath)
    if not path.is_file():
        raise KnowledgeFileNotFound(relpath)
    fm, body = split_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    # Values are carried through as they were parsed, not stringified: a YAML
    # list a person wrote must come back a YAML list, or the stamp has still
    # damaged their file — just more quietly than deleting the key would.
    merged: dict[str, Any] = {k: v for k, v in fm.items() if v not in (None, "")}
    stamp = when or _now()
    merged[CURATED_AT_KEY] = stamp
    _atomic_write(path, _render(merged, body))
    _align_mtime(path, stamp)


def edited_documents(collection: str) -> tuple[str, ...]:
    """Documents changed since curation last saw them, oldest first.

    The comparison is the file's own modification time against its own
    ``coffer_curated_at``: no state file, no table, and nothing that can
    disagree with the disk. A document a person has just edited — or written
    from scratch, with no stamp at all — is newer than its stamp and comes
    back; one nothing has touched does not.
    """
    directory = paths.collection_dir(collection)
    if not directory.is_dir():
        return ()
    pending: list[tuple[float, str]] = []
    for root, dirnames, filenames in os.walk(directory):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        at_root = pathlib.Path(root) == directory
        for name in sorted(filenames):
            if not is_markdown(name) or (at_root and name == paths.README_NAME):
                continue
            # One read and one stat per file: this runs on every sweep, so it
            # is deliberately not built on `walk_files` + `read_file`, which
            # would open each document three times a minute for nothing.
            path = pathlib.Path(root) / name
            fm, _ = split_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
            mtime = path.stat().st_mtime
            stamp = str(fm.get(CURATED_AT_KEY) or "")
            if stamp and _parse(stamp) >= mtime:
                continue
            pending.append((mtime, paths.relative_of(path)))
    return tuple(relpath for _, relpath in sorted(pending))


def _parse(stamp: str) -> float:
    try:
        return datetime.fromisoformat(stamp).timestamp()
    except ValueError:
        return 0.0


# ----- the inbox ----------------------------------------------------------


def _inbox_item(collection: str, name: str) -> pathlib.Path:
    """One inbox item by its file name, guarded like any other segment."""
    paths.check_segment(name, f"{collection}/{paths.INBOX_DIR_NAME}/{name}")
    return paths.inbox_dir(collection) / name


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
    now = _now()
    _atomic_write(
        target,
        _render(
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
    fm, body = split_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
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
    )


def discard_material(collection: str, name: str) -> None:
    """Delete an inbox item a pass has folded in."""
    _inbox_item(collection, name).unlink(missing_ok=True)


def promote(collection: str, name: str) -> KnowledgeFile:
    """Make an inbox item a document of its own, as it stands (FR-029).

    The path with no model to merge it: the material is knowledge the moment it
    arrives, so it must not wait in a hidden directory for a connection that
    may never be configured. It lands at the collection root, stamped as
    curated — nothing is going to curate it, and an unstamped document would
    only be handed back by every sweep.
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


def create_collection_dir(name: str) -> pathlib.Path:
    """Create a collection's directory (FR-008)."""
    directory = paths.collection_dir(name)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def remove_collection_dir(name: str) -> None:
    directory = paths.collection_dir(name)
    if directory.is_dir():
        shutil.rmtree(directory)


def rename_collection_dir(old: str, new: str) -> None:
    """Move a collection's directory when its Resource is renamed.

    A collection's name IS its directory, so a rename of the label has to move
    the folder with it; this is the whole of what the ``knowledge`` kind's
    ``on_rename`` hook does.

    **A target that already exists is refused, never merged or replaced.** The
    framework has already checked that no ``knowledge`` *row* holds the new
    name, but a directory can sit there with no row behind it — a folder
    somebody made by hand under ``~/.coffer/knowledge/``, or one a failed
    cleanup left behind — and the check has to be explicit, because
    ``rename(2)`` would not make it for us: it fails on a non-empty target but
    quietly succeeds over an *empty* directory. Neither outcome is one to pick
    by accident. Merging adopts files into the corpus that nobody registered
    and that curation would then rewrite; replacing destroys them.
    ``create_collection`` already refuses exactly this situation with
    ``CollectionExists``, and this is the same rule on the other write path.

    A missing SOURCE is tolerated instead, and the asymmetry is deliberate: a
    row whose directory is gone is already broken, and refusing to rename it
    would take away the one thing about it the user can still fix.
    """
    target = paths.collection_dir(new)
    if target.exists() or target.is_symlink():
        raise FileExistsError(str(target))
    source = paths.collection_dir(old)
    if not source.is_dir():
        return
    source.rename(target)
