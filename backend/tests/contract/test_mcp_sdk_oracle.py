"""Contract test: drive coffer's /mcp endpoint with the official mcp SDK
as a black-box client. If the SDK accepts the responses without raising,
the wire format is spec-compliant.

The test boots an in-process daemon on a random loopback port via a
background thread running uvicorn (same runtime as production), then uses
the mcp SDK's streamable_http_client + ClientSession to exercise:

    initialize → tools/list → tools/call

If any step raises (Pydantic ValidationError, protocol violation, etc.),
the test fails — so the SDK's own validation is the oracle.
"""

from __future__ import annotations

import os
import re
import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from tests.fixtures.keyring import install_in_memory_keyring
from tests.fixtures.net import free_port

_FAKE = Path(__file__).resolve().parents[1] / "fixtures" / "fake_mcp_server.py"

_TOKEN = "test-oracle-token"
_HEADERS = {"X-Coffer-Token": _TOKEN}

#: FR-050: the gateway exposes EXACTLY ONE built-in knowledge tool. Upload is
#: not among them — a document enters through a human surface, not an agent's
#: tool call — and neither is any way to READ: an agent reads the files with
#: its own tools at the paths its delivered skill carries.
_KNOWLEDGE_TOOLS = frozenset({"coffer__write"})

#: The five that went with the retrieval surface. Asserted absent by name, so a
#: revival reds this with the name in the message rather than as an anonymous
#: set difference — and so the claim survives someone adding a sixth built-in
#: to an unrelated slice.
_RETIRED_KNOWLEDGE_TOOLS = frozenset(
    {
        "coffer__list",
        "coffer__grep",
        "coffer__read",
        "coffer__search",
        "coffer__delete",
    }
)

#: The rest of the built-in roster, which this test asserts nothing about
#: beyond "it is not knowledge's". Named so the wire assertion below can be an
#: exact one without swallowing a second knowledge tool into a vague
#: superset. `scripts/check_architecture_doc.py` is the gate that owns the full
#: roster and reds when a slice registers a tool the architecture doc never
#: names; here the split is what scopes the claim to one kind.
_NON_KNOWLEDGE_BUILTIN_TOOLS = frozenset(
    {
        "coffer__recall",
        "coffer__diagnose",
        "coffer__search_tools",
    }
)

_APPLICATION_ROOT = Path(__file__).resolve().parents[2] / "coffer" / "application"
#: The same declaration shape `scripts/check_architecture_doc.py` scrapes.
_TOOL_DECL = re.compile(r'BuiltinTool\(\s*name="([a-z_]+)"')


def _tools_declared_under(package: Path) -> set[str]:
    """The `coffer__` tool names declared by the sources under `package`.

    Read off disk rather than trusted from the wire, so "exactly one" is
    pinned at the source too: a second knowledge tool added in
    `application/knowledge/` reds this even before anyone checks whether the
    gateway advertises it.
    """
    return {
        f"coffer__{name}"
        for path in package.rglob("*.py")
        for name in _TOOL_DECL.findall(path.read_text(encoding="utf-8"))
    }


