"""One-way rewrite of the flat collection into two lanes (spec knowledge).

Since 0066 a collection has been a flat directory of Markdown beside a hidden
``.raw/`` holding the bytes an upload arrived as, and a hidden ``.history/``
holding what a rewrite replaced. The redesign splits that into two visible
lanes with different authors: ``sources/`` is what a person, an upload or
``coffer__write`` put there, and ``topics/`` is what the curation pass derives
from it and the only lane an agent reads.

Everything that exists today is a *source*. Nothing in the old tree was derived
— there was no curation pass to derive it — so the rewrite is not a
classification problem: every content file moves into ``sources/`` with its
nesting intact, and ``topics/`` is created **empty**. It stays empty until the
first curation pass runs, which is why the same upgrade seeds
``auto_curate_enabled`` on (spec knowledge "Keep auto-curation on for migrated
vaults"): a migrated vault that never curates would hand every agent an empty
catalogue forever.

``.raw/`` stops being hidden rather than being deleted. A PDF someone uploaded
is the truest source there is, and the only reason it was hidden was to keep it
out of a retrieval index that no longer exists — so each original moves into
``sources/`` beside the Markdown that was extracted from it, under its own
name and its own extension. A name already taken is suffixed, never
overwritten: two files that happen to share a name are two files.

``.history/`` is deleted outright. It existed because a topic document was the
only copy of what it said, so replacing one destroyed writing nobody else held.
Sources are now that copy, and they are never rewritten by anything unattended.

**The backup comes first.** The corpus is the user's own writing, this pass
moves every file in it, and the lane an agent reads is empty on the other side.
Before a single file moves, the whole root is copied to a sibling directory
named after this revision, and the path is logged. It is the only protection
those files have, and a second run reuses it rather than copying a tree this
pass has already rewritten over the top of the original.

Idempotent throughout. A collection with nothing outside its lanes and no
hidden directory is one this pass walks past — it neither backs up again nor
moves anything — so running the upgrade twice is a no-op rather than a second
backup and a second round of renames.

Frozen, like ``knowledge_tree_0066``: a migration describes one moment in
history and must not change behaviour because the product's live path helpers
later did. The lane names and the root resolution below are copies, not
imports — including the retired shared master's folder name, which this
migration is required to take with it. That one used to be imported from the
knowledge layer; it is spelled out here now, because the layer stopped writing
that folder and a one-time script must not depend on today's code to say what
yesterday's vault looked like.
"""

from __future__ import annotations

import logging
import os
import pathlib
import shutil
from dataclasses import dataclass, field

logger = logging.getLogger("alembic.runtime.migration")

#: The revision this rewrite belongs to. It names the backup directory, so a
#: user who finds one can tell which upgrade made it.
REVISION = "0085"

README_NAME = "README.md"

#: The two lanes, as 0085 introduced them.
SOURCES_DIR_NAME = "sources"
TOPICS_DIR_NAME = "topics"
LANES = (SOURCES_DIR_NAME, TOPICS_DIR_NAME)

#: The hidden directories this revision retires.
RAW_DIR_NAME = ".raw"
HISTORY_DIR_NAME = ".history"

#: ``<root>.pre-0085.bak``, a sibling of the root rather than a child of it:
#: inside, it would be walked as a collection by the very pass it protects.
BACKUP_SUFFIX = f".pre-{REVISION}.bak"

#: How many suffixed names to try before giving up on a colliding original.
_MAX_SUFFIX = 1000


def knowledge_root() -> pathlib.Path:
    """The directory the knowledge layer lives in, as 0085 resolved it.

    ``$COFFER_KNOWLEDGE_ROOT`` wins when set (tests point it at a temp
    directory); otherwise ``$HOME/.coffer/knowledge``, with ``~`` expanded when
    ``HOME`` is unset. A copy of the live helper, deliberately: this pass moves
    every file under whatever it returns, so it must keep returning what it
    returned the day this revision shipped.
    """
    override = os.environ.get("COFFER_KNOWLEDGE_ROOT")
    if override:
        return pathlib.Path(override)
    home = pathlib.Path(os.environ.get("HOME", "~")).expanduser()
    return home / ".coffer" / "knowledge"


