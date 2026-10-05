"""Values a person said are not secrets (spec secret "Remember a value a
person says is not a secret").

Find plaintext keys and vault sync's push check both stop reporting such a
value on this machine, wherever it sits and whatever else in its file changes.
A value is remembered only by its **fingerprint**: an HMAC under a key derived
from the master key (``PLAINTEXT_IGNORE_KEY_CONTEXT``), so the list holds no
value and no plain hash a guess could be checked against. Matching is by the
fingerprint alone — the statement is about the value — while each entry keeps
where it was first found, for display and the audit.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from coffer.application.secret.presence import derive_purpose_key
from coffer.domain.secrets import PLAINTEXT_IGNORE_KEY_CONTEXT

#: ``value -> fingerprint``, or ``None`` when no master key is available.
Fingerprinter = Callable[[str], str | None]


@dataclass(frozen=True, slots=True)
class IgnoredValue:
    """One remembered value: its fingerprint and where it was first found."""

    fingerprint: str
    rule: str
    #: A vault-relative file path, or ``mcp_server/<name>/<env|header>`` for a server.
    place: str
    key: str
    actor: str
    ignored_at: str


class PlaintextIgnorePort(Protocol):
    """``local/secret/plaintext-ignored.json``: machine-local, never synced."""

    def fingerprints(self) -> frozenset[str]: ...
    def entries(self) -> tuple[IgnoredValue, ...]: ...
    def add(self, entries: Iterable[IgnoredValue]) -> None: ...
    def remove(self, fingerprints: Iterable[str]) -> None: ...


def fingerprint(master_key: bytes, value: str) -> str:
    """The value's fingerprint under ``master_key``; the same on every machine
    that shares the vault's master key."""
    key = derive_purpose_key(master_key, PLAINTEXT_IGNORE_KEY_CONTEXT)
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def fingerprinter(current_key: Callable[[], bytes | None]) -> Fingerprinter:
    """A :data:`Fingerprinter` over whatever master key is current."""

    def of(value: str) -> str | None:
        key = current_key()
        return fingerprint(key, value) if key else None

    return of


__all__ = ["Fingerprinter", "IgnoredValue", "PlaintextIgnorePort", "fingerprint", "fingerprinter"]
