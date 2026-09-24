"""Wire shapes for /api/v1/sync (spec vault-sync).

Split out of ``sync_routes.py`` for the file-size tier. Remote shapes carry
``credential_ref`` and never the push credential itself, so a remote can be
rendered in a browser, logged, or pasted into a bug report with nothing to
redact.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from coffer.domain.sync.backup import (
    BRANCH_PATTERN,
    DEFAULT_BRANCH,
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_WORKTREE,
    MIN_INTERVAL_SECONDS,
    URL_PATTERN,
    validate_branch,
    validate_url,
)
from coffer.domain.sync.convergence import ConvergeStatus
from coffer.domain.sync.diff import ChangeStatus
from coffer.domain.sync.errors import BackupRemoteInvalid


class DocChangeOut(BaseModel):
    """One document's fate in one round: what moved, and which way."""

    path: str
    #: The domain enum rather than ``str``, for the reason ``RoundOut.status``
    #: is: the contract narrows this field, so the wire model declares the
    #: three values once instead of restating them in a comment.
    status: ChangeStatus


class DiffCountsOut(BaseModel):
    """What a round moved, as a tally AND as the list behind it.

    The tally alone is what a row can show; the list is what the reader opens
    the row to find out. A round reporting `+1 ~1` and then "nothing further to
    report" is the surface refusing to answer the only question the row raises,
    and the paths were in the payload the whole time.
    """

    added: int = 0
    modified: int = 0
    deleted: int = 0
    #: Every path this side of the round touched, sorted, with its status.
    changes: list[DocChangeOut] = []


class FailureOut(BaseModel):
    path: str
    reason: str


class BreachOut(BaseModel):
    area: str
    deleted: int
    total: int


class PendingConfirmationOut(BaseModel):
    """A round the deletion guard held.

    ``direction`` says which way it tripped: ``apply`` means the remote would
    delete too much of this vault, ``publish`` means this vault would delete
    too much of the remote — the case where this machine is the damaged one.
    """

    direction: str
    breaches: list[BreachOut]
    paths: list[str]
    raised_at: datetime


class JoinPreviewOut(BaseModel):
    """The join a round would make, stated before anything is applied.

    ``joining`` is False for a machine that already converged here: adopting
    is then an ordinary round with nothing to announce. ``case`` is
    ``ambiguous`` for a returning machine whose base is gone, which still
    needs the explicit ``keep-local`` choice (or a rebuild) before it joins.
    """

    joining: bool
    case: Literal["new", "returning", "ambiguous"] | None = None
    #: The commit a returning machine recovered from its own descriptor.
    base: str | None = None
    #: ISO date this machine last converged with the remote; None when new.
    last_converged_on: str | None = None
    #: Documents the remote changed since this machine's base — everything it
    #: holds, for a new machine. None when the base is gone.
    remote_changed: int | None = None
    #: Documents this vault holds.
    vault_documents: int | None = None


class RoundOut(BaseModel):
    """One converge round's outcome."""

    #: The whole of ``ConvergeStatus``, and the field that discriminates this
    #: one shape across every round-shaped operation. The domain enum itself
    #: rather than ``str``, so the vocabulary is declared once and the
    #: generated contract narrows to it instead of promising any string.
    status: ConvergeStatus
    #: ``new`` or ``returning`` when this round joined a remote; null otherwise.
    join: str | None = None
    applied: DiffCountsOut
    published: DiffCountsOut
    commit: str | None = None
    conflicts: list[str] = []
    #: Paths an agent merged. Always reported, successful or not: a silent
    #: machine merge of the user's own notes is what they would most want told.
    agent_resolved: list[str] = []
    failures: list[FailureOut] = []
    #: Paths this round met that can never apply on this machine. Held and
    #: not retried; not failures.
    not_applicable: list[str] = []
    locked_refs: list[str] = []
    pending: PendingConfirmationOut | None = None
    #: On an ``awaiting_join`` round, the join it detected and did not apply.
    join_report: JoinPreviewOut | None = None
    error: str | None = None


class RunRecordOut(RoundOut):
    """One round as the history holds it: the same report, plus when.

    A superset of ``RoundOut`` rather than a shape of its own, so the two
    surfaces that show a round — the status page and the history table — can
    never drift into describing it differently. The timestamps are what the
    last-round view never needed and a history cannot do without.
    """

    #: The history row's id. A row key for a surface, never shown: two rounds
    #: that changed nothing are otherwise indistinguishable values.
    id: int
    started_at: datetime
    finished_at: datetime


