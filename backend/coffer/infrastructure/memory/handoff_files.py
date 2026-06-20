"""On-disk handoff (working-state) files: one per (project store × branch).

Files-as-truth, frontmatter ``{branch, updated_at}`` + freeform body. Mirrors
``infrastructure/memory/files.py`` but a handoff is overwrite-per-branch and is
NOT indexed for recall (it lives in the store's ``handoff/`` subdir, which the
recall glob never descends into). Frontmatter parse/render is delegated to the
shared ``infrastructure.knowledge.frontmatter`` (the PyYAML owner), exactly as
the per-fact files do.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from coffer.infrastructure.knowledge.frontmatter import (
    render_frontmatter,
    split_frontmatter,
)

_SLUG_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def branch_slug(branch: str) -> str:
    """A filesystem-safe slug for a branch name (``feature/x`` → ``feature-x``)."""
    return _SLUG_RE.sub("-", branch).strip("-")


@dataclass(frozen=True)
class HandoffFile:
    """A handoff file read from disk: the branch, the freeform body, and the
    timestamp of the last overwrite."""

    branch: str
    body: str
    updated_at: datetime


def write_handoff(path: Path, *, branch: str, body: str, updated_at: datetime) -> None:
    """Write (overwrite) the handoff for a branch: frontmatter + body."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = render_frontmatter({"branch": branch, "updated_at": updated_at.isoformat()}, body)
    path.write_text(text, encoding="utf-8")


def read_handoff(path: Path) -> HandoffFile | None:
    """Read + parse a handoff file, or ``None`` if it does not exist."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    meta, body = split_frontmatter(text)
    return HandoffFile(
        branch=str(meta.get("branch", "")),
        # ``render_frontmatter`` normalises the body with ``strip("\n")`` and
        # re-adds a single trailing newline; strip it back here for a true
        # write→read roundtrip (matches how the per-fact reader treats bodies).
        body=body.strip("\n"),
        updated_at=_parse_updated_at(meta.get("updated_at")),
    )


def _parse_updated_at(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
