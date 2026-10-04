"""What the sync service answers the Sync page and ``coffer sync`` with.

Plain, frozen shapes assembled from the round's state, the vault's history and
the machines' descriptors; the surfaces project them onto their wire models.
Nothing here is stored.
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.domain.sync.machine import MachineDescriptor
from coffer.domain.sync.plaintext import PlaintextFinding
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import AppliedChange, RoundRecord
from coffer.domain.sync.stops import ConflictFile, Stop


@dataclass(frozen=True)
class AreaCounts:
    """What the vault holds at ``HEAD``, by the areas the Sync page shows."""

    knowledge_documents: int = 0
    skills: int = 0
    resources: int = 0
    secrets: int = 0
    #: Whether the remote carries the secrets (``include_secret``).
    secrets_synced: bool = False


@dataclass(frozen=True)
class WaitingCommit:
    """One commit this vault has that the remote does not (yet)."""

    version: str
    time: str
    writer: str
    summary: str
    changes: tuple[AppliedChange, ...] = ()


@dataclass(frozen=True)
class Problem:
    """Why sync is not working right now, in terms of what a person can do.

    ``kind``: ``unreachable`` / ``auth_failed`` / ``waiting_approval`` / ``push_failed`` /
    ``plaintext_found`` / ``cloud_folder`` / ``layout`` / ``git_missing`` /
    ``failed``. ``handoff`` is the prompt for the person's agent when the fix
    is outside Coffer (spec vault-sync "Hand a remote's failure to an agent",
    "Refuse to push a plaintext secret"); ``plaintext`` is what a
    ``plaintext_found`` round found, never a value."""

    kind: str
    message: str
    secret_ref: str | None = None
    since: str | None = None
    handoff: str | None = None
    plaintext: tuple[PlaintextFinding, ...] = ()


@dataclass(frozen=True)
class SyncStatus:
    remote: SyncRemote | None
    machine_id: str
    machine_name: str
    joined: bool
    running_since: str | None
    last_round: RoundRecord | None
    next_round_at: str | None
    machines: int
    areas: AreaCounts
    waiting: tuple[WaitingCommit, ...]
    vault_path: str
    synchroniser: str | None
    problem: Problem | None
    conflicts: int = 0
    held: int = 0
    join_choices: int = 0
    #: How many commits this vault has that the remote (as last fetched) does
    #: not, and how many the remote has that this vault does not.
    ahead: int = 0
    behind: int = 0
    #: Where the vault's files really are (``vault_path`` may be a link to it),
    #: and the folder "Move the vault" offers.
    vault_real_path: str | None = None
    default_vault_path: str | None = None


@dataclass(frozen=True)
class StoppedFile:
    file: ConflictFile
    #: The hand-merge copy under ``derived/sync-conflicts/``, once opened.
    editor_path: str | None = None
    #: An encrypted secret: answered with this machine's or the other's only.
    secret: bool = False
    #: Whether an agent may merge it (spec vault-sync "Hand conflicting
    #: files to an agent").
    agent_mergeable: bool = False
    #: ``handed_off`` / ``merged_by_agent`` once it was handed to an agent;
    #: ``merged_at`` is when the agent's merge was saved. Neither is an answer.
    agent_state: str | None = None
    merged_at: str | None = None


@dataclass(frozen=True)
class HoldGroup:
    """The held losses under one folder, and how much of it they are."""

    folder: str
    paths: tuple[str, ...]
    #: How many files the folder held before the round.
    total: int


@dataclass(frozen=True)
class StoppedRound:
    stop: Stop
    files: tuple[StoppedFile, ...] = ()
    groups: tuple[HoldGroup, ...] = ()
    #: The machines whose changes raised the stop (incoming), by label.
    machines: tuple[str, ...] = ()
    confirmed: bool = False


@dataclass(frozen=True)
class FileVersions:
    """One stopped file's three versions, as text, and what each answer
    changes on this machine."""

    path: str
    ours: str | None
    theirs: str | None
    base: str | None
    #: The unified diff taking the other machine's version makes here.
    take_theirs: str
    binary: bool = False
    #: The hand-merge copy as saved, once it exists (never for a secret).
    edited: str | None = None
    #: An agent's merge of it (the saved copy, no marker left), and the diff
    #: from this machine's version to it.
    merged: str | None = None
    merged_diff: str | None = None


@dataclass(frozen=True)
class HandoffResult:
    """What handing conflicting files to an agent produced: the prompt, and
    the files it covers."""

    prompt: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class RemoteCheck:
    """``empty`` / ``vault`` / ``other`` / ``unreachable`` / ``auth_failed`` /
    ``failed``, with the remote's layout when it holds a vault."""

    result: str
    tip: str | None = None
    layout: int | None = None
    detail: str | None = None


@dataclass(frozen=True)
class MachineView:
    descriptor: MachineDescriptor
    is_self: bool
    #: Whether this machine's key opens that machine's secrets; ``None`` when
    #: either side published no fingerprint.
    key_matches: bool | None
    #: What that machine's last round did, from its newest merge commit (for
    #: this machine, from its own history).
    last_round: str | None = None


@dataclass(frozen=True)
class RollbackView:
    snapshot: str
    snapshot_commit: str
    snapshot_time: str | None
    reverses: tuple[AppliedChange, ...] = ()
    kept: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoundPage:
    rounds: tuple[RoundRecord, ...] = ()
    total: int = 0
    next_cursor: str | None = None


__all__ = [
    "AreaCounts",
    "FileVersions",
    "HandoffResult",
    "HoldGroup",
    "MachineView",
    "Problem",
    "RemoteCheck",
    "RollbackView",
    "RoundPage",
    "StoppedFile",
    "StoppedRound",
    "SyncStatus",
    "WaitingCommit",
]
