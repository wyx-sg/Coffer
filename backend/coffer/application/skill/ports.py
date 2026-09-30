"""Application-layer Protocols for skill infrastructure dependencies.

Defined here so application code does not import from
``coffer.infrastructure.skill`` (Contract 2 — application MUST NOT depend
on infrastructure). Concrete implementations live in
``coffer.infrastructure.skill.*`` and are injected at the composition
root (``coffer.surfaces.http.agent_skill_wiring``).

These Protocols are kept intentionally loose — they capture only the
members the skill application layer actually calls. Concrete adapters in
infrastructure may expose extra methods.
"""

from __future__ import annotations

import pathlib
from typing import Any, Protocol

from coffer.domain.skill.binding import BindingState, LinkMode
from coffer.domain.skill.scan import ScanEntry
from coffer.domain.skill.source_status import SourceStatus


class MasterStorePort(Protocol):
    """Per-OS canonical skill folder store under ``~/.coffer/vault/skills/``."""

    @property
    def root(self) -> pathlib.Path: ...

    @property
    def derived_root(self) -> pathlib.Path: ...

    @property
    def backup_root(self) -> pathlib.Path: ...

    def ensure_root(self) -> None: ...

    def exists(self, name: str) -> bool: ...

    def paths_for(self, name: str) -> Any: ...

    def copy_in(
        self, *, src: pathlib.Path, name: str, meta: dict[str, Any] | None = ...
    ) -> Any: ...

    def atomic_replace(
        self, *, src: pathlib.Path, name: str, meta: dict[str, Any] | None = ...
    ) -> Any: ...

    def delete(self, name: str) -> None: ...

    def find_orphans(self, known_names: set[str]) -> list[str]: ...


class SkillBindingRepoPort(Protocol):
    """Persistence boundary for the ``skill_agent_bindings`` join table."""

    async def list_enabled(self) -> list[BindingState]: ...

    async def list_all(self) -> list[BindingState]: ...

    async def list_for_skill(self, skill_uid: str) -> list[BindingState]: ...

    async def list_for_agent(self, agent_uid: str) -> list[BindingState]: ...

    async def find(self, skill_uid: str, agent_uid: str) -> BindingState | None: ...

    async def upsert(
        self,
        *,
        skill_uid: str,
        agent_uid: str,
        enabled: bool,
        last_linked_at: Any | None = ...,
        last_link_path: str | None = ...,
        link_mode: LinkMode | None = ...,
    ) -> BindingState: ...

    async def delete(self, skill_uid: str, agent_uid: str) -> None: ...

    async def delete_for_skill(self, skill_uid: str) -> Any: ...

    async def delete_for_agent(self, agent_uid: str) -> Any: ...


class WorkspaceScanPort(Protocol):
    """Directory scanning for unmanaged-skill discovery (see "List unmanaged skills in
    an agent's skill locations").

    Builds ``ScanEntry`` values from one agent skill location; the pure
    classification (managed vs. unmanaged vs. foreign) happens in
    ``coffer.domain.skill.scan.classify``.
    """

    def scan_dir(self, root: pathlib.Path) -> list[ScanEntry]: ...


class SyncEnginePort(Protocol):
    """Per-OS symlink / junction operations + drift classification."""

    def make_directory_link(self, *, target: pathlib.Path, link: pathlib.Path) -> LinkMode: ...

    def remove_directory_link(
        self, link: pathlib.Path, *, link_mode: LinkMode | None = ...
    ) -> None: ...

    def classify_target(
        self,
        *,
        link: pathlib.Path,
        expected_master: pathlib.Path,
        link_mode: LinkMode | None,
    ) -> Any: ...

    def infer_link_mode(self, link: pathlib.Path) -> LinkMode:
        """Best-effort: what kind of link is actually on disk at ``link``?

        Used when a target is already correctly linked but no binding row
        recorded the mode, so a junction / copy-fallback isn't mislabelled
        SYMLINK.
        """
        ...


class GitSourcePort(Protocol):
    """``git`` over a skill's repository (``infrastructure.skill.git_source``).

    Every method raises ``SkillSourceUnreachable`` with git's own message when
    git fails; nothing here writes outside the directories it is given.
    """

    async def clone(self, url: str, dest: pathlib.Path) -> None: ...

    async def resolve(self, repo: pathlib.Path, ref: str | None, *, url: str) -> str: ...

    async def checkout(
        self, repo: pathlib.Path, commit: str, subpath: str, dest: pathlib.Path, *, url: str
    ) -> pathlib.Path: ...

    async def has_commit(self, repo: pathlib.Path, commit: str) -> bool: ...

    async def commits(
        self, repo: pathlib.Path, base: str, head: str, subpath: str, *, limit: int = ...
    ) -> list[Any]: ...

    async def changed_files(
        self, repo: pathlib.Path, base: str, head: str, subpath: str
    ) -> list[Any]: ...


class ArchiveReaderPort(Protocol):
    """Reads an uploaded skill archive into staging, refusing it first
    (``infrastructure.skill.archive_reader``)."""

    def save_upload(self, stream: Any, dest: pathlib.Path, *, cap_bytes: int) -> int: ...

    def extract(self, archive: pathlib.Path, dest: pathlib.Path, *, cap_bytes: int) -> None: ...


class SourceStatusRepoPort(Protocol):
    """A Git-imported skill's last update check, machine-local
    (``local/skill-source-status.json``)."""

    async def get(self, skill_uid: str) -> SourceStatus | None: ...

    async def list_all(self) -> dict[str, SourceStatus]: ...

    async def put(self, status: SourceStatus) -> SourceStatus: ...

    async def delete(self, skill_uid: str) -> None: ...
