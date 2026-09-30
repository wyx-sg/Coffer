"""The one user-owned sync remote (spec vault-sync "Allow at most one user-owned sync remote").

A remote is a rendezvous, never a system of record: each machine's vault
stays complete, so the remote can be deleted and rebuilt from any one machine.
It is machine-local configuration (``local/sync/remote.json``) — which remote
this machine converges with is a fact about this machine.

``credential_ref`` names a secret in the credential store; the secret itself
is never on this object, so a remote can be logged or returned by the API
without redaction. ``include_credentials`` decides whether ``credentials/``
is committed at all (ADR credentials-across-machines).
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any

from coffer.domain.error_base import CofferError

DEFAULT_BRANCH = "main"
DEFAULT_INTERVAL_SECONDS = 3600
MIN_INTERVAL_SECONDS = 60

_BRANCH_FORBIDDEN_CHARS = re.compile(r"[\x00-\x20\x7f~^:?*\[\\]")
BRANCH_PATTERN = r"^[^-\s~^:?*\[\\\x00-\x1f\x7f][^\s~^:?*\[\\\x00-\x1f\x7f]*$"
URL_PATTERN = r"^[^-\s]\S*$"


class SyncRemoteInvalid(CofferError):  # noqa: N818
    """A URL or branch git would read as an option or refuse. Maps to 422."""

    code = "SYNC_REMOTE_INVALID"


def validate_branch(branch: str) -> str:
    """``branch`` stripped, or ``SyncRemoteInvalid`` if git would refuse it
    (the rules of ``git check-ref-format --branch``, restated)."""
    name = branch.strip()
    if not name:
        raise SyncRemoteInvalid("branch must not be empty")
    if name.startswith("-"):
        raise SyncRemoteInvalid("branch must not start with '-'")
    if _BRANCH_FORBIDDEN_CHARS.search(name):
        raise SyncRemoteInvalid("branch contains a character git does not allow")
    if ".." in name or "@{" in name:
        raise SyncRemoteInvalid("branch must not contain '..' or '@{'")
    if name == "HEAD" or name.endswith(".") or name.endswith("/") or name.startswith("/"):
        raise SyncRemoteInvalid(f"not a usable branch name: {name!r}")
    for component in name.split("/"):
        if not component:
            raise SyncRemoteInvalid("branch must not contain an empty path component")
        if component.startswith(".") or component.endswith(".lock"):
            raise SyncRemoteInvalid(f"not a usable branch name: {name!r}")
    return name


def validate_url(url: str) -> str:
    """``url`` stripped, or ``SyncRemoteInvalid`` when git would read it as an
    option rather than a remote."""
    value = url.strip()
    if not value:
        raise SyncRemoteInvalid("url must not be empty")
    if value.startswith("-") or any(ch.isspace() for ch in value):
        raise SyncRemoteInvalid("url must not start with '-' or contain spaces")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class SyncRemote:
    url: str
    branch: str = DEFAULT_BRANCH
    credential_ref: str | None = None
    include_credentials: bool = False
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS
    enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "url", validate_url(self.url))
        object.__setattr__(self, "branch", validate_branch(self.branch))
        if self.interval_seconds <= 0:
            raise SyncRemoteInvalid("interval_seconds must be positive")
        if self.interval_seconds < MIN_INTERVAL_SECONDS:
            object.__setattr__(self, "interval_seconds", MIN_INTERVAL_SECONDS)

    def to_json(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> SyncRemote:
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in known})


__all__ = [
    "BRANCH_PATTERN",
    "DEFAULT_BRANCH",
    "DEFAULT_INTERVAL_SECONDS",
    "MIN_INTERVAL_SECONDS",
    "URL_PATTERN",
    "SyncRemote",
    "SyncRemoteInvalid",
    "validate_branch",
    "validate_url",
]
