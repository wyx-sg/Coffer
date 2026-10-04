"""Writing the knowledge directory, and reading one file out of it.

What the directory *looks like* — the counts, the levels, the walks a
catalogue is built from — is ``catalogue.py``. This module is the half that
changes bytes.

Every operation here is a filesystem operation and nothing else: no index is
updated, because there is none (spec knowledge "Store each collection as one
tree of Markdown files"). That is what lets a person's edit in their own
editor and an agent's reach the same bytes with nothing in between.

Two kinds of file live under a collection, and this module is where they meet:

* **Documents** — the visible tree. A person edits them in their own editor,
  an agent with its own file tools; Coffer writes them through
  :func:`write_file`.
* **Material** — the hidden ``.inbox/``, written and read by ``inbox.py``. A
  file waits there only until the next sweep promotes it into a document (see
  "Promote submitted material at once").
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
from datetime import UTC, datetime
from typing import Any

from coffer.domain.knowledge.entry import ACTOR_AGENT, KnowledgeFile
from coffer.domain.knowledge.errors import (
    KnowledgeFileConflict,
    KnowledgeFileNotFound,
    UnsafeKnowledgePath,
)
from coffer.domain.vault.errors import VaultFileStale
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.catalogue import is_markdown
from coffer.infrastructure.knowledge.frontmatter import (
    render_frontmatter,
    replace_body,
    split_frontmatter,
)
from coffer.infrastructure.knowledge.history import Transaction
from coffer.infrastructure.knowledge.naming import slugify, unique_name

#: The frontmatter keys this layer writes, in render order (see "Carry title,
#: description and actor in frontmatter"). Anything else a person put in the
#: file is kept and rendered after them: that requirement says what Coffer
#: writes, not what a person may not.
_ORDERED_KEYS = ("title", "description", "actor", "created_at", "updated_at")


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def fingerprint(raw: bytes) -> str:
    """sha256 hex of a file's bytes — the same digest a skill file's read carries.

    What an edit hands back (see "Save a document edited in the web UI"): a
    file whose bytes moved since the editor loaded them is refused, not
    overwritten.
    """
    return hashlib.sha256(raw).hexdigest()


def decode(raw: bytes) -> str:
    """Bytes as text, newlines normalised the way ``Path.read_text`` does."""
    text = raw.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_file(relpath: str) -> KnowledgeFile:
    """A file's frontmatter and body, plus the absolute paths a surface shows."""
    path = paths.resolve(relpath)
    if not path.is_file():
        raise KnowledgeFileNotFound(relpath)
    raw = path.read_bytes()
    fm, body = split_frontmatter(decode(raw))
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
        fingerprint=fingerprint(raw),
    )


