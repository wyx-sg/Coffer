"""The ``initialize`` handshake carries Coffer's MCP ``instructions``
(ADR budget-driven-tool-tiering).

This is the only channel a server has into the client's system prompt. Without
it no agent is ever told what Coffer is or that ``coffer__search_tools`` reaches
the tools tiering leaves unlisted — the contract exists but never arrives.
"""

from __future__ import annotations

import pathlib

from coffer.application.mcp.gateway_instructions import (
    MAX_INSTRUCTIONS_CHARS,
    PROTOCOL_VERSION,
    SERVER_CAPABILITIES,
    build_initialize_result,
    build_instructions,
)


def test_instructions_fit_the_system_prompt_budget():
    # It lands in every session's system prompt; tool tiering caps it so the context
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


def test_instructions_only_name_tools_that_exist() -> None:
    """Every tool the handshake advertises must actually be registered.

    Nothing else validates this text: it is written into the client's system
    prompt and never called against, so a tool that is renamed or retired
    leaves the instructions telling every agent to call a name the gateway no
    longer answers. That is exactly what happened when the knowledge layer
    replaced ``recall`` / ``remember`` / ``search_knowledge`` / ``ask``.
    """
    from coffer.application.builtin_tools import BuiltinToolRegistry
    from coffer.application.diagnostics import register_diagnostics_builtin_tools
    from coffer.application.knowledge.builtin_tools import register_knowledge_builtin_tools
    from coffer.application.mcp.gateway_instructions import NAMED_TOOLS
    from coffer.application.skill.builtin_tools import register_skill_builtin_tools

    registry = BuiltinToolRegistry()
    register_knowledge_builtin_tools(
        registry,
        knowledge_service=None,  # type: ignore[arg-type]
    )
    register_skill_builtin_tools(
        registry,
        resources=None,  # type: ignore[arg-type]
        skill_service=None,  # type: ignore[arg-type]
    )
    register_diagnostics_builtin_tools(
        registry,
        audit_repo=None,  # type: ignore[arg-type]
        log_path=lambda: pathlib.Path("daemon.log"),
    )
    # ``search_tools`` is answered by the gateway itself rather than the
    # registry, so it is the one name that is legitimately not in there.
    available = {tool.name for tool in registry.list()} | {"search_tools"}

    assert available == NAMED_TOOLS, (
        f"instructions name unregistered tools: {sorted(NAMED_TOOLS - available)}; "
        f"registered tools the instructions never name: {sorted(available - NAMED_TOOLS)}"
    )

    text = build_instructions(hidden_count=70)
    named_in_text = {name for name in NAMED_TOOLS if name in text}
    assert named_in_text == NAMED_TOOLS, (
        f"NAMED_TOOLS lists tools the text does not name: {NAMED_TOOLS - named_in_text}"
    )
