"""Wire models of the secret boundary: approvals, presence grants, `coffer run`,
the plaintext scan and the boundary's switch (spec secret).

None of these carries a secret value except :class:`RevealedSecretOut` and
:class:`ResolvedSecretsOut`, and each of those answers only a request that
proved itself: a reveal needs a presence grant the desktop app signed, and a
resolve answers only standalone ``secret/`` names, audited per name.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

_GRANT_OPS = Literal[
    "reveal", "approve", "approve_batch", "export_master_key", "import_master_key", "uninstall"
]


class PresenceGrantIn(BaseModel):
    """A grant the desktop shell signed after its presence check."""

    nonce: str = Field(min_length=8, max_length=128)
    signature: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")
    #: The approval's target fingerprint the person was shown. When sent, the
    #: grant is signed over ``<id>@<fingerprint>`` and the approval is applied
    #: only while it is still pending for that very target (design
    #: align-cli-with-ui-and-add-tool-environments D9).
    fingerprint: str | None = Field(default=None, max_length=128)


class AttestIn(BaseModel):
    """The desktop shell's challenge to a daemon: prove you hold the master key."""

    nonce: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class AttestOut(BaseModel):
    #: ``hex(HMAC-SHA256(attest key, "coffer-attest/v1\n" + nonce + "\n" + port))``.
    signature: str


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
    #: Protects the backup; the import on another machine asks for it. Checked
    #: by the route (at least eight characters) rather than by the schema, so
    #: a refusal never logs it. Never stored or recorded.
    passphrase: str


class MasterKeyExportOut(BaseModel):
    path: str
    fingerprint: str


class ApprovalOut(BaseModel):
    """A change waiting for a present human in the desktop app."""

    id: str
    op: Literal["bind", "disable_protection"]
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
    #: What the approval is pinned to; a batch approval names it so a target that
    #: moved since the person looked is skipped, not approved.
    target_fingerprint: str | None = None
    decided_at: str | None = None
    decided_by: str | None = None


class BatchItemIn(BaseModel):
    """One approval as the person was shown it."""

    id: str = Field(min_length=1, max_length=64)
    fingerprint: str = Field(default="", max_length=128)


class BatchApproveIn(PresenceGrantIn):
    """Approve every listed approval under one grant over exactly this list."""

    items: list[BatchItemIn] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _distinct(self) -> BatchApproveIn:
        if len({i.id for i in self.items}) != len(self.items):
            raise ValueError("an approval is listed twice")
        return self


class BatchRejectIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _distinct(self) -> BatchRejectIn:
        if len(set(self.ids)) != len(self.ids):
            raise ValueError("an approval is listed twice")
        return self


class BatchResultOut(BaseModel):
    id: str
    outcome: Literal["approved", "rejected", "skipped"]
    #: Why a skipped one was left as it is.
    reason: Literal["changed", "not_pending", "not_found", "not_batchable", "failed"] | None = None
    approval: ApprovalOut | None = None


class BatchOut(BaseModel):
    results: list[BatchResultOut]


class ApprovalListOut(BaseModel):
    approvals: list[ApprovalOut]


class ResolveSecretsIn(BaseModel):
    """What `coffer run` asks for: standalone secret names, and what for."""

    names: list[str] = Field(min_length=1, max_length=64)
    #: The command's program and working directory, for the audit row only —
    #: never the rest of argv, which may itself carry a secret.
    argv0: str = Field(min_length=1, max_length=1024)
    cwd: str = Field(default="", max_length=4096)


class ResolvedSecretsOut(BaseModel):
    values: dict[str, str]


class LocalAccessIn(BaseModel):
    """A standalone secret's local-process grant to ask for or withdraw."""

    name: str = Field(min_length=1, max_length=128)


class LocalAccessOut(BaseModel):
    #: ``on`` (granted), ``pending`` (a request waits in the desktop app) or ``off``.
    local_access: Literal["on", "pending", "off"]
    #: The approval that would grant it, while one waits.
    approval_id: str | None = None


class SecretBoundarySettingsOut(BaseModel):
    #: Whether a secret waits for approval before going somewhere new.
    require_approval: bool
    #: The approval that would turn it off, while one waits.
    pending_approval_id: str | None = None
    #: Whether this build defaults it on (a signed release) or off (an unsigned
    #: build, whose master key a same-user process can read).
    default_on: bool = True


class SecretBoundarySettingsIn(BaseModel):
    require_approval: bool


class SecretScanFindingOut(BaseModel):
    """Where one plaintext secret is and what it would become — never its value."""

    id: str
    source: Literal["skill", "mcp_server"]
    #: The skill's or the server's name.
    resource: str
    resource_uid: str | None = None
    path: str | None = None  # a skill's file and line
    line: int | None = None
    field: Literal["env", "header"] | None = None
    key: str
    #: The label a skill's secret gets; its id and a server's ref are minted on import.
    proposed_name: str | None = None
    #: The id of the detector rule that found the value.
    rule: str
    ignored: bool = False  # a person said it is not a secret


class SecretScanOut(BaseModel):
    findings: list[SecretScanFindingOut]
    #: How many skill files and MCP servers the scan read.
    files_checked: int = 0
    servers_checked: int = 0


class SecretImportIn(BaseModel):
    #: Finding ids to move; omitted moves every finding.
    ids: list[str] | None = None
    dry_run: bool = False


