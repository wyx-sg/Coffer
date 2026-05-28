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
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

from coffer.domain.skill.binding import BindingState, LinkMode


class MasterStorePort(Protocol):
    """Per-OS canonical skill folder store under ``~/.coffer/skills/``."""

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


class SourceFetcherPort(Protocol):
    """Fetch a remote skill source into a temporary working folder."""

    def fetched(
        self,
        *,
        git_url: str,
        git_ref: str,
        git_subpath: str = "",
    ) -> AbstractAsyncContextManager[pathlib.Path]: ...


class SyncEnginePort(Protocol):
    """Per-OS symlink / junction operations + drift classification."""

    def make_directory_link(self, *, target: pathlib.Path, link: pathlib.Path) -> LinkMode: ...

    def remove_directory_link(self, link: pathlib.Path) -> None: ...

    def classify_target(
        self,
        *,
        link: pathlib.Path,
        expected_master: pathlib.Path,
        link_mode: LinkMode | None,
    ) -> Any: ...
