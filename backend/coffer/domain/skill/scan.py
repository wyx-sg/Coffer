"""Classify unmanaged skills found in an agent's skill location(s).

A skill directory entry is *Coffer-managed* when it is a symlink whose
resolved target lives inside the master store root (``~/.coffer/skills/``).
Everything else is *unmanaged*:

- **Dot-entries** (``name.startswith(".")``) — internal entries such as
  ``.system`` used by Codex — are silently excluded; they are never skills.
- **Plain files** (``is_dir=False`` with no ``link_target``) — not
  skill-shaped; silently excluded.
- **Foreign links** — symlinks whose target is outside the master store.
  They are listed as ``UnmanagedSkill(foreign_link=True)`` to surface them
  to the user; they are never adoptable (origin is unknown).
- **Plain directories** — hand-copied or installed by another tool; listed
  as ``UnmanagedSkill(foreign_link=False)`` and adoptable.

This module is **pure domain code** — it contains no filesystem I/O.
Filesystem scanning is the responsibility of the infrastructure layer, which
builds ``ScanEntry`` values and passes them to ``classify``.

``scan_locations`` is intentionally kept in ``coffer.domain.agent.scan``
(not here) because it depends on ``AgentType``; the import-linter contracts
(Contract 5c in ``pyproject.toml``) forbid ``coffer.domain.skill`` from
importing ``coffer.domain.agent``.  Infrastructure / application code that
needs both should import ``classify`` from here and ``scan_locations`` from
``coffer.domain.agent.scan``.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass


@dataclass(frozen=True)
class ScanEntry:
    """One directory entry found in an agent skill location (built by infrastructure)."""

    name: str
    path: pathlib.Path
    is_dir: bool
    # Fully resolved ABSOLUTE target when the entry is a symlink — relative
    # targets would silently misclassify managed links as unmanaged.
    link_target: pathlib.Path | None = None


@dataclass(frozen=True)
class UnmanagedSkill:
    """A skill-shaped entry Coffer does not manage."""

    name: str
    path: pathlib.Path
    foreign_link: bool  # symlink pointing outside the master store — listed, never adoptable


def classify(entries: list[ScanEntry], *, master_root: pathlib.Path) -> list[UnmanagedSkill]:
    """Filter *entries* down to unmanaged, skill-shaped items.

    Rules (applied in order):
    1. Dot-entries are excluded (internal / hidden).
    2. Entries whose ``link_target`` is inside ``master_root`` (including any
       subpath thereof) are Coffer-managed — excluded.
    3. Plain files (``is_dir=False``, no ``link_target``) are not
       skill-shaped — excluded.
    4. Everything else is unmanaged: links pointing outside the master store
       (directory- or file-shaped) get ``foreign_link=True``, plain
       directories get ``foreign_link=False``.

    Order of the input is preserved. ``master_root`` and every
    ``link_target`` must be absolute (resolved) paths — relative paths would
    make rule 2 silently never match.
    """
    if not master_root.is_absolute():
        raise ValueError(f"master_root must be absolute, got {master_root}")
    out: list[UnmanagedSkill] = []
    for e in entries:
        if e.link_target is not None and not e.link_target.is_absolute():
            raise ValueError(f"link_target must be resolved/absolute, got {e.link_target}")
        if e.name.startswith("."):
            continue  # .system & hidden entries
        if e.link_target is not None and e.link_target.is_relative_to(master_root):
            continue  # Coffer-managed delivery link
        if e.link_target is None and not e.is_dir:
            continue  # plain file — not skill-shaped
        out.append(UnmanagedSkill(name=e.name, path=e.path, foreign_link=e.link_target is not None))
    return out
