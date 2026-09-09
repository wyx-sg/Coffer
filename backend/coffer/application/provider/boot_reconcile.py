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

import json
import pathlib
import tomllib
from collections.abc import Awaitable, Callable
from typing import Protocol as _Protocol

from coffer.application.provider.projector import ProviderProjector
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import spec_for
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import Protocol, ProviderConfig
from coffer.domain.provider.projection import (
    remove_anthropic_settings,
    remove_codex_provider,
    target_for_agent,
    wire_for_agent,
)
from coffer.domain.resource import Resource


class _Lister(_Protocol):
    async def list(self) -> list[Resource]: ...


class _ConfigFileStore(_Protocol):
    def read_text(self, path: pathlib.Path) -> str | None: ...


#: ``(wire) -> None`` — ``ProviderService.deactivate``, the one operation that
#: puts an agent type back on its built-in login (clearing the flag, auditing
#: the switch, and removing any keys that ARE there).
Deactivate = Callable[[Protocol], Awaitable[object]]


def _projection_present(text: str, agent_type: AgentType) -> bool:
    """Whether Coffer's keys are in ``text``.

    Asked by removing them and seeing whether anything moved, so the check can
    never drift from what projection actually writes — the remover is the same
    pure function ``deproject`` uses. The comparison is on PARSED data, not on
    the strings: the removers re-serialise, so an untouched file comes back
    reindented and a textual diff would claim a projection in every file.

    A document neither Coffer nor the remover can parse is not evidence of
    anything; the caller treats that (via the raised error) as "assume present".
    """
    if not text.strip():
        return False
    if agent_type is AgentType.CLAUDE_CODE:
        return bool(json.loads(remove_anthropic_settings(text)) != json.loads(text))
    return bool(tomllib.loads(remove_codex_provider(text)) != tomllib.loads(text))


class ProviderProjectionBootHeal:
    """Clears an ``is_active`` flag the agent's real config contradicts."""

    def __init__(
        self,
        *,
        providers: _Lister,
        agents: _Lister,
        config_store: _ConfigFileStore,
        deactivate: Deactivate,
    ) -> None:
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
        active = await self._active_by_agent_type()
        for agent_type, connection in active.items():
            registered = ProviderProjector.agents_of_type(agents, agent_type)
            if not registered:
                # Nothing of this type on this machine: the flag describes
                # another machine's agents and must be left alone.
                continue
            if self._any_projected(registered, agent_type):
                continue
            wire = wire_for_agent(agent_type)
            if wire is None:  # pragma: no cover — every type maps to a wire
                continue
            try:
                await self._deactivate(wire)
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

    async def _active_by_agent_type(self) -> dict[AgentType, str]:
        """The connection name flagged active for each agent type it covers."""
        active: dict[AgentType, str] = {}
        for row in sorted(await self._providers.list(), key=lambda r: r.name):
            try:
                cfg = ProviderConfig.model_validate(row.config)
            except Exception:
                continue
            if not cfg.is_active:
                continue
            for value in cfg.resolved_compatible_agents():
                try:
                    agent_type = AgentType(value)
                except ValueError:
                    continue
                active.setdefault(agent_type, row.name)
        return active

    def _any_projected(self, agents: list[Resource], agent_type: AgentType) -> bool:
        """True when at least one registered agent of this type really carries
        Coffer's keys. One is enough: the flag is per connection, not per agent,
        so a single projected agent means the activation did take effect."""
        target = target_for_agent(agent_type)
        if target is None:  # pragma: no cover — every type has a target
            return True
        for agent in agents:
            try:
                cfg = AgentConfig.model_validate(agent.config)
                spec = spec_for(cfg.type, target.config_key, cfg.resolved_config_dir())
                text = self._config_store.read_text(spec.path) or ""
                projected = _projection_present(text, agent_type)
            except Exception:
                # Unreadable or unparseable: assume projected. Guessing "absent"
                # from a file we could not inspect would clear a flag on no
                # evidence, which is the worse of the two mistakes.
                return True
            if projected:
                return True
        return False


__all__ = ["Deactivate", "ProviderProjectionBootHeal"]
