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
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.descriptor import AgentDescriptor
from coffer.domain.agent.detection import DetectionState, ProgramInfo, classify
from coffer.domain.agent.facets import AgentCatalog
from coffer.domain.agent.types import AgentType
from coffer.domain.resource import Resource


@dataclass(frozen=True)
class AgentCandidate:
    """An agent seen on this machine that is not registered yet."""

    type: AgentType
    display_name: str
    config_dir: str
    default_skill_dir: str
    suggested_name: str
    state: DetectionState
    version: str | None

    @property
    def addable(self) -> bool:
        """Only an agent that is installed and has its config directory can be
        registered: registration never creates the config directory, and a
        directory whose program is gone belongs to no working agent."""
        return self.state is DetectionState.INSTALLED_ACTIVE


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


def _suffix(path: pathlib.Path) -> str:
    """A name-safe tail for a candidate in a non-standard directory."""
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", path.name.lstrip(".")).strip("-")
    return slug or "custom"


class AutoDetectService:
    """Read-only detection of installed agents (no registration side effects)."""

    def __init__(
        self,
        *,
        agent_service: _AgentLister,
        catalog: AgentCatalog,
        environ: Callable[[], dict[str, str]] = lambda: dict(os.environ),
        dir_exists: Callable[[pathlib.Path], bool] = _is_dir,
    ) -> None:
        self._agents = agent_service
        self._catalog = catalog
        self._environ = environ
        self._dir_exists = dir_exists

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

    async def discover(self) -> list[AgentCandidate]:
        """Every agent seen here that is not registered yet, as candidates.

        Read-only: it never writes. A directory a registered agent already
        holds is skipped, so the list only shows what is not managed yet — a
        removed agent re-appears here while its program or directory remains.
        """
        registered: list[pathlib.Path] = []
        for row in await self._agents.list():
            try:
                registered.append(AgentConfig.model_validate(row.config).resolved_config_dir())
            except Exception:
                continue
        candidates: list[AgentCandidate] = []
        for descriptor in self._catalog:
            program = await asyncio.to_thread(self._program, descriptor)
            for index, config_dir in enumerate(self._looked_at(descriptor)):
                if any(_same_dir(config_dir, r) for r in registered):
                    continue
                exists = await asyncio.to_thread(self._dir_exists, config_dir)
                state = classify(program, config_dir_exists=exists)
                if state is DetectionState.MISSING:
                    continue
                name = descriptor.type.default_name()
                candidates.append(
                    AgentCandidate(
                        type=descriptor.type,
                        display_name=descriptor.display_name,
                        config_dir=str(config_dir),
                        default_skill_dir=str(config_dir / descriptor.skill_subpath),
                        suggested_name=name if index == 0 else f"{name}-{_suffix(config_dir)}",
                        state=state,
                        version=program.version,
                    )
                )
        return candidates


__all__ = ["AgentCandidate", "AgentDetection", "AutoDetectService"]
