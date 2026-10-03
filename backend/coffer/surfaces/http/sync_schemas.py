"""Wire shapes for /api/v1/sync: status, rounds, the remote, machines, the key
(spec vault-sync; ADR sync-applies-clean-merges-and-stops-on-any-conflict).

The shapes of a stopped round, a hold and a join live in
``sync_stop_schemas``. Remote shapes carry ``secret_ref`` and never the
push token, so a remote can be rendered, logged or pasted into a bug report
with nothing to redact.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from coffer.domain.sync.remote import (
    BRANCH_PATTERN,
    DEFAULT_BRANCH,
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_USERNAME,
    MIN_INTERVAL_SECONDS,
    URL_PATTERN,
    SyncRemoteInvalid,
    validate_branch,
    validate_url,
)
from coffer.domain.sync.rounds import RoundStatus
from coffer.surfaces.http.handoff_schemas import HandoffOut


class SyncChangeOut(BaseModel):
    """One file a round (or a commit) changed."""

    path: str
    status: Literal["added", "modified", "removed"]


class PulledCommitOut(BaseModel):
    version: str
    time: str
    #: The machine that made it, by label (``None`` for a hand commit).
    machine: str | None
    files: int


class PlaintextFindingOut(BaseModel):
    """Where a round found a plaintext secret: the file, the line and the name
    the value was assigned to (``token`` for one recognised by its shape).
    Never the value."""

    path: str
    line: int
    key: str
    #: Whether the file still holds it; ``False``: only an earlier, unpushed
    #: commit does.
    current: bool


class RoundOut(BaseModel):
    """One recorded round: what it pulled, applied and pushed, and why it
    stopped or failed."""

    id: int | None
    status: RoundStatus
    started_at: str
    finished_at: str
    trigger: str
    from_commit: str | None
    to_commit: str | None
    snapshot: str | None
    pulled: list[PulledCommitOut]
    applied: list[SyncChangeOut]
    pushed: list[SyncChangeOut]
    with_machines: list[str]
    conflicts: int
    held: int
    detail: str | None
    path: str | None
    join: str | None
    pulled_files: int
    pushed_files: int
    #: What a ``plaintext_found`` round found; empty otherwise.
    plaintext: list[PlaintextFindingOut] = []
    #: How many unpushed commits the round folded into one so a value removed
    #: from a file since was not pushed (0: none).
    folded: int = 0


class SyncRunListOut(BaseModel):
    """A page of the history, newest first, and how many rounds it holds."""

    rounds: list[RoundOut]
    total: int
    next_cursor: str | None = None


def _url(value: str) -> str:
    try:
        return validate_url(value)
    except SyncRemoteInvalid as exc:
        raise ValueError(str(exc)) from exc


def _branch(value: str) -> str:
    try:
        return validate_branch(value)
    except SyncRemoteInvalid as exc:
        raise ValueError(str(exc)) from exc


#: A username git can send: no blank, colon, at-sign or slash.
USERNAME_PATTERN = r"^[^\s:@/]+$"


class SyncRemoteIn(BaseModel):
    url: str = Field(min_length=1, pattern=URL_PATTERN)
    branch: str = Field(default=DEFAULT_BRANCH, pattern=BRANCH_PATTERN)
    secret_ref: str | None = None
    #: The username an HTTPS token is sent with (Bitbucket and Azure DevOps
    #: need a real one; GitHub and GitLab ignore it).
    username: str = Field(
        default=DEFAULT_USERNAME, min_length=1, max_length=128, pattern=USERNAME_PATTERN
    )
    #: Whether ``secret/`` (ciphertext only) travels with the vault.
    include_secret: bool = False
    interval_seconds: int = Field(default=DEFAULT_INTERVAL_SECONDS, ge=MIN_INTERVAL_SECONDS)
    enabled: bool = True

    @field_validator("url")
    @classmethod
    def check_url(cls, value: str) -> str:
        return _url(value)

    @field_validator("branch")
    @classmethod
    def check_branch(cls, value: str) -> str:
        return _branch(value)


class SyncRemoteOut(BaseModel):
    url: str
    branch: str
    secret_ref: str | None
    username: str
    include_secret: bool
    interval_seconds: int
    enabled: bool


class SyncRemoteStateOut(BaseModel):
    configured: bool
    remote: SyncRemoteOut | None


class SyncRemoteClearedOut(BaseModel):
    cleared: bool
    #: Whether ``POST /sync/remote/restore`` can put it back (Undo).
    restorable: bool = False


class RemoteCheckIn(BaseModel):
    url: str = Field(min_length=1, pattern=URL_PATTERN)
    branch: str = Field(default=DEFAULT_BRANCH, pattern=BRANCH_PATTERN)
    secret_ref: str | None = None
    username: str = Field(
        default=DEFAULT_USERNAME, min_length=1, max_length=128, pattern=USERNAME_PATTERN
    )

    @field_validator("url")
    @classmethod
    def check_url(cls, value: str) -> str:
        return _url(value)

    @field_validator("branch")
    @classmethod
    def check_branch(cls, value: str) -> str:
        return _branch(value)


class RemoteCheckOut(BaseModel):
    """What the remote holds: ``empty`` (the first push fills it), ``vault``
    (a Coffer vault, with its layout), ``other`` (a repository that is not
    one), ``unreachable``, ``auth_failed`` or ``failed`` (with git's
    message)."""

    result: Literal["empty", "vault", "other", "unreachable", "auth_failed", "failed"]
    tip: str | None
    layout: int | None
    detail: str | None


class AreaCountsOut(BaseModel):
    knowledge_documents: int
    skills: int
    resources: int
    secrets: int
    secrets_synced: bool


class WaitingCommitOut(BaseModel):
    """One commit the remote does not have yet."""

    version: str
    time: str
    #: ``user`` (a person through Coffer), ``disk``, ``agent``, ``daemon``,
    #: ``curation`` or ``sync``.
    writer: str
    summary: str
    changes: list[SyncChangeOut]


class ProblemOut(BaseModel):
    kind: Literal[
        "unreachable",
        "auth_failed",
        "waiting_approval",
        "push_failed",
        "plaintext_found",
        "cloud_folder",
        "layout",
        "git_missing",
        "failed",
    ]
    #: Git's message, with any credential in it scrubbed.
    message: str
    secret_ref: str | None
    since: str | None
    #: The chore for the person's agent when the fix is outside Coffer — a
    #: rejected push, a refused sign-in, an unreachable remote, git missing.
    #: Never carries a token or a secret's value.
    handoff: HandoffOut | None = None
    #: For ``plaintext_found``: each place the value was found, never the value.
    plaintext: list[PlaintextFindingOut] = []


class SyncStatusOut(BaseModel):
    configured: bool
    remote: SyncRemoteOut | None
    machine_id: str
    machine_name: str
    joined: bool
    #: When the round now running started; ``None`` when none is.
    running_since: str | None
    last_round: RoundOut | None
    next_round_at: str | None
    machines: int
    areas: AreaCountsOut
    waiting: list[WaitingCommitOut]
    vault_path: str
    #: The tool whose synchronised folder holds the vault (sync is paused).
    synchroniser: str | None
    problem: ProblemOut | None
    conflicts: int
    held: int
    join_choices: int
    #: Commits this vault has that the remote (as last fetched) lacks, and the
    #: other way round — the Overview's "1 behind · 0 ahead".
    ahead: int = 0
    behind: int = 0
    #: Where the vault's files really are (``vault_path`` is the path Coffer
    #: uses and may be a link to it): the "From" of Move the vault.
    vault_real_path: str | None = None
    #: The folder Move the vault offers: ``~/.coffer/vault`` as a real folder.
    default_vault_path: str | None = None


class VaultMoveIn(BaseModel):
    #: The folder to move the vault to: absolute (``~`` allowed), empty or absent.
    to: str


class VaultMoveOut(BaseModel):
    #: The folder the vault was in; it is left empty for the person to delete.
    origin: str = Field(alias="from")
    to: str

    model_config = ConfigDict(populate_by_name=True)


class SyncPluginOut(BaseModel):
    id: str
    name: str
    marketplace: str | None
    enabled: bool
    version: str | None


class AgentInventoryOut(BaseModel):
    type: str
    name: str
    plugins: list[SyncPluginOut]


class MachineOut(BaseModel):
    machine_id: str
    name: str
    os: str
    hostname: str
    coffer_version: str
    #: The last round that moved anything, as that machine recorded it.
    last_round_at: str | None
    last_converged_commit: str | None
    key_fingerprint: str | None
    #: Whether this machine's key opens that machine's secrets.
    key_matches: bool | None
    is_self: bool
    last_round: str | None
    agents: list[AgentInventoryOut]


class MachineListOut(BaseModel):
    machines: list[MachineOut]


class MachineRenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class MachineRemovedOut(BaseModel):
    removed: bool


class KeyFingerprintOut(BaseModel):
    fingerprint: str | None


class KeyMaterialIn(BaseModel):
    #: The key file's text as the person picked it: a ``.cfk`` backup or a
    #: bare key.
    material: str = Field(min_length=1)


class KeyPreviewOut(BaseModel):
    """A key file beside this machine's key, before anything is replaced."""

    #: The key in the file (12 hex characters, never the key).
    fingerprint: str
    #: This machine's key, or null when it holds none yet.
    current_fingerprint: str | None
    #: True when both are the same key, so importing changes nothing.
    same: bool
    #: True for a passphrase-protected ``.cfk`` backup.
    protected: bool


