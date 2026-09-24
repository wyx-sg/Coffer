"""Boot migration: move a custom-dir Claude Code agent's MCP entry home → own file.

Until Coffer honoured a custom config directory for ``.claude.json``, it
installed EVERY Claude Code agent's ``coffer`` entry into ``$HOME/.claude.json``
— carrying that agent's uid as ``--agent-uid <uid>``. Claude Code started with
``CLAUDE_CONFIG_DIR=<dir>`` never reads the home file (it keeps
``<dir>/.claude.json``), so after the upgrade the custom agent shows "not
installed", and the home entry left behind makes the DEFAULT agent show
"installed" while the shim reports someone else's uid.

This runs once per daemon start and is idempotent: for each registered
``claude_code`` agent whose config directory is not the default, a home entry
whose ``--agent-uid`` is THAT agent's uid is installed into the agent's own
``.claude.json`` (unless that file already has a ``coffer`` entry) and then
removed from the home file — the same atomic write + ``.bak`` rotation and the
same audit events as install/uninstall (spec agent-registry/claude-code
"Install Coffer's MCP entry into Claude Code's .claude.json"). Entries for any other uid,
entries with no uid, and every non-Coffer entry are never touched. A file that does not
parse is left alone and logged; so is its counterpart, so nothing half-moves.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Protocol

from coffer.application.agent.config_file_service import ConfigFileStorePort
from coffer.application.audit_service import AuditService
from coffer.domain.agent.allowlists import claude_global_config
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import ConfigFileFormat, spec_for
from coffer.domain.agent.descriptor import descriptor_for
from coffer.domain.agent.mcp_install import (
    apply_install,
    apply_uninstall,
    installed_agent_uid,
    installed_command,
    is_installed,
)
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ConfigFileFormatInvalid
from coffer.domain.resource import Resource

logger = logging.getLogger(__name__)

#: Same automatic actor the other boot heals record (see skill boot_reconcile).
BOOT_ACTOR = "system"


class _AgentLister(Protocol):
    async def list(self) -> list[Resource]: ...


class ClaudeHomeMcpEntryMigration:
    """Moves stale home ``.claude.json`` entries to custom-dir agents' own file."""

    def __init__(
        self, *, agent_service: _AgentLister, audit: AuditService, store: ConfigFileStorePort
    ) -> None:
        self._agents = agent_service
        self._audit = audit
        self._store = store

    async def heal(self) -> list[str]:
        """Move what belongs elsewhere; one note per moved entry."""
        descriptor = descriptor_for(AgentType.CLAUDE_CODE)
        injection = descriptor.mcp
        if injection is None:  # pragma: no cover - Claude Code always has one
            return []
        fmt, ck = injection.format, injection.container_key
        home_path = claude_global_config(descriptor.default_config_dir())
        home_text = self._read(home_path, fmt, ck)
        if not home_text:
            return []  # absent, empty or unparseable (logged): nothing to move
        home_uid = installed_agent_uid(fmt, home_text, container_key=ck)
        if home_uid is None:
            return []
        notes: list[str] = []
        for agent in await self._agents.list():
            if agent.uid != home_uid:
                continue
            cfg = AgentConfig.model_validate(agent.config)
            if cfg.type is not AgentType.CLAUDE_CODE:
                continue
            target = spec_for(cfg.type, injection.config_key, cfg.resolved_config_dir()).path
            if target == home_path:
                continue  # the default dir: the home file IS its own file
            target_text = self._read(target, fmt, ck)
            if target_text is None:
                logger.warning(
                    "claude_mcp_home_migration: %s holds agent %s's entry; not moved "
                    "because %s does not parse",
                    home_path,
                    agent.uid,
                    target,
                )
                continue
            await self._move(agent, (home_path, home_text), (target, target_text), fmt, ck)
            notes.append(f"moved agent {agent.uid}'s coffer MCP entry from {home_path} to {target}")
        return notes

    def _read(self, path: pathlib.Path, fmt: ConfigFileFormat, ck: str | None) -> str | None:
        """The file's text if it parses (``""`` when absent), else ``None``
        after logging which file was left alone."""
        text = self._store.read_text(path)
        if text is None:
            return ""
        try:
            is_installed(fmt, text, container_key=ck)
        except ConfigFileFormatInvalid:
            logger.warning("claude_mcp_home_migration: %s does not parse; left alone", path)
            return None
        return text

    async def _move(
        self,
        agent: Resource,
        home: tuple[pathlib.Path, str],
        target: tuple[pathlib.Path, str],
        fmt: ConfigFileFormat,
        ck: str | None,
    ) -> None:
        """Install into ``target`` (unless it already has an entry), then
        remove from ``home`` — install first, so a failure between the two
        leaves the entry in both places rather than in neither."""
        (home_path, home_text), (target_path, target_text) = home, target
        if not is_installed(fmt, target_text, container_key=ck):
            shim = installed_command(fmt, home_text, container_key=ck) or ""
            new_text = apply_install(fmt, target_text, shim, container_key=ck, agent_uid=agent.uid)
            self._store.write_text_atomic(target_path, new_text)
            await self._audit.record(
                AuditEventType.AGENT_MCP_INSTALLED.value,
                resource=agent,
                actor=BOOT_ACTOR,
                details={
                    "command": shim,
                    "path": str(target_path),
                    "migrated_from": str(home_path),
                },
            )
        self._store.write_text_atomic(home_path, apply_uninstall(fmt, home_text, container_key=ck))
        await self._audit.record(
            AuditEventType.AGENT_MCP_UNINSTALLED.value,
            resource=agent,
            actor=BOOT_ACTOR,
            details={"path": str(home_path), "migrated_to": str(target_path)},
        )


__all__ = ["BOOT_ACTOR", "ClaudeHomeMcpEntryMigration"]
