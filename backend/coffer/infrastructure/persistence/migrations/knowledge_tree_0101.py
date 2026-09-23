"""One-way rewrite of the two lanes into one tree.

Spec knowledge "Migrate the two-lane corpus into the inbox".

Since 0085 a collection has been two visible lanes with different authors:
``sources/``, what a person, an upload or ``coffer__write`` put there, and
``topics/``, what the curation pass derived from it. The redesign makes a
collection **one tree of documents** that a person and curation write
together, with new knowledge arriving as material in a hidden ``.inbox/`` that
curation merges in.

Nothing in the old tree is simply renamed into the new one. The developer asked
for the whole corpus to be **distilled again**, so every Markdown file in both
lanes becomes inbox material, and the ordinary curation sweep folds them into
fresh documents one pass at a time. The topic documents go in first — they are
already organised by subject, so the first passes lay down a structure the
sources are then merged into — and the sources follow in the order they were
last touched. With no internal model configured, the sweep promotes each item
to a document as it stands, so nothing waits on a connection nobody set up.

What does not carry over is anything that is not Markdown: an upload's original
bytes lived beside its extracted text in ``sources/``, and the new layer keeps
knowledge, not the documents it arrived in. Those files survive only in the
backup.

**The backup comes first.** This pass empties the tree an agent reads until the
sweep refills it, and it deletes the originals outright. Before a single file
moves, the whole root is copied to a sibling directory named after this
revision, and the path is logged. A second run reuses that backup rather than
photographing a tree this pass has already rewritten.

Idempotent throughout. A collection with neither lane is one this pass walks
past, so running the upgrade twice is a no-op rather than a second backup.

Frozen, like ``knowledge_tree_0085``: a migration describes one moment in
history and must not change behaviour because the product's live path helpers
later did. The lane names, the inbox name and the root resolution below are
copies, not imports.
"""

from __future__ import annotations

import logging
import os
import pathlib
import shutil
import time
from dataclasses import dataclass, field

logger = logging.getLogger("alembic.runtime.migration")

#: The revision this rewrite belongs to. It names the backup directory, so a
#: user who finds one can tell which upgrade made it.
REVISION = "0101"

README_NAME = "README.md"
MARKDOWN_SUFFIX = ".md"

#: The two lanes this revision retires, in the order their files are queued.
TOPICS_DIR_NAME = "topics"
SOURCES_DIR_NAME = "sources"
LANES = (TOPICS_DIR_NAME, SOURCES_DIR_NAME)

#: Where material waits to be merged, as 0101 introduced it.
INBOX_DIR_NAME = ".inbox"

#: ``<root>.pre-0101.bak``, a sibling of the root rather than a child of it:
#: inside, it would be walked as a collection by the very pass it protects.
BACKUP_SUFFIX = f".pre-{REVISION}.bak"

#: How many suffixed names to try before giving up on a colliding item.
_MAX_SUFFIX = 1000


def knowledge_root() -> pathlib.Path:
    """The directory the knowledge layer lives in, as 0101 resolved it.

    ``$COFFER_KNOWLEDGE_ROOT`` wins when set (tests point it at a temp
    directory); otherwise ``$HOME/.coffer/knowledge``. A copy of the live
    helper, deliberately: this pass moves every file under whatever it returns.
    """
    override = os.environ.get("COFFER_KNOWLEDGE_ROOT")
    if override:
        return pathlib.Path(override)
    home = pathlib.Path(os.environ.get("HOME", "~")).expanduser()
    return home / ".coffer" / "knowledge"


@dataclass
class OneTreeReport:
    """What the pass actually did — logged by the caller, asserted by tests."""

    backup: str = ""
    queued: int = 0
    dropped: int = 0
    collections: set[str] = field(default_factory=set)

    def __str__(self) -> str:
        collections = ", ".join(sorted(self.collections)) or "none"
        backup = self.backup or "not needed"
        return (
            f"{self.queued} file(s) queued for re-curation, "
            f"{self.dropped} non-Markdown file(s) left to the backup "
            f"across [{collections}]; backup: {backup}"
        )


