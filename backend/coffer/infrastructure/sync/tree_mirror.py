"""Differential convergence of a bundle directory (spec vault-sync).

Two helpers, one rule: **write only what changed, delete only what is gone,
never a blanket rmtree**. That rule is normative (spec vault-sync "Why deletion
is safe"): the working tree is what git three-way-merges, so a clear-and-rewrite
makes "this vault never absorbed it" indistinguishable from "this vault deleted
it", which is the 2026-07-10 mutual-deletion incident.

``_mirror_tree`` converges a destination tree on a *source tree* — live→bundle
on export and bundle→live on import. ``_converge_files`` converges a
destination directory on an *in-memory* set of documents, for the areas an
export serializes rather than copies (``resources/``, ``state/``,
``credentials/``). Same diff, same deletion discipline, one implementation of
each half.

Both accept ``protected``: destination-relative paths that MUST survive even
though the source does not produce them. Those are the retry set — documents
this vault failed to absorb — and deleting one would publish a deletion the
user never made.
"""

from __future__ import annotations

import pathlib
import shutil
from collections.abc import Mapping
from collections.abc import Set as AbstractSet


def _tree_files(root: pathlib.Path) -> dict[pathlib.Path, pathlib.Path]:
    """rel-path -> absolute path for every file under ``root``.

    Everything counts, hidden entries included: a knowledge scope keeps its
    ingested originals in ``.raw/`` and the revisions a tidy pass replaced in
    ``.history/``, and both are source of truth the other machine wants."""
    if not root.exists():
        return {}
    out: dict[pathlib.Path, pathlib.Path] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        out[path.relative_to(root)] = path
    return out


def _mirror_tree(
    src: pathlib.Path,
    dst: pathlib.Path,
    *,
    delete_missing: bool = True,
    protected: AbstractSet[str] = frozenset(),
) -> None:
    """Converge ``dst`` on ``src`` by copying only changed files and deleting
    only files gone from ``src`` — never a blanket rmtree.

    Used in both directions: live→bundle on export (``delete_missing=True``,
    so a bundle rewritten in place stops carrying what the vault deleted) and
    bundle→live on import (``delete_missing=False``: a bundle is a snapshot of
    one machine, never an assertion about what should exist here).

    ``protected`` holds POSIX paths relative to ``dst`` that survive the
    deletion pass regardless: on export those are the held paths, which this
    vault has not absorbed and therefore has not deleted either.
    """
    dst.mkdir(parents=True, exist_ok=True)
    src_files = _tree_files(src)
    dst_files = _tree_files(dst)
    for rel, src_path in src_files.items():
        target = dst_files.get(rel)
        if target is not None and target.read_bytes() == src_path.read_bytes():
            continue
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_path, out)
    if not delete_missing:
        return
    for rel in dst_files.keys() - src_files.keys():
        if rel.as_posix() in protected:
            continue
        (dst / rel).unlink(missing_ok=True)


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
