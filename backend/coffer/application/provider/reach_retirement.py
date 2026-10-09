"""Retire a connection's off switch and per-agent scope (ADR
provider-reach-is-what-its-addresses-serve; spec provider-switching "Retire
the off switch and scope of existing connections").

A connection reaches the agents its addresses serve, and which connection an
agent runs on is the agent's own choice; there is nothing left to switch off or
scope. Connections saved before that rule are brought in line at startup:

- an agent on a switched-off connection was already on its own login as far
  as routing went; it is put back on it properly (Coffer's keys removed from
  its config, its connection cleared), so turning the connection on cannot
  quietly re-route it;
- the connection is then switched on, and any scope it stored is cleared.

Idempotent: a connection that is on and unscoped is left alone. Best-effort: a
failure is logged, never fatal, and the next start tries again.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from coffer.application.provider.anthropic_address import fill_anthropic_addresses
from coffer.domain.agent.config import AgentConfig

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService

_log = logging.getLogger(__name__)
_ACTOR = "coffer"


async def retire_off_switch(service: ProviderService) -> list[str]:
    """Do what the module says; the names of the connections changed."""
    changed: list[str] = []
    for row in await service.list():
        try:
            if not row.enabled:
                for agent in await service._agents.list():
                    cfg = AgentConfig.model_validate(agent.config)
                    if cfg.connection_uid == row.uid:
                        await service.deactivate(cfg.type, actor=_ACTOR)
                await service._resources.set_enabled(row.uid, True, actor=_ACTOR)
            if row.scope is not None:
                await service._resources.update_scope(row.uid, None, actor=_ACTOR)
            if not row.enabled or row.scope is not None:
                changed.append(row.name)
        except Exception:
            _log.warning("provider.reach_retire_failed", exc_info=True)
    if changed:
        _log.info("provider.reach_retired", extra={"connections": changed})
    return changed


async def migrate_saved_connections(service: ProviderService) -> None:
    """Bring connections saved under older rules in line before the boot pass
    projects them: retire their off switch and scope, then fill in the
    Anthropic address (ADRs provider-reach-is-what-its-addresses-serve,
    one-connection-serves-both-wires)."""
    await retire_off_switch(service)
    await fill_anthropic_addresses(service)


__all__ = ["migrate_saved_connections", "retire_off_switch"]
