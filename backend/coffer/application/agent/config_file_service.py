"""AgentConfigFileService — list / read / write an agent's curated config files.

Exposes list + read + write over the per-type config-file allowlist. Writes are
atomic (temp file + rename) and keep a `.bak` copy of the prior content, so a bad
edit is always recoverable. (The same atomic-write/backup machinery on the
`ConfigFileStorePort` is also reused by the Coffer-MCP install/uninstall flow in
`mcp_service.py`.)

Resolves an agent to its `AgentType`, then operates on that type's config-file
allowlist (`domain/agent/config_files.py`). Filesystem access goes through a
`ConfigFileStorePort` (Protocol) whose concrete implementation lives in
`infrastructure/agent/config_file_store.py` (Contract 2b: application defines
the port, infrastructure implements it).

The allowlist is the security boundary: every read/write resolves a
`ConfigFileSpec` via `spec_for`, which raises `ConfigFileNotAllowed` for an
unknown key *before* any filesystem call — so a caller can never address an
arbitrary path. Writes additionally run `validate_content` so malformed
JSON/TOML is rejected (`ConfigFileFormatInvalid` → 422) before the file is
touched, leaving the on-disk file unchanged.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import (
    ConfigFileFormat,
    ConfigFileSpec,
    FileStat,
    config_files_for,
    spec_for,
    validate_content,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Resource, ResourceRef


class ConfigFileStorePort(Protocol):
    """Filesystem operations for config files. Implemented in infrastructure."""

    def read_text(self, path: pathlib.Path) -> str | None:
        """Return file text, or ``None`` if the file does not exist."""
        ...

    def stat(self, path: pathlib.Path) -> FileStat | None:
        """Return size + mtime, or ``None`` if the file does not exist."""
        ...

    def write_text_atomic(self, path: pathlib.Path, text: str) -> None:
        """Atomically write ``text`` to ``path`` (temp file + rename).

        Backs up any existing file to ``<path>.bak`` first and creates parent
        directories as needed.
        """
        ...


@dataclass(frozen=True)
class ConfigFileInfo:
    """List/metadata view of one config file."""

    key: str
    display_name: str
    path: str
    format: ConfigFileFormat
    exists: bool
    size: int | None
    modified_at: datetime | None


@dataclass(frozen=True)
class ConfigFileContent:
    """Content view of one config file."""

    key: str
    format: ConfigFileFormat
    exists: bool
    content: str


# Structural type for the agent-lookup dependency — avoids a hard import of
# AgentService (and keeps this service unit-testable with a fake).
class _AgentLookup(Protocol):
    async def get(self, name: str) -> Resource: ...


class AgentConfigFileService:
    def __init__(
        self,
        *,
        agent_service: _AgentLookup,
        audit: AuditService,
        store: ConfigFileStorePort,
    ) -> None:
        self._agents = agent_service
        self._audit = audit
        self._store = store

    async def _config_for(self, name: str) -> AgentConfig:
        # Raises ResourceNotFound (→ 404) when the agent doesn't exist.
        resource = await self._agents.get(name)
        return AgentConfig.model_validate(resource.config)

    def _info(self, spec: ConfigFileSpec) -> ConfigFileInfo:
        st = self._store.stat(spec.path)
        return ConfigFileInfo(
            key=spec.key,
            display_name=spec.display_name,
            path=str(spec.path),
            format=spec.format,
            exists=st is not None,
            size=st.size if st else None,
            modified_at=st.modified_at if st else None,
        )

    async def list_files(self, name: str) -> list[ConfigFileInfo]:
        cfg = await self._config_for(name)
        return [self._info(spec) for spec in config_files_for(cfg.type, cfg.resolved_config_dir())]

    async def read_file(self, name: str, key: str) -> ConfigFileContent:
        cfg = await self._config_for(name)
        spec = spec_for(cfg.type, key, cfg.resolved_config_dir())  # ConfigFileNotAllowed → 404
        text = self._store.read_text(spec.path)
        return ConfigFileContent(
            key=spec.key,
            format=spec.format,
            exists=text is not None,
            content=text or "",
        )

    async def write_file(
        self, name: str, key: str, content: str, *, actor: str = "api"
    ) -> ConfigFileInfo:
        """Atomically write `content` to the allowlisted config file `key`.

        Resolves the spec via `spec_for` (unknown key → `ConfigFileNotAllowed`
        → 404, before any filesystem access), validates `content` against the
        file's format (malformed JSON/TOML → `ConfigFileFormatInvalid` → 422,
        before any write so the on-disk file is left unchanged), writes atomically
        keeping a `.bak` of the prior content, records an audit entry, and returns
        the refreshed metadata view.
        """
        cfg = await self._config_for(name)
        spec = spec_for(cfg.type, key, cfg.resolved_config_dir())  # ConfigFileNotAllowed → 404
        validate_content(spec.format, content)  # raises ConfigFileFormatInvalid → 422
        self._store.write_text_atomic(spec.path, content)  # atomic + <path>.bak
        await self._audit.record(
            AuditEventType.AGENT_CONFIG_FILE_WRITTEN.value,
            ref=ResourceRef("agent", name),
            actor=actor,
            details={"key": spec.key},
        )
        return self._info(spec)
