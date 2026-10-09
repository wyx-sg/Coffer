"""Uninstall Coffer from this machine (spec daemon "Uninstall Coffer from this
machine"; design D3 of ``add-self-update-and-uninstall``).

Coffer writes into files it does not own: the agents' MCP config, settings and
hooks, their skill folders, the login items, the shell profiles and Warp's
launch configurations. Each kind already knows how to take its own writes out
again; this runs them all, in the order that keeps anything from coming back:

1. Inside the reconciler's hold: the model-provider routing (it runs Coffer's
   binaries), every agent's connection — MCP entry and memory hook — and every
   skill link with its delivery records.
2. Freeze the reconciler for the rest of the process, so no pass restores a
   link before the daemon exits.
3. The machine-level files: the start-at-login job, the terminal launch files,
   the installer's ``PATH`` lines and ``~/.coffer/bin``.

Each step is attempted even when an earlier one failed and reports its own
outcome. Nothing in ``~/.coffer`` besides ``bin`` is touched: the vault, the
settings and the history stay for a reinstall. Stopping the daemon and deleting
the data are the caller's (``surfaces/http/daemon_uninstall_routes.py``).
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.types import AgentType
from coffer.domain.resource import Resource

_logger = logging.getLogger(__name__)

Outcome = Literal["done", "nothing", "failed"]


@dataclass(frozen=True)
class StepResult:
    """One step of the uninstall, as the person reads it."""

    key: str
    outcome: Outcome
    #: What was removed, or why the step failed.
    detail: str = ""


@dataclass
class UninstallReport:
    steps: list[StepResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(s.outcome != "failed" for s in self.steps)


class _Agents(Protocol):
    async def list(self) -> list[Resource]: ...


class _Providers(Protocol):
    async def deactivate(self, agent_type: AgentType, *, actor: str = ...) -> object: ...


class _Connections(Protocol):
    async def disconnect(self, agent_uid: str, *, actor: str) -> object: ...


class _Skills(Protocol):
    async def cleanup_bindings_for_agent(self, agent: Resource) -> None: ...


class _Reconciler(Protocol):
    def hold(self) -> contextlib.AbstractAsyncContextManager[None]: ...
    def freeze(self) -> None: ...


#: A machine-level step: it removes what it finds and says what that was;
#: an empty answer means there was nothing to remove.
FileStep = Callable[[], Sequence[str]]


@dataclass(frozen=True)
class MachineSteps:
    """The machine-level removals, from the infrastructure layer."""

    login_job: FileStep
    terminal_files: FileStep
    path_lines: FileStep
    binaries: FileStep


class UninstallService:
    def __init__(
        self,
        *,
        agents: _Agents,
        providers: _Providers | None,
        connections: _Connections,
        skills: _Skills,
        reconciler: _Reconciler,
        machine: MachineSteps,
        run_blocking: Callable[[FileStep], Awaitable[Sequence[str]]],
    ) -> None:
        self._agents = agents
        self._providers = providers
        self._connections = connections
        self._skills = skills
        self._reconciler = reconciler
        self._machine = machine
        self._blocking = run_blocking

    async def run(self, *, actor: str) -> UninstallReport:
        report = UninstallReport()
        async with self._reconciler.hold():
            agents = await self._safe_agents(report)
            await self._each_agent(report, "provider_routing", agents, self._unroute(actor))
            await self._each_agent(report, "agent_connections", agents, self._disconnect(actor))
            await self._each_agent(report, "skill_links", agents, self._unlink)
            self._reconciler.freeze()
        for key, step in (
            ("login_job", self._machine.login_job),
            ("terminal_files", self._machine.terminal_files),
            ("path_lines", self._machine.path_lines),
            ("binaries", self._machine.binaries),
        ):
            report.steps.append(await self._file_step(key, step))
        _logger.info(
            "daemon.uninstalled",
            extra={"steps": {s.key: s.outcome for s in report.steps}},
        )
        return report

    async def _safe_agents(self, report: UninstallReport) -> list[Resource]:
        try:
            return await self._agents.list()
        except Exception as exc:
            report.steps.append(StepResult("agents", "failed", _reason(exc)))
            return []

    def _unroute(self, actor: str) -> Callable[[Resource], Awaitable[bool]]:
        async def step(agent: Resource) -> bool:
            if self._providers is None:
                return False
            await self._providers.deactivate(_type(agent), actor=actor)
            return True

        return step

    def _disconnect(self, actor: str) -> Callable[[Resource], Awaitable[bool]]:
        async def step(agent: Resource) -> bool:
            await self._connections.disconnect(agent.uid, actor=actor)
            return True

        return step

    async def _unlink(self, agent: Resource) -> bool:
        await self._skills.cleanup_bindings_for_agent(agent)
        return True

    async def _each_agent(
        self,
        report: UninstallReport,
        key: str,
        agents: Sequence[Resource],
        step: Callable[[Resource], Awaitable[bool]],
    ) -> None:
        done: list[str] = []
        failed: list[str] = []
        for agent in agents:
            try:
                if await step(agent):
                    done.append(agent.name)
            except Exception as exc:
                _logger.warning("daemon.uninstall_step_failed %s %s: %r", key, agent.uid, exc)
                failed.append(f"{agent.name}: {_reason(exc)}")
        if failed:
            report.steps.append(StepResult(key, "failed", "; ".join(failed)))
        elif done:
            report.steps.append(StepResult(key, "done", ", ".join(done)))
        else:
            report.steps.append(StepResult(key, "nothing"))

    async def _file_step(self, key: str, step: FileStep) -> StepResult:
        try:
            removed = await self._blocking(step)
        except Exception as exc:
            _logger.warning("daemon.uninstall_step_failed %s: %r", key, exc)
            return StepResult(key, "failed", _reason(exc))
        return (
            StepResult(key, "done", ", ".join(removed)) if removed else StepResult(key, "nothing")
        )


def _type(agent: Resource) -> AgentType:
    return AgentConfig.model_validate(agent.config).type


def _reason(exc: BaseException) -> str:
    return (str(exc) or type(exc).__name__)[:300]


@contextlib.asynccontextmanager
async def no_hold() -> AsyncIterator[None]:
    """A hold that holds nothing (tests)."""
    yield


__all__ = [
    "FileStep",
    "MachineSteps",
    "StepResult",
    "UninstallReport",
    "UninstallService",
    "no_hold",
]
