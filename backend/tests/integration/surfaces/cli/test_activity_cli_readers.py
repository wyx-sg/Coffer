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