class KeyImportIn(BaseModel):
    material: str
    #: Opens a ``.cfk`` backup; not needed for a bare key. Never stored or
    #: recorded.
    passphrase: str | None = None


class KeyImportOut(BaseModel):
    #: The key this machine now uses.
    fingerprint: str
    #: True when a different key was installed before (it is kept as a backup).
    replaced: bool
    #: How many stored secrets the key decrypts.
    readable: int
    #: The stored secrets it still cannot decrypt.
    locked_refs: list[str]


__all__ = [
    "AgentInventoryOut",
    "AreaCountsOut",
    "KeyFingerprintOut",
    "KeyImportIn",
    "KeyImportOut",
    "KeyMaterialIn",
    "KeyPreviewOut",
    "MachineListOut",
    "MachineOut",
    "MachineRemovedOut",
    "MachineRenameIn",
    "ProblemOut",
    "PulledCommitOut",
    "RemoteCheckIn",
    "RemoteCheckOut",
    "RoundOut",
    "SyncChangeOut",
    "SyncPluginOut",
    "SyncRemoteClearedOut",
    "SyncRemoteIn",
    "SyncRemoteOut",
    "SyncRemoteStateOut",
    "SyncRunListOut",
    "SyncStatusOut",
    "WaitingCommitOut",
]
