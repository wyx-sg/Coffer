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
from coffer.application.binary_deploy import user_bin_dir
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import ConfigFileSpec, spec_for
from coffer.domain.agent.descriptor import descriptor_for
from coffer.domain.agent.mcp_injection import McpInjectionSpec
from coffer.domain.agent.mcp_install import (
    apply_install,
    apply_uninstall,
    installed_command,
    is_installed,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ShimNotFound
from coffer.domain.resource import Resource
from coffer.domain.workspace_errors import McpInstallUnsupported

_SHIM_BINARY = "coffer-mcp-shim"


def _stable_path(candidate: pathlib.Path) -> str:
    """``candidate``, named the way it stays true across upgrades.

    A frozen build lands in ``~/.coffer/bin/<version>/`` with the public names
    symlinked into it, and a deploy prunes all but the last few version
    directories (see ``binary_deploy``). Every branch below reaches the shim by
    a path that resolves into the current version directory -- ``which`` finds
    the public symlink, and a CLI started through that symlink has the version
    directory as ``sys.executable``'s parent. Writing the resolved path into an
    agent's config file pins it to a directory that a later upgrade deletes, so
    whenever the candidate is the deployed shim its public name is returned
    instead. Anything else -- a venv console script, an override pointing
    somewhere of its own -- is resolved as before.
    """
    public = user_bin_dir() / _SHIM_BINARY
    try:
        if public.exists() and public.resolve() == candidate.resolve():
            return str(public)
    except OSError:
        pass
    return str(candidate.resolve())


def default_shim_resolver() -> str:
    """Resolve an absolute path to the ``coffer-mcp-shim`` binary.

    A desktop- or venv-launched daemon does not inherit the shell ``PATH``, so
    we try, in order: an explicit ``COFFER_MCP_SHIM_PATH`` override, a ``PATH``
    lookup, the running interpreter's own scripts directory (where pip / uv
    place console scripts — found via ``sysconfig`` even when the venv's bin is
    off ``PATH`` and ``sys.executable`` is a symlink to the base interpreter),
    then the bundled binary next to the running executable (PyInstaller dist).
    Whichever branch answers, the deployed shim is named by its public
    ``~/.coffer/bin/coffer-mcp-shim`` rather than the version directory behind
    it (see :func:`_stable_path`). Raises ``ShimNotFound`` if none resolve.
    """
    override = os.environ.get("COFFER_MCP_SHIM_PATH")
    if override and pathlib.Path(override).exists():
        return _stable_path(pathlib.Path(override))
    found = shutil.which(_SHIM_BINARY)
    if found:
        return _stable_path(pathlib.Path(found))
    scripts_dir = sysconfig.get_path("scripts")
    if scripts_dir:
        installed = pathlib.Path(scripts_dir) / _SHIM_BINARY
        if installed.exists():
            return _stable_path(installed)
    bundled = pathlib.Path(sys.executable).resolve().parent / _SHIM_BINARY
    if bundled.exists():
        return _stable_path(bundled)
    raise ShimNotFound(_SHIM_BINARY)


@dataclass(frozen=True)
class McpInstallStatus:
    installed: bool
    command: str | None


class _AgentLookup(Protocol):
    async def get(self, uid: str) -> Resource: ...


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

    async def _mcp_spec(self, uid: str) -> tuple[Resource, ConfigFileSpec, McpInjectionSpec]:
        """The agent row, its MCP config file and how that file is shaped.

        The row travels with the other two because the write paths need it
        twice over: the audit entry is keyed on the resource, and the entry
        Coffer writes carries the agent's uid so the shim can report which
        agent it is speaking for.

        Raises ResourceNotFound (→ 404) when the agent doesn't exist.
        """
        resource = await self._agents.get(uid)
        cfg = AgentConfig.model_validate(resource.config)
        injection = descriptor_for(cfg.type).mcp
        if injection is None:
            raise McpInstallUnsupported(cfg.type.value)
        spec = spec_for(cfg.type, injection.config_key, cfg.resolved_config_dir())
        return resource, spec, injection

    async def status(self, uid: str) -> McpInstallStatus:
        _agent, spec, inj = await self._mcp_spec(uid)
        text = self._store.read_text(spec.path) or ""
        return McpInstallStatus(
            installed=is_installed(spec.format, text, container_key=inj.container_key),
            command=installed_command(spec.format, text, container_key=inj.container_key),
        )

    async def install(self, uid: str, *, actor: str = "api") -> McpInstallStatus:
        agent, spec, inj = await self._mcp_spec(uid)
        shim = self._resolve_shim()  # raises ShimNotFound (→ 422) before any write
        text = self._store.read_text(spec.path) or ""
        new_text = apply_install(
            spec.format,
            text,
            shim,
            container_key=inj.container_key,
            entry_style=inj.entry_style,
            agent_uid=agent.uid,
        )
        self._store.write_text_atomic(spec.path, new_text)
        await self._audit.record(
            AuditEventType.AGENT_MCP_INSTALLED.value,
            resource=agent,
            actor=actor,
            details={"command": shim, "path": str(spec.path)},
        )
        return McpInstallStatus(installed=True, command=shim)

    async def uninstall(self, uid: str, *, actor: str = "api") -> McpInstallStatus:
        agent, spec, inj = await self._mcp_spec(uid)
        text = self._store.read_text(spec.path)
        # No-op success when not installed — don't write or audit.
        if text is None or not is_installed(spec.format, text, container_key=inj.container_key):
            return McpInstallStatus(installed=False, command=None)
        new_text = apply_uninstall(spec.format, text, container_key=inj.container_key)
        self._store.write_text_atomic(spec.path, new_text)
        await self._audit.record(
            AuditEventType.AGENT_MCP_UNINSTALLED.value,
            resource=agent,
            actor=actor,
            details={"path": str(spec.path)},
        )
        return McpInstallStatus(installed=False, command=None)
