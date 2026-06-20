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
from coffer.domain.skill.external_dir import ExternalDirRegistration
from coffer.domain.skill.scan import ScanEntry


class MasterStorePort(Protocol):
    """Per-OS canonical skill folder store under ``~/.coffer/skills/``."""

    @property
    def root(self) -> pathlib.Path: ...

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

    async def list_for_skill(self, skill_id: int) -> list[BindingState]: ...

    async def list_for_agent(self, agent_id: int) -> list[BindingState]: ...

    async def find(self, skill_id: int, agent_id: int) -> BindingState | None: ...

    async def upsert(
        self,
        *,
        skill_id: int,
        agent_id: int,
        enabled: bool,
        last_linked_at: Any | None = ...,
        last_link_path: str | None = ...,
        link_mode: LinkMode | None = ...,
    ) -> BindingState: ...

    async def delete_for_skill(self, skill_id: int) -> Any: ...

    async def delete_for_agent(self, agent_id: int) -> Any: ...


class WorkspaceScanPort(Protocol):
    """Directory scanning for unmanaged-skill discovery (FR-022).

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


class ExternalDirRegistrarPort(Protocol):
    """Register / deregister a Coffer-owned external skill directory in an
    agent's own config file (spec 005, EXTERNAL_DIR delivery — Hermes).

    Both operations are idempotent; ``deregister`` is a no-op when the entry,
    container path, or file is absent.
    """

    def register(self, reg: ExternalDirRegistration) -> None: ...

    def deregister(self, reg: ExternalDirRegistration) -> None: ...