@dataclass
class TreeMigrationReport:
    """What the pass actually did — logged by the caller, asserted by tests."""

    backup: str = ""
    sources_moved: int = 0
    originals_revealed: int = 0
    hidden_dirs_removed: int = 0
    lanes_created: int = 0
    collections: set[str] = field(default_factory=set)

    def __str__(self) -> str:
        collections = ", ".join(sorted(self.collections)) or "none"
        backup = self.backup or "not needed"
        return (
            f"{self.sources_moved} file(s) into sources/, "
            f"{self.originals_revealed} original(s) revealed, "
            f"{self.hidden_dirs_removed} hidden dir(s) removed, "
            f"{self.lanes_created} lane(s) created "
            f"across [{collections}]; backup: {backup}"
        )


def _exists(path: pathlib.Path) -> bool:
    """Whether anything occupies ``path`` — including a dangling symlink.

    ``Path.exists`` follows the link and answers False for one whose target is
    gone, which would make this pass move a file onto a name that is already
    taken by something a person can still see.
    """
    return path.is_symlink() or path.exists()


def _collections(root: pathlib.Path) -> list[pathlib.Path]:
    """Every collection directory, in a stable order.

    Hidden top-level entries are skipped: a collection is a directory a person
    named, and nothing Coffer writes at the root is one.
    """
    if not root.is_dir():
        return []
    return sorted(c for c in root.iterdir() if c.is_dir() and not c.name.startswith("."))


def _content_files(collection: pathlib.Path) -> list[tuple[pathlib.Path, pathlib.PurePath]]:
    """Every file that still has to move, with its collection-relative path.

    Everything under ``sources/`` or ``topics/`` is already where it belongs,
    and every hidden path is handled separately — ``.raw/`` by
    :func:`_reveal_originals`, ``.history/`` by deletion. The collection's own
    ``README.md`` stays at the root, outside both lanes, because it describes
    the collection rather than living in it (see "Keep the collection README
    out of the corpus"); a ``README.md`` inside a *nested* folder is ordinary
    content and moves with the rest.

    Extension is not a filter. The rewrite takes every content file, and a
    collection's root may hold an original an older build put there beside the
    Markdown; leaving it behind would strand it in a directory this pass is
    about to declare empty.
    """
    found: list[tuple[pathlib.Path, pathlib.PurePath]] = []
    for path in sorted(collection.rglob("*")):
        relative = path.relative_to(collection)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if relative.parts[0] in LANES:
            continue
        if not path.is_file():
            continue
        if len(relative.parts) == 1 and relative.name == README_NAME:
            continue
        found.append((path, relative))
    return found


def _needs_rewrite(collection: pathlib.Path) -> bool:
    """Whether this collection still holds anything the rewrite must touch.

    This is what makes a re-run free rather than merely harmless: a collection
    already in the new shape answers False, so no backup is taken, no file is
    renamed a second time, and no already-suffixed name grows another suffix.

    An empty directory outside the lanes does not count. It holds nothing to
    move, and treating it as work would make an empty folder a person left
    behind enough to trigger a fresh backup on every upgrade.
    """
    if (collection / RAW_DIR_NAME).is_dir() or (collection / HISTORY_DIR_NAME).is_dir():
        return True
    return bool(_content_files(collection))


def _free_path(candidate: pathlib.Path) -> pathlib.Path:
    """``candidate``, suffixed only if that name is already taken.

    Never overwrite. Two files that arrive at one name are two files — most
    often an uploaded original and a same-named source — and the one already on
    disk is the one a person may have edited.
    """
    if not _exists(candidate):
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    for n in range(2, _MAX_SUFFIX):
        alternative = candidate.with_name(f"{stem}-{n}{suffix}")
        if not _exists(alternative):
            return alternative
    raise ValueError(f"cannot find a free name beside {candidate}")


