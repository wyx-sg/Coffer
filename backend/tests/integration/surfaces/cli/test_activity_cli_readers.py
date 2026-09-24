"""The command-line readers survive the Activity page (spec web-ui "Keep the
command-line record readers").

Gathering the audit log and the MCP invocation log onto one web page must not
withdraw the scripts' way in: ``coffer audit`` and ``coffer mcp invocations``
still read each record through a running (in-process) daemon.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from typing import Any

import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli.main import app
from tests.integration.surfaces.cli.test_mcp_cmd import (  # noqa: F401  (fixture import)
    _register_server,
    mcp_daemon,
)

_runner = CliRunner()


@pytest.mark.acceptance(spec="web-ui", scenario="the command-line readers still read the records")
def test_coffer_audit_still_reads_the_audit_log(in_proc_daemon: Any) -> None:
    from coffer.surfaces.cli import _client as _cli_client

    client, _info = _cli_client.client_or_exit()
    created = client.post(
        "/resources", json={"kind": "fake_kind", "name": "reader-probe", "config": {"foo": 1}}
    )
    assert created.status_code == 201, created.text

    result = _runner.invoke(app, ["audit", "list", "--json"])
    assert result.exit_code == 0, result.output
    entries = json.loads(result.output)["audit_events"]
    assert any(e.get("resource_name") == "reader-probe" for e in entries), entries


@pytest.mark.acceptance(spec="web-ui", scenario="the command-line readers still read the records")
def test_coffer_mcp_invocations_still_reads_the_invocation_log(mcp_daemon: Any) -> None:  # noqa: F811
    from coffer.domain.mcp.capability import MCPInvocation
    from coffer.infrastructure.mcp.persistence import MCPInvocationRepo
    from coffer.infrastructure.persistence.engine import (
        create_async_engine_with_pragmas,
        session_maker,
    )

    uid = _register_server()
    engine = create_async_engine_with_pragmas(os.environ["COFFER_DB_URL"])

    async def _seed() -> None:
        await MCPInvocationRepo(session_maker(engine)).insert(
            MCPInvocation(
                id=None,
                timestamp=datetime.now(tz=UTC),
                resource_uid=uid,
                capability_type="tool",
                capability_key="list_directory",
                duration_ms=9,
                status="ok",
                error_message=None,
                session_id=None,
            )
        )
        await engine.dispose()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_seed())
    loop.close()

    result = _runner.invoke(app, ["mcp", "invocations", "fs", "--json"])
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)["invocations"]
    assert [r["capability_key"] for r in rows] == ["list_directory"]


def _seed_rows(rows: list[tuple[str, str, str]]) -> None:
    """Seed one invocation per ``(resource_uid, capability_key, status)``."""
    from coffer.domain.mcp.capability import MCPInvocation
    from coffer.infrastructure.mcp.persistence import MCPInvocationRepo
    from coffer.infrastructure.persistence.engine import (
        create_async_engine_with_pragmas,
        session_maker,
    )

    engine = create_async_engine_with_pragmas(os.environ["COFFER_DB_URL"])

    async def _seed() -> None:
        repo = MCPInvocationRepo(session_maker(engine))
        for uid, key, status in rows:
            await repo.insert(
                MCPInvocation(
                    id=None,
                    timestamp=datetime.now(tz=UTC),
                    resource_uid=uid,
                    capability_type="tool",
                    capability_key=key,
                    duration_ms=3,
                    status=status,
                    error_message=None,
                    session_id=None,
                )
            )
        await engine.dispose()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_seed())
    loop.close()


@pytest.mark.acceptance(spec="web-ui", scenario="the command-line readers still read the records")
def test_coffer_mcp_invocations_without_a_server_reads_every_server(mcp_daemon: Any) -> None:  # noqa: F811
    """No server named: the cross-server log the Activity page reads, including
    Coffer's own built-in calls and a deleted server's rows."""
    fs = _register_server("fs")
    git = _register_server("git")
    _seed_rows(
        [
            (fs, "read_file", "ok"),
            (git, "git_log", "error"),
            ("coffer", "coffer__recall", "ok"),
            ("deleted:old", "gone_tool", "ok"),
        ]
    )

    result = _runner.invoke(app, ["mcp", "invocations", "--json"])

    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)["invocations"]
    assert {(r["resource_uid"], r["capability_key"]) for r in rows} == {
        (fs, "read_file"),
        (git, "git_log"),
        ("coffer", "coffer__recall"),
        ("deleted:old", "gone_tool"),
    }
    names = {r["resource_uid"]: r["resource_name"] for r in rows}
    assert names[fs] == "fs" and names[git] == "git" and names["coffer"] is None


def test_coffer_mcp_invocations_without_a_server_keeps_its_filters(mcp_daemon: Any) -> None:  # noqa: F811
    fs = _register_server("fs")
    _seed_rows([(fs, "a", "ok"), ("coffer", "b", "error"), (fs, "c", "error")])

    errors = _runner.invoke(app, ["mcp", "invocations", "--status", "error", "--json"])
    capped = _runner.invoke(app, ["mcp", "invocations", "--limit", "1", "--json"])
    future = _runner.invoke(
        app, ["mcp", "invocations", "--since", "2999-01-01T00:00:00+00:00", "--json"]
    )

    assert errors.exit_code == capped.exit_code == future.exit_code == 0, errors.output
    assert {r["capability_key"] for r in json.loads(errors.output)["invocations"]} == {"b", "c"}
    assert len(json.loads(capped.output)["invocations"]) == 1
    assert json.loads(future.output) == {"invocations": []}


def test_coffer_mcp_invocations_table_names_each_rows_server(mcp_daemon: Any) -> None:  # noqa: F811
    fs = _register_server("fs")
    _seed_rows([(fs, "read_file", "ok"), ("deleted:old", "gone_tool", "ok")])

    result = _runner.invoke(app, ["mcp", "invocations"], env={"COLUMNS": "200"})

    assert result.exit_code == 0, result.output
    fs_line = next(line for line in result.output.splitlines() if "read_file" in line)
    gone_line = next(line for line in result.output.splitlines() if "gone_tool" in line)
    assert "fs" in fs_line.split("read_file")[0]
    assert "deleted:old" in gone_line


def test_coffer_mcp_invocations_with_a_server_stays_on_that_server(mcp_daemon: Any) -> None:  # noqa: F811
    fs = _register_server("fs")
    _seed_rows([(fs, "read_file", "ok"), ("coffer", "coffer__recall", "ok")])

    result = _runner.invoke(app, ["mcp", "invocations", "fs", "--json"])

    assert result.exit_code == 0, result.output
    assert [r["capability_key"] for r in json.loads(result.output)["invocations"]] == ["read_file"]
