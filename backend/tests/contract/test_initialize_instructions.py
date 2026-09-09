"""The ``initialize`` handshake carries Coffer's MCP ``instructions`` (ADR-046).

This is the only channel a server has into the client's system prompt. Without
it no agent is ever told what Coffer is or that ``coffer__search_tools`` reaches
the tools tiering leaves unlisted — the contract exists but never arrives.
"""

from __future__ import annotations

from coffer.application.mcp.gateway_instructions import (
    MAX_INSTRUCTIONS_CHARS,
    PROTOCOL_VERSION,
    SERVER_CAPABILITIES,
    build_initialize_result,
    build_instructions,
)


def test_instructions_fit_the_system_prompt_budget():
    # It lands in every session's system prompt; ADR-046 caps it so the context
    # it spends stays far below what tiering saves.
    assert len(build_instructions(hidden_count=0)) <= MAX_INSTRUCTIONS_CHARS
    assert len(build_instructions(hidden_count=999_999)) <= MAX_INSTRUCTIONS_CHARS


def test_instructions_name_the_escape_hatch():
    assert "coffer__search_tools" in build_instructions(hidden_count=70)


def test_instructions_report_the_hidden_count():
    assert "70" in build_instructions(hidden_count=70)


def test_no_hidden_tools_means_no_misleading_claim():
    """Never tell the agent tools are hidden when none are."""
    text = build_instructions(hidden_count=0)
    assert "not listed" not in text
    assert "search_tools" not in text


def test_initialize_result_keeps_the_protocol_contract():
    result = build_initialize_result(hidden_count=0)

    assert result["protocolVersion"] == PROTOCOL_VERSION
    assert result["capabilities"] == SERVER_CAPABILITIES
    assert result["serverInfo"]["name"] == "coffer"
    assert 0 < len(result["instructions"]) <= MAX_INSTRUCTIONS_CHARS
