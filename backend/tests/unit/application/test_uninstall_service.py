"""The uninstall's order and its report (spec daemon "Uninstall Coffer from this
machine"; design D3 of add-self-update-and-uninstall)."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Sequence
from types import SimpleNamespace
from typing import Any

from coffer.application.uninstall import FileStep, MachineSteps, UninstallService
from coffer.domain.agent.types import AgentType


def _agent(uid: str, kind: str) -> Any:
    return SimpleNamespace(uid=uid, name=uid, config={"type": kind})


class Log:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.held = False


class Agents:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    async def list(self) -> list[Any]:
        return self.rows


class Providers:
    def __init__(self, log: Log) -> None:
        self.log = log

    async def deactivate(self, agent_type: AgentType, *, actor: str = "api") -> None:
        assert self.log.held
        self.log.calls.append(f"provider:{agent_type.value}")


class Connections:
    def __init__(self, log: Log, fail: str | None = None) -> None:
        self.log, self.fail = log, fail

    async def disconnect(self, agent_uid: str, *, actor: str) -> None:
        assert self.log.held
        if agent_uid == self.fail:
            raise OSError("config is read-only")
        self.log.calls.append(f"disconnect:{agent_uid}")


class Skills:
    def __init__(self, log: Log) -> None:
        self.log = log

    async def cleanup_bindings_for_agent(self, agent: Any) -> None:
        self.log.calls.append(f"unlink:{agent.uid}")


class Reconciler:
    def __init__(self, log: Log) -> None:
        self.log = log
        self.frozen = False

    @contextlib.asynccontextmanager
    async def hold(self) -> AsyncIterator[None]:
        self.log.held = True
        try:
            yield
        finally:
            self.log.held = False

    def freeze(self) -> None:
        assert self.log.held
        self.frozen = True
        self.log.calls.append("freeze")


async def _blocking(step: FileStep) -> Sequence[str]:
    return step()


def _service(
    log: Log, rows: list[Any], *, fail: str | None = None
) -> tuple[UninstallService, Reconciler]:
    reconciler = Reconciler(log)

    def step(name: str, removed: list[str]) -> FileStep:
        def run() -> list[str]:
            log.calls.append(name)
            return removed

        return run

    def broken() -> list[str]:
        raise PermissionError("Operation not permitted")

    machine = MachineSteps(
        login_job=step("login_job", ["/p/dev.coffer.daemon.plist"]),
        terminal_files=step("terminal_files", []),
        path_lines=broken,
        binaries=step("binaries", ["/h/.coffer/bin"]),
    )
    service = UninstallService(
        agents=Agents(rows),
        providers=Providers(log),
        connections=Connections(log, fail),
        skills=Skills(log),
        reconciler=reconciler,
        machine=machine,
        run_blocking=_blocking,
    )
    return service, reconciler


async def test_agents_are_cleaned_in_order_under_the_hold_then_the_reconciler_freezes() -> None:
    log = Log()
    service, reconciler = _service(log, [_agent("a1", "claude_code"), _agent("a2", "codex")])
    report = await service.run(actor="cli")
    assert log.calls[:7] == [
        "provider:claude_code",
        "provider:codex",
        "disconnect:a1",
        "disconnect:a2",
        "unlink:a1",
        "unlink:a2",
        "freeze",
    ]
    assert log.calls[7:] == ["login_job", "terminal_files", "binaries"]
    assert reconciler.frozen
    outcomes = {s.key: s.outcome for s in report.steps}
    assert outcomes == {
        "provider_routing": "done",
        "agent_connections": "done",
        "skill_links": "done",
        "login_job": "done",
        "terminal_files": "nothing",
        "path_lines": "failed",
        "binaries": "done",
    }
    assert not report.ok


async def test_a_failing_agent_does_not_stop_the_others() -> None:
    log = Log()
    service, _ = _service(log, [_agent("a1", "claude_code"), _agent("a2", "codex")], fail="a1")
    report = await service.run(actor="cli")
    assert "disconnect:a2" in log.calls
    step = next(s for s in report.steps if s.key == "agent_connections")
    assert step.outcome == "failed" and "read-only" in step.detail
