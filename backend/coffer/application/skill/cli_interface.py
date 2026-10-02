"""A command-line tool's interface: read on request, kept per version.

``CliInterfaceService.get`` only reads what was kept — it never runs the tool,
so the page and the polls that fetch it start no process. ``read`` runs the
tool's help (``cli_discovery``) in a worker thread and keeps the tree on this
machine. What was kept is current while the tool's path, version and file
(size and mtime) are the same; a changed tool reads as ``not_read`` again, and
Read commands again replaces the tree. One read of a tool at a time.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Protocol

from coffer.application.skill.cli_discovery import HelpRunnerPort, discover
from coffer.application.skill.cli_requirements import CliRequirementService
from coffer.domain.skill.cli_help import DiscoveryStatus, Interface


class InterfaceStorePort(Protocol):
    def get(self, command: str) -> Interface | None: ...

    def put(self, command: str, interface: Interface) -> None: ...


class CliInterfaceService:
    def __init__(
        self,
        *,
        requirements: CliRequirementService,
        runner: HelpRunnerPort,
        store: InterfaceStorePort,
    ) -> None:
        self._requirements = requirements
        self._runner = runner
        self._store = store
        self._locks: dict[str, asyncio.Lock] = {}

    async def get(self, command: str) -> Interface:
        """What was kept for the tool as it is now; never runs it."""
        key, version = await self._identity(command)
        if key is None:
            return self._unavailable(command)
        kept = await asyncio.to_thread(self._store.get, command)
        if kept is not None and kept.key == key:
            return kept
        return Interface(DiscoveryStatus.NOT_READ, key=key, version=version)

    async def read(self, command: str) -> Interface:
        """Run the tool's help again and keep the result."""
        async with self._locks.setdefault(command, asyncio.Lock()):
            key, version = await self._identity(command)
            if key is None:
                return self._unavailable(command)
            path = key.split("\n", 1)[0]
            found = await asyncio.to_thread(discover, self._runner, path)
            found = replace(found, key=key, version=version)
            await asyncio.to_thread(self._store.put, command, found)
            return found

    async def _identity(self, command: str) -> tuple[str | None, str | None]:
        """``(key, version)``: the key is the path, version and file
        fingerprint the tree is valid for. ``None`` when the tool is not on
        this machine."""
        view = await self._requirements.get(command)
        path = view.probe.path
        if path is None:
            return None, None
        fingerprint = await asyncio.to_thread(self._requirements.fingerprint, path)
        return f"{path}\n{view.probe.version}\n{fingerprint}", view.probe.version

    @staticmethod
    def _unavailable(command: str) -> Interface:
        return Interface(
            DiscoveryStatus.UNAVAILABLE, message=f"{command} was not found on this machine."
        )


__all__ = ["CliInterfaceService", "InterfaceStorePort"]
