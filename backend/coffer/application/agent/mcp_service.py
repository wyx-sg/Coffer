"""AgentMcpService — install / uninstall / status for Coffer's own MCP server.

Reuses the config-file store (atomic write + ``.bak``) and the pure text
transforms in ``domain/agent/mcp_install.py``. The agent's MCP config file is
itself an allowlisted config file:

- ``claude_code`` → the ``global`` key (``~/.claude.json``, JSON)
- ``codex``       → the ``config`` key (``~/.codex/config.toml``, TOML)
"""

from __future__ import annotations

import os
import pathlib
import shutil
import sys
import sysconfig
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from coffer.application.agent.config_file_service import ConfigFileStorePort
from coffer.application.audit_service import AuditService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import ConfigFileSpec, spec_for
from coffer.domain.agent.mcp_install import (
    apply_install,
    apply_uninstall,
    installed_command,
    is_installed,
)
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ShimNotFound
from coffer.domain.resource import Resource, ResourceRef

# Which allowlisted config-file key holds each type's MCP servers.
_MCP_CONFIG_KEY: dict[AgentType, str] = {
    AgentType.CLAUDE_CODE: "global",
    AgentType.CODEX: "config",
}

_SHIM_BINARY = "coffer-mcp-shim"


def default_shim_resolver() -> str:
    """Resolve an absolute path to the ``coffer-mcp-shim`` binary.

    A desktop- or venv-launched daemon does not inherit the shell ``PATH``, so
    we try, in order: an explicit ``COFFER_MCP_SHIM_PATH`` override, a ``PATH``
    lookup, the running interpreter's own scripts directory (where pip / uv
    place console scripts — found via ``sysconfig`` even when the venv's bin is
    off ``PATH`` and ``sys.executable`` is a symlink to the base interpreter),
    then the bundled binary next to the running executable (PyInstaller dist).
    Raises ``ShimNotFound`` if none resolve.
    """
    override = os.environ.get("COFFER_MCP_SHIM_PATH")
    if override and pathlib.Path(override).exists():
        return str(pathlib.Path(override).resolve())
    found = shutil.which(_SHIM_BINARY)
    if found:
        return str(pathlib.Path(found).resolve())
    scripts_dir = sysconfig.get_path("scripts")
    if scripts_dir:
        installed = pathlib.Path(scripts_dir) / _SHIM_BINARY
        if installed.exists():
            return str(installed.resolve())
    bundled = pathlib.Path(sys.executable).resolve().parent / _SHIM_BINARY
    if bundled.exists():
        return str(bundled)
    raise ShimNotFound(_SHIM_BINARY)


@dataclass(frozen=True)
class McpInstallStatus:
    installed: bool
    command: str | None


class _AgentLookup(Protocol):
    async def get(self, name: str) -> Resource: ...


class AgentMcpService:
    def __init__(
        self,
        *,
        agent_service: _AgentLookup,
        audit: AuditService,
        store: ConfigFileStorePort,
        shim_resolver: Callable[[], str] = default_shim_resolver,
    ) -> None:
        self._agents = agent_service
        self._audit = audit
        self._store = store
        self._resolve_shim = shim_resolver

    async def _mcp_spec(self, name: str) -> ConfigFileSpec:
        # Raises ResourceNotFound (→ 404) when the agent doesn't exist.
        resource = await self._agents.get(name)
        cfg = AgentConfig.model_validate(resource.config)
        return spec_for(cfg.type, _MCP_CONFIG_KEY[cfg.type], cfg.resolved_config_dir())

    async def status(self, name: str) -> McpInstallStatus:
        spec = await self._mcp_spec(name)
        text = self._store.read_text(spec.path) or ""
        return McpInstallStatus(
            installed=is_installed(spec.format, text),
            command=installed_command(spec.format, text),
        )

    async def install(self, name: str, *, actor: str = "api") -> McpInstallStatus:
        spec = await self._mcp_spec(name)
        shim = self._resolve_shim()  # raises ShimNotFound (→ 422) before any write
        text = self._store.read_text(spec.path) or ""
        new_text = apply_install(spec.format, text, shim)
        self._store.write_text_atomic(spec.path, new_text)
        await self._audit.record(
            AuditEventType.AGENT_MCP_INSTALLED.value,
            ref=ResourceRef("agent", name),
            actor=actor,
            details={"command": shim, "path": str(spec.path)},
        )
        return McpInstallStatus(installed=True, command=shim)

    async def uninstall(self, name: str, *, actor: str = "api") -> McpInstallStatus:
        spec = await self._mcp_spec(name)
        text = self._store.read_text(spec.path)
        # No-op success when not installed — don't write or audit.
        if text is None or not is_installed(spec.format, text):
            return McpInstallStatus(installed=False, command=None)
        new_text = apply_uninstall(spec.format, text)
        self._store.write_text_atomic(spec.path, new_text)
        await self._audit.record(
            AuditEventType.AGENT_MCP_UNINSTALLED.value,
            ref=ResourceRef("agent", name),
            actor=actor,
            details={"path": str(spec.path)},
        )
        return McpInstallStatus(installed=False, command=None)
