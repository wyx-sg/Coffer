"""Differential convergence of a bundle directory (spec vault-sync).

Two helpers, one rule: **write only what changed, delete only what is gone,
never a blanket rmtree**. That rule is normative (spec vault-sync "Why deletion
is safe"): the working tree is what git three-way-merges, so a clear-and-rewrite
makes "this vault never absorbed it" indistinguishable from "this vault deleted
it", which is the 2026-07-10 mutual-deletion incident.

``_mirror_tree`` converges a destination tree on a *source tree* — the live
knowledge and skill directories into the working tree. ``_converge_files``
converges a destination directory on an *in-memory* set of documents, for the
areas an export serializes rather than copies (``resources/``, ``state/``,
``credentials/``). Same diff, same deletion discipline, one implementation of
each half.

Both accept ``protected``: destination-relative paths that MUST survive even
though the source does not produce them. Those are the retry set — documents
this vault failed to absorb — and deleting one would publish a deletion the
user never made.

Both walk with :func:`_tree_files`, which sees only **regular files that are
not inside a ``.git`` directory**. A symlink is skipped without being followed:
what it points at is not vault content, and a link to a file outside the vault
would otherwise be copied into the working tree and pushed. A nested ``.git``
is skipped because those are another repository's internals — git will not
track them, and a working tree that contained them would confuse the merge.
"""

from __future__ import annotations

import os
import pathlib
from collections.abc import Mapping
from collections.abc import Set as AbstractSet

_GIT_DIR = ".git"


def _tree_files(
    root: pathlib.Path, skipped: list[str] | None = None
) -> dict[pathlib.Path, pathlib.Path]:
    """rel-path -> absolute path for every regular file under ``root``.

    Hidden entries count: a knowledge scope keeps its ingested originals in
    ``.raw/`` and the revisions a tidy pass replaced in ``.history/``, and both
    are source of truth the other machine wants. Symlinks (to files or to
    directories) and anything named ``.git`` are left out and, when ``skipped``
    is given, their root-relative POSIX paths are appended to it so the caller
    can say so once."""
    if not root.exists():
        return {}
    out: dict[pathlib.Path, pathlib.Path] = {}
    _walk(root, root, out, skipped)
    return out


def _walk(
    root: pathlib.Path,
    directory: pathlib.Path,
    out: dict[pathlib.Path, pathlib.Path],
    skipped: list[str] | None,
) -> None:
    with os.scandir(directory) as entries:
        listing = sorted(entries, key=lambda e: e.name)
    for entry in listing:
        path = pathlib.Path(entry.path)
        rel = path.relative_to(root)
        if entry.name == _GIT_DIR or entry.is_symlink():
            if skipped is not None:
                skipped.append(rel.as_posix())
            continue
        if entry.is_dir(follow_symlinks=False):
            _walk(root, path, out, skipped)
        elif entry.is_file(follow_symlinks=False):
            out[rel] = path


def _under(rel: str, prefixes: AbstractSet[str]) -> bool:
    """Whether a tree-relative POSIX path sits inside one of ``prefixes``.

    The prefixes are directory prefixes and carry their trailing ``/``, so
    ``skills/coffer-guide/`` never matches ``skills/coffer-guidelines/``.
    """
    return any(rel.startswith(prefix) for prefix in prefixes)


def _excluding(
    files: dict[pathlib.Path, pathlib.Path], prefixes: AbstractSet[str]
) -> dict[pathlib.Path, pathlib.Path]:
    """``files`` without the entries under any of ``prefixes``."""
    if not prefixes:
        return files
    return {rel: path for rel, path in files.items() if not _under(rel.as_posix(), prefixes)}


def _mirror_tree(
    src: pathlib.Path,
    dst: pathlib.Path,
    *,
    protected: AbstractSet[str] = frozenset(),
    excluded: AbstractSet[str] = frozenset(),
) -> list[str]:
    """Converge ``dst`` on ``src`` by copying only changed files and deleting
    only files gone from ``src`` — never a blanket rmtree.

    Runs live→bundle on every serialization, so a bundle rewritten in place
    stops carrying what the vault deleted. ``protected`` holds POSIX paths
    relative to ``dst`` that survive the deletion pass regardless: those are
    the held paths, which this vault has not absorbed and therefore has not
    deleted either.

    ``excluded`` holds directory prefixes, relative to both trees, that this
    mirror **does not see at all**: nothing under one is copied out, and
    nothing under one is deleted from ``dst`` either. Both halves matter and
    they are not the same rule as ``protected``.

    * Not copied, because what lives there is derived output every machine
      regenerates for itself and no two machines render identically (spec
      vault-sync "Withhold derived output in both halves").
    * Not deleted, because the working tree may already carry a copy an older
      build published. Removing it would stage a deletion — and a deletion is
      the one change every machine acts on. A machine still running that older
      build would take it as an instruction to unlink its own live master
      folder, which is exactly the mid-upgrade surprise this change exists to
      avoid. The stale bytes are inert instead: no build that has this rule
      reads them, writes them or diffs them again.

    Returns the ``src``-relative paths it skipped — symlinks and ``.git``
    entries — so the caller can report them. Excluded paths are not reported:
    a symlink is a surprise worth a line in the log, while this is policy.
    """
    dst.mkdir(parents=True, exist_ok=True)
    seen: list[str] = []
    src_files = _excluding(_tree_files(src, seen), excluded)
    dst_files = _excluding(_tree_files(dst), excluded)
    skipped = [rel for rel in seen if not _under(rel, excluded)]
    for rel, src_path in src_files.items():
        target = dst_files.get(rel)
        if target is not None and target.read_bytes() == src_path.read_bytes():
            continue
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(src_path.read_bytes())
    for rel in dst_files.keys() - src_files.keys():
        if rel.as_posix() in protected:
            continue
        (dst / rel).unlink(missing_ok=True)
    return skipped


def _converge_files(
    dst: pathlib.Path,
    desired: Mapping[str, bytes],
    *,
    protected: AbstractSet[str] = frozenset(),
) -> None:
    """Converge ``dst`` on an in-memory set of documents, exactly as
    ``_mirror_tree`` converges it on a source tree.

    ``desired`` maps a POSIX path relative to ``dst`` to the bytes that path
    must hold. A file whose bytes already match is left alone — untouched, so
    its mtime does not move and an unchanged vault stages nothing. A file
    ``desired`` does not name is removed, because the serializer produces every
    document this vault holds and so its absence is a real deletion — unless it
    is in ``protected``, which the export must preserve rather than publish.

    An empty ``desired`` never conjures the directory: an export that carries
    no credentials must leave no ``credentials/`` behind.
    """
    if not desired and not dst.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    existing = {rel.as_posix(): path for rel, path in _tree_files(dst).items()}
    for rel, payload in desired.items():
        current = existing.get(rel)
        if current is not None and current.read_bytes() == payload:
            continue
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(payload)
    for rel in existing.keys() - desired.keys() - set(protected):
        (dst / rel).unlink(missing_ok=True)
