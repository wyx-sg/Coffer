"""Wire models of the secret boundary: approvals, presence grants, `coffer run`,
the plaintext scan and the boundary's switch (spec credentials).

None of these carries a secret value except :class:`RevealedSecretOut` and
:class:`ResolvedSecretsOut`, and each of those answers only a request that
proved itself: a reveal needs a presence grant the desktop app signed, and a
resolve answers only standalone ``secret/`` names, audited per name.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from coffer.surfaces.http.handoff_schemas import HandoffOut

_GRANT_OPS = Literal["reveal", "approve", "export_master_key"]


class PresenceGrantIn(BaseModel):
    """A grant the desktop shell signed after its presence check."""

    nonce: str = Field(min_length=8, max_length=128)
    signature: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")


class PresenceChallengeIn(BaseModel):
    op: _GRANT_OPS
    #: The ref to reveal, the approval id to approve, or the directory to write
    #: a key backup into.
    target: str = Field(min_length=1, max_length=1024)


class PresenceChallengeOut(BaseModel):
    nonce: str
    op: _GRANT_OPS
    target: str
    expires_in_seconds: int


class PresenceStatusOut(BaseModel):
    """Whether this daemon's grants hold against a local agent."""

    #: Where the master key lives, which is what the grant key derives from.
    master_key_storage: Literal["file", "keychain", "keychain_access_group"] | None
    #: True when the key is not in a signed build's Keychain access group: a
    #: process that reads the key file could sign a grant, so the boundary does
    #: not hold. The desktop app says so on every presence-gated action.
    development: bool


class RevealIn(PresenceGrantIn):
    ref: str = Field(min_length=1, max_length=256)


class RevealedSecretOut(BaseModel):
    value: str = Field(description="The secret, for the present human who asked.")


class MasterKeyExportIn(PresenceGrantIn):
    #: The directory the person picked; the file name is Coffer's.
    directory: str = Field(min_length=1, max_length=1024)


class MasterKeyExportOut(BaseModel):
    path: str
    fingerprint: str


class ApprovalOut(BaseModel):
    """A change waiting for a present human in the desktop app."""

    id: str
    op: Literal["bind", "replace_value", "disable_protection"]
    status: Literal["pending", "approved", "rejected", "superseded"]
    description: str
    created_at: str
    requested_by: str
    ref: str | None = None
    destination_kind: str | None = None
    destination_uid: str | None = None
    destination_label: str | None = None
    slot: str | None = None
    target: str | None = None
    decided_at: str | None = None
    decided_by: str | None = None


class ApprovalListOut(BaseModel):
    approvals: list[ApprovalOut]


class CredentialWriteOut(BaseModel):
    """202 answer to a write that replaces a value in use: it waits, sealed."""

    approval: ApprovalOut


class ResolveSecretsIn(BaseModel):
    """What `coffer run` asks for: standalone secret names, and what for."""

    names: list[str] = Field(min_length=1, max_length=64)
    #: The command's program and working directory, for the audit row only —
    #: never the rest of argv, which may itself carry a secret.
    argv0: str = Field(min_length=1, max_length=1024)
    cwd: str = Field(default="", max_length=4096)


class ResolvedSecretsOut(BaseModel):
    values: dict[str, str]


class SecretScanFindingOut(BaseModel):
    id: str
    path: str
    source: Literal["secrets_file", "skill"]
    key: str
    line: int
    proposed_name: str


class SecretScanMentionOut(BaseModel):
    skill: str
    path: str
    line: int
    mention: str


class SecretScanOut(BaseModel):
    """Plaintext secrets found in files — where they are, never what they are."""

    findings: list[SecretScanFindingOut]
    mentions: list[SecretScanMentionOut]
    #: With mentions: rewriting those skills to get their values through
    #: `coffer run`, handed to the person's agent. Names places and secret
    #: names only, never a value.
    handoff: HandoffOut | None


class SecretImportIn(BaseModel):
    #: Finding ids to move; omitted moves every finding.
    ids: list[str] | None = None
    dry_run: bool = False


class SecretImportMovedOut(BaseModel):
    id: str
    path: str
    name: str
    uri: str


class SecretImportSkippedOut(BaseModel):
    id: str
    path: str
    reason: str


class SecretImportOut(BaseModel):
    moved: list[SecretImportMovedOut]
    skipped: list[SecretImportSkippedOut]
    dry_run: bool


class SecretBoundarySettingsOut(BaseModel):
    #: Whether a secret waits for approval before going somewhere new.
    require_approval: bool
    #: The approval that would turn it off, while one waits.
    pending_approval_id: str | None = None


class SecretBoundarySettingsIn(BaseModel):
    require_approval: bool
