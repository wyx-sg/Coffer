"""Per-agent adapters for Coffer's own session-start-like hook (spec memory
FR-054/FR-055): which config-file key holds it, which event it sits on, and
how to build/find/remove the installed entry.

`application.memory.delivery.DeliveryService` composes against these two
singletons by `AgentType`, through the `domain.memory.delivery.DeliveryAdapter`
Protocol — it never opens a settings file itself, and never imports
`claude_code`/`codex` by name past this module.
"""

from __future__ import annotations

from coffer.infrastructure.memory.delivery.claude_code import ADAPTER as CLAUDE_CODE_ADAPTER
from coffer.infrastructure.memory.delivery.codex import ADAPTER as CODEX_ADAPTER

__all__ = ["CLAUDE_CODE_ADAPTER", "CODEX_ADAPTER"]
