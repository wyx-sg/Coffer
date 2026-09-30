"""Coffer's own MCP entry as a reconcile target, over real config files.

The entry is judged by its parameters — the shim path and ``--agent-uid`` —
not by the key being there (ADR one-level-triggered-reconciler-compares-
parameters). Before this, a moved shim or an entry naming another agent read
as "installed": the MCP-entry twin of PR #413.
"""

from __future__ import annotations

import json
import pathlib
import tomllib
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.agent.mcp_reconcile import McpEntryTarget
from coffer.application.audit_service import AuditService
from coffer.application.reconcile.reconciler import Reconciler
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEntry
from coffer.domain.errors import ShimNotFound
from coffer.domain.reconcile import Disposition, Op, Outcome, Trigger
from coffer.domain.resource import Resource
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from tests.support.homes import IsolatedHome, fake_agent_dir


class _Audit:
    def __init__(self) -> None:
        self.rows: list[AuditEntry] = []

    async def insert(self, entry: AuditEntry) -> None:
        self.rows.append(entry)

    async def query(self, **_: Any) -> list[AuditEntry]:
        return list(self.rows)


class _Agents:
    def __init__(self, rows: list[Resource]) -> None:
        self.rows = rows

    async def list(self) -> list[Resource]:
        return list(self.rows)


def _agent(uid: str, agent_type: AgentType, config_dir: pathlib.Path | None = None) -> Resource:
    now = datetime.now(tz=UTC)
    config: dict[str, Any] = {"type": agent_type.value}
    if config_dir is not None:
        config["config_dir"] = str(config_dir)
    return Resource(
        uid=uid,
        kind="agent",
        name=f"{agent_type.value}-{uid}",
        description=None,
        config=config,
        enabled=True,
        created_at=now,
        updated_at=now,
    )


def _setup(rows: list[Resource], shim: str | None) -> tuple[Reconciler, _Audit, McpEntryTarget]:
    def _resolve() -> str:
        if shim is None:
            raise ShimNotFound("coffer-mcp-shim")
        return shim

    target = McpEntryTarget(agents=_Agents(rows), store=ConfigFileStore(), shim_resolver=_resolve)
    audit = _Audit()
    rec = Reconciler(audit=AuditService(audit))
    rec.register(target)
    return rec, audit, target


def _claude_json(path: pathlib.Path) -> dict[str, Any]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="a stale Coffer MCP entry is repaired with its current parameters",
)
@pytest.mark.acceptance(
    spec="resource-framework", scenario="a changed parameter is drift and is repaired"
)
async def test_a_moved_shim_path_is_drift_and_is_repaired(isolated_home: IsolatedHome) -> None:
    claude = fake_agent_dir(isolated_home, AgentType.CLAUDE_CODE)
    agent = _agent("u-claude", AgentType.CLAUDE_CODE)
    path = claude.write(
        "global",
        json.dumps(
            {
                "mcpServers": {
                    "coffer": {
                        "command": "/old/bin/coffer-mcp-shim",
                        "args": ["--agent-uid", agent.uid],
                    },
                    "other": {"command": "npx", "args": ["their-server"]},
                },
                "projects": {"/work": {"history": ["ü"]}},
            }
        ),
    )
    rec, audit, _ = _setup([agent], "/new/bin/coffer-mcp-shim")

    plan = await rec.plan()
    (item,) = plan.results
    assert item.change.difference.op is Op.MODIFY
    assert item.change.difference.changed_params == ("command",)
    assert item.change.decision.reason_code == "stale_entry"

    report = await rec.run(trigger=Trigger.PERIOD)
    assert [r.outcome for r in report.results] == [Outcome.APPLIED]
    data = _claude_json(path)
    assert data["mcpServers"]["coffer"] == {
        "command": "/new/bin/coffer-mcp-shim",
        "args": ["--agent-uid", agent.uid],
    }
    # Everything that is not Coffer's own entry is untouched.
    assert data["mcpServers"]["other"] == {"command": "npx", "args": ["their-server"]}
    assert data["projects"] == {"/work": {"history": ["ü"]}}
    (row,) = audit.rows
    assert (row.event_type, row.actor, row.resource_name) == (
        "agent_mcp_installed",
        "system",
        agent.name,
    )
    assert row.details["repaired"] == ["command"]
    # Converged: the next pass finds nothing.
    assert (await rec.plan()).results == ()


