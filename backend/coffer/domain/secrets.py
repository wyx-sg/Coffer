"""The secret boundary's vocabulary: destinations, bindings, approvals, names.

A *destination* is a place Coffer sends a secret's plaintext — an MCP server's
environment variable or HTTP header, a channel adapter's credential, the sync
remote's push token, a provider connection's key. A *binding* is one secret
(a credential ref) sent to one slot of one destination, and it is approved for
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
from typing import Literal

#: The store namespace standalone secrets live under.
SECRET_NAMESPACE = "secret/"
#: How a file cites a standalone secret.
SECRET_URI_PREFIX = "coffer://secret/"
#: One ref segment, at most 64 characters: the name is quoted in files Coffer
#: cannot see, so it is fixed after creation.
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_URI_RE = re.compile(r"coffer://secret/([A-Za-z0-9_.-]{1,64})")

#: What a pending approval asks the person to allow.
ApprovalOp = Literal["bind", "add_secret", "replace_value", "disable_protection"]
ApprovalStatus = Literal["pending", "approved", "rejected", "superseded"]

#: What a presence grant may authorise. Each is one operation on one target.
GrantOp = Literal["reveal", "approve", "export_master_key"]
GRANT_OPS: tuple[str, ...] = ("reveal", "approve", "export_master_key")


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

    ``op`` is ``bind`` (a secret to a new destination or target),
    ``add_secret`` (a new standalone secret; its value waits as ciphertext),
    ``replace_value`` (a new value for a secret already in use; the new value
    waits as ciphertext and never appears here) or ``disable_protection``
    (turning the approval requirement off).
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
        if self.op == "bind":
            return (
                f"send secret {self.ref!r} to {self.destination_kind} "
                f"{self.destination_label!r} ({self.slot}) at {self.target}"
            )
        if self.op == "add_secret":
            name = standalone_name(self.ref or "") or self.ref
            return f"add the new secret {name!r}"
        if self.op == "replace_value":
            return f"replace the value of secret {self.ref!r}"
        return "turn off approval for new secret destinations"


def grant_message(op: str, target: str, nonce: str) -> bytes:
    """The exact bytes a presence grant signs (the desktop shell signs the same)."""
    return f"coffer-presence-grant/v1\n{op}\n{target}\n{nonce}".encode()


#: The context string the grant key is derived under, from the master key.
GRANT_KEY_CONTEXT = b"coffer-presence-grant-key/v1"


def sync_remote_destination(url: str) -> SecretDestination:
    """The sync remote's push token goes to the remote's URL; there is one remote."""
    return SecretDestination(kind="sync_remote", uid="remote", target=f"git {url}", label="sync")


def channel_destination(
    uid: str, name: str, channel_type: str, app_id: str = ""
) -> SecretDestination:
    """A channel's credential goes to its platform, as the app it names."""
    target = f"{channel_type} app {app_id}" if app_id else f"{channel_type} bot"
    return SecretDestination(kind="channel", uid=uid, target=target, label=name)
