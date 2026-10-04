"""Whether a remote's layout can be converged with.

Spec vault-sync "Report a join before applying it".
"""

from __future__ import annotations

from coffer.application.sync.round_deps import RoundDeps
from coffer.domain.sync.rounds import RoundStatus


def layout_refusal(d: RoundDeps, tip: str) -> tuple[RoundStatus, str] | None:
    """Why a remote at ``tip`` cannot be converged with, or ``None``.

    A remote written by a newer Coffer is refused: this build would misread
    it. A remote at an older layout is not refused: this vault replaces it
    (see ``is_older`` and ``round_replace``)."""
    layout = d.layout_of(tip)
    if layout is not None and layout > d.layout:
        return (
            RoundStatus.REMOTE_TOO_NEW,
            f"the remote's layout {layout} is newer than this build's {d.layout}; "
            "upgrade Coffer on this machine",
        )
    return None


def is_older(d: RoundDeps, tip: str) -> bool:
    """The remote at ``tip`` holds an older layout than this build's."""
    layout = d.layout_of(tip)
    return layout is not None and layout < d.layout
