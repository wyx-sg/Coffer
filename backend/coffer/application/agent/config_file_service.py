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
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import (
    ConfigFileFormat,
    ConfigFileKind,
    ConfigFileSpec,
    DirEntryInfo,
    FileStat,
    config_files_for,
    spec_for,
    validate_child_relpath,
    validate_content,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ConfigFileNotAllowed
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.workspace_errors import ConfigFileStale

# Prefix of a LEGACY memory-projection block marker. Native projection was
# removed (ADR-026) so Coffer no longer writes this block; the flag only lets
# the editor annotate a leftover block as safe-to-delete, never parses it.
MEMORY_BLOCK_MARKER = "<!-- coffer:memory"


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

    def list_dir(self, root: pathlib.Path) -> list[DirEntryInfo] | None:
        """Recursive listing of regular ``.md`` files under ``root``.

        Returns ``None`` when ``root`` is not a directory. Symlinked files are
        skipped. Sorted by relpath for deterministic output.
        """
        ...

    def delete_with_backup(self, path: pathlib.Path) -> bool:
        """Copy content to ``<path>.bak``, then remove the file.

        Returns ``False`` when the file is already absent.
        """
        ...

    def fingerprint(self, text: str | None) -> str:
        """sha256 hex-digest of the content; ``""`` for a missing file (text=None)."""
        ...

    def resolved_within(self, path: pathlib.Path, root: pathlib.Path) -> bool:
        """Whether ``path`` resolves (following symlinks) inside ``root``."""
        ...


@dataclass(frozen=True)
class ConfigFileInfo:
    """List/metadata view of one config file."""

    key: str
    display_name: str
    path: str
    folder_path: str
    format: ConfigFileFormat
    kind: str
    exists: bool
    size: int | None
    modified_at: datetime | None
    files: list[DirEntryInfo] | None = field(default=None)


@dataclass(frozen=True)
class ConfigFileContent:
    """Content view of one config file."""

    key: str
    path: str
    folder_path: str
    format: ConfigFileFormat
    exists: bool
    content: str
    fingerprint: str
    memory_block: bool


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

    def _child_path(self, spec: ConfigFileSpec, relpath: str) -> pathlib.Path:
        """Validated child path: pure relpath rules + resolved containment.

        `validate_child_relpath` covers traversal/extension by path math; the
        store's `resolved_within` then re-checks with symlinks resolved so a
        symlinked child pointing outside the entry's directory is rejected
        (spec 004 FR-035 "no symlink escape").
        """
        path = validate_child_relpath(spec.path, relpath)
        if not self._store.resolved_within(path, spec.path):
            raise ConfigFileNotAllowed("child", relpath)
        return path

    def _info(self, spec: ConfigFileSpec) -> ConfigFileInfo:
        if spec.kind is ConfigFileKind.DIRECTORY:
            listing = self._store.list_dir(spec.path)
            return ConfigFileInfo(
                key=spec.key,
                display_name=spec.display_name,
                path=str(spec.path),
                folder_path=str(spec.path.parent),
                format=spec.format,
                kind=spec.kind.value,
                exists=listing is not None,
                size=None,
                modified_at=None,
                files=listing,
            )
        st = self._store.stat(spec.path)
        return ConfigFileInfo(
            key=spec.key,
            display_name=spec.display_name,
            path=str(spec.path),
            folder_path=str(spec.path.parent),
            format=spec.format,
            kind=spec.kind.value,
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
        if spec.kind is ConfigFileKind.DIRECTORY:
            raise ConfigFileNotAllowed(cfg.type.value, key)
        text = self._store.read_text(spec.path)
        return ConfigFileContent(
            key=spec.key,
            path=str(spec.path),
            folder_path=str(spec.path.parent),
            format=spec.format,
            exists=text is not None,
            content=text or "",
            fingerprint=self._store.fingerprint(text),
            memory_block=MEMORY_BLOCK_MARKER in (text or ""),
        )

    async def write_file(
        self,
        name: str,
        key: str,
        content: str,
        *,
        expected_fingerprint: str | None = None,
        actor: str = "api",
    ) -> ConfigFileInfo:
        """Atomically write `content` to the allowlisted config file `key`.

        Resolves the spec via `spec_for` (unknown key → `ConfigFileNotAllowed`
        → 404, before any filesystem access). DIRECTORY specs → `ConfigFileNotAllowed`.
        When `expected_fingerprint` is supplied, reads the current content and
        checks for staleness before any write (`ConfigFileStale` → 409).
        Validates `content` against the file's format (malformed JSON/TOML →
        `ConfigFileFormatInvalid` → 422, before any write so the on-disk file is
        left unchanged), writes atomically keeping a `.bak` of the prior content,
        records an audit entry, and returns the refreshed metadata view.
        """
        cfg = await self._config_for(name)
        spec = spec_for(cfg.type, key, cfg.resolved_config_dir())  # ConfigFileNotAllowed → 404
        if spec.kind is ConfigFileKind.DIRECTORY:
            raise ConfigFileNotAllowed(cfg.type.value, key)
        if expected_fingerprint is not None:
            current = self._store.read_text(spec.path)
            if self._store.fingerprint(current) != expected_fingerprint:
                raise ConfigFileStale(key)
        validate_content(spec.format, content)  # raises ConfigFileFormatInvalid → 422
        self._store.write_text_atomic(spec.path, content)  # atomic + <path>.bak
        await self._audit.record(
            AuditEventType.AGENT_CONFIG_FILE_WRITTEN.value,
            ref=ResourceRef("agent", name),
            actor=actor,
            details={"key": spec.key},
        )
        return self._info(spec)

    async def read_child(self, name: str, key: str, relpath: str) -> ConfigFileContent:
        """Read a child file of a DIRECTORY-type config entry.

        Returns ``exists=False``, empty content, and ``fingerprint=""`` when the
        child is missing; never creates the file.
        """
        cfg = await self._config_for(name)
        spec = spec_for(cfg.type, key, cfg.resolved_config_dir())  # ConfigFileNotAllowed → 404
        if spec.kind is not ConfigFileKind.DIRECTORY:
            raise ConfigFileNotAllowed(cfg.type.value, key)
        path = self._child_path(spec, relpath)  # ConfigFileNotAllowed on traversal/escape
        text = self._store.read_text(path)
        return ConfigFileContent(
            key=key,
            path=str(path),
            folder_path=str(path.parent),
            format=spec.format,
            exists=text is not None,
            content=text or "",
            fingerprint=self._store.fingerprint(text),
            memory_block=MEMORY_BLOCK_MARKER in (text or ""),
        )

    async def write_child(
        self,
        name: str,
        key: str,
        relpath: str,
        content: str,
        *,
        expected_fingerprint: str | None = None,
        actor: str = "api",
    ) -> ConfigFileInfo:
        """Write a child file of a DIRECTORY-type config entry.

        Performs an optional stale check, validates content, writes atomically,
        records an audit entry, and returns the refreshed directory listing.
        """
        cfg = await self._config_for(name)
        spec = spec_for(cfg.type, key, cfg.resolved_config_dir())  # ConfigFileNotAllowed → 404
        if spec.kind is not ConfigFileKind.DIRECTORY:
            raise ConfigFileNotAllowed(cfg.type.value, key)
        path = self._child_path(spec, relpath)  # ConfigFileNotAllowed on traversal/escape
        if expected_fingerprint is not None:
            current = self._store.read_text(path)
            if self._store.fingerprint(current) != expected_fingerprint:
                raise ConfigFileStale(key)
        validate_content(spec.format, content)  # markdown → no-op, kept for symmetry
        self._store.write_text_atomic(path, content)
        await self._audit.record(
            AuditEventType.AGENT_CONFIG_FILE_WRITTEN.value,
            ref=ResourceRef("agent", name),
            actor=actor,
            details={"key": key, "child": relpath},
        )
        return self._info(spec)

    async def delete_child(self, name: str, key: str, relpath: str, *, actor: str = "api") -> None:
        """Delete a child file of a DIRECTORY-type config entry (with backup).

        Raises `ConfigFileNotAllowed` when the child is missing.
        """
        cfg = await self._config_for(name)
        spec = spec_for(cfg.type, key, cfg.resolved_config_dir())  # ConfigFileNotAllowed → 404
        if spec.kind is not ConfigFileKind.DIRECTORY:
            raise ConfigFileNotAllowed(cfg.type.value, key)
        path = self._child_path(spec, relpath)  # ConfigFileNotAllowed on traversal/escape
        deleted = self._store.delete_with_backup(path)
        if not deleted:
            raise ConfigFileNotAllowed("child", relpath)
        await self._audit.record(
            AuditEventType.AGENT_CONFIG_FILE_DELETED.value,
            ref=ResourceRef("agent", name),
            actor=actor,
            details={"key": key, "child": relpath},
        )
