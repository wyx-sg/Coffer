"""An agent's merge of a conflicting file, read off the marked-up copy (spec
vault-sync "Hand conflicting files to an agent").

Coffer writes git's marked-up merge of a file outside the vault
(``derived/sync-conflicts/``) and the person's agent writes its merge into that
same copy. The merge is never stored as an answer: a file handed to an agent is
``merged_by_agent`` once its copy has left git's marked-up text and holds no
conflict marker, and only the person marking it resolved turns it into an
answer. Nothing here writes into the vault.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from coffer.application.sync.round_deps import RoundDeps
from coffer.domain.sync.stops import ConflictFile

_MARKER = re.compile(rb"^(<{7}|={7}|>{7})( |$)", re.M)

#: A handed-over file whose copy is still git's marked-up text.
HANDED_OFF = "handed_off"
#: A handed-over file whose copy the agent has merged.
MERGED_BY_AGENT = "merged_by_agent"


def marker_line(data: bytes) -> int | None:
    """The 1-based line of the first conflict marker in ``data``, if any."""
    match = _MARKER.search(data)
    return data[: match.start()].count(b"\n") + 1 if match else None


def marked_up(d: RoundDeps, found: ConflictFile) -> bytes:
    """git's marked-up merge of ``found``: both versions between markers."""
    blobs = d.git.blobs([b for b in (found.ours, found.base, found.theirs) if b])
    return d.git.merge_file(
        blobs.get(found.ours or "", b""),
        blobs.get(found.base or "", b""),
        blobs.get(found.theirs or "", b""),
        (d.machine.label(), found.theirs_machine or "the other machine"),
    )


@dataclass(frozen=True)
class MergeInfo:
    #: ``HANDED_OFF`` or ``MERGED_BY_AGENT``.
    state: str
    merged_at: str | None = None
    #: What the merge changes against this machine's version (unified diff).
    diff: str | None = None


def merge_info(d: RoundDeps, found: ConflictFile) -> MergeInfo | None:
    """Where ``found``'s hand-off stands, or ``None`` if it was never handed over."""
    if found.handed_at is None or d.scratch is None:
        return None
    data = d.scratch.read(found.path)
    if data is None or marker_line(data) is not None or data == marked_up(d, found):
        return MergeInfo(HANDED_OFF)
    return MergeInfo(MERGED_BY_AGENT, merged_at=d.scratch.modified(found.path))


__all__ = [
    "HANDED_OFF",
    "MERGED_BY_AGENT",
    "MergeInfo",
    "marked_up",
    "marker_line",
    "merge_info",
]