async def test_a_stale_or_missing_agent_uid_is_drift_and_is_repaired(
    isolated_home: IsolatedHome,
) -> None:
    codex = fake_agent_dir(isolated_home, AgentType.CODEX)
    agent = _agent("u-codex", AgentType.CODEX)
    path = codex.write(
        "config",
        'model = "o4"\n\n[mcp_servers.coffer]\n'
        'command = "/bin/shim"\nargs = ["--agent", "codex"]\n',
    )
    rec, audit, _ = _setup([agent], "/bin/shim")
    (item,) = (await rec.plan()).results
    assert item.change.difference.changed_params == ("args",)

    await rec.run(trigger=Trigger.BOOT)
    doc = tomllib.loads(path.read_text(encoding="utf-8"))
    assert doc["model"] == "o4"
    assert doc["mcp_servers"]["coffer"] == {
        "command": "/bin/shim",
        "args": ["--agent-uid", agent.uid],
    }
    assert [r.event_type for r in audit.rows] == ["agent_mcp_installed"]


async def test_an_agent_without_an_entry_is_never_given_one(isolated_home: IsolatedHome) -> None:
    """Connecting is the user's act: a missing entry is not drift."""
    claude = fake_agent_dir(isolated_home, AgentType.CLAUDE_CODE)
    path = claude.write("global", json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    before = path.read_text(encoding="utf-8")
    rec, audit, _ = _setup([_agent("u1", AgentType.CLAUDE_CODE)], "/bin/shim")
    report = await rec.run(trigger=Trigger.PERIOD)
    assert report.results == ()
    assert path.read_text(encoding="utf-8") == before
    assert audit.rows == []


@pytest.mark.acceptance(
    spec="agent-registry/claude-code",
    scenario="an entry installed before the config dir was honoured moves to the agent's own file",
)
async def test_a_misplaced_entry_moves_to_the_agents_own_file(
    isolated_home: IsolatedHome, tmp_path: pathlib.Path
) -> None:
    """An older Coffer wrote a custom-dir Claude agent's entry into the
    standard ``~/.claude.json``; the pass installs it into ``<dir>/.claude.json``
    first and removes it from the home file second. An entry for an agent this
    machine does not have, and every foreign entry, stay."""
    custom = tmp_path / "work-claude"
    fake_agent_dir(isolated_home, AgentType.CLAUDE_CODE, config_dir=custom)
    agent = _agent("u-work", AgentType.CLAUDE_CODE, custom)
    home_json = isolated_home.root / ".claude.json"
    home_json.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "coffer": {"command": "/bin/shim", "args": ["--agent-uid", agent.uid]},
                    "theirs": {"command": "x"},
                }
            }
        ),
        encoding="utf-8",
    )
    rec, audit, _ = _setup([agent], "/bin/shim")
    plan = await rec.plan()
    assert [(r.change.difference.op, r.change.decision.reason_code) for r in plan.results] == [
        (Op.ADD, "misplaced_entry"),
        (Op.REMOVE, "misplaced_entry"),
    ]

    await rec.run(trigger=Trigger.BOOT)
    assert _claude_json(custom / ".claude.json") == {
        "mcpServers": {"coffer": {"command": "/bin/shim", "args": ["--agent-uid", agent.uid]}}
    }
    assert _claude_json(home_json) == {"mcpServers": {"theirs": {"command": "x"}}}
    assert [r.event_type for r in audit.rows] == ["agent_mcp_installed", "agent_mcp_uninstalled"]
    assert audit.rows[1].details["moved_to"] == str(custom / ".claude.json")


async def test_an_entry_for_an_unknown_agent_is_left_alone(isolated_home: IsolatedHome) -> None:
    home_json = isolated_home.root / ".claude.json"
    text = json.dumps(
        {"mcpServers": {"coffer": {"command": "/x", "args": ["--agent-uid", "gone"]}}}
    )
    home_json.write_text(text, encoding="utf-8")
    rec, _audit, _ = _setup([], "/bin/shim")
    assert (await rec.run(trigger=Trigger.PERIOD)).results == ()
    assert home_json.read_text(encoding="utf-8") == text


