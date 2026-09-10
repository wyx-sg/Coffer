"""Agent plugin inventory as a synced state area (spec vault-export-import).

**An inventory, not a replicator.** Export writes down which plugins each
agent has on THIS machine; import stores that list in the vault and writes
nothing into any agent's config. On a new machine you read the list and install
them with the vendor's own CLI.

That asymmetry is deliberate, not a shortcut. Coffer removed its plugin write
paths precisely because hand-writing another tool's private config format
corrupts it silently when the format moves (spec agent-registry FR-032/FR-033), and it
never had an *install* path at all — the retired code could only toggle and
uninstall. "Keep the writes so sync can use them later" was never a real
argument: installing is the one action sync would need, and it would have had
to be written from scratch regardless.

What the inventory does give is the thing an agent cannot do for itself. Codex
on a new laptop has no idea which sixteen plugins the old one had; that list
exists only on the machine that holds them. Carrying it is the same shape as
aggregating MCP servers or sharing skills — Coffer knowing something across
machines that no single agent does.
"""

from __future__ import annotations

from typing import Any, Protocol

from coffer.application.resource_service import ResourceService

AREA = "agent-plugins"


class _PluginListerPort(Protocol):
    """The read half of ``AgentPluginService`` (structural, so this module does
    not depend on the service's whole surface)."""

    async def list_plugins(self, name: str) -> Any: ...


class AgentPluginSyncState:
    """Implements ``application.sync.ports.SyncedStatePort`` structurally."""

    area = AREA

    def __init__(self, resources: ResourceService, plugins: _PluginListerPort) -> None:
        self._resources = resources
        self._plugins = plugins

    async def export_docs(self) -> tuple[list[tuple[str, dict[str, object]]], list[str]]:
        """One doc per agent that has plugins; agents with none are skipped.

        A read failure on one agent (an unreadable config dir, a config that no
        longer parses) skips that agent rather than failing the export — a
        bundle is worth more with fifteen of sixteen agents than not at all.
        """
        docs: list[tuple[str, dict[str, object]]] = []
        owned: list[str] = []
        for resource in await self._resources.list(kind="agent"):
            owned.append(resource.name)
            try:
                listing = await self._plugins.list_plugins(resource.name)
            except Exception:
                continue
            items = [
                {
                    "id": p.id,
                    "name": p.name,
                    "marketplace": p.marketplace,
                    "enabled": p.enabled,
                    # Best-effort: absent for agents whose inventory records no
                    # version. Written so the far side knows what to install,
                    # not to pin it.
                    "version": p.version,
                }
                for p in getattr(listing, "items", [])
            ]
            if not items:
                continue
            marketplaces = [
                {"name": m.name, "source_type": m.source_type, "source": m.source}
                for m in getattr(listing, "marketplaces", [])
            ]
            docs.append(
                (
                    resource.name,
                    {
                        "agent": resource.name,
                        "plugins": sorted(items, key=lambda p: str(p["id"])),
                        "marketplaces": sorted(marketplaces, key=lambda m: str(m["name"])),
                    },
                )
            )
        return docs, owned

    async def import_docs(self, docs: list[tuple[str, dict[str, object]]]) -> list[tuple[str, str]]:
        """A no-op by design: the bundle already holds the inventory.

        Import writes nothing into any agent's configuration. Coffer has no
        install path and deliberately does not hand-write another tool's
        private plugin format; the list lands in
        ``~/.coffer/sync/state/agent-plugins/<agent>.yaml`` for the user to
        read and act on with the vendor's own CLI.

        Returning no errors is the honest answer — nothing was attempted, so
        nothing failed.
        """
        return []
