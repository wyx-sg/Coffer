"""Unit tests for the aggregate list fan-out (gateway_aggregate_lists).

The fan-out's contract is isolation: one broken upstream must never take
down the whole aggregate list (and with it every chat turn that builds its
tool set from tools/list).
"""

from __future__ import annotations

import pytest

from coffer.application.mcp.discovery import DiscoveredTool
from coffer.application.mcp.gateway_aggregate_lists import list_tools_across
from coffer.domain.errors import CredentialLocked, CredentialMissing


def _tool(server: str, name: str) -> DiscoveredTool:
    return DiscoveredTool(
        prefixed_name=f"{server}__{name}",
        original_name=name,
        description=None,
        input_schema={},
        enabled=True,
    )


class _FakeDiscovery:
    """Maps server name -> list of tools, or an exception to raise."""

    def __init__(self, behaviour: dict[str, list[DiscoveredTool] | Exception]) -> None:
        self._behaviour = behaviour

    async def list_tools(self, server: str) -> list[DiscoveredTool]:
        out = self._behaviour[server]
        if isinstance(out, Exception):
            raise out
        return out


async def _noop_subscribe(server: str) -> None:
    return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        CredentialLocked("keychain is locked: (-128, 'Keychain Access Denied')"),
        CredentialMissing("confluence.API_TOKEN"),
    ],
    ids=["locked", "missing"],
)
async def test_credential_failure_on_one_server_is_dropped_not_fatal(
    error: Exception,
) -> None:
    """A server whose credentials can't be resolved is dropped from the
    aggregate, exactly like a dead or timed-out upstream — the other
    servers' tools still come back."""
    discovery = _FakeDiscovery(
        {
            "good": [_tool("good", "read_file")],
            "broken": error,
        }
    )

    result = await list_tools_across(discovery, _noop_subscribe, ["good", "broken"])  # type: ignore[arg-type]

    names = {t["name"] for t in result["tools"]}
    assert names == {"good__read_file"}
