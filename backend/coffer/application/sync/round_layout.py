"""Whether a remote's layout can be converged with.

Spec vault-sync "Report a join before applying it".
"""

from __future__ import annotations

from coffer.application.sync.round_deps import RoundDeps
from coffer.domain.sync.rounds import RoundStatus


def layout_refusal(d: RoundDeps, tip: str) -> tuple[RoundStatus, str] | None:
    """Why a remote at ``tip`` cannot be converged with, or ``None``.

    A remote carries exactly this build's layout or it is refused, in either
    direction: a newer one is another Coffer's, and an older one is rebuilt
    from a migrated machine rather than converted here (ADR
    every-vault-file-carries-its-format-version)."""
    layout = d.layout_of(tip)
    if layout is None or layout == d.layout:
        return None
    if layout > d.layout:
        return (
            RoundStatus.REMOTE_TOO_NEW,
            f"the remote's layout {layout} is newer than this build's {d.layout}; "
            "upgrade Coffer on this machine",
        )
    return (
        RoundStatus.REMOTE_TOO_OLD,
        f"the remote is at layout {layout}, older than this build's {d.layout}; rebuild it "
        "from a machine that has been upgraded (clear it and let that machine push), "
        "then join it from here",
    )
