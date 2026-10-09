"""What each experimental feature closes beyond its routes, through the real daemon.

Spec experimental-features "Close every surface of a switched-off feature" and
"Withdraw what a switched-off feature put in front of agents", on the shipped
features. Boots ``create_app`` under a throwaway HOME with the fixtures of
``test_feature_gates``.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.infrastructure.daemon import config as daemon_config
from tests.integration.surfaces.http import test_feature_gates as gates
from tests.integration.surfaces.http import test_feature_kind_gates as kind_gates
from tests.support.mcp_wire import INIT_PARAMS

home = gates.home
_client = gates._client
_switch = gates._switch
_assert_disabled = gates._assert_disabled


@pytest.mark.parametrize(
    ("key", "kind"),
    [("knowledge", "knowledge"), ("memory", "memory")],
)
def test_a_kind_an_experimental_feature_owns_is_out_of_reach_while_it_is_off(
    home: pathlib.Path, key: str, kind: str
) -> None:
    daemon_config.write_feature_setting(key, False)
    with _client() as c:
        _assert_disabled(c.get("/api/v1/resources", params={"kind": kind}), key)
        # An unfiltered list leaves its rows out; an always-on kind is untouched.
        listed = c.get("/api/v1/resources").json()["resources"]
        assert all(r["kind"] != kind for r in listed)
        assert c.get("/api/v1/resources", params={"kind": "agent"}).status_code == 200
        assert c.get("/api/v1/resources", params={"kind": "skill"}).status_code == 200
        # The provider kind graduated with models: never out of reach.
        assert c.get("/api/v1/resources", params={"kind": "provider"}).status_code == 200
        # Switching on makes the kind reachable again, without a restart.
        _switch(c, key, True)
        assert c.get("/api/v1/resources", params={"kind": kind}).status_code == 200


def _unknown_call(c: object, name: str) -> bool:
    session = gates._mcp(c, None, "initialize", INIT_PARAMS).headers["mcp-session-id"]  # type: ignore[arg-type]
    unknown = gates._mcp(
        c,  # type: ignore[arg-type]
        session,
        "tools/call",
        {"name": "coffer__nosuchtool", "arguments": {}},
    ).json()
    called = gates._mcp(
        c,  # type: ignore[arg-type]
        session,
        "tools/call",
        {"name": name, "arguments": {}},
    ).json()
    return gates._unknown_as(called, unknown, name)


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="knowledge off leaves coffer__search_tools the only built-in tool",
)
@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="knowledge off leaves memory and channels working",
)
def test_knowledge_off_hides_the_write_tool(home: pathlib.Path) -> None:
    with _client() as c:
        on_tools = {t for t in kind_gates._listed_tools(c) if t.startswith("coffer__")}
        assert on_tools == {"coffer__search_tools"}
        assert "Its knowledge is markdown" in kind_gates._instructions(c)
        # There is no write tool to hide: it is unknown with the feature on, too.
        assert _unknown_call(c, "coffer__write")

        _switch(c, "knowledge", False)
        # Memory and conversations carry on.
        assert c.get("/api/v1/memory/partitions").status_code == 200
        assert c.get("/api/v1/agent-sessions").status_code == 200
        tools = {t for t in kind_gates._listed_tools(c) if t.startswith("coffer__")}
        text = kind_gates._instructions(c)
        assert tools == {"coffer__search_tools"}
        # The handshake names exactly the tools the list carries and says nothing
        # of knowledge; the memory root is still there, memory being on.
        assert kind_gates._named_tools(text) <= tools
        assert "Its knowledge is markdown" not in text
        assert kind_gates._names_memory(text)
        # A call to the withdrawn tool answers as an unknown tool.
        assert _unknown_call(c, "coffer__write")

        _switch(c, "knowledge", True)
        assert "Its knowledge is markdown" in kind_gates._instructions(c)


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="memory off hides the memory root",
)
@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="memory off leaves knowledge and channels working",
)
def test_memory_off_hides_the_memory_root(home: pathlib.Path) -> None:
    with _client() as c:
        assert kind_gates._names_memory(kind_gates._instructions(c))

        _switch(c, "memory", False)
        # Knowledge and conversations carry on.
        assert c.get("/api/v1/knowledge/collections").status_code == 200
        assert c.get("/api/v1/agent-sessions").status_code == 200
        text = kind_gates._instructions(c)
        assert not kind_gates._names_memory(text)
        # Knowledge is its own feature and stays in the handshake.
        assert "Its knowledge is markdown" in text

        _switch(c, "memory", True)
        assert kind_gates._names_memory(kind_gates._instructions(c))


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="knowledge off re-renders the coffer-guide skill without its knowledge sections",
)
def test_knowledge_off_re_renders_the_guide_without_its_knowledge_sections(
    home: pathlib.Path,
) -> None:
    with _client() as c:
        before = kind_gates._guide(home)
        assert "Knowledge is a directory of files" in before
        assert "Tidying a collection" in before

        _switch(c, "knowledge", False)
        off = kind_gates._guide(home)
        assert "Tidying a collection" not in off
        assert "Knowledge is a directory of files" not in off
        assert kind_gates._names_memory(off)
        assert "coffer__search_tools" in off
        assert "<!--" not in off

        _switch(c, "knowledge", True)
        assert kind_gates._guide(home) == before


def test_memory_off_re_renders_the_guide_without_its_memory_sections(
    home: pathlib.Path,
) -> None:
    with _client() as c:
        before = kind_gates._guide(home)
        assert kind_gates._names_memory(before)
        assert "Coffer reads your memory" in before

        _switch(c, "memory", False)
        off = kind_gates._guide(home)
        assert not kind_gates._names_memory(off)
        assert "Coffer reads your memory" not in off
        assert "Knowledge is a directory of files" in off
        assert "<!--" not in off

        _switch(c, "memory", True)
        assert kind_gates._guide(home) == before
