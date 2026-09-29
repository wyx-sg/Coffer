"""Every tool and prompt row of the capabilities read carries the length of the
name a client shows for it (spec mcp-gateway "Flag tools whose client-visible
name is too long").

This is the backend half of the flag: the field, computed the same way on the
live read and on the cached one. The Tools tab and ``coffer mcp cap list`` flag
a row from it; nothing here disables, renames or hides a tool.
"""

from __future__ import annotations

import pytest

from coffer.application.mcp.discovery import DiscoveredPrompt, DiscoveredTool
from coffer.domain.mcp.namespace import client_name_length, prefix_prompt, prefix_tool
from coffer.surfaces.http.mcp.capability_views import live_capability_list

SERVER = "docs"
#: ``mcp__coffer__docs__`` is 19 characters, so these give 70 and 40.
LONG_TOOL = "t" * (70 - 19)
SHORT_TOOL = "s" * (40 - 19)


def _tool(name: str) -> DiscoveredTool:
    return DiscoveredTool(
        prefixed_name=prefix_tool(SERVER, name),
        original_name=name,
        description=None,
        input_schema={},
        enabled=True,
    )


def test_the_length_is_that_of_the_name_a_client_shows() -> None:
    assert client_name_length("docs__search") == len("mcp__coffer__docs__search")


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a tool with an over-long client-visible name is flagged"
)
def test_every_tool_row_carries_its_client_name_length() -> None:
    out = live_capability_list(
        SERVER,
        [_tool(LONG_TOOL), _tool(SHORT_TOOL)],
        [],
        [
            DiscoveredPrompt(
                prefixed_name=prefix_prompt(SERVER, "summarise"),
                original_name="summarise",
                description=None,
                arguments=[],
                enabled=True,
            )
        ],
    )
    by_name = {t.original_name: t for t in out.tools}
    assert by_name[LONG_TOOL].client_name_length == 70
    assert by_name[SHORT_TOOL].client_name_length == 40
    # The flag is information: both tools stay enabled, under their usual names.
    assert by_name[LONG_TOOL].enabled and by_name[SHORT_TOOL].enabled
    assert by_name[LONG_TOOL].prefixed_name == f"{SERVER}__{LONG_TOOL}"
    # Prompts are named on the same wire and carry the same field.
    assert out.prompts[0].client_name_length == len("mcp__coffer__docs__summarise")
    # And it is on the wire, where the Tools tab and the CLI read it.
    assert out.model_dump(mode="json")["tools"][0]["client_name_length"] == 70