async def test_a_missing_launcher_blocks_the_repair_and_writes_nothing(
    isolated_home: IsolatedHome, tmp_path: pathlib.Path
) -> None:
    custom = tmp_path / "work-claude"
    fake_agent_dir(isolated_home, AgentType.CLAUDE_CODE, config_dir=custom)
    agent = _agent("u-work", AgentType.CLAUDE_CODE, custom)
    home_json = isolated_home.root / ".claude.json"
    text = json.dumps(
        {"mcpServers": {"coffer": {"command": "/gone", "args": ["--agent-uid", agent.uid]}}}
    )
    home_json.write_text(text, encoding="utf-8")
    rec, audit, _ = _setup([agent], None)
    report = await rec.run(trigger=Trigger.PERIOD)
    assert {r.change.decision.disposition for r in report.results} == {Disposition.BLOCKED}
    assert {r.change.decision.reason_code for r in report.results} == {"missing_launcher"}
    assert home_json.read_text(encoding="utf-8") == text
    assert not (custom / ".claude.json").exists()
    assert audit.rows == []


async def test_a_file_that_does_not_parse_is_left_alone(isolated_home: IsolatedHome) -> None:
    claude = fake_agent_dir(isolated_home, AgentType.CLAUDE_CODE)
    path = claude.write("global", "{ not json")
    rec, _audit, _ = _setup([_agent("u1", AgentType.CLAUDE_CODE)], "/bin/shim")
    report = await rec.run(trigger=Trigger.PERIOD)
    assert report.results == () and report.failures == ()
    assert path.read_text(encoding="utf-8") == "{ not json"


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a repair whose audit cannot be recorded is put back"
)
async def test_an_audit_failure_puts_the_file_back(isolated_home: IsolatedHome) -> None:
    claude = fake_agent_dir(isolated_home, AgentType.CLAUDE_CODE)
    agent = _agent("u1", AgentType.CLAUDE_CODE)
    text = json.dumps(
        {"mcpServers": {"coffer": {"command": "/old", "args": ["--agent-uid", "u1"]}}}
    )
    path = claude.write("global", text)

    class _Broken(_Audit):
        async def insert(self, entry: AuditEntry) -> None:
            raise RuntimeError("disk full")

    target = McpEntryTarget(
        agents=_Agents([agent]), store=ConfigFileStore(), shim_resolver=lambda: "/new"
    )
    rec = Reconciler(audit=AuditService(_Broken()))
    rec.register(target)
    (result,) = (await rec.run(trigger=Trigger.PERIOD)).results
    assert result.outcome is Outcome.FAILED
    assert path.read_text(encoding="utf-8") == text


async def test_the_default_agents_own_entry_in_the_home_file_is_left_alone(
    isolated_home: IsolatedHome, tmp_path: pathlib.Path
) -> None:
    fake_agent_dir(isolated_home, AgentType.CLAUDE_CODE)
    default = _agent("u-default", AgentType.CLAUDE_CODE)
    custom_dir = tmp_path / "work-claude"
    fake_agent_dir(isolated_home, AgentType.CLAUDE_CODE, config_dir=custom_dir)
    custom = _agent("u-work", AgentType.CLAUDE_CODE, custom_dir)
    home_json = isolated_home.root / ".claude.json"
    text = json.dumps(
        {"mcpServers": {"coffer": {"command": "/bin/shim", "args": ["--agent-uid", default.uid]}}}
    )
    home_json.write_text(text, encoding="utf-8")
    rec, _audit, _ = _setup([default, custom], "/bin/shim")
    assert (await rec.run(trigger=Trigger.PERIOD)).results == ()
    assert home_json.read_text(encoding="utf-8") == text
    assert not (custom_dir / ".claude.json").exists()


async def test_an_entry_already_in_the_agents_file_only_leaves_the_home_file(
    isolated_home: IsolatedHome, tmp_path: pathlib.Path
) -> None:
    custom = tmp_path / "work-claude"
    fake_agent_dir(isolated_home, AgentType.CLAUDE_CODE, config_dir=custom)
    agent = _agent("u-work", AgentType.CLAUDE_CODE, custom)
    entry = {"command": "/bin/shim", "args": ["--agent-uid", agent.uid]}
    (custom / ".claude.json").write_text(json.dumps({"mcpServers": {"coffer": entry}}), "utf-8")
    home_json = isolated_home.root / ".claude.json"
    home_json.write_text(json.dumps({"mcpServers": {"coffer": entry}}), encoding="utf-8")
    rec, audit, _ = _setup([agent], "/bin/shim")
    (only,) = (await rec.run(trigger=Trigger.BOOT)).results
    assert only.change.difference.op is Op.REMOVE and only.outcome is Outcome.APPLIED
    assert _claude_json(home_json) == {"mcpServers": {}}
    assert _claude_json(custom / ".claude.json") == {"mcpServers": {"coffer": entry}}
    assert [r.event_type for r in audit.rows] == ["agent_mcp_uninstalled"]