def _collections(root: pathlib.Path) -> list[pathlib.Path]:
    if not root.is_dir():
        return []
    return sorted(
        d
        for d in root.iterdir()
        if d.is_dir() and not d.is_symlink() and not d.name.startswith(".")
    )


def _needs_rewrite(collection: pathlib.Path) -> bool:
    return any((collection / lane).is_dir() for lane in LANES)


def _back_up(root: pathlib.Path, report: OneTreeReport) -> None:
    backup = root.with_name(root.name + BACKUP_SUFFIX)
    if not backup.exists():
        shutil.copytree(root, backup, symlinks=True)
    report.backup = str(backup)
    logger.info("knowledge root backed up to %s before merging the lanes", backup)


def _lane_files(lane: pathlib.Path) -> list[pathlib.Path]:
    """Every regular file under one lane, hidden entries skipped."""
    found: list[pathlib.Path] = []
    for root, dirnames, filenames in os.walk(lane):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            path = pathlib.Path(root) / name
            if name.startswith(".") or path.is_symlink() or not path.is_file():
                continue
            found.append(path)
    return found


def _item_name(lane: pathlib.Path, path: pathlib.Path) -> str:
    """A flat inbox name that still says where the file came from."""
    relative = path.relative_to(lane).with_suffix("")
    return "-".join([lane.name, *relative.parts]) + MARKDOWN_SUFFIX


def _free(directory: pathlib.Path, name: str) -> pathlib.Path:
    candidate = directory / name
    if not (candidate.exists() or candidate.is_symlink()):
        return candidate
    stem = candidate.stem
    for n in range(2, _MAX_SUFFIX):
        candidate = directory / f"{stem}-{n}{MARKDOWN_SUFFIX}"
        if not (candidate.exists() or candidate.is_symlink()):
            return candidate
    raise FileExistsError(str(directory / name))


def _queue(collection: pathlib.Path, report: OneTreeReport) -> None:
    """Move both lanes' Markdown into the inbox, topics first, then drop them."""
    inbox = collection / INBOX_DIR_NAME
    ordered: list[tuple[pathlib.Path, pathlib.Path]] = []
    for lane_name in LANES:
        lane = collection / lane_name
        if not lane.is_dir():
            continue
        files = _lane_files(lane)
        documents = [p for p in files if p.name.endswith(MARKDOWN_SUFFIX) and p.name != README_NAME]
        report.dropped += len(files) - len(documents)
        if lane_name == SOURCES_DIR_NAME:
            # Sources in the order they were last touched, so material is
            # merged in the order it was written.
            documents.sort(key=lambda p: p.stat().st_mtime)
        ordered += [(lane, p) for p in documents]

    if ordered:
        inbox.mkdir(exist_ok=True)
    # The inbox is drained oldest-first by mtime, so each item's mtime is set
    # to its place in the queue: one second apart, ending now.
    now = time.time()
    for index, (lane, path) in enumerate(ordered):
        target = _free(inbox, _item_name(lane, path))
        path.rename(target)
        stamp = now - (len(ordered) - index)
        os.utime(target, (stamp, stamp))
        report.queued += 1

    for lane_name in LANES:
        lane = collection / lane_name
        if lane.is_dir() and not lane.is_symlink():
            shutil.rmtree(lane)


def migrate() -> OneTreeReport:
    """Queue every collection's lanes for re-curation. Safe to run twice."""
    report = OneTreeReport()
    root = knowledge_root()
    collections = [c for c in _collections(root) if _needs_rewrite(c)]
    if not collections:
        return report
    # The backup covers the whole root and is taken once, before the first
    # move — not per collection, which would photograph a tree half-rewritten.
    _back_up(root, report)
    for collection in collections:
        _queue(collection, report)
        report.collections.add(collection.name)
    return report


__all__ = ["BACKUP_SUFFIX", "OneTreeReport", "knowledge_root", "migrate"]
