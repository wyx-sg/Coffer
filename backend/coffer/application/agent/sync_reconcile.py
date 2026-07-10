"""Agent import gate + side-effect reconciliation for sync (spec 010 import
reconciliation).

Gate: an agent doc only imports on a machine where its config dir exists and
its skill dir is usable — the same checks ``AgentService.register`` runs on
the front door. A machine without the agent installed quarantines the doc
(retried every run; self-heals once the agent is installed), instead of
creating a registry row pointing at a dead directory.

Hook: two agent-config fields drive on-disk side-effects that the registry
upsert alone does not perform — ``disable_native_memory`` (the native-config
transform of spec 004 slice 6) and ``follow_all_skills`` (skill delivery,
FR-025). After every import both are re-applied idempotently from the
converged rows.
"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol

from coffer.application.agent.service import AgentService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import spec_for
from coffer.domain.agent.descriptor import native_memory_disable_target
from coffer.domain.agent.native_memory_disable import apply_disable, apply_restore
from coffer.domain.errors import ConfigValidationError


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
        on_skill_policy_changed: Callable[[str], Awaitable[None]] | None = None,
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
            try:
                await asyncio.to_thread(self._apply_native_memory, cfg)
            except Exception as e:
                errors.append(f"{row.name} (native memory): {e}")
            if self._on_skill_policy_changed is not None:
                try:
                    # Re-run delivery reconciliation for the row's follow
                    # policy (per-skill failures are tolerated inside).
                    await self._on_skill_policy_changed(row.name)
                except Exception as e:
                    errors.append(f"{row.name} (skill delivery): {e}")
        return errors

    def _apply_native_memory(self, cfg: AgentConfig) -> None:
        """The on-disk half of ``AgentService.set_disable_native_memory``,
        applied from the row's CURRENT value (no flag flip, no audit — the
        originating machine already audited the user's action)."""
        target = native_memory_disable_target(cfg.type)
        if target is None:
            return  # the type has no native memory to disable — nothing to converge
        config_key, fmt = target
        spec = spec_for(cfg.type, config_key, cfg.resolved_config_dir())
        text = self._store.read_text(spec.path) or ""
        if cfg.disable_native_memory:
            new_text = apply_disable(text, fmt=fmt, agent_type=cfg.type)
        else:
            new_text = apply_restore(text, fmt=fmt, agent_type=cfg.type)
        if new_text != text:
            self._store.write_text_atomic(spec.path, new_text)
