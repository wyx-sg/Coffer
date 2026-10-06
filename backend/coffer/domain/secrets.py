"""The secret boundary's vocabulary: destinations, bindings, approvals, names.

A *destination* is a place Coffer sends a secret's plaintext — an MCP server's
environment variable or HTTP header, a channel adapter's secret, the sync
remote's push token, a provider connection's key. A *binding* is one secret
(a secret ref) sent to one slot of one destination, and it is approved for
one *target*: the thing that actually receives the value (a stdio server's
command line, an HTTP server's URL, a provider's base URL). Changing the target
is sending the secret somewhere new, so an approval is pinned to the target's
fingerprint, never to the destination's identity alone (ADR
only-a-present-human-sees-a-secret-or-sends-it-somewhere-new, rule 2).

A *standalone secret* lives under the ``secret/`` namespace of the same store
and is cited as ``coffer://secret/<name>`` from files Coffer cannot see (ADR
standalone-secrets-are-named-references-injected-into-one-child).

Pure: no I/O, no clock, no storage.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
import uuid
from collections.abc import Iterable
from typing import Literal

#: The store namespace standalone secrets live under.
SECRET_NAMESPACE = "secret/"
#: How a file cites a standalone secret.
SECRET_URI_PREFIX = "coffer://secret/"
#: One ref segment, at most 64 characters: the name is quoted in files Coffer
#: cannot see, so it is fixed after creation.
# One segment of ``[A-Za-z0-9_.-]``, never only dots: ``.`` and ``..`` name no file.
_NAME_RE = re.compile(r"^(?!\.+$)[A-Za-z0-9_.-]{1,64}$")
_URI_RE = re.compile(r"coffer://secret/([A-Za-z0-9_.-]{1,64})")

#: What a pending approval asks the person to allow.
ApprovalOp = Literal["bind", "disable_protection"]
ApprovalStatus = Literal["pending", "approved", "rejected", "superseded"]

#: What a presence grant may authorise. Each is one operation on one target.
GRANT_OPS: tuple[str, ...] = (
    "reveal",
    "approve",
    "approve_batch",
    "export_master_key",
    "import_master_key",
)


#: Longest label and description a person can give a secret.
LABEL_MAX = 64
DESCRIPTION_MAX = 200


ORIGIN_PAGE = "page"
ORIGIN_DIALOG = "dialog"


@dataclasses.dataclass(frozen=True, slots=True)
class SecretNote:
    """What a person said about a secret: a name they recognise and what it is
    for. The ref stays the identity; neither changes anything that cites it."""

    label: str | None = None
    description: str | None = None
    #: The uid of the resource this secret was minted for; its deletion may
    #: release the secret, when nothing else cites it.
    created_for: str | None = None
    #: Where it was added: ``page`` (the Secrets page, ``coffer secret set
    #: --name``: a person made it for itself) or ``dialog`` (written under a
    #: minted id by a resource dialog, an import or a service, for the resource
    #: that is about to cite it). Editing the label never changes it.
    origin: str | None = None

    @property
    def empty(self) -> bool:
        return not (self.label or self.description or self.created_for or self.origin)


#: A channel's secret fields and the slot name each one fills.
CHANNEL_SECRET_SLOTS: dict[str, str] = {
    "bot_token_ref": "bot-token",
    "app_secret_ref": "app-secret",
}


def slot_of(kind: str, key: str) -> str:
    """The slot a kind's secret-ref key fills: an MCP server's env var or header
    name as it is, a channel's field logical name, a provider's ``key``."""
    if kind == "channel":
        return CHANNEL_SECRET_SLOTS.get(key) or key.removesuffix("_ref").replace("_", "-")
    if kind == "provider":
        return "key"
    return key


_MINTED_RE = re.compile(r"^secret/[0-9a-f]{32}$")


def is_minted_ref(ref: str) -> bool:
    """Whether ``ref`` is a minted id, ``secret/<32 hex>``: every secret's id,
    whoever it is for. A person never picks one; Coffer mints it (spec secret
    "Mint every secret's id; a person names it")."""
    return bool(_MINTED_RE.match(ref))


def mint_secret_name() -> str:
    """A fresh id for a standalone secret added without a name: 32 hex characters."""
    return uuid.uuid4().hex


def is_valid_secret_name(name: str) -> bool:
    return bool(_NAME_RE.match(name)) and name not in {".", ".."}


def secret_ref(name: str) -> str:
    """The store ref a standalone secret ``name`` lives under."""
    return f"{SECRET_NAMESPACE}{name}"


def secret_uri(name: str) -> str:
    return f"{SECRET_URI_PREFIX}{name}"


def is_standalone_ref(ref: str) -> bool:
    return ref.startswith(SECRET_NAMESPACE) and is_valid_secret_name(ref[len(SECRET_NAMESPACE) :])


def standalone_name(ref: str) -> str | None:
    return ref[len(SECRET_NAMESPACE) :] if is_standalone_ref(ref) else None


def parse_secret_uri(value: str) -> str | None:
    """The name a whole value cites (``coffer://secret/<name>``), else None."""
    match = _URI_RE.fullmatch(value.strip())
    return match.group(1) if match else None


def cited_secret_names(text: str) -> set[str]:
    """Every standalone-secret name a piece of text mentions by URI."""
    return set(_URI_RE.findall(text))


def default_env_var(name: str) -> str:
    """The variable ``coffer run --secret NAME`` sets: upper-cased, ``-``/``.`` → ``_``."""
    return re.sub(r"[-.]", "_", name).upper()


def fingerprint(target: str) -> str:
    """A stable digest of where a value goes; what an approval is pinned to."""
    return hashlib.sha256(target.encode("utf-8")).hexdigest()[:32]


@dataclasses.dataclass(frozen=True, slots=True)
class SecretDestination:
    """Where a set of secrets is about to be sent.

    ``kind`` and ``uid`` identify the thing that consumes the secrets (a
    resource's kind and uid, or ``sync_remote`` / ``remote``); ``target`` is
    the human-readable description of what actually receives the value, shown
    verbatim in the approval and in the operating system's presence prompt;
    ``label`` is the name a person recognises.
    """

    kind: str
    uid: str
    target: str
    label: str

    @property
    def target_fingerprint(self) -> str:
        return fingerprint(self.target)


@dataclasses.dataclass(frozen=True, slots=True)
class SecretBinding:
    """One ref approved for one slot of one destination, at one target."""

    ref: str
    destination_kind: str
    destination_uid: str
    slot: str
    target_fingerprint: str
    approved_at: str
    approval_id: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class SecretApproval:
    """A change that waits for a present human in the desktop app.

    ``op`` is ``bind`` (a secret to a new destination or target) or
    ``disable_protection`` (turning the approval requirement off).
    """

    id: str
    op: ApprovalOp
    status: ApprovalStatus
    created_at: str
    requested_by: str
    ref: str | None = None
    destination_kind: str | None = None
    destination_uid: str | None = None
    destination_label: str | None = None
    slot: str | None = None
    target: str | None = None
    target_fingerprint: str | None = None
    decided_at: str | None = None
    decided_by: str | None = None

    def describe(self) -> str:
        """One line a person can approve or refuse on sight."""
        if self.op == "bind" and self.destination_kind == LOCAL_PROCESS_KIND:
            return (
                f"let coffer run hand secret {self.ref!r} to programs on this Mac, "
                "including ones an agent starts, which can read it"
            )
        if self.op == "bind":
            return (
                f"send secret {self.ref!r} to {self.destination_kind} "
                f"{self.destination_label!r} ({self.slot}) at {self.target}"
            )
        return "turn off approval for new secret destinations"

    def destination(self) -> SecretDestination:
        """Where a ``bind`` approval sends its secret, as the boundary checks it."""
        return SecretDestination(
            self.destination_kind or "",
            self.destination_uid or "",
            self.target or "",
            self.destination_label or "",
        )


def batch_target(items: Iterable[tuple[str, str]]) -> str:
    """The target a batch grant is signed over: a digest of exactly the
    ``(approval id, target fingerprint)`` pairs the person was shown.

    An id fixes the secret, the destination and the slot (a changed target is a
    new approval), and the fingerprint fixes the target, so the digest names
    everything approved. Sorted and newline-joined, so the order the page lists
    them in does not matter; the desktop shell computes the same string.
    """
    lines = sorted(f"{approval_id}:{fingerprint}" for approval_id, fingerprint in items)
    return "batch:" + hashlib.sha256("\n".join(lines).encode()).hexdigest()


def pinned_target(approval_id: str, fingerprint: str) -> str:
    """The target a single approval's grant is signed over when it is pinned to
    the approval's target: ``<id>@<fingerprint>`` (design
    align-cli-with-ui-and-add-tool-environments D9)."""
    return f"{approval_id}@{fingerprint}"


def grant_message(op: str, target: str, nonce: str) -> bytes:
    """The exact bytes a presence grant signs (the desktop shell signs the same)."""
    return f"coffer-presence-grant/v1\n{op}\n{target}\n{nonce}".encode()


#: The context string the grant key is derived under, from the master key.
GRANT_KEY_CONTEXT = b"coffer-presence-grant-key/v1"
#: The other keys derived from the master key, one per purpose, so a key that
#: proves one thing never proves another. In a signed build only Coffer's own
#: binaries can read the master key, so only they can hold these.
#: Seals the secret boundary's machine-local files (bindings, approvals, switch).
BOUNDARY_STATE_KEY_CONTEXT = b"coffer-boundary-state-key/v1"
#: The daemon answers the desktop shell's challenge with it: this is Coffer's daemon.
DAEMON_ATTEST_KEY_CONTEXT = b"coffer-daemon-attest-key/v1"
#: The model proxy answers the daemon's challenge with it: this is Coffer's proxy.
PROXY_ATTEST_KEY_CONTEXT = b"coffer-proxy-attest-key/v1"
#: Fingerprints a plaintext value a person said is not a secret (spec secret
#: "Remember a value a person says is not a secret"): no value, no plain hash.
PLAINTEXT_IGNORE_KEY_CONTEXT = b"coffer-plaintext-ignore-key/v1"


#: The destination kind of the local-process grant: a standalone secret that
#: ``coffer run`` may hand to a program on this machine.
LOCAL_PROCESS_KIND = "local_process"
#: Its one uid and slot: there is one such destination per secret.
LOCAL_PROCESS_UID = "coffer-run"
LOCAL_PROCESS_SLOT = "env"


def local_process_destination() -> SecretDestination:
    """Any program on this Mac that ``coffer run`` starts — including one an agent
    starts, which can then read the value. A high-trust grant: a person approves it
    in the desktop app, never the build's default or a value just supplied."""
    return SecretDestination(
        kind=LOCAL_PROCESS_KIND,
        uid=LOCAL_PROCESS_UID,
        target="any program coffer run starts on this Mac, which can read the value",
        label="coffer run",
    )


def sync_remote_destination(url: str) -> SecretDestination:
    """The sync remote's push token goes to the remote's URL; there is one remote."""
    return SecretDestination(kind="sync_remote", uid="remote", target=f"git {url}", label="sync")


def channel_destination(
    uid: str, name: str, channel_type: str, app_id: str = ""
) -> SecretDestination:
    """A channel's secret goes to its platform, as the app it names."""
    target = f"{channel_type} app {app_id}" if app_id else f"{channel_type} bot"
    return SecretDestination(kind="channel", uid=uid, target=target, label=name)
