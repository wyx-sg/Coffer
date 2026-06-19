"""Filesystem-facing scope helpers for the shared knowledge substrate.

Computes the git-root of a working directory (walking up for a ``.git`` marker)
and derives a **deterministic** project ULID from that root so the same project
always resolves to the same per-project scope across sessions / machines without
a registry table. The git-root walk is the only filesystem access here.

Lives in the kind-agnostic ``infrastructure/knowledge`` substrate so both faces
share one implementation: the memory face (``infrastructure/memory/scope_fs``
re-exports these) and the KB face (per-project document scope, ADR-030). The
composition root injects ``git_root`` / ``project_ulid`` where resolution is
needed (the application layer never imports infrastructure directly).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ULID_LEN = 26


def git_root(cwd: str | Path) -> Path | None:
    """The nearest ancestor of ``cwd`` containing a ``.git`` entry, or ``None``.

    ``.git`` may be a directory (normal repo) or a file (worktree / submodule).
    """
    start = Path(cwd).expanduser()
    try:
        start = start.resolve()
    except OSError:
        return None
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def project_ulid(root: str | Path) -> str:
    """A deterministic 26-char Crockford-base32 id for a project root.

    Not a time-ordered ULID — it is a stable content-addressed id of the
    absolute root path, so the same checkout always maps to the same scope.
    """
    digest = hashlib.sha256(str(Path(root)).encode("utf-8")).digest()
    value = int.from_bytes(digest[:16], "big")  # 128 bits, ULID-width
    out = ["0"] * _ULID_LEN
    for i in range(_ULID_LEN - 1, -1, -1):
        out[i] = _CROCKFORD[value & 0x1F]
        value >>= 5
    return "".join(out)