def _move(source: pathlib.Path, destination: pathlib.Path) -> pathlib.Path:
    """Move one file, creating the nesting it lands in. Returns where it went."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    target = _free_path(destination)
    shutil.move(str(source), str(target))
    return target


def _back_up(root: pathlib.Path, report: TreeMigrationReport) -> None:
    """Copy the whole root beside itself before anything moves.

    An existing backup is kept as it is and never refreshed. By the time a
    second run happens the root is already rewritten, so copying over the
    backup would replace the only pre-migration copy of the user's corpus with
    a copy of the post-migration one — turning the safety net into a duplicate
    of what it protects against.
    """
    backup = root.parent / f"{root.name}{BACKUP_SUFFIX}"
    report.backup = str(backup)
    if _exists(backup):
        logger.info("knowledge backup already present at %s", backup)
        return
    shutil.copytree(root, backup, symlinks=True)
    logger.info("knowledge root backed up to %s before the two-lane rewrite", backup)


def _move_content(
    collection: pathlib.Path, sources: pathlib.Path, report: TreeMigrationReport
) -> None:
    """Every content file into ``sources/``, with its nesting preserved.

    ``a/b.md`` at the collection root becomes ``sources/a/b.md``: the folders a
    person made are their own organisation of the material, and flattening them
    would discard a judgement Coffer has no business overruling (see "Allow
    nesting without giving it meaning").
    """
    for path, relative in _content_files(collection):
        _move(path, sources / relative)
        report.sources_moved += 1


def _reveal_originals(
    collection: pathlib.Path, sources: pathlib.Path, report: TreeMigrationReport
) -> None:
    """Every ``.raw/`` original into ``sources/``, visible, under its own name.

    Runs after :func:`_move_content` so a collision is resolved in the content
    file's favour: the Markdown someone has been reading keeps the name it had,
    and the original that shares it takes the suffix.
    """
    raw = collection / RAW_DIR_NAME
    if not raw.is_dir():
        return
    for path in sorted(raw.rglob("*")):
        if not path.is_file():
            continue
        _move(path, sources / path.relative_to(raw))
        report.originals_revealed += 1


def _remove_hidden(collection: pathlib.Path, report: TreeMigrationReport) -> None:
    """Delete ``.raw/`` and ``.history/``; neither survives this revision.

    ``.raw/`` is empty by now — its contents are in ``sources/`` — and
    ``.history/`` goes with whatever it still holds: it recorded what a rewrite
    replaced, and nothing rewrites a source.
    """
    for name in (RAW_DIR_NAME, HISTORY_DIR_NAME):
        hidden = collection / name
        if hidden.is_dir():
            shutil.rmtree(hidden, ignore_errors=True)
            report.hidden_dirs_removed += 1


def _prune_empty(collection: pathlib.Path) -> None:
    """Remove the folders the move emptied, deepest first.

    A folder that still holds something is left exactly as it is — this
    removes the husk of a moved directory, never a directory with content.
    """
    for path in sorted(collection.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if not path.is_dir() or path.is_symlink():
            continue
        relative = path.relative_to(collection)
        if relative.parts[0] in LANES or any(part.startswith(".") for part in relative.parts):
            continue
        if not any(path.iterdir()):
            path.rmdir()


def _ensure_lanes(collection: pathlib.Path, report: TreeMigrationReport) -> pathlib.Path:
    """Create ``sources/`` and ``topics/``, and return the first.

    Both are created even for a collection with nothing to move, and
    ``topics/`` is left empty on purpose: the lanes are the shape every surface
    and every path helper now assumes, so a collection missing one would read
    as broken rather than as new.
    """
    for lane in LANES:
        directory = collection / lane
        if not directory.is_dir():
            directory.mkdir(parents=True, exist_ok=True)
            report.lanes_created += 1
    return collection / SOURCES_DIR_NAME


def _retire_shared_skill(master_root: pathlib.Path | None) -> None:
    """Drop the shared ``coffer-knowledge`` master folder.

    A stale shared master left in the store would keep being delivered beside
    the generated skill — the same layer, described twice, one of the
    descriptions wrong.

    The removal is spelled out here rather than called out to the knowledge
    layer, as it once was. What that folder looked like stopped being a live
    fact the moment the layer stopped writing it: a migration describes the
    vault as it was on the day it ran, and reaching into today's code for that
    is how a one-time script acquires a dependency that has to keep compiling
    forever.
    """
    if master_root is None:
        return
    folder = master_root / "coffer-knowledge"
    if folder.is_dir() and not folder.is_symlink():
        shutil.rmtree(folder, ignore_errors=True)


def migrate(*, master_root: pathlib.Path | None = None) -> TreeMigrationReport:
    """Rewrite every collection into two lanes. Safe to run twice."""
    report = TreeMigrationReport()
    root = knowledge_root()
    collections = _collections(root)

    # The backup covers the whole root and is taken once, before the first
    # move — not per collection, which would photograph a tree half-rewritten.
    if any(_needs_rewrite(collection) for collection in collections):
        _back_up(root, report)

    for collection in collections:
        sources = _ensure_lanes(collection, report)
        _move_content(collection, sources, report)
        _reveal_originals(collection, sources, report)
        _remove_hidden(collection, report)
        _prune_empty(collection)
        report.collections.add(collection.name)

    _retire_shared_skill(master_root)
    return report
