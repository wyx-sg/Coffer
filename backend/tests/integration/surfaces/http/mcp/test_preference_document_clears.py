"""Clearing the last entry of one kind in a server's preference document.

Spec mcp-gateway "Toggle individual capabilities" and "Choose how each tool is
exposed". The document holds two lists — tools switched off and tools whose
exposure the person chose. Emptying one while the other still has an entry
must remove it from the file; the vault writer keeps any key a new document
does not name, so the emptied list used to survive and the change read back as
if it had never happened.
"""

from __future__ import annotations

import pytest

from coffer.application.mcp.tool_exposure import exposure_overrides
from coffer.infrastructure.mcp.persistence import MCPCapabilityPreferenceStore
from tests.integration.surfaces.http.mcp.test_page_routes import _stdio, ctx  # noqa: F401
from tests.support.vault_stores import derived_sm

pytestmark = pytest.mark.asyncio


def _exposure(uid: str, tool: str) -> str:
    return f"/api/v1/resources/mcp_server/{uid}/tools/{tool}/exposure"


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="switching the last disabled tool back on holds beside a pin"
)
async def test_the_last_switched_off_tool_comes_back_on_beside_a_pin(ctx):  # noqa: F811
    srv = await ctx.server("smart", _stdio())
    await ctx.tools(srv, "a", "b")
    assert (
        await ctx.client.patch(_exposure(srv.uid, "a"), json={"mode": "listed"})
    ).status_code == 204
    await ctx.prefs.set_enabled(srv.uid, "tool", "b", False)

    back = await ctx.prefs.set_enabled(srv.uid, "tool", "b", True)

    assert back is not None and back.enabled is True
    # A fresh store over the same vault is what a restarted daemon builds.
    reopened = MCPCapabilityPreferenceStore(derived_sm())
    found = await reopened.find(srv.uid, "tool", "b")
    assert found is not None and found.enabled is True
    assert reopened.exposure_for(srv.uid) == {"a": "listed"}


async def test_the_last_pin_clears_beside_a_switched_off_tool(ctx):  # noqa: F811
    srv = await ctx.server("smart", _stdio())
    await ctx.tools(srv, "a", "b")
    await ctx.prefs.set_enabled(srv.uid, "tool", "b", False)
    assert (
        await ctx.client.patch(_exposure(srv.uid, "a"), json={"mode": "listed"})
    ).status_code == 204

    assert (
        await ctx.client.patch(_exposure(srv.uid, "a"), json={"mode": "auto"})
    ).status_code == 204

    reopened = MCPCapabilityPreferenceStore(derived_sm())
    assert reopened.exposure_for(srv.uid) == {}
    assert await exposure_overrides(reopened, [srv]) == {}
    found = await reopened.find(srv.uid, "tool", "b")
    assert found is not None and found.enabled is False
