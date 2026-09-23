"""Agent import gate + side-effect reconciliation for sync (spec vault-sync import
reconciliation).

Gate: an agent doc only imports where its config dir exists and its skill
dir is usable — the same checks ``AgentService.register`` runs on the front
door. An installation without the agent refuses the doc as not applicable here
(``AGENT_CONFIG_DIR_MISSING``: held, not retried), instead of creating a
registry row pointing at a dead directory; an unusable skill dir is retried.

Hook: importing resources changes which skills each agent should be holding. A
skill's reach — its ``enabled`` flag and its ``scope`` — is this machine's own
and never arrives with the document, but the set of skill ROWS does change, and
the registry upsert alone performs no on-disk delivery. After every import each
agent's delivered set is reconciled idempotently against the delivery predicate
(spec skill-manager FR-012) from the converged rows and this machine's reach.
"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol

from coffer.application.agent.service import AgentService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.errors import AgentConfigDirMissing, ConfigValidationError


class _ConfigFileStore(Protocol):
    def read_text(self, path: pathlib.Path) -> str | None: ...
    def write_text_atomic(self, path: pathlib.Path, text: str) -> None: ...


class AgentImportGate:
    """Implements ``application.sync.ports.ImportGate`` structurally."""

    kind = "agent"

    async def validate(self, config: Mapping[str, object]) -> None:
        try:
            cfg = AgentConfig.model_validate(dict(config))
        except Exception as e:
            raise ConfigValidationError(str(e)) from e
        # Same machine-local precondition as AgentService.register: the config
        # dir must already exist here (the agent is installed) and the skill
        # subdir must be usable. A missing config dir means the agent is not
        # installed on this machine — AgentConfigDirMissing, which the round
        # records as not applicable here instead of retrying it every round.
        # An unusable skill dir stays SkillDirNotWritable → retried.
        config_dir = cfg.resolved_config_dir()
        if not await asyncio.to_thread(config_dir.is_dir):
            raise AgentConfigDirMissing(str(config_dir))
        await asyncio.to_thread(
            AgentService._ensure_skill_dir,
            cfg.resolved_config_dir(),
            cfg.resolved_skill_dir(),
        )


class AgentSideEffectsReconcile:
    """Implements ``application.sync.ports.PostImportHook`` structurally."""

    kind = "agent"

    def __init__(
        self,
        agents: AgentService,
        config_file_store: _ConfigFileStore,
        reconcile_skill_delivery: Callable[[str], Awaitable[list[str]]] | None = None,
    ) -> None:
        self._agents = agents
        self._store = config_file_store
        self._reconcile_skill_delivery = reconcile_skill_delivery

    async def reconcile(self) -> list[str]:
        errors: list[str] = []
        for row in await self._agents.list():
            try:
                cfg = AgentConfig.model_validate(row.config)
            except Exception as e:
                errors.append(f"{row.name}: {e}")
                continue
            # A stale row whose config dir vanished must not be resurrected by
            # a reconcile write (mkdir -p) — report and leave it alone.
            if not cfg.resolved_config_dir().is_dir():
                errors.append(f"{row.name}: config dir missing on this machine; skipped")
                continue
            if self._reconcile_skill_delivery is not None:
                try:
                    # Re-run delivery reconciliation against the predicate;
                    # per-skill failures come back as strings. The hook is keyed
                    # on the agent's uid, which is what a skill's scope holds.
                    for failure in await self._reconcile_skill_delivery(row.uid):
                        errors.append(f"{row.name} (skill delivery): {failure}")
                except Exception as e:
                    errors.append(f"{row.name} (skill delivery): {e}")
        return errors
