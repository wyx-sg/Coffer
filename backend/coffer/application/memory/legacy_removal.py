"""Remove the retired memory layer's hook from every agent (spec memory
"Remove the memory delivery hook on upgrade").

Earlier builds installed a ``coffer-memory`` hook into Claude Code's
``settings.json`` and Codex's ``hooks.json``. Every start of the daemon looks
for it in each registered agent's file and removes Coffer's entries only,
leaving every other hook and key as it was; a file with none is not touched,
so the step is idempotent and costs a read per agent once it has run. Each
agent it changed is one ``memory_hook_removed`` event.
"""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Sequence
from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import spec_for
from coffer.domain.agent.descriptor import descriptor_for
from coffer.domain.audit import AuditEventType
from coffer.domain.memory.legacy_hook import MalformedHooksFile, remove_entries
from coffer.domain.resource import Resource

logger = logging.getLogger(__name__)

#: Who removes it: nobody asked, the upgrade did.
UPGRADE_ACTOR = "system:upgrade"


class HooksFileStore(Protocol):
    """The two operations this step needs on an agent's config file; the
    agent kind's ``ConfigFileStore`` satisfies it (and backs a file up before
    rewriting it)."""

    def read_text(self, path: pathlib.Path) -> str | None: ...

    def write_text_atomic(self, path: pathlib.Path, text: str) -> None: ...


async def remove_memory_hooks(
    agents: Sequence[Resource], store: HooksFileStore, audit: AuditService
) -> int:
    """Remove Coffer's memory hook entries from each agent's hooks file;
    return how many agents were changed. A file that does not parse is left
    alone and logged."""
    changed = 0
    for agent in agents:
        cfg = AgentConfig.model_validate(agent.config)
        # The hook sat in the agent's first hook-carrying file: Claude Code's
        # ``settings.json``, Codex's ``hooks.json``.
        keys = descriptor_for(cfg.type).hook_source_keys
        if not keys:
            continue
        key = keys[0]
        path = spec_for(cfg.type, key, cfg.resolved_config_dir()).path
        text = store.read_text(path)
        if text is None:
            continue
        try:
            new = remove_entries(text)
        except MalformedHooksFile:
            logger.warning("memory.legacy_hook.unreadable %s", path)
            continue
        if new is None:
            continue
        store.write_text_atomic(path, new)
        await audit.record(
            AuditEventType.MEMORY_HOOK_REMOVED.value,
            resource=agent,
            actor=UPGRADE_ACTOR,
            details={"path": str(path)},
        )
        changed += 1
    return changed


__all__ = ["UPGRADE_ACTOR", "HooksFileStore", "remove_memory_hooks"]
