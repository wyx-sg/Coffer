"""Which connection an agent's file is on, for the provider projection target."""

from __future__ import annotations

from typing import Any

from coffer.domain.resource import Resource


def named_connection(
    have: dict[str, Any], want: dict[str, Any] | None, by_uid: dict[str, Resource]
) -> str | None:
    """The wanted connection, when every key whose wanted value names it
    (Codex's provider label) holds what it writes, or — when none does — when
    every key Coffer owns holds what projecting it would write."""
    if want is None:
        return None
    uid = str(want["connection"])
    row = by_uid.get(uid)
    labels = [uid] + ([row.name] if row is not None and row.name else [])
    naming = [
        k
        for k, v in want.items()
        if k != "connection" and isinstance(v, str) and any(n in v for n in labels)
    ]
    if naming and all(have.get(k) == want[k] for k in naming):
        return uid
    # A file that names no connection at all — the proxy form, where the
    # agent calls the local proxy and the proxy decides the upstream — is
    # on the wanted connection exactly when every key Coffer owns holds
    # what projecting it would write.
    if not naming and all(have.get(k) == v for k, v in want.items() if k != "connection"):
        return uid
    return None
