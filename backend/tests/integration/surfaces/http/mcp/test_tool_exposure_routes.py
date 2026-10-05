"""PATCH a tool's exposure, one or many: persistence, the tiering read that
reports it, the gateway-facing overrides, and the audit entry (spec mcp-gateway
"Choose how each tool is exposed")."""

from __future__ import annotations

import pytest

from coffer.application.mcp.tool_exposure import exposure_overrides
from coffer.infrastructure.mcp.persistence import MCPCapabilityPreferenceStore
from tests.integration.surfaces.http.mcp.test_page_routes import _stdio, ctx  # noqa: F401
from tests.support.vault_stores import derived_sm

pytestmark = pytest.mark.asyncio


def _url(uid: str, tool: str | None = None) -> str:
    base = f"/api/v1/resources/mcp_server/{uid}/tools"
    return f"{base}/{tool}/exposure" if tool else f"{base}/exposure"


async def _tiering(ctx, uid: str) -> dict:  # noqa: F811
    return (await ctx.client.get(f"/api/v1/resources/mcp_server/{uid}/tiering")).json()


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a tool's exposure is chosen by the person")
async def test_patch_one_tool_pins_it_and_the_tiering_read_says_so(ctx, monkeypatch):  # noqa: F811
    monkeypatch.setenv("COFFER_TOOL_TIERING_BUDGET", "2")
    srv = await ctx.server("smart", _stdio())
    await ctx.tools(srv, "a", "b", "c")
    await ctx.call(srv.uid, "b")

    r = await ctx.client.patch(_url(srv.uid, "c"), json={"mode": "listed"})
    assert r.status_code == 204

    by_tool = {t["tool"]: t for t in (await _tiering(ctx, srv.uid))["tools"]}
    assert by_tool["c"] | {} == {
        "tool": "c",
        "mode": "listed",
        "effective": "listed",
        "reason": "pinned",
    }
    assert by_tool["b"]["mode"] == "auto" and by_tool["b"]["effective"] == "listed"
    assert by_tool["a"]["effective"] == "search" and by_tool["a"]["reason"] == "low_use"


async def test_patch_batch_sets_many_and_auto_clears(ctx):  # noqa: F811
    srv = await ctx.server("smart", _stdio())
    await ctx.tools(srv, "a", "b", "c")

    r = await ctx.client.patch(_url(srv.uid), json={"tools": ["a", "b"], "mode": "search"})
    assert r.status_code == 204
    assert ctx.prefs.exposure_for(srv.uid) == {"a": "search", "b": "search"}

    await ctx.client.patch(_url(srv.uid), json={"tools": ["a"], "mode": "auto"})
    assert ctx.prefs.exposure_for(srv.uid) == {"b": "search"}


async def test_an_unknown_tool_changes_nothing(ctx):  # noqa: F811
    srv = await ctx.server("smart", _stdio())
    await ctx.tools(srv, "a")

    one = await ctx.client.patch(_url(srv.uid, "ghost"), json={"mode": "search"})
    batch = await ctx.client.patch(_url(srv.uid), json={"tools": ["a", "ghost"], "mode": "search"})

    assert one.status_code == 404 and batch.status_code == 404
    assert ctx.prefs.exposure_for(srv.uid) == {}


async def test_a_bad_mode_is_refused(ctx):  # noqa: F811
    srv = await ctx.server("smart", _stdio())
    await ctx.tools(srv, "a")

    assert (await ctx.client.patch(_url(srv.uid, "a"), json={"mode": "pinned"})).status_code == 422


async def test_the_override_survives_a_restart_and_a_switch_toggle(ctx):  # noqa: F811
    srv = await ctx.server("smart", _stdio())
    await ctx.tools(srv, "a", "b")
    await ctx.client.patch(_url(srv.uid, "a"), json={"mode": "search"})

    # Turning the tool off and on again leaves the exposure alone.
    await ctx.prefs.set_enabled(srv.uid, "tool", "a", False)
    await ctx.prefs.set_enabled(srv.uid, "tool", "a", True)
    # A fresh store over the same vault is what a restarted daemon builds.
    reopened = MCPCapabilityPreferenceStore(derived_sm())

    assert reopened.exposure_for(srv.uid) == {"a": "search"}
    assert await exposure_overrides(reopened, [srv]) == {"smart__a": "search"}


async def test_the_change_is_audited(ctx):  # noqa: F811
    srv = await ctx.server("smart", _stdio())
    await ctx.tools(srv, "a", "b")

    await ctx.client.patch(_url(srv.uid), json={"tools": ["a", "b"], "mode": "listed"})

    rows = await ctx.audit.query(event_type="tool_exposure_changed")
    assert len(rows) == 1
    assert rows[0].details["key"] == "2 tools" and rows[0].details["mode"] == "listed"


def _group(*tools: str, off: tuple[str, ...] = ()) -> dict:
    return {
        "transport": {
            "type": "http_api",
            "base_url": "https://billing.example/v1",
            "tools": [
                {"name": t, "method": "GET", "path": f"/{t}", "enabled": t not in off}
                for t in tools
            ],
        }
    }


async def test_a_custom_tool_groups_tools_take_an_exposure_before_any_agent_listed_them(ctx):  # noqa: F811
    """A group's tools are its config: no discovery has to have seen them first."""
    group = await ctx.server("billing", _group("list_invoices", "refund", off=("refund",)))

    r = await ctx.client.patch(_url(group.uid, "list_invoices"), json={"mode": "search"})
    assert r.status_code == 204
    assert ctx.prefs.exposure_for(group.uid) == {"list_invoices": "search"}
    assert await exposure_overrides(ctx.prefs, [group]) == {"billing__list_invoices": "search"}

    split = await _tiering(ctx, group.uid)
    assert split["tool_count"] == 2
    by_tool = {t["tool"]: t for t in split["tools"]}
    assert by_tool["list_invoices"]["mode"] == "search"
    assert by_tool["list_invoices"]["effective"] == "search"
    assert by_tool["list_invoices"]["reason"] == "search_only"
    # A switched-off tool is offered to no agent, so it has no exposure to report.
    assert "refund" not in by_tool

    ghost = await ctx.client.patch(_url(group.uid, "ghost"), json={"mode": "listed"})
    assert ghost.status_code == 404
    rows = await ctx.audit.query(event_type="tool_exposure_changed")
    assert [r.details["key"] for r in rows] == ["list_invoices"]
