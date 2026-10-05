"""A standalone secret's local-process grant, read from lists already loaded
(spec secret "Resolve standalone secrets into one child with coffer run")."""

from __future__ import annotations

from typing import Literal

from coffer.domain.secrets import LOCAL_PROCESS_KIND, SecretApproval, SecretBinding


def local_access_of(
    bindings: list[SecretBinding], pending: list[SecretApproval], ref: str
) -> Literal["on", "pending", "off"]:
    """A standalone secret's local-process grant, from the lists already read."""
    if any(b.ref == ref and b.destination_kind == LOCAL_PROCESS_KIND for b in bindings):
        return "on"
    if any(
        a.op == "bind" and a.ref == ref and a.destination_kind == LOCAL_PROCESS_KIND
        for a in pending
    ):
        return "pending"
    return "off"
