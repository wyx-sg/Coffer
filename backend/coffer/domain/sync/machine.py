"""What a machine is, in a vault that spans several (spec vault-sync).

Identity and name are separate things, and keeping them separate is the whole
point of this module:

* ``machine_id`` is **derived from the host** and never changes. It keys the
  descriptor's filename, every ``scope.machines`` entry, and the registry
  table. It must survive reinstalling and uninstalling Coffer, because a
  machine that comes back under a new id is a ghost — everything scoped to the
  old one silently stops — and because only a surviving id can tell a machine
  *returning* to a remote from one joining it for the first time. Those two
  cases need opposite handling, so that distinction is load-bearing.
* ``name`` is a label the user may change at any time, at no cost, because
  nothing references it.

Pure domain: deriving the id from the host is infrastructure's job, and the
hashing that turns a hardware identifier into something publishable lives here
because it is part of what a machine id *is*.
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Mapping
from datetime import date
from typing import Any

#: Domain-separates the digest, so a Coffer machine id can never collide with
#: some other use of the same platform identifier.
_PREFIX = "coffer-machine:"
#: Long enough that collision is not a concern, short enough to read in a UI.
ID_LENGTH = 16


def derive_machine_id(raw: str) -> str:
    """Turn a platform identifier into the id that travels.

    The raw value is a hardware or install identifier — an ``IOPlatformUUID``,
    a ``/etc/machine-id``. It MUST NOT be written into the user's repository,
    so what travels is a digest of it. Stable for the life of the host, and
    not reversible into the identifier it came from.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError("cannot derive a machine id from an empty identifier")
    return hashlib.sha256((_PREFIX + raw).encode("utf-8")).hexdigest()[:ID_LENGTH]


@dataclasses.dataclass(frozen=True, slots=True)
class MachineDescriptor:
    """One machine's published self-description.

    Each machine writes exactly one of these, at ``machines/<id>.yaml``, and
    writes no other machine's. Disjoint ownership is why the registry needs no
    convergence machinery of its own: two machines can never stage a change to
    the same path, so git merges descriptors trivially and the registry is
    simply whatever ``machines/*.yaml`` currently holds.
    """

    machine_id: str
    name: str
    os: str
    hostname: str
    coffer_version: str
    #: The day this machine last converged. A *day*, not an instant: restamping
    #: every round would commit a heartbeat every interval, and the history is
    #: meant to record changes rather than ticks.
    last_converged_on: date | None = None
    #: The pointer this machine reached, published so the remote can hand it
    #: back. The local pointer is lost to a reinstall or a wiped ``~/.coffer``;
    #: this copy is what lets a returning machine recover its base instead of
    #: being mistaken for a new one and republishing everything the others
    #: deleted while it was away.
    last_converged_commit: str | None = None
    #: Short hash of the master key, so another machine can say "your
    #: credentials will not decrypt here" instead of the user comparing
    #: fingerprints by hand. Never the key.
    key_fingerprint: str | None = None
    #: Names of the agents registered on this machine.
    agents: tuple[str, ...] = ()

    def to_doc(self) -> dict[str, Any]:
        """The serialized form. Deterministic: the bundle sorts keys, and every
        value here is a scalar or a list of scalars."""
        return {
            "name": self.name,
            "os": self.os,
            "hostname": self.hostname,
            "coffer_version": self.coffer_version,
            "last_converged_on": self.last_converged_on.isoformat()
            if self.last_converged_on
            else None,
            "last_converged_commit": self.last_converged_commit,
            "key_fingerprint": self.key_fingerprint,
            "agents": list(self.agents),
        }

    @classmethod
    def from_doc(cls, machine_id: str, doc: Mapping[str, Any]) -> MachineDescriptor:
        """Parse a descriptor another machine wrote.

        Tolerant by design: a descriptor is written by a possibly-newer build
        on someone else's machine, and a field this build does not understand
        must not stop the registry from rendering. Missing fields become None.
        """
        raw_day = doc.get("last_converged_on")
        agents = doc.get("agents")
        return cls(
            machine_id=machine_id,
            name=str(doc.get("name") or machine_id),
            os=str(doc.get("os") or ""),
            hostname=str(doc.get("hostname") or ""),
            coffer_version=str(doc.get("coffer_version") or ""),
            last_converged_on=_parse_day(raw_day),
            last_converged_commit=_opt_str(doc.get("last_converged_commit")),
            key_fingerprint=_opt_str(doc.get("key_fingerprint")),
            agents=tuple(str(a) for a in agents) if isinstance(agents, list) else (),
        )

    def stamped_on(self, day: date, commit: str | None) -> MachineDescriptor:
        """This descriptor with today's convergence recorded."""
        return dataclasses.replace(self, last_converged_on=day, last_converged_commit=commit)


def _opt_str(value: Any) -> str | None:
    return str(value) if isinstance(value, str) and value else None


def _parse_day(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
