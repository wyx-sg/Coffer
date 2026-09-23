"""Deciding what base a machine with no pointer starts from (spec vault-sync).

A round with no pointer is joining a remote, and there are two kinds of joiner
that need opposite treatment:

* **New** — the remote's registry does not hold this machine's id. Base is
  git's empty tree, so the diff can only contain additions: the machine takes
  everything the remote holds, keeps everything it had, and publishes the
  union. Deletion is structurally impossible, not merely avoided.
* **Returning** — the id *is* there, so this machine converged before and lost
  its pointer to a reinstall or a wiped ``~/.coffer``. Its own descriptor names
  the commit it reached; that becomes the base and the round is an ordinary
  stale-machine round.

Treating a returning machine as new is a data-loss bug, not a conservative
default: its vault still holds what it held before, so a union republishes
every document the other machines deleted while it was away, all at once, and
raises no conflict — because a union has no base to disagree with.

This is what a **derived** machine id buys. An id Coffer generated and stored
would be gone with the pointer, and the two cases would be indistinguishable.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import yaml

from coffer.application.sync.ports import GitMirrorPort
from coffer.domain.sync.convergence import JoinKind, JoinPreview
from coffer.domain.sync.errors import SyncJoinAmbiguous
from coffer.domain.sync.machine import MachineDescriptor


@dataclasses.dataclass(frozen=True, slots=True)
class Join:
    kind: JoinKind
    pointer: str
    #: The day this machine last converged, for the surfaces to report. None
    #: for a new machine.
    last_converged_on: date | None = None


__all__ = ["Join", "JoinPreview", "JoinResolver"]


class JoinResolver:
    """Reads the remote's registry to place this machine."""

    def __init__(self, *, machine_id: str, branch: str) -> None:
        self._machine_id = machine_id
        self._branch = branch

    async def resolve(self, mirror: GitMirrorPort, *, choice: str | None = None) -> Join:
        """Place this machine against the remote.

        ``choice`` is the user's explicit answer for the one case that has no
        safe default: a machine whose descriptor is in the registry but whose
        recorded base is gone from the history. ``"keep-local"`` joins it as
        new, publishing this vault's documents as additions — which may
        resurrect what others deleted, and says so. The other answer, rebuilding
        this machine from the remote, is not a base at all but a different
        operation (``ConvergeService.rebuild``), so it never reaches here.
        Without an answer this raises rather than guessing.
        """
        descriptor = await self._published_descriptor(mirror)
        if descriptor is None:
            return Join(JoinKind.NEW, mirror.EMPTY_TREE)

        commit = descriptor.last_converged_commit
        if commit is not None and await self._still_in_history(mirror, commit):
            return Join(JoinKind.RETURNING, commit, descriptor.last_converged_on)

        if choice == "keep-local":
            return Join(JoinKind.NEW, mirror.EMPTY_TREE, descriptor.last_converged_on)
        raise SyncJoinAmbiguous(self._machine_id)

    async def last_converged_on(self, mirror: GitMirrorPort) -> date | None:
        """The day this machine's own descriptor says it last converged."""
        descriptor = await self._published_descriptor(mirror)
        return descriptor.last_converged_on if descriptor is not None else None

    async def _published_descriptor(self, mirror: GitMirrorPort) -> MachineDescriptor | None:
        raw = await mirror.read_file(f"origin/{self._branch}", f"machines/{self._machine_id}.yaml")
        if raw is None:
            return None
        try:
            doc = yaml.safe_load(raw.decode("utf-8"))
        except (yaml.YAMLError, UnicodeDecodeError):
            # A descriptor this build cannot read still proves the machine has
            # been here, and that is the fact this decision turns on.
            return MachineDescriptor.from_doc(self._machine_id, {})
        if not isinstance(doc, dict):
            return MachineDescriptor.from_doc(self._machine_id, {})
        return MachineDescriptor.from_doc(self._machine_id, doc)

    async def _still_in_history(self, mirror: GitMirrorPort, commit: str) -> bool:
        """Whether the recorded base is still reachable.

        A rewritten history leaves a descriptor pointing at nothing, and
        diffing against a commit that is gone would fail mid-round rather than
        at the decision.
        """
        try:
            return bool(await mirror.resolve_revision(commit))
        except Exception:
            return False
