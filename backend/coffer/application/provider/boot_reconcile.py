"""Boot heal for a connection Coffer believes is active but the agent is not on.

``is_active`` is a flag in Coffer's database; what it MEANS is a handful of keys
inside a file Coffer does not own — ``~/.claude/settings.json``, Codex's
``config.toml``. Those files are rewritten by their own CLIs, by other tooling,
and by the user, and are restored wholesale from backups. Nothing puts Coffer's
keys back, and nothing noticed they had gone: observed on a real machine, where
an ``is_active`` connection routed to Claude Code left no trace at all in the
settings file. The agent had been running on its built-in login for weeks while
every Coffer surface that asks "which connection is active here" answered from
the stale flag — including the chat model picker, which offered only that
connection's model ids.

**Direction matters.** This heals by clearing the flag, NEVER by writing the
projection back. Re-projecting would look symmetrical and is what the sync
post-import hook does — but the two have different evidence. An import just
carried the user's explicit switch from another machine; a flag left over from
some earlier session carries no such warrant, and acting on it would silently
re-route a user's agent through a gateway they are not currently using. The
agent's own config is the ground truth for what the agent is running on; Coffer
corrects its own record to match, and the user re-activates in one click if they
did want the connection.

The reverse drift — Coffer's keys present in the file while the registry says
inactive — is only reported. Removing them would change what the agent talks to,
which is exactly the kind of surprise this module exists to avoid.
"""

from __future__ import annotations

import pathlib
from collections.abc import Awaitable, Callable
from typing import Protocol as _Protocol

from coffer.application.provider.projector import ProviderProjector
from coffer.application.provider.targets import projection_targets
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import spec_for
from coffer.domain.agent.facets import AgentCatalog
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.resource import Resource


class _Lister(_Protocol):
    async def list(self) -> list[Resource]: ...


class _ConfigFileStore(_Protocol):
    def read_text(self, path: pathlib.Path) -> str | None: ...


#: ``(agent_type) -> None`` — ``ProviderService.deactivate``, the one operation
#: that puts an agent type back on its built-in login (clearing the flag,
#: auditing the switch, and removing any keys that ARE there).
Deactivate = Callable[[AgentType], Awaitable[object]]


class ProviderProjectionBootHeal:
    """Clears an ``is_active`` flag the agent's real config contradicts."""

    def __init__(
        self,
        *,
        providers: _Lister,
        agents: _Lister,
        config_store: _ConfigFileStore,
        deactivate: Deactivate,
        catalog: AgentCatalog,
    ) -> None:
        self._catalog = catalog
        self._providers = providers
        self._agents = agents
        self._config_store = config_store
        self._deactivate = deactivate

    async def heal(self) -> list[str]:
        """Returns one human-readable note per thing found — healed or merely
        reported. Never raises: a config file Coffer cannot read is somebody
        else's file being odd, not a reason for the daemon not to come up.
        """
        notes: list[str] = []
        agents = await self._enabled_agents()
        active = await self._active_by_agent_type(agents)
        for agent_type, connection in active.items():
            registered = ProviderProjector.agents_of_type(agents, agent_type)
            if not registered:
                # Nothing of this type on this machine: the flag describes
                # another machine's agents and must be left alone.
                continue
            if self._any_projected(registered, agent_type):
                continue
            try:
                await self._deactivate(agent_type)
            except Exception as e:
                notes.append(f"{agent_type.value}: could not clear stale '{connection}': {e}")
                continue
            notes.append(
                f"{agent_type.value}: '{connection}' was marked active but its projection is "
                "absent from the agent's config; cleared the flag — the agent is on its "
                "built-in login. Re-activate the connection to use it again."
            )
        return notes

    # --- internals -----------------------------------------------------------

    async def _enabled_agents(self) -> list[Resource]:
        """Agent rows whose config still parses. A row Coffer can no longer read
        is surfaced by the agent routes; it must not stop this pass."""
        rows: list[Resource] = []
        for row in await self._agents.list():
            try:
                AgentConfig.model_validate(row.config)
            except Exception:
                continue
            rows.append(row)
        return rows

    async def _active_by_agent_type(self, agents: list[Resource]) -> dict[AgentType, str]:
        """The connection name flagged active for each agent type it covers.

        ``agents`` is the registry the connections' scopes are resolved against
        — a scope holds agent uids, so which types a connection reaches is a
        question only the registry can answer. The caller has already read it
        for the projection check, so it is passed in rather than re-listed.
        """
        active: dict[AgentType, str] = {}
        for row in sorted(await self._providers.list(), key=lambda r: r.name):
            try:
                cfg = ProviderConfig.model_validate(row.config)
            except Exception:
                continue
            if not cfg.is_active:
                continue
            # Framework scope decides the reach (ADR per-agent-resource-scope); ``is_active``
            # decides only whether this is the connection currently projected
            # into those agents, which is the very claim this pass verifies.
            for agent_type in projection_targets(row, cfg, agents):
                active.setdefault(agent_type, row.name)
        return active

    def _any_projected(self, agents: list[Resource], agent_type: AgentType) -> bool:
        """True when at least one registered agent of this type really carries
        Coffer's keys. One is enough: the flag is per connection, not per agent,
        so a single projected agent means the activation did take effect."""
        facet = self._catalog.provider_projection(agent_type)
        if facet is None:
            # Nothing this agent could carry: the flag cannot be contradicted.
            return True
        for agent in agents:
            try:
                cfg = AgentConfig.model_validate(agent.config)
                spec = spec_for(cfg.type, facet.config_key, cfg.resolved_config_dir())
                text = self._config_store.read_text(spec.path) or ""
                # Asked of the facet, which removes its keys and compares the
                # parsed documents — so the check never drifts from what
                # projection writes. A document that does not parse raises.
                projected = facet.is_present(text)
            except Exception:
                # Unreadable or unparseable: assume projected. Guessing "absent"
                # from a file we could not inspect would clear a flag on no
                # evidence, which is the worse of the two mistakes.
                return True
            if projected:
                return True
        return False


__all__ = ["Deactivate", "ProviderProjectionBootHeal"]