class SecretImportMovedOut(BaseModel):
    id: str
    source: Literal["skill", "mcp_server"]
    resource: str
    #: A skill's minted standalone name; absent in a dry run.
    name: str | None = None
    #: The label a skill's secret is given (the finding's proposed name).
    label: str | None = None
    #: The ref the value is stored under; absent in a dry run, where it is
    #: minted on import.
    ref: str | None = None
    #: `coffer://secret/<name>`, for a skill's value.
    uri: str | None = None


class SecretImportSkippedOut(BaseModel):
    id: str
    source: Literal["skill", "mcp_server"]
    resource: str
    reason: str
    #: The secret the value was stored as, when it was stored.
    name: str | None = None
    #: The value is in the store, but its file could not be rewritten and
    #: still holds it; moving the finding again retries the file.
    stored: bool = False


class SecretImportOut(BaseModel):
    moved: list[SecretImportMovedOut]
    skipped: list[SecretImportSkippedOut]
    dry_run: bool


# --- Storing, labelling and listing secrets ---


#: A ref: slash-separated segments of ``[A-Za-z0-9_.-]``, none made only of dots
#: (``.`` and ``..`` name no file, and would escape the store's directory).
_REF_PATTERN = r"^\.*[A-Za-z0-9_-][A-Za-z0-9_.-]*(/\.*[A-Za-z0-9_-][A-Za-z0-9_.-]*)*$"


class SecretSetIn(BaseModel):
    """Request body for storing a secret in the secret store.

    Secrets are Fernet-encrypted into the vault; only ciphertext is
    persisted; audit rows carry the ref only. A new secret's id is minted by
    the daemon: omit ``ref`` and the answer carries the minted ``secret/<hex>``.
    A ``ref`` replaces the value of a secret that exists (a new ref must itself
    be ``secret/<32 hex>``).
    """

    ref: str | None = Field(
        default=None,
        min_length=1,
        pattern=_REF_PATTERN,
        description=(
            "An existing secret's ref, to replace its value. Omit it to create "
            "a new secret under a minted id."
        ),
    )
    label: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="The name the person gives the secret, stored as its label.",
    )
    description: str | None = Field(
        default=None, min_length=1, max_length=200, description="What the secret is for."
    )
    created_for: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description=(
            "The uid of the resource a new secret is minted for; deleting that "
            "resource releases the secret when nothing else cites it."
        ),
    )
    value: str = Field(min_length=1, max_length=8192, description="The secret value.")


class SecretMintedOut(BaseModel):
    """A secret stored under an id the daemon minted."""

    ref: str = Field(description="The minted ref, secret/<32 hex characters>.")
    uri: str = Field(description="How a file cites it: coffer://secret/<32 hex characters>.")


class SecretNotesIn(BaseModel):
    """Set a ref's label and description. A field left out is unchanged; an
    empty string removes it."""

    ref: str = Field(min_length=1, pattern=_REF_PATTERN)
    label: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=200)


class SecretNotesOut(BaseModel):
    ref: str
    label: str | None = None
    description: str | None = None


class SecretExistsOut(BaseModel):
    """Presence-only response — never carries the secret value."""

    present: bool = Field(description="Whether a secret is stored under the ref.")


class SecretCiterOut(BaseModel):
    """A resource citing a secret ref — identity and label, never config."""

    uid: str
    kind: str
    name: str
    #: The key it cites the ref under: an MCP server's env var or header name, a
    #: channel's secret field (bot-token, app-secret), a provider's `key`.
    slot: str | None = None


class SecretBindingOut(BaseModel):
    """One destination a secret is sent to (or waits to be sent to)."""

    destination_kind: str
    destination_uid: str
    slot: str
    status: Literal["approved", "pending"]
    approval_id: str | None = None


class SecretRefOut(BaseModel):
    """One stored or cited secret ref: presence and references, never a value."""

    ref: str
    #: The name the person gave it, if any (never changes the ref).
    label: str | None = None
    #: What it is for, in the person's words.
    description: str | None = None
    #: The uid of the resource it was minted for, if any.
    created_for: str | None = None
    present: bool = Field(description="Whether a secret is stored under the ref.")
    #: Stored, but this Mac's master key cannot open it (it came with the vault
    #: from a machine holding another key). With ``present`` false, the row is
    #: "Missing on this Mac".
    locked: bool = False
    created_at: str | None = None
    #: When a consumer last had the value decrypted on this Mac.
    last_used_at: str | None = None
    cited_by: list[SecretCiterOut]
    #: The ``coffer://secret/<name>`` a file cites, for a standalone secret.
    uri: str | None = None
    #: Skills in the master store whose files mention the standalone secret.
    mentioned_by_skills: list[str] = Field(default_factory=list)
    #: Nothing cites it — no resource, no skill: the cleanup candidate.
    unreferenced: bool = False
    #: Where its value is approved to go, and where it waits for approval.
    bindings: list[SecretBindingOut] = Field(default_factory=list)
    #: Whether another process of this user can read the value where Coffer
    #: puts it: a stdio MCP server's environment, or a ``coffer run`` child.
    readable_by_local_processes: bool = False
    #: A standalone secret's local-process grant (`coffer run`): ``on``,
    #: ``pending`` (a request waits in the desktop app) or ``off``; ``None`` for
    #: a resource's secret, which `coffer run` never answers.
    local_access: Literal["on", "pending", "off"] | None = None


class SecretListOut(BaseModel):
    """Every stored ref and every ref a registered resource cites, sorted by ref."""

    refs: list[SecretRefOut]