def atomic_write(path: pathlib.Path, text: str) -> None:
    """Write ``text`` to ``path`` through a sibling temp file and one rename.

    The guard is re-run here, on the parent that exists by now, because this
    is the last step before bytes land: ``resolve`` checked the path when the
    caller named it, and nothing between then and now may have redirected the
    directory out of the root. The temp file is opened ``O_NOFOLLOW`` and
    ``O_EXCL`` so a planted symlink under its name cannot carry the bytes
    elsewhere, and the final rename never follows a link.
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


def render(frontmatter: dict[str, Any], body: str) -> str:
    """The known keys in their fixed order, then anything else, unharmed.

    The tail matters. A save rewrites a file a *person* also edits,
    so dropping a key it does not recognise would quietly delete their own
    `tags:` or `reviewed_by:` from a document.
    """
    ordered = {k: frontmatter[k] for k in _ORDERED_KEYS if frontmatter.get(k)}
    extra = {k: v for k, v in frontmatter.items() if k not in _ORDERED_KEYS and v is not None}
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
    """Create a document under ``directory``, or replace the one at ``relpath``.

    Both are knowledge-root-relative. ``directory`` is a collection or a folder
    inside one; ``relpath`` must name a document (``paths.require_document``).
    Replacing preserves ``created_at`` so the file keeps its own history even
    though nothing but the file records it.
    """
    now = timestamp()
    created = now
    carried: dict[str, Any] = {}
    if relpath is not None:
        paths.require_document(relpath)
        target = paths.resolve(relpath)
        if target.is_file():
            existing, _ = split_frontmatter(target.read_text(encoding="utf-8", errors="replace"))
            created = str(existing.get("created_at") or now)
            # A person's own keys (`tags:`, `reviewed_by:`, `draft: false`)
            # outlive a rewrite; only the keys Coffer owns are replaced.
            carried = {k: v for k, v in existing.items() if k not in _ORDERED_KEYS}
    else:
        parent = paths.resolve(directory)
        parent.mkdir(parents=True, exist_ok=True)
        name = unique_name(parent, slugify(title))
        target = parent / name
        paths.require_document(paths.relative_of(target))
    frontmatter: dict[str, Any] = {
        **carried,
        "title": title,
        "description": description,
        "actor": actor,
        "created_at": created,
        "updated_at": now,
    }
    text = render(frontmatter, body)
    atomic_write(target, text)
    return read_file(paths.relative_of(target))


def save_body(
    relpath: str, body: str, *, expected_fingerprint: str, tx: Transaction | None = None
) -> KnowledgeFile:
    """Replace a document's body, keeping its frontmatter as it stands.

    A person's edit from the web UI (see "Save a document edited in the web
    UI"). ``expected_fingerprint`` is what the editor's read carried: a file
    whose bytes moved since — a person's own editor, an agent — is
    refused with ``KnowledgeFileConflict`` and left untouched. The write goes
    through the operation's vault transaction (``tx``), which compares the
    fingerprint again under the vault's write lock, so a change that lands
    between this read and the write is refused the same way.

    Only a Markdown document can be saved: ``require_document`` keeps the
    collection, its README and the inbox out of reach, and a file a person
    dropped in that is not Markdown is bytes this route has no business
    rewriting as text.
    """
    paths.require_document(relpath)
    path = paths.resolve(relpath)
    if not path.is_file():
        raise KnowledgeFileNotFound(relpath)
    if not is_markdown(path.name):
        raise UnsafeKnowledgePath(relpath, "only a Markdown document can be edited")
    raw = path.read_bytes()
    if fingerprint(raw) != expected_fingerprint:
        raise _conflict(relpath, raw)
    text = replace_body(decode(raw), body)
    if tx is None:
        atomic_write(path, text)
        return read_file(relpath)
    try:
        tx.write(relpath, text.encode("utf-8"), expected_fingerprint)
    except VaultFileStale as exc:
        raise _conflict(relpath, path.read_bytes() if path.is_file() else b"") from exc
    return read_file(relpath)


def _conflict(relpath: str, raw: bytes) -> KnowledgeFileConflict:
    """The refusal carries the document as it is now, so the editor can Reload,
    Compare or Copy the person's text without a second save over it."""
    _, current = split_frontmatter(decode(raw))
    return KnowledgeFileConflict(
        relpath, current_body=current, current_fingerprint=fingerprint(raw)
    )


def write_bytes(relpath: str, raw: bytes) -> None:
    """Put a document's exact bytes back — a restored version."""
    paths.require_document(relpath)
    path = paths.resolve(relpath)
    atomic_write(path, decode(raw))


def delete_file(relpath: str) -> None:
    paths.require_document(relpath)
    path = paths.resolve(relpath)
    if not path.is_file():
        raise KnowledgeFileNotFound(relpath)
    path.unlink()


def create_collection_dir(name: str) -> pathlib.Path:
    """Create a collection's directory (see "Create collections only deliberately")."""
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
    somebody made by hand under ``~/.coffer/vault/knowledge/``, or one a failed
    cleanup left behind — and the check has to be explicit, because
    ``rename(2)`` would not make it for us: it fails on a non-empty target but
    quietly succeeds over an *empty* directory. Neither outcome is one to pick
    by accident. Merging adopts files into the corpus that nobody registered;
    replacing destroys them.
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
