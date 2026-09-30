"""Discover locally-installed agents, and detect a registered agent's state
(spec agent-registry).

Detection has two signals (``domain.agent.detection``): the agent's program on
its real ``PATH``, asked through the agent's dependency probe facet, and its
config directory on disk. Discovery reports every directory Coffer has reason
to look at — each type's standard location, plus the directory the type's own
environment variable (``CLAUDE_CONFIG_DIR``, ``CODEX_HOME``) names in the
daemon's environment when it is set — as a *candidate* when either signal is
there and no registered agent already holds that directory. Nothing is
registered automatically, and nothing is scanned beyond those directories.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from coffer.application.agent.install_handoff import (
    MachineFacts,
    agent_install_handoff,
    agent_program_handoff,
)
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.descriptor import AgentDescriptor
from coffer.domain.agent.detection import DetectionState, ProgramInfo, classify
from coffer.domain.agent.facets import AgentCatalog
from coffer.domain.agent.types import AgentType
from coffer.domain.resource import Resource


@dataclass(frozen=True)
class AgentTypeDetection:
    """What this machine holds of one supported type — the row the Agents page
    always renders for it, registered or not (spec agent-registry "Report every
    supported type's detection state")."""

    type: AgentType
    display_name: str
    #: The registered agent's directory, or — for a type not registered — the
    #: directory Add would register: the standard one, or the one the type's
    #: environment variable names when only that one exists.
    config_dir: str
    #: The type's standard directory (``~/.claude``, ``~/.codex``) — where Add
    #: registers when it is given no other.
    standard_config_dir: str
    default_skill_dir: str
    state: DetectionState
    version: str | None
    #: The registered agent of this type, when there is one.
    uid: str | None = None
    #: Another directory seen for this type — the one its environment variable
    #: names — offered as "use a different config directory", never added.
    other_config_dir: str | None = None

    @property
    def name(self) -> str:
        return self.type.default_name()

    @property
    def addable(self) -> bool:
        """Whether Add may register this type here: not registered yet, and its
        program is installed. ``installed_never_run`` is addable — registration
        creates the standard directory — while ``config_only`` is not, because a
        directory whose program is gone belongs to no working agent."""
        return self.uid is None and self.state.installed

    @property
    def is_candidate(self) -> bool:
        """Not registered, and seen here by either signal."""
        return self.uid is None and self.state is not DetectionState.MISSING


@dataclass(frozen=True)
class AgentDetection:
    """What the two signals say about one agent's config directory."""

    state: DetectionState
    version: str | None


class _AgentLister(Protocol):
    async def list(self) -> list[Resource]: ...


def _is_dir(path: pathlib.Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def _same_dir(a: pathlib.Path, b: pathlib.Path) -> bool:
    try:
        return a.expanduser().resolve() == b.expanduser().resolve()
    except OSError:
        return a == b


class AutoDetectService:
    """Read-only detection of installed agents (no registration side effects)."""

    def __init__(
        self,
        *,
        agent_service: _AgentLister,
        catalog: AgentCatalog,
        environ: Callable[[], dict[str, str]] = lambda: dict(os.environ),
        dir_exists: Callable[[pathlib.Path], bool] = _is_dir,
        machine: Callable[[], str] = lambda: "unknown",
        lookup_path: Callable[[], str] = lambda: os.environ.get("PATH", ""),
    ) -> None:
        self._agents = agent_service
        self._catalog = catalog
        self._environ = environ
        self._dir_exists = dir_exists
        # What an install prompt says about this machine: its OS and
        # architecture, and the PATH the dependency probes look programs up on.
        self._machine = machine
        self._lookup_path = lookup_path

    async def _facts(self) -> MachineFacts:
        # The first ask of the lookup PATH may start the login shell.
        return MachineFacts(
            machine=self._machine(), lookup_path=await asyncio.to_thread(self._lookup_path)
        )

    async def install_handoff(self, rows: list[AgentTypeDetection]) -> str | None:
        """The prompt that installs one of the supported types, while none of
        ``rows`` is installed; ``None`` once one is."""
        if not rows or any(row.state.installed for row in rows):
            return None
        return agent_install_handoff(rows, await self._facts())

    async def program_handoff(
        self, agent_type: AgentType, config_dir: str, state: DetectionState, *, registered: bool
    ) -> str | None:
        """The prompt that installs (or reinstalls) ``agent_type``'s program
        while it is not found; ``None`` while it is."""
        if state.installed:
            return None
        return agent_program_handoff(
            agent_type,
            config_dir=config_dir,
            state=state,
            registered=registered,
            facts=await self._facts(),
        )

    def _program(self, descriptor: AgentDescriptor) -> ProgramInfo:
        probe = descriptor.dependency_probe
        return probe.probe() if probe is not None else ProgramInfo()

    async def detect(self, agent_type: AgentType, config_dir: pathlib.Path) -> AgentDetection:
        """The detection state of an agent of ``agent_type`` at ``config_dir``."""
        descriptor = self._catalog.get(agent_type)
        program = await asyncio.to_thread(self._program, descriptor)
        exists = await asyncio.to_thread(self._dir_exists, config_dir)
        return AgentDetection(classify(program, config_dir_exists=exists), program.version)

    def _looked_at(self, descriptor: AgentDescriptor) -> list[pathlib.Path]:
        """The standard directory, then the one the type's environment variable
        names in the daemon's environment, when set and different."""
        dirs = [descriptor.default_config_dir()]
        named = self._environ().get(descriptor.home_env_var, "") if descriptor.home_env_var else ""
        if named.strip():
            env_dir = pathlib.Path(named).expanduser()
            if env_dir.is_absolute() and not _same_dir(env_dir, dirs[0]):
                dirs.append(env_dir)
        return dirs

    async def types(self) -> list[AgentTypeDetection]:
        """One row per supported type, in manifest order, registered or not.

        Read-only: it never writes. A registered type reports its agent's own
        directory; any other reports the directory Add would register — the
        standard one unless only the one the type's environment variable names
        exists — with the other named as ``other_config_dir`` when it exists.
        """
        registered: dict[AgentType, Resource] = {}
        for row in await self._agents.list():
            try:
                registered.setdefault(AgentConfig.model_validate(row.config).type, row)
            except Exception:
                continue
        rows: list[AgentTypeDetection] = []
        for descriptor in self._catalog:
            program = await asyncio.to_thread(self._program, descriptor)
            agent = registered.get(descriptor.type)
            looked_at = self._looked_at(descriptor)
            exists = [await asyncio.to_thread(self._dir_exists, d) for d in looked_at]
            if agent is not None:
                config_dir = AgentConfig.model_validate(agent.config).resolved_config_dir()
                dir_exists = await asyncio.to_thread(self._dir_exists, config_dir)
            else:
                pick = 1 if len(looked_at) > 1 and exists[1] and not exists[0] else 0
                config_dir, dir_exists = looked_at[pick], exists[pick]
            others = [
                d
                for d, e in zip(looked_at, exists, strict=True)
                if e and not _same_dir(d, config_dir)
            ]
            rows.append(
                AgentTypeDetection(
                    type=descriptor.type,
                    display_name=descriptor.display_name,
                    config_dir=str(config_dir),
                    standard_config_dir=str(looked_at[0]),
                    default_skill_dir=str(config_dir / descriptor.skill_subpath),
                    state=classify(program, config_dir_exists=dir_exists),
                    version=program.version,
                    uid=agent.uid if agent is not None else None,
                    other_config_dir=str(others[0]) if others else None,
                )
            )
        return rows

    async def discover(self) -> list[AgentTypeDetection]:
        """The types seen here that are not registered yet, as candidates —
        at most one per type. A removed agent re-appears here while its program
        or directory remains."""
        return [row for row in await self.types() if row.is_candidate]


__all__ = ["AgentDetection", "AgentTypeDetection", "AutoDetectService"]
