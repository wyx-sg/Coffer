"""Give existing OpenAI-protocol connections the Anthropic address they need
(ADR one-connection-serves-both-wires; spec provider-switching "Fill in the
Anthropic address of an existing connection").

A connection serves Claude Code only when it has an address for the Anthropic
wire. Connections saved before that rule get one at startup, so nothing that
worked stops working and a known vendor works from both agents:

- its base URL is a vendor whose Anthropic root is known (DeepSeek) and Codex
  does not run on it → that root. The key then waits for approval for the new
  address before it is sent there, as for any new destination. Codex on it
  would wait too, so it is left alone then; Claude Code on it was failing
  anyway, since the vendor's OpenAI root does not serve the Anthropic wire;
- otherwise, a Claude Code agent runs on it → the Anthropic address is its base
  URL, which is where its requests already went (a gateway that serves both
  wires at one root); the key's destination is unchanged, so nothing waits for
  approval.

An Anthropic-protocol connection Codex runs on is not changed: its wire can't
be edited under a running agent. The agent keeps running on it (the reach is
the scope, and the proxy sends Codex's wire to its base URL); only a new switch
onto it is refused.

Idempotent: a connection that has an Anthropic address is left alone, so a
later edit (clearing it) sticks. Best-effort: a failure is logged, never fatal.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from coffer.application.provider.targets import agent_wire
from coffer.domain.agent.config import AgentConfig
from coffer.domain.provider.config import Protocol, ProviderConfig

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService

_log = logging.getLogger(__name__)

#: Vendors that serve the Anthropic wire at their own root, by OpenAI base URL
#: (the Add dialog's presets name the same pairs).
KNOWN_ANTHROPIC_ROOTS = {"https://api.deepseek.com": "https://api.deepseek.com/anthropic"}


def _norm(url: str) -> str:
    return url.strip().rstrip("/").lower()


def anthropic_address_for(
    cfg: ProviderConfig, *, claude_code_on_it: bool, codex_on_it: bool
) -> str | None:
    """The Anthropic address to give ``cfg``, or ``None`` to leave it alone."""
    if cfg.protocol is not Protocol.OPENAI or cfg.is_local or cfg.anthropic_base_url:
        return None
    known = KNOWN_ANTHROPIC_ROOTS.get(_norm(cfg.base_url))
    if known:
        return known if not codex_on_it else None
    return cfg.base_url if claude_code_on_it else None


async def fill_anthropic_addresses(service: ProviderService) -> list[str]:
    """Fill in what :func:`anthropic_address_for` says; the names changed."""
    # The wires the agents on each connection speak.
    on: dict[str, set[str | None]] = {}
    for row in await service._agents.list():
        try:
            agent = AgentConfig.model_validate(row.config)
        except ValueError:
            continue
        if agent.connection_uid:
            on.setdefault(agent.connection_uid, set()).add(agent_wire(agent.type))
    changed: list[str] = []
    for row in await service.list():
        try:
            cfg = ProviderConfig.model_validate(row.config)
            agents = on.get(row.uid, set())
            address = anthropic_address_for(
                cfg,
                claude_code_on_it=Protocol.ANTHROPIC.value in agents,
                codex_on_it=Protocol.OPENAI.value in agents,
            )
            if address is None:
                continue
            await service.update(row.uid, anthropic_base_url=address, actor="coffer")
            changed.append(row.name)
        except Exception:
            _log.warning("provider.anthropic_address_fill_failed", exc_info=True)
    if changed:
        _log.info("provider.anthropic_address_filled", extra={"connections": changed})
    return changed


__all__ = ["KNOWN_ANTHROPIC_ROOTS", "anthropic_address_for", "fill_anthropic_addresses"]
