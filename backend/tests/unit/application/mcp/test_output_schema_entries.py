"""Unit: ``outputSchema`` is threaded through the tool list entry, the search
entry and discovery's view of an upstream tool; absent means no key at all."""

from __future__ import annotations

from coffer.application.mcp.discovery import DiscoveredTool
from coffer.application.mcp.gateway_aggregate_lists import _tool_entry
from coffer.application.mcp.gateway_tool_search import _result_entry

_SCHEMA = {"type": "object", "properties": {"n": {"type": "integer"}}}


def _tool(output_schema):
    return DiscoveredTool(
        prefixed_name="s__t",
        original_name="t",
        description="d",
        input_schema={"type": "object"},
        enabled=True,
        output_schema=output_schema,
    )


def test_list_entry_carries_output_schema():
    assert _tool_entry(_tool(_SCHEMA))["outputSchema"] == _SCHEMA


def test_list_entry_without_output_schema_is_unchanged():
    assert _tool_entry(_tool(None)) == {
        "name": "s__t",
        "description": "d",
        "inputSchema": {"type": "object"},
    }


def test_search_entry_carries_output_schema_only_when_listed():
    with_schema = {"name": "s__t", "description": "d", "inputSchema": {}, "outputSchema": _SCHEMA}
    assert _result_entry(with_schema, 1.0, {})["outputSchema"] == _SCHEMA
    without = {"name": "s__t", "description": "d", "inputSchema": {}}
    assert "outputSchema" not in _result_entry(without, 1.0, {})
