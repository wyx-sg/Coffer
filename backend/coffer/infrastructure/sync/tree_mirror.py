"""Tree mirroring for export bundles (spec 010).

``_mirror_tree`` converges a destination tree on a source tree diff-aware in
both directions: live→bundle on export (deleting what the vault no longer
holds, so a re-export is a faithful snapshot) and bundle→live on import with
``delete_missing=False``, because import never deletes.
"""

from __future__ import annotations

import pathlib
import shutil


def _tree_files(root: pathlib.Path, exclude: frozenset[str]) -> dict[pathlib.Path, pathlib.Path]:
    """rel-path -> absolute path for every file under ``root``, skipping any
    path with an excluded basename component."""
    if not root.exists():
        return {}
    out: dict[pathlib.Path, pathlib.Path] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in exclude for part in rel.parts):
            continue
        out[rel] = path
    return out


def _mirror_tree(
    src: pathlib.Path,
    dst: pathlib.Path,
    exclude: frozenset[str] = frozenset(),
    *,
    delete_missing: bool = True,
) -> None:
    """Converge ``dst`` on ``src`` by copying only changed files and deleting
    only files gone from ``src`` — never a blanket rmtree.

    Used in both directions: live→bundle on export (``delete_missing=True``,
    so a bundle rewritten in place stops carrying what the vault deleted) and
    bundle→live on import (``delete_missing=False``: a bundle is a snapshot of
    one machine, never an assertion about what should exist here).
    """
    dst.mkdir(parents=True, exist_ok=True)
    src_files = _tree_files(src, exclude)
    dst_files = _tree_files(dst, exclude)
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
        (dst / rel).unlink(missing_ok=True)
