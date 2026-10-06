"""What the sync service needs beyond a round's own ports.

The round (``round_ports``) runs in one worker thread and touches only git
and files. The service around it also answers the Sync page: the secret files a
remote would carry, this machine's descriptor with its agents' plugin
inventory, and a remote probed before it is saved. Each is a port here so the
application layer names no adapter. The master key's own operations are the
secret store's (``application.secret.master_key_import``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from coffer.application.sync.round_ports import MachinePort
from coffer.domain.sync.machine import AgentInventory, MachineDescriptor


class SecretFilesPort(Protocol):
    """The ciphertext files a remote that carries secrets would push."""

    def count(self) -> int: ...
    def locked_refs(self) -> list[str]: ...


class HostMachinePort(MachinePort, Protocol):
    """This machine: the round's port plus what the machines list and a
    rename read."""

    def set_agents(self, agents: Sequence[AgentInventory]) -> None: ...
    def describe(
        self, *, last_round_at: str | None, last_commit: str | None
    ) -> MachineDescriptor: ...


class AgentInventoryPort(Protocol):
    """Each agent registered on this machine and the plugins it has."""

    async def inventory(self) -> list[AgentInventory]: ...


class RemoteProbePort(Protocol):
    """A look at a remote before it is saved (the setup form's "Check")."""

    def probe(
        self, url: str, branch: str, token: str | None, username: str | None = None
    ) -> str | None: ...
    def probe_layout(
        self, url: str, branch: str, token: str | None, username: str | None = None
    ) -> int | None: ...


__all__ = [
    "AgentInventoryPort",
    "HostMachinePort",
    "RemoteProbePort",
    "SecretFilesPort",
]


class VaultMoverPort(Protocol):
    """Moves the vault's folder to another place and says where it is."""

    def real_path(self) -> str: ...
    def default_path(self) -> str: ...
    def check(self, to: str) -> None: ...
    def move(self, to: str) -> tuple[str, str]: ...
