"""Wire shapes for /api/v1/sync: status, rounds, the remote, machines, the key
(spec vault-sync; ADR sync-applies-clean-merges-and-stops-on-any-conflict).

The shapes of a stopped round, a hold and a join live in
``sync_stop_schemas``. Remote shapes carry ``credential_ref`` and never the
push token, so a remote can be rendered, logged or pasted into a bug report
with nothing to redact.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

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


class SyncRunListOut(BaseModel):
    """A page of the history, newest first, and how many rounds it holds."""

    rounds: list[RoundOut]
    total: int


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
    credential_ref: str | None = None
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
    credential_ref: str | None
    username: str
    include_secret: bool
    interval_seconds: int
    enabled: bool


class SyncRemoteStateOut(BaseModel):
    configured: bool
    remote: SyncRemoteOut | None


class SyncRemoteClearedOut(BaseModel):
    cleared: bool


class RemoteCheckIn(BaseModel):
    url: str = Field(min_length=1, pattern=URL_PATTERN)
    branch: str = Field(default=DEFAULT_BRANCH, pattern=BRANCH_PATTERN)
    credential_ref: str | None = None
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
    kind: Literal["unreachable", "auth_failed", "push_failed", "cloud_folder", "layout", "failed"]
    message: str
    credential_ref: str | None
    since: str | None


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
    material: str = Field(min_length=1)


class KeyImportOut(BaseModel):
    #: Secrets this machine's key still does not open.
    locked_refs: list[str]


__all__ = [
    "AgentInventoryOut",
    "AreaCountsOut",
    "KeyFingerprintOut",
    "KeyImportOut",
    "KeyMaterialIn",
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
