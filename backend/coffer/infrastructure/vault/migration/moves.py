"""Moving the trees into their class directories, and back (plan q9 §3 step 4).

Every move is a rename, never a copy, so undoing it is a rename too and a
tree too large to copy moves as fast as a small one. A move whose target
already exists is refused rather than merged: merging two trees is a decision
this step cannot take for a person.

Links elsewhere on the machine that point into a moved tree (an agent's
memory directory linked into the old memory tree, a skill delivered as a
link into the old master folder) are reported, never touched: they are
outside Coffer's home, and the reconciler re-delivers skills on its own.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from coffer.infrastructure.vault.home import coffer_home
from coffer.infrastructure.vault.migration.errors import MigrationRefused
from coffer.infrastructure.vault.migration.places import TREE_MOVES, at
from coffer.infrastructure.vault.migration.record import Move

#: Where agents keep the directories Coffer may have linked into its trees.
_AGENT_DIRS = (".claude", ".codex")
_LINK_DEPTH = 3


def move_trees(home: Path, on_move: Callable[[Move], None]) -> list[Move]:
    """Rename every old tree that exists to its new place, calling
    ``on_move`` after each so the record never lags the disk."""
    done: list[Move] = []
    for source, target in TREE_MOVES:
        src, dst = at(home, source), at(home, target)
        if not src.exists() and not src.is_symlink():
            continue
        if dst.exists() or dst.is_symlink():
            raise MigrationRefused(f"cannot move {src} to {dst}: {dst} already exists")
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        move = Move(source=source, target=target)
        done.append(move)
        on_move(move)
    return done


def reverse_moves(home: Path, moves: list[Move]) -> list[str]:
    """Rename each moved tree back, newest first; answer what could not be."""
    problems: list[str] = []
    for move in reversed(moves):
        src, dst = at(home, move.target), at(home, move.source)
        if not src.exists() and not src.is_symlink():
            problems.append(f"{src} is gone; {dst} was not restored")
            continue
        if dst.exists() or dst.is_symlink():
            problems.append(f"{dst} exists again; {src} was left where it is")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
    return problems


def links_into_old_trees(home: Path) -> list[str]:
    """Links in the agents' directories that pointed into a tree that moved."""
    bases = {coffer_home(home), coffer_home(home).resolve()}
    old = [base / source for base in bases for source, _t in TREE_MOVES]
    found: list[str] = []
    for name in _AGENT_DIRS:
        root = home / name
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            depth = Path(dirpath).relative_to(root).parts
            if len(depth) >= _LINK_DEPTH:
                dirnames[:] = []
            for entry in [*dirnames, *filenames]:
                path = Path(dirpath) / entry
                if not path.is_symlink():
                    continue
                target = Path(os.path.normpath(Path(dirpath) / os.readlink(path)))
                if any(target == o or o in target.parents for o in old):
                    found.append(f"{path} -> {target}")
            dirnames[:] = [d for d in dirnames if not (Path(dirpath) / d).is_symlink()]
    return sorted(found)


__all__ = ["links_into_old_trees", "move_trees", "reverse_moves"]
