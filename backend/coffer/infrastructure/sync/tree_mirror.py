"""Tree mirroring for the sync workspace (spec 010).

``_mirror_tree`` converges a destination tree on a source tree diff-aware in
both directions: workspace→live (the live trees are watched by auto-sync and
hold machine-local derived files a rewrite would destroy) and live→workspace
(where ``delete_missing=False`` protects not-yet-imported remote files).
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

    Used in both directions: workspace→live (the live trees are watched by the
    auto-sync watcher and hold machine-local derived files a rewrite would
    delete) and live→workspace (where ``delete_missing=False`` keeps
    remote-authored files this machine has not imported yet — exporting their
    absence would delete them from every other machine).
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
