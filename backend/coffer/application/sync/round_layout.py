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


def unseen_older(d: RoundDeps, tip: str, local: str) -> tuple[RoundStatus, str] | None:
    """Why a joined machine may not replace an older-layout remote at ``tip``,
    or ``None``. Replacing it is safe only when this vault already merged the
    remote's tip; otherwise the commits another machine pushed since would be
    dropped from the remote, and applied as deletions on that machine once it
    upgrades. A machine that has not joined replaces only from the join
    preview, which lists what goes away."""
    if not d.state.joined() or d.git.is_ancestor(tip, local):
        return None
    newest = d.git.log(start=tip, limit=1)
    by = newest[0].meta.machine if newest and newest[0].meta.machine else "another machine"
    return (
        RoundStatus.OLDER_REMOTE_HAS_CHANGES,
        f"the remote, at an older layout, has changes this machine has not pulled "
        f"(last pushed by {by}); upgrade Coffer on that machine and let it sync first",
    )


def is_older(d: RoundDeps, tip: str) -> bool:
    """The remote at ``tip`` holds an older layout than this build's."""
    layout = d.layout_of(tip)
    return layout is not None and layout < d.layout
