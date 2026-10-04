"""What a machine is, in a vault that spans several (spec vault-sync
"Publish one descriptor per machine", "Keep machine identity across reinstalls").

Identity and name are separate things, and keeping them separate is the point:

* ``machine_id`` is **derived from the host** and never changes. It names the
  descriptor's file (``machines/<machine_id>.json``) and the ``Coffer-Machine``
  trailer of every commit this machine makes. It must survive reinstalling
  Coffer: only a surviving id tells a machine *returning* to a remote — whose
  descriptor carries the commit it last converged at, the base of its join —
  from one joining for the first time.
* ``name`` is a label a person may change at any time, at no cost, because
  nothing references it.

Each machine writes exactly one descriptor and no other machine's, so two
machines never change the same file and descriptors never conflict (spec
vault-sync "Write only this machine's descriptor"). The descriptor also
carries each agent's plugin inventory: the one thing about a machine's agents
no single agent can tell another machine — which plugins to install there,
with the vendor's own CLI (spec vault-sync "Record plugins as an inventory,
not a replicator").

Pure domain: deriving the id from the host is infrastructure's job; the hash
that turns a hardware identifier into something publishable is part of what a
machine id *is*, so it lives here.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping
from typing import Any

#: Domain-separates the digest, so a Coffer machine id can never collide with
#: some other use of the same platform identifier.
_PREFIX = "coffer-machine:"
#: Long enough that collision is not a concern, short enough to read in a UI.
ID_LENGTH = 16
#: The descriptor's own format version (ADR every-vault-file-carries-its-format-version).
DESCRIPTOR_FORMAT = 1


def derive_machine_id(raw: str) -> str:
    """Turn a platform identifier into the id that travels.

    The raw value is a hardware or install identifier — an ``IOPlatformUUID``,
    a ``/etc/machine-id``. It must not be written into the user's repository,
    so what travels is a digest of it: stable for the life of the host, and
    not reversible into the identifier it came from.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError("cannot derive a machine id from an empty identifier")
    return hashlib.sha256((_PREFIX + raw).encode("utf-8")).hexdigest()[:ID_LENGTH]


@dataclasses.dataclass(frozen=True, slots=True)
class Plugin:
    """One plugin an agent has on the machine, as its vendor names it."""

    id: str
    name: str = ""
    marketplace: str | None = None
    enabled: bool = True
    version: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class AgentInventory:
    """One agent on the machine: its type and the plugins it has."""

    type: str
    name: str = ""
    plugins: tuple[Plugin, ...] = ()


@dataclasses.dataclass(frozen=True, slots=True)
class MachineDescriptor:
    """One machine's published self-description, ``machines/<id>.json``."""

    machine_id: str
    name: str
    os: str = ""
    hostname: str = ""
    coffer_version: str = ""
    #: When this machine last finished a round that moved anything (ISO time).
    last_round_at: str | None = None
    #: The commit that round converged at — the base a returning machine's
    #: join recovers when its own local state is gone.
    last_converged_commit: str | None = None
    #: Short hash of the master key, so another machine can say "your secrets
    #: will not decrypt here". Never the key.
    key_fingerprint: str | None = None
    agents: tuple[AgentInventory, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "format_version": DESCRIPTOR_FORMAT,
            "machine_id": self.machine_id,
            "name": self.name,
            "os": self.os,
            "hostname": self.hostname,
            "coffer_version": self.coffer_version,
            "last_round_at": self.last_round_at,
            "last_converged_commit": self.last_converged_commit,
            "key_fingerprint": self.key_fingerprint,
            "agents": [
                {
                    "type": a.type,
                    "name": a.name,
                    "plugins": [dataclasses.asdict(p) for p in a.plugins],
                }
                for a in self.agents
            ],
        }

    def to_bytes(self) -> bytes:
        return (json.dumps(self.to_json(), indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    @classmethod
    def from_json(cls, machine_id: str, doc: Mapping[str, Any]) -> MachineDescriptor:
        """Parse a descriptor another machine wrote.

        Tolerant by design: a descriptor may come from a newer build on
        someone else's machine, and a field this build does not know must not
        stop the machines list from rendering. Missing fields read as empty.
        """
        agents: list[AgentInventory] = []
        for raw in doc.get("agents") or ():
            if not isinstance(raw, Mapping) or not raw.get("type"):
                continue
            plugins = tuple(
                Plugin(
                    id=str(p.get("id")),
                    name=str(p.get("name") or ""),
                    marketplace=_opt_str(p.get("marketplace")),
                    enabled=bool(p.get("enabled", True)),
                    version=_opt_str(p.get("version")),
                )
                for p in raw.get("plugins") or ()
                if isinstance(p, Mapping) and p.get("id")
            )
            agents.append(
                AgentInventory(
                    type=str(raw["type"]), name=str(raw.get("name") or ""), plugins=plugins
                )
            )
        return cls(
            machine_id=str(doc.get("machine_id") or machine_id),
            name=str(doc.get("name") or machine_id),
            os=str(doc.get("os") or ""),
            hostname=str(doc.get("hostname") or ""),
            coffer_version=str(doc.get("coffer_version") or ""),
            last_round_at=_opt_str(doc.get("last_round_at")),
            last_converged_commit=_opt_str(doc.get("last_converged_commit")),
            key_fingerprint=_opt_str(doc.get("key_fingerprint")),
            agents=tuple(agents),
        )

    @classmethod
    def parse(cls, machine_id: str, data: bytes) -> MachineDescriptor | None:
        """A descriptor from its file's bytes, or ``None`` when they are not
        a JSON object."""
        try:
            doc = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None
        return cls.from_json(machine_id, doc) if isinstance(doc, dict) else None


def descriptor_path(machine_id: str) -> str:
    """Where a machine's descriptor lives in the vault."""
    return f"machines/{machine_id}.json"


def machine_id_of(path: str) -> str | None:
    """The machine a descriptor path names, or ``None`` for another path."""
    if path.startswith("machines/") and path.endswith(".json") and path.count("/") == 1:
        return path[len("machines/") : -len(".json")] or None
    return None


def _opt_str(value: Any) -> str | None:
    return str(value) if isinstance(value, str) and value else None


__all__ = [
    "DESCRIPTOR_FORMAT",
    "ID_LENGTH",
    "AgentInventory",
    "MachineDescriptor",
    "Plugin",
    "derive_machine_id",
    "descriptor_path",
    "machine_id_of",
]
