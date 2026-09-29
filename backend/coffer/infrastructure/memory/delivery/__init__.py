"""Per-agent adapters for Coffer's own session-start-like hook.

See spec memory "Install delivery hooks explicitly and removably". Which
config-file key holds it, which event it sits on, and how to build/find/remove
the installed entry.

Each adapter declares the agent it serves; the composition root binds them to
the agents' projection facets (ADR agent-mechanisms-are-optional-facets-on-the-
descriptor), and `application.memory.delivery.DeliveryService` asks the facet,
through the `domain.memory.delivery.DeliveryAdapter` Protocol — it never opens
a settings file itself, and never names an agent.
"""

from __future__ import annotations

import dataclasses

from coffer.domain.memory.delivery import DeliveryAdapter
from coffer.infrastructure.memory.delivery.claude_code import ADAPTER as CLAUDE_CODE_ADAPTER
from coffer.infrastructure.memory.delivery.codex import ADAPTER as CODEX_ADAPTER

#: The adapters with the bare `coffer` name, for a caller that has no CLI path.
DELIVERY_ADAPTERS = (CLAUDE_CODE_ADAPTER, CODEX_ADAPTER)


def delivery_adapters(cli: str) -> tuple[DeliveryAdapter, ...]:
    """Every adapter, each installing a hook that runs the `coffer` CLI at
    `cli` — the absolute path the composition root resolved."""
    return tuple(dataclasses.replace(a, cli=cli) for a in DELIVERY_ADAPTERS)


__all__ = ["CLAUDE_CODE_ADAPTER", "CODEX_ADAPTER", "DELIVERY_ADAPTERS", "delivery_adapters"]
