"""Parsing what ``git log`` and ``git status`` answer over the vault."""

from __future__ import annotations

from datetime import UTC, datetime

from coffer.domain.vault.history import ADDED, MODIFIED, REMOVED, Commit, PathChange
from coffer.domain.vault.writers import parse_meta

#: One record: a record separator, the commit id, its parents, its committer
#: time and its raw message, then a group separator before the ``--raw`` /
#: ``--numstat`` lines.
LOG_FORMAT = "--format=%x1e%H%x1f%P%x1f%ct%x1f%B%x1d"


def _status(letter: str) -> str:
    return {"A": ADDED, "D": REMOVED}.get(letter[:1], MODIFIED)


def parse_log(raw: bytes) -> list[Commit]:
    """Every record of a ``LOG_FORMAT`` log run with ``--raw --numstat``."""
    out: list[Commit] = []
    for record in raw.decode("utf-8", "replace").split("\x1e"):
        if not record.strip():
            continue
        head, _, tail = record.partition("\x1d")
        version, _, rest = head.partition("\x1f")
        parents, _, rest = rest.partition("\x1f")
        when, _, body = rest.partition("\x1f")
        statuses: dict[str, str] = {}
        counts: dict[str, tuple[int, int]] = {}
        for line in tail.split("\n"):
            if not line.strip():
                continue
            if line.startswith(":"):
                fields, _, path = line.partition("\t")
                statuses[path] = _status(fields.split()[-1])
                continue
            added, _, rest_line = line.partition("\t")
            removed, _, path = rest_line.partition("\t")
            if path:
                counts[path] = (
                    int(added) if added.isdigit() else 0,
                    int(removed) if removed.isdigit() else 0,
                )
        out.append(
            Commit(
                version=version.strip(),
                time=datetime.fromtimestamp(int(when or 0), tz=UTC),
                meta=parse_meta(body),
                paths=tuple(
                    PathChange(
                        path=path,
                        status=status,
                        added=counts.get(path, (0, 0))[0],
                        removed=counts.get(path, (0, 0))[1],
                    )
                    for path, status in statuses.items()
                ),
                parents=tuple(p for p in parents.split() if p),
            )
        )
    return out


def parse_status(raw: bytes) -> list[tuple[str, str]]:
    """``(code, path)`` for each entry of ``status --porcelain=v1 -z``,
    renames disabled so every entry names one path."""
    out: list[tuple[str, str]] = []
    for entry in raw.decode("utf-8", "replace").split("\0"):
        if len(entry) < 4:
            continue
        out.append((entry[:2], entry[3:]))
    return out


def parse_ls_tree(raw: bytes) -> dict[str, str]:
    """``{path: blob id}`` from ``ls-tree -r -z`` (blobs only)."""
    out: dict[str, str] = {}
    for entry in raw.decode("utf-8", "replace").split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob":
            out[path] = parts[2]
    return out


__all__ = ["LOG_FORMAT", "parse_log", "parse_ls_tree", "parse_status"]
