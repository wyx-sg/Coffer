"""Agent import gate + side-effect reconciliation for sync (spec vault-export-import import
reconciliation).

Gate: an agent doc only imports where its config dir exists and its skill
dir is usable — the same checks ``AgentService.register`` runs on the front
door. An installation without the agent quarantines the doc (retried every
run; self-heals once the agent is installed), instead of creating a registry
row pointing at a dead directory.

Hook: one agent-config field drives an on-disk side-effect that the registry
upsert alone does not perform — ``follow_all_skills`` (skill delivery, FR-025).
After every import it is re-applied idempotently from the converged rows.
"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol

from coffer.application.agent.service import AgentService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.errors import ConfigValidationError


class _ConfigFileStore(Protocol):
    def read_text(self, path: pathlib.Path) -> str | None: ...
    def write_text_atomic(self, path: pathlib.Path, text: str) -> None: ...


class AgentImportGate:
    """Implements ``application.sync.ports.ImportGate`` structurally."""

    kind = "agent"

    async def validate(
        self, config: Mapping[str, object], *, scope: list[str] | None = None
    ) -> None:
        # ``scope`` is accepted for interface compatibility only: the `agent`
        # kind declares no activation scope (ADR per-agent-resource-scope), so there is nothing to
        # gate on here.
        del scope
        try:
            cfg = AgentConfig.model_validate(dict(config))
        except Exception as e:
            raise ConfigValidationError(str(e)) from e
        # Same machine-local precondition as AgentService.register: the config
        # dir must already exist here (the agent is installed) and the skill
        # subdir must be usable. Raises SkillDirNotWritable → quarantine.
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
        on_skill_policy_changed: Callable[[str], Awaitable[list[str]]] | None = None,
    ) -> None:
        self._agents = agents
        self._store = config_file_store
        self._on_skill_policy_changed = on_skill_policy_changed

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
            if self._on_skill_policy_changed is not None:
                try:
                    # Re-run delivery reconciliation for the row's follow
                    # policy; per-skill failures come back as strings.
                    for failure in await self._on_skill_policy_changed(row.name):
                        errors.append(f"{row.name} (skill delivery): {failure}")
                except Exception as e:
                    errors.append(f"{row.name} (skill delivery): {e}")
        return errors
