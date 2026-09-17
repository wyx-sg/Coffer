"""Writing the knowledge directory, and reading one file out of it.

What the directory *looks like* — the counts, the levels, the walks a
catalogue is built from — is ``catalogue.py``. This module is the half that
changes bytes.

Every operation here is a filesystem operation and nothing else: no index is
updated, because there is none (spec knowledge FR-001). That is what lets a
person's edit in their own editor and an agent's ``coffer__write`` reach the
same bytes with nothing in between.

What this module does *not* do is decide which lane a caller may touch. It
takes lane-qualified paths and resolves them through
``paths.require_lane``; the rule that curation writes only ``topics/`` and
everyone else only ``sources/`` is enforced by the callers that name the lane
(``application.knowledge.service`` and ``application.knowledge.curate_tools``).
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

#: Frontmatter key carrying when curation last consumed a source (FR-028).
#: Written by Coffer into a file a person owns, deliberately: it is feedback
#: the person can see in their own editor, and it means the watermark needs no
#: state file, no table and nothing to keep level with the disk.
INGESTED_AT_KEY = "coffer_ingested_at"

#: The frontmatter keys this layer writes, in render order (FR-003). Anything
#: else a person put in the file is kept and rendered after them: FR-003 says
#: what Coffer writes, not what a person may not.
_ORDERED_KEYS = ("title", "description", "actor", "created_at", "updated_at", INGESTED_AT_KEY)


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
        ingested_at=str(fm.get(INGESTED_AT_KEY) or ""),
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

    The tail matters. ``mark_ingested`` rewrites a file a *person* owns to add
    one stamp, unattended, every time curation consumes it — so dropping a key
    it does not recognise would quietly delete their own `tags:` or
    `reviewed_by:` from the lane this design promises is theirs.
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
) -> KnowledgeFile:
    """Create a file under ``directory``, or replace the one at ``relpath``.

    Both are knowledge-root-relative and lane-qualified; the caller decides
    which lane, and ``paths.require_lane`` refuses anything outside one.
    Replacing preserves ``created_at`` so the file keeps its own history even
    though nothing but the file records it, and drops any prior
    ``coffer_ingested_at``: new bytes are material curation has not seen.
    """
    now = _now()
    created = now
    if relpath is not None:
        paths.require_lane(relpath)
        target = paths.resolve(relpath)
        if target.is_file():
            existing, _ = split_frontmatter(target.read_text(encoding="utf-8", errors="replace"))
            created = str(existing.get("created_at") or now)
    else:
        paths.require_lane(f"{directory.strip('/')}/placeholder.md")
        parent = paths.resolve(directory)
        parent.mkdir(parents=True, exist_ok=True)
        name = unique_name(parent, slugify(title))
        target = parent / name
    _atomic_write(
        target,
        _render(
            {
                "title": title,
                "description": description,
                "actor": actor,
                "created_at": created,
                "updated_at": now,
            },
            body,
        ),
    )
    return read_file(paths.relative_of(target))


def write_original(collection: str, filename: str, data: bytes) -> str:
    """Keep an uploaded document's own bytes in ``sources/``, visibly (FR-016).

    Unlike the ``.raw/`` directory this replaces, the original is an ordinary
    file beside the text extracted from it: there is no retrieval surface it
    could pollute, so there is nothing for hiding it to buy, and a person
    scrolling their own ``sources/`` should see what they actually sent.
    """
    directory = paths.sources_dir(collection)
    directory.mkdir(parents=True, exist_ok=True)
    suffix = pathlib.Path(filename).suffix
    stem = slugify(pathlib.Path(filename).stem)
    name = stem + suffix
    if (directory / name).exists():
        for n in range(2, 1000):
            candidate = f"{stem}-{n}{suffix}"
            if not (directory / candidate).exists():
                name = candidate
                break
    target = directory / name
    paths.assert_inside_root(target, paths.relative_of(target))
    target.write_bytes(data)
    return paths.relative_of(target)


def delete_file(relpath: str) -> None:
    paths.require_lane(relpath)
    path = paths.resolve(relpath)
    if not path.is_file():
        raise KnowledgeFileNotFound(relpath)
    path.unlink()


def mark_ingested(relpath: str, *, when: str | None = None) -> None:
    """Stamp a source as consumed by curation, changing nothing else (FR-028).

    Called only after a pass completes. A pass that fails leaves the stamp
    unset, so the material is curated by a later sweep rather than lost to one
    that half-ran.
    """
    paths.require_lane(relpath, expected=paths.SOURCES_DIR_NAME)
    path = paths.resolve(relpath)
    if not path.is_file():
        raise KnowledgeFileNotFound(relpath)
    fm, body = split_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    # Values are carried through as they were parsed, not stringified: a YAML
    # list a person wrote must come back a YAML list, or the stamp has still
    # damaged their file — just more quietly than deleting the key would.
    merged: dict[str, Any] = {k: v for k, v in fm.items() if v not in (None, "")}
    stamp = when or _now()
    merged[INGESTED_AT_KEY] = stamp
    _atomic_write(path, _render(merged, body))
    # Writing the stamp is itself a modification, so without this the file's
    # mtime would land just after the stamp it carries and `pending_sources`
    # would hand the same source back on every sweep, forever. Setting the
    # mtime to the stamp makes the file say the true thing — its last
    # modification *was* this stamping — and any later edit by a person moves
    # mtime past it again, which is the whole comparison.
    with contextlib.suppress(OSError):
        seconds = _parse(stamp)
        if seconds:
            os.utime(path, (seconds, seconds))


def pending_sources(collection: str) -> tuple[str, ...]:
    """Sources changed since curation last consumed them, oldest first.

    The comparison is the file's own modification time against its own
    ``coffer_ingested_at``: no state file, no table, and nothing that can
    disagree with the disk. A file a person has just edited is newer than its
    stamp and comes back; one nothing has touched does not.
    """
    directory = paths.sources_dir(collection)
    if not directory.is_dir():
        return ()
    pending: list[tuple[float, str]] = []
    for root, dirnames, filenames in os.walk(directory):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if not is_markdown(name):
                continue
            # One read and one stat per file: this runs on every sweep, so it
            # is deliberately not built on `walk_files` + `read_file`, which
            # would open each source three times a minute for nothing.
            path = pathlib.Path(root) / name
            fm, _ = split_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
            mtime = path.stat().st_mtime
            stamp = str(fm.get(INGESTED_AT_KEY) or "")
            if stamp and _parse(stamp) >= mtime:
                continue
            pending.append((mtime, paths.relative_of(path)))
    return tuple(relpath for _, relpath in sorted(pending))


def _parse(stamp: str) -> float:
    try:
        return datetime.fromisoformat(stamp).timestamp()
    except ValueError:
        return 0.0


def create_collection_dir(name: str) -> pathlib.Path:
    """Create a collection and both of its lanes (FR-008)."""
    directory = paths.collection_dir(name)
    directory.mkdir(parents=True, exist_ok=True)
    for lane in paths.LANES:
        paths.lane_dir(name, lane).mkdir(parents=True, exist_ok=True)
    return directory


def remove_collection_dir(name: str) -> None:
    directory = paths.collection_dir(name)
    if directory.is_dir():
        shutil.rmtree(directory)