@pytest.fixture
async def running_daemon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Boot an in-process daemon on a random port; yield (port, token, root).

    We use an async fixture so we can await httpx health-checks and the
    REST registration call from within the fixture body. ``root`` is the
    knowledge tree this daemon writes into — it comes back because the layer
    has no read tool any more, so confirming a write means looking at the
    directory. It is read out of the environment rather than guessed from
    ``HOME``: the suite-wide ``_isolated_knowledge_root`` fixture pins it, and
    that is the value the daemon in this process resolves.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    knowledge_root = Path(os.environ["COFFER_KNOWLEDGE_ROOT"])
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    # Port range must not clash with other parallel test processes
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59600")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59649")
    install_in_memory_keyring(monkeypatch)

    port = free_port()

    from coffer.surfaces.http.app import create_app
    from coffer.surfaces.http.auth import set_active_token
    from coffer.surfaces.http.daemon_routes import set_port

    app = create_app()
    set_active_token(_TOKEN)
    set_port(port)

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="error",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=lambda: server.run(), daemon=True)
    thread.start()

    # Wait for the server to be ready (up to 15 s to allow Alembic migrations)
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        pytest.fail(f"daemon did not bind on port {port} within 15 s")

    # Wait for /api/v1/daemon/status to return 200 (Alembic + lifespan done)
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as c:
        for _ in range(60):
            try:
                r = await c.get("/api/v1/daemon/status")
                if r.status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(0.2)
        else:
            server.should_exit = True
            thread.join(timeout=5)
            pytest.fail("daemon /status did not return 200 in time")

        # Re-apply the token (lifespan may have set a different one if daemon.json existed)
        set_active_token(_TOKEN)

        # Register a fake MCP server via the REST API so tools/list has something
        r = await c.post(
            "/api/v1/resources",
            json={
                "kind": "mcp_server",
                "name": "fs",
                "config": {
                    "transport": {
                        "type": "stdio",
                        "command": sys.executable,
                        "args": [
                            str(_FAKE),
                            "--scenario",
                            "basic",
                            "--tools",
                            "read_file",
                            "write_file",
                        ],
                    },
                },
            },
            headers=_HEADERS,
        )
        assert r.status_code == 201, f"resource registration failed: {r.status_code} {r.text}"

    yield port, _TOKEN, knowledge_root

    server.should_exit = True
    thread.join(timeout=10)


