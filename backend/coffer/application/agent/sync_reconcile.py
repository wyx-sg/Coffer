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
from typing import Any, Protocol

from coffer.application.agent.service import AgentService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import spec_for
from coffer.domain.agent.descriptor import native_memory_disable_target
from coffer.domain.agent.native_memory_disable import apply_disable, apply_restore, is_disabled
from coffer.domain.errors import ConfigValidationError
from coffer.domain.scope import machine_in_scope


class _ConfigFileStore(Protocol):
    def read_text(self, path: pathlib.Path) -> str | None: ...
    def write_text_atomic(self, path: pathlib.Path, text: str) -> None: ...


class AgentImportGate:
    """Implements ``application.sync.ports.ImportGate`` structurally."""

    kind = "agent"

    def __init__(self, machine_id: Callable[[], Awaitable[str | None]] | None = None) -> None:
        # ADR-045 machine axis (spec 004 amendment, Task 12): this daemon's
        # local machine id, so an agent doc scoped to a DIFFERENT machine can
        # be recognized as such. None (unwired) means "no filtering" — the
        # legacy single-machine contract, mirroring ChannelRuntime / SkillService.
        self._machine_id_provider = machine_id
        self._machine_id_cache: str | None = None

    async def _local_machine_id(self) -> str | None:
        if self._machine_id_provider is None:
            return None
        if self._machine_id_cache is None:
            self._machine_id_cache = await self._machine_id_provider()
        return self._machine_id_cache

    async def validate(
        self, config: Mapping[str, object], *, scope: dict[str, Any] | None = None
    ) -> None:
        local = await self._local_machine_id()
        if local is not None and not machine_in_scope(scope, local):
            # Spec 004 amendment: an agent scoped to another machine causes NO
            # quarantine noise here — the row upserts dormant. Config parsing
            # and the dir/skill checks below are machine-local preconditions
            # that are meaningless for an agent never installed on THIS machine.
            return
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
        machine_id: Callable[[], Awaitable[str | None]] | None = None,
    ) -> None:
        self._agents = agents
        self._store = config_file_store
        self._on_skill_policy_changed = on_skill_policy_changed
        # ADR-045 machine axis (spec 004 amendment, Task 12): see AgentImportGate.
        self._machine_id_provider = machine_id
        self._machine_id_cache: str | None = None

    async def _local_machine_id(self) -> str | None:
        if self._machine_id_provider is None:
            return None
        if self._machine_id_cache is None:
            self._machine_id_cache = await self._machine_id_provider()
        return self._machine_id_cache

    async def reconcile(self) -> list[str]:
        errors: list[str] = []
        local = await self._local_machine_id()
        for row in await self._agents.list():
            if local is not None and not machine_in_scope(row.scope, local):
                # Out-of-scope agent: silent skip (not an error, not
                # reported) — no native-memory write, no skill-delivery call.
                # apply_follow_for_agent already no-ops for it (Task 11); this
                # skip additionally avoids the native-memory disk write it
                # doesn't cover.
                continue
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
            try:
                await asyncio.to_thread(self._apply_native_memory, cfg)
            except Exception as e:
                errors.append(f"{row.name} (native memory): {e}")
            if self._on_skill_policy_changed is not None:
                try:
                    # Re-run delivery reconciliation for the row's follow
                    # policy; per-skill failures come back as strings.
                    for failure in await self._on_skill_policy_changed(row.name):
                        errors.append(f"{row.name} (skill delivery): {failure}")
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
        text = self._store.read_text(spec.path)
        # Converge on SEMANTICS, not bytes: an already-correct file is never
        # rewritten (no reformat of user formatting, no `{}` file creation,
        # no churn on every import). is_disabled("") is False, so a missing
        # file with the flag off is already converged.
        if is_disabled(text or "", fmt=fmt, agent_type=cfg.type) == cfg.disable_native_memory:
            return
        if cfg.disable_native_memory:
            new_text = apply_disable(text or "", fmt=fmt, agent_type=cfg.type)
        else:
            new_text = apply_restore(text or "", fmt=fmt, agent_type=cfg.type)
        self._store.write_text_atomic(spec.path, new_text)
