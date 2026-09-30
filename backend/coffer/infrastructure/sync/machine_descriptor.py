"""This machine as a sync round describes it (implements
``application.sync.round_ports.MachinePort``).

The descriptor is ``machines/<machine id>.json`` (spec vault-sync "Carry the
descriptor fields"): the id derived from the host, the label a person chose,
the OS and host name, this build's version, the time of the last round that
moved anything and the commit it converged at, the key fingerprint, and each
agent with its plugin inventory. The inventory is gathered by the service
before every round (it is read through the agents' own config, which is async
work) and handed in here, so that writing the descriptor inside the round's
worker thread reads nothing but memory and the label file.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable, Mapping, Sequence

from coffer.domain.sync.machine import (
    AgentInventory,
    MachineDescriptor,
    descriptor_path,
    machine_id_of,
)


class HostMachine:
    def __init__(
        self,
        *,
        machine_id: str,
        name: Callable[[], str],
        os_label: Callable[[], str],
        coffer_version: str,
        key_fingerprint: Callable[[], str | None],
        hostname: Callable[[], str] = socket.gethostname,
    ) -> None:
        self._id = machine_id
        self._name = name
        self._os = os_label
        self._version = coffer_version
        self._fingerprint = key_fingerprint
        self._hostname = hostname
        self._agents: tuple[AgentInventory, ...] = ()
        self._lock = threading.Lock()

    def set_agents(self, agents: Sequence[AgentInventory]) -> None:
        with self._lock:
            self._agents = tuple(sorted(agents, key=lambda a: (a.type, a.name)))

    def agents(self) -> tuple[AgentInventory, ...]:
        with self._lock:
            return self._agents

    # --- MachinePort -----------------------------------------------------------

    def machine_id(self) -> str:
        return self._id

    def label(self) -> str:
        return self._name() or self._id

    def descriptor_path(self) -> str:
        return descriptor_path(self._id)

    def describe(self, *, last_round_at: str | None, last_commit: str | None) -> MachineDescriptor:
        return MachineDescriptor(
            machine_id=self._id,
            name=self.label(),
            os=self._os(),
            hostname=self._hostname(),
            coffer_version=self._version,
            last_round_at=last_round_at,
            last_converged_commit=last_commit,
            key_fingerprint=self._fingerprint(),
            agents=self.agents(),
        )

    def descriptor(self, *, last_round_at: str | None, last_commit: str | None) -> bytes:
        return self.describe(last_round_at=last_round_at, last_commit=last_commit).to_bytes()

    def labels(self, files: Mapping[str, bytes]) -> dict[str, str]:
        """Each descriptor's machine id to its label (the id when unreadable)."""
        out: dict[str, str] = {}
        for path, data in files.items():
            machine = machine_id_of(path)
            if machine is None:
                continue
            parsed = MachineDescriptor.parse(machine, data)
            out[machine] = parsed.name if parsed is not None else machine
        return out


__all__ = ["HostMachine"]