@pytest.mark.acceptance(spec="mcp-gateway", scenario="register a stdio MCP server")
@pytest.mark.acceptance(
    spec="knowledge",
    scenario="exactly one built-in knowledge tool appears in the client tool list",
)
@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="Coffer exposes no skill tools over MCP",
)
async def test_sdk_round_trip(running_daemon: tuple[int, str, Path]) -> None:
    """Drive the /mcp endpoint via the mcp SDK; SDK validation is the oracle.

    If ClientSession.initialize(), list_tools(), or call_tool() succeed without
    raising, the wire format is spec-compliant (the SDK validates every field
    through its Pydantic models on parse).
    """
    port, token, knowledge_root = running_daemon

    async def _create_collection(name: str) -> None:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as http:
            r = await http.post(
                "/api/v1/knowledge/collections",
                json={"name": name, "description": "oracle round-trip"},
                headers={"X-Coffer-Token": token},
            )
            assert r.status_code in (201, 409), r.text

    mcp_url = f"http://127.0.0.1:{port}/mcp"
    headers = {"X-Coffer-Token": token}

    async with (
        streamable_http_client(mcp_url, http_client=create_mcp_http_client(headers=headers)) as (
            read,
            write,
        ),
        ClientSession(read, write) as session,
    ):
        # 1. Initialize — SDK validates InitializeResult shape
        init = await session.initialize()
        assert init.server_info.name == "coffer", (
            f"expected server_info.name='coffer', got {init.server_info.name!r}"
        )

        # 2. tools/list — SDK validates ListToolsResult.
        # Upstream tools must appear; Coffer's own built-in tools (coffer__*)
        # also appear in the list — accept any superset that contains the
        # fake upstream's two tools.
        tools_result = await session.list_tools()
        tool_names = {t.name for t in tools_result.tools}
        assert {"fs__read_file", "fs__write_file"}.issubset(tool_names), (
            f"upstream tools missing from list: {tool_names}"
        )
        # TEST22-002: positively assert that Coffer's own built-in tools
        # (coffer__*) appear in the same listing — this is the acceptance
        # scenario "built-in tools appear in client tool list". Without
        # this check the test passed even when the KB tools were missing.
        assert any(n.startswith("coffer__") for n in tool_names), (
            f"no coffer__ built-in tools found in tools/list: {tool_names}"
        )
        # And the knowledge tools specifically. FR-050 says EXACTLY ONE, so
        # this is an equality and not the `issubset` it used to be: a subset
        # check let a second knowledge tool — an agent-callable `upload`, say,
        # which FR-050 rules out by name — ship without anything going red.
        #
        # The knowledge-owned half of the roster is isolated by subtracting the
        # built-ins other slices own, so this asserts about one kind
        # rather than about every built-in Coffer happens to have.
        coffer_tools = {n for n in tool_names if n.startswith("coffer__")}
        # skill-manager FR-031: no skill tool rides the wire. Both supported
        # agent types read skills natively from `<config_dir>/skills/`, where
        # delivery already puts them, and serving the master store over MCP
        # would be a second delivery path with no per-agent scope on it.
        assert not {"coffer__list_skills", "coffer__load_skill"} & coffer_tools, (
            f"skill tools are exposed over MCP: {sorted(coffer_tools)}"
        )
        instructions = init.instructions or ""
        assert not {"list_skills", "load_skill"} & set(instructions.split()), (
            f"the initialize instructions still name a skill tool: {instructions!r}"
        )
        knowledge_on_the_wire = coffer_tools - _NON_KNOWLEDGE_BUILTIN_TOOLS
        assert knowledge_on_the_wire == set(_KNOWLEDGE_TOOLS), (
            f"the knowledge tools in tools/list are not exactly the one FR-050 "
            f"name; unexpected={sorted(knowledge_on_the_wire - _KNOWLEDGE_TOOLS)}; "
            f"missing={sorted(_KNOWLEDGE_TOOLS - knowledge_on_the_wire)}"
        )
        # The five retired names, asserted absent individually. The equality
        # above already implies it; this says which five, so a revival reds
        # with the name rather than with a set difference a reader has to
        # decode.
        assert not (tool_names & _RETIRED_KNOWLEDGE_TOOLS), (
            f"a retired retrieval tool is back on the wire: "
            f"{sorted(tool_names & _RETIRED_KNOWLEDGE_TOOLS)}"
        )
        # Pinned at the source as well as on the wire: a second tool declared
        # in the knowledge slice but not yet registered with the gateway is
        # still a second tool, and a reviewer should see it here.
        declared = _tools_declared_under(_APPLICATION_ROOT / "knowledge")
        assert declared == set(_KNOWLEDGE_TOOLS), (
            f"backend/coffer/application/knowledge declares "
            f"{len(declared)} built-in tool(s), not the one FR-050 allows; "
            f"unexpected={sorted(declared - _KNOWLEDGE_TOOLS)}; "
            f"missing={sorted(_KNOWLEDGE_TOOLS - declared)}"
        )

        # 3. tools/call — SDK validates CallToolResult
        call_result = await session.call_tool(
            "fs__read_file",
            arguments={"path": "/tmp/oracle-test"},
        )
        # Reaching here means the SDK parsed the response without errors.
        assert call_result.content is not None, "expected non-empty content"

        # 4. tools/call of the one coffer__ BUILT-IN end-to-end through the
        # daemon (review gap: builtins were only ever listed, never called over
        # the wire). The collection has to exist first — nothing
        # auto-provisions one (spec knowledge FR-008).
        #
        # There is no read tool left to confirm the write with, which is the
        # point of the redesign, so the confirmation is the file itself: the
        # daemon runs in this process over an isolated HOME, so the collection
        # can be read off disk exactly as the agent's own `Read` would. No
        # internal model is configured here, so the material is promoted to a
        # document on the spot rather than waiting in the inbox (FR-029).
        await _create_collection("oracle")
        write_result = await session.call_tool(
            "coffer__write",
            arguments={
                "title": "Axolotls",
                "description": "an oracle smoke fact",
                "body": "oracle smoke fact about axolotls",
                "collection": "oracle",
            },
        )
        assert not write_result.is_error, write_result.content

        assert "written" in str(write_result.content), write_result.content
        landed = knowledge_root / "oracle" / "axolotls.md"
        assert landed.is_file(), (
            "coffer__write did not become a document in the collection: "
            f"{sorted(p.name for p in landed.parent.iterdir()) if landed.parent.is_dir() else []}"
        )
        assert "oracle smoke fact about axolotls" in landed.read_text(encoding="utf-8")
        # And nothing is left waiting in the inbox behind it.
        inbox = knowledge_root / "oracle" / ".inbox"
        assert not inbox.is_dir() or list(inbox.iterdir()) == []
