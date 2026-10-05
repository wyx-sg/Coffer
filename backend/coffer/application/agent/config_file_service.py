"""AgentConfigFileService — list an agent's curated config files.

Lists the per-type config-file allowlist with each file's location, size and
modified time (spec agent-registry "List an agent's config files with their
locations"). Coffer serves no file's content and writes none on the person's
behalf; the person opens a file in their own editor.

Resolves an agent to its `AgentType`, then lists that type's allowlist
(`domain/agent/config_files.py`). Filesystem access goes through a
`ConfigFileStorePort` (Protocol) whose concrete implementation lives in
`infrastructure/agent/config_file_store.py` (Contract 2b: application defines
the port, infrastructure implements it). The port's atomic write, backup and
fingerprint are what Coffer's own writers reuse (spec agent-registry "Back up
and compare-and-swap every write Coffer makes to an agent's config").
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import (
    ConfigFileFormat,
    ConfigFileKind,
    ConfigFileSpec,
    DirEntryInfo,
    FileStat,
    config_files_for,
)
from coffer.domain.resource import Resource


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

        Creates parent directories as needed. Every write first copies the prior content to a
        timestamped file under ``~/.coffer/config-backups/`` (never next to the
        file). These are the user's own config files, so a RUN of bad edits has
        to be recoverable, not just the last one; the ``config_backups``
        retention policy bounds the folder and keeps each file's newest.

        The adapter also accepts an ``expected_fingerprint`` keyword for an
        optimistic staleness check; it is absent from this port because the
        callers that want it (``application.provider.projector``) declare their own narrower port
        that includes it.
        """
        ...

    def list_dir(self, root: pathlib.Path) -> list[DirEntryInfo] | None:
        """Recursive listing of regular ``.md`` files under ``root``.

        Returns ``None`` when ``root`` is not a directory. Symlinked files are
        skipped. Sorted by relpath for deterministic output.
        """
        ...

    def delete_with_backup(self, path: pathlib.Path) -> bool:
        """Copy content to a timestamped backup in Coffer's folder, as a write
        does, then remove the file.

        Returns ``False`` when the file is already absent.
        """
        ...

    def fingerprint(self, text: str | None) -> str:
        """sha256 hex-digest of the content; ``""`` for a missing file (text=None)."""
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


# Structural type for the agent-lookup dependency — avoids a hard import of
# AgentService (and keeps this service unit-testable with a fake). Keyed on the
# agent's uid: every method here is reached from a surface that has already
# resolved whatever the human typed.
class _AgentLookup(Protocol):
    async def get(self, uid: str) -> Resource: ...


class AgentConfigFileService:
    def __init__(self, *, agent_service: _AgentLookup, store: ConfigFileStorePort) -> None:
        self._agents = agent_service
        self._store = store

    async def _config_for(self, uid: str) -> AgentConfig:
        """The agent's parsed config. Raises ResourceNotFound (→ 404) when it doesn't exist."""
        return AgentConfig.model_validate((await self._agents.get(uid)).config)

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

    async def list_files(self, uid: str) -> list[ConfigFileInfo]:
        cfg = await self._config_for(uid)
        return [self._info(spec) for spec in config_files_for(cfg.type, cfg.resolved_config_dir())]