class SyncRunListOut(BaseModel):
    #: Newest first, capped by the route. Every round, including the ones that
    #: changed nothing — those are what make a gap in the record visible.
    runs: list[RunRecordOut]


class AdoptIn(BaseModel):
    #: Only for a returning machine whose recorded base is gone from the
    #: remote's history: ``keep-local`` joins as new and publishes this vault's
    #: documents as additions. Absent, that case is refused rather than guessed.
    choice: str | None = None


class SyncRemoteIn(BaseModel):
    """The remote as the user configures it.

    Every field but the URL carries the spec's default, so a ``PUT`` with a
    bare URL is a complete configuration rather than a half-set one.

    The URL and the branch become arguments to ``git``. Neither may begin with
    ``-`` — git would read it as an option, and ``--receive-pack=<cmd>`` is a
    command — and the branch is held to ``git check-ref-format --branch``. The
    ``pattern`` catches the shape at the wire; the validators run the domain's
    full rule, so a bad name is a 422 here rather than a git error later.
    """

    url: str = Field(pattern=URL_PATTERN)
    branch: str = Field(default=DEFAULT_BRANCH, pattern=BRANCH_PATTERN)
    #: A name in the credential store — never the secret. The daemon resolves
    #: it at push time and nowhere else.
    credential_ref: str | None = None
    include_credentials: bool = False
    interval_seconds: int = Field(default=DEFAULT_INTERVAL_SECONDS, ge=MIN_INTERVAL_SECONDS)
    enabled: bool = True
    worktree_path: str = Field(default=DEFAULT_WORKTREE, min_length=1)

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        try:
            return validate_url(value)
        except BackupRemoteInvalid as e:
            raise ValueError(e.reason) from e

    @field_validator("branch")
    @classmethod
    def _branch(cls, value: str) -> str:
        try:
            return validate_branch(value)
        except BackupRemoteInvalid as e:
            raise ValueError(e.reason) from e


class SyncRemoteOut(BaseModel):
    url: str
    branch: str
    credential_ref: str | None
    include_credentials: bool
    interval_seconds: int
    enabled: bool
    worktree_path: str


class SyncRemoteStateOut(BaseModel):
    #: ``False`` on a fresh vault. Sync being off is the ordinary state, not an
    #: error, so an unconfigured remote is a 200 with ``remote: null``.
    configured: bool
    remote: SyncRemoteOut | None


class SyncRemoteClearedOut(BaseModel):
    #: ``False`` when there was nothing to clear — delete is idempotent.
    cleared: bool


class SyncStatusOut(BaseModel):
    configured: bool
    remote: SyncRemoteOut | None
    last_run: RoundOut | None
    #: This machine's own id, so a surface can mark its row in the registry.
    machine_id: str
    #: ``False`` when the id came from the local fallback file rather than the
    #: host, which means it does not survive deleting ``~/.coffer``.
    machine_id_is_derived: bool
    #: Whether this machine has joined the remote. Until it has, a round
    #: reports ``awaiting_join`` and only ``POST /adopt`` joins.
    joined: bool = False
    #: Every path recorded as not applicable on this machine, sorted.
    not_applicable: list[str] = []


class MachineOut(BaseModel):
    machine_id: str
    name: str
    os: str
    hostname: str
    coffer_version: str
    #: The *day* this machine last converged. A day rather than an instant
    #: because an idle machine must not commit a heartbeat every round.
    last_converged_on: str | None
    #: Null when either side has published no fingerprint yet. ``False`` means
    #: that machine's credentials cannot be decrypted here.
    key_matches: bool | None
    agents: list[str]
    is_self: bool


class MachineListOut(BaseModel):
    machines: list[MachineOut]


class MachineRenameIn(BaseModel):
    name: str


class MachineRemovedOut(BaseModel):
    #: Retiring a machine removes its descriptor and rewrites nothing else. No
    #: scope can name a machine (reach is machine-local); a channel's binding
    #: and the curation owner do name one, and are then reported as naming a
    #: machine the registry no longer holds.
    removed: bool


class RestoreIn(BaseModel):
    #: A sha, a ref, or a ``YYYY-MM-DD`` date resolving to the last commit at
    #: or before it — the tip cannot return something deleted last week.
    at: str | None = None


class KeyMaterialIn(BaseModel):
    material: str


class KeyMaterialOut(BaseModel):
    material: str


class KeyImportOut(BaseModel):
    locked_refs: list[str]


class KeyFingerprintOut(BaseModel):
    fingerprint: str | None
