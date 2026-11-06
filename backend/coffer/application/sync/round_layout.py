"""Whether a remote's layout can be converged with.

Spec vault-sync "Report a join before applying it".
"""

from __future__ import annotations

from coffer.application.sync.round_deps import RoundDeps
from coffer.domain.sync.machine import MachineDescriptor, machine_id_of
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import RoundStatus
from coffer.domain.vault.layout import MACHINES


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


def key_refusal(d: RoundDeps, remote: SyncRemote, tip: str) -> tuple[RoundStatus, str] | None:
    """Why a remote that carries secrets cannot be synced with while another
    machine's master key differs from this one's, or ``None``.

    Ciphertext encrypted under another key cannot be opened here, and "the
    fresher encryption wins" would let it replace a value this machine can
    open; the two machines would then overwrite each other every round. So
    nothing moves until the keys match (spec vault-sync "Refuse to carry
    secrets between machines whose master keys differ")."""
    if not remote.include_secret:
        return None
    own = d.machine.machine_id()
    mine = MachineDescriptor.parse(own, d.machine.descriptor(last_round_at=None, last_commit=None))
    my_key = mine.key_fingerprint if mine else None
    files = {p: b for p, b in d.git.files(tip, MACHINES + "/").items() if machine_id_of(p)}
    data = d.git.blobs(list(files.values()))
    differ: list[str] = []
    for path, blob in sorted(files.items()):
        machine = machine_id_of(path)
        if machine is None or machine == own or blob not in data:
            continue
        peer = MachineDescriptor.parse(machine, data[blob])
        if peer is None or peer.key_fingerprint is None or peer.key_fingerprint == my_key:
            continue
        differ.append(peer.name or machine)
    if not differ:
        return None
    return (
        RoundStatus.KEY_MISMATCH,
        f"this remote carries secrets and the master key on {', '.join(differ)} differs from "
        "this machine's; import the same master key on Settings > Security, then sync again",
    )


def refusal(d: RoundDeps, remote: SyncRemote, tip: str) -> tuple[RoundStatus, str] | None:
    """Why a round or a join must not converge with the remote at ``tip``."""
    return layout_refusal(d, tip) or key_refusal(d, remote, tip)


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
