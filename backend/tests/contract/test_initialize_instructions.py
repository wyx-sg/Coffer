"""The ``initialize`` handshake carries Coffer's MCP ``instructions``
(ADR budget-driven-tool-tiering).

This is the only channel a server has into the client's system prompt. Without
it no agent is ever told what Coffer is or that ``coffer__search_tools`` reaches
the tools tiering leaves unlisted — the contract exists but never arrives.
"""

from __future__ import annotations

import pathlib

import pytest

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


def test_instructions_are_never_truncated_to_fit():
    """The cap must be met by writing, not by the builder's final slice.

    ``build_instructions`` ends in ``[:MAX_INSTRUCTIONS_CHARS]``. That is a
    backstop, and a silent one: text grown past the cap would reach the client
    cut mid-sentence, with nothing raised and nothing logged. So assert the
    untruncated text fits — at ``hidden_count=0`` and at a count with more
    digits than any real catalogue will ever produce.
    """
    from coffer.application.mcp.gateway_instructions import _BASE, _TIERED

    assert len(_BASE) <= MAX_INSTRUCTIONS_CHARS
    longest = _BASE + _TIERED.format(n=999_999)
    assert len(longest) <= MAX_INSTRUCTIONS_CHARS, (
        f"instructions are {len(longest)} chars, over the {MAX_INSTRUCTIONS_CHARS} "
        "cap: the builder would silently cut the tail off"
    )
    assert build_instructions(hidden_count=999_999) == longest


def test_instructions_name_the_escape_hatch():
    assert "coffer__search_tools" in build_instructions(hidden_count=70)


def test_instructions_name_every_builtin_tool_even_with_nothing_hidden():
    """All four names, in every session (spec knowledge "Keep the handshake
    instructions to what a skill cannot carry").

    The names are what make the tools recognisable in a tool list, and that is
    not a fact about this session. ``coffer__search_tools`` used to be named
    only inside the tiering paragraph, which ``build_instructions`` omits at
    ``hidden_count=0`` — so a session with nothing hidden was never told the
    escape hatch existed at all.
    """
    from coffer.application.mcp.gateway_instructions import NAMED_TOOLS

    text = build_instructions(hidden_count=0)
    missing = {name for name in NAMED_TOOLS if f"coffer__{name}" not in text}
    assert not missing, f"handshake never names: {sorted(missing)}"


def test_instructions_report_the_hidden_count():
    assert "70" in build_instructions(hidden_count=70)


def test_no_hidden_tools_means_no_misleading_claim():
    """Never tell the agent tools are hidden when none are.

    Naming the escape hatch is unconditional (see the test above); the *claim*
    that something is currently unlisted is what must not appear when nothing
    is. So this asserts the tiering sentence is absent, rather than the tool
    name — an assertion on the name is what kept the name out of the base text.
    """
    from coffer.application.mcp.gateway_instructions import _TIERED

    text = build_instructions(hidden_count=0)
    assert "not listed" not in text
    assert "budgeted slice" not in text
    # Nothing of the tiering paragraph survives, however it is later worded.
    assert not any(
        fragment and fragment in text for fragment in _TIERED.replace("{n}", "\x00").split("\x00")
    )


def test_initialize_result_keeps_the_protocol_contract():
    result = build_initialize_result(hidden_count=0)

    assert result["protocolVersion"] == PROTOCOL_VERSION
    assert result["capabilities"] == SERVER_CAPABILITIES
    assert result["serverInfo"]["name"] == "coffer"
    assert 0 < len(result["instructions"]) <= MAX_INSTRUCTIONS_CHARS


@pytest.mark.acceptance(
    spec="knowledge", scenario="the handshake names Coffer's tools and points at the skill"
)
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
    from coffer.application.memory.builtin_recall_tool import register_recall_tool

    registry = BuiltinToolRegistry()
    register_knowledge_builtin_tools(
        registry,
        knowledge_service=None,  # type: ignore[arg-type]
    )
    register_diagnostics_builtin_tools(
        registry,
        audit_repo=None,  # type: ignore[arg-type]
        log_path=lambda: pathlib.Path("daemon.log"),
    )
    # The defect this line fixes: memory's registrar was never called here, so
    # ``coffer__recall`` was absent from ``available`` and the equality below
    # held only because the instructions did not name it either. A gate that
    # assembles an incomplete registry cannot tell "not advertised" from "does
    # not exist" — it passed for as long as the omission was symmetrical, and
    # recall went unmentioned in the handshake the whole time.
    register_recall_tool(
        registry,
        recall_service=None,  # type: ignore[arg-type]
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


def test_instructions_name_only_the_tools_the_list_carries() -> None:
    """A tool a switched-off feature took out of the list is not advertised
    (spec experimental-features "Withdraw what a switched-off feature put in
    front of agents"), and neither is the knowledge layer without its tool."""
    without_memory = build_instructions(hidden_count=0, tools=["write", "diagnose"])
    assert "coffer__recall" not in without_memory
    assert "coffer__write" in without_memory
    assert "coffer__search_tools" in without_memory

    neither = build_instructions(hidden_count=0, tools=["diagnose"])
    assert "coffer__write" not in neither
    assert "coffer__recall" not in neither
    assert "knowledge" not in neither
    assert "coffer__diagnose" in neither
    assert "coffer__search_tools" in neither
    assert len(build_instructions(hidden_count=999_999, tools=[])) <= MAX_INSTRUCTIONS_CHARS


def test_every_tool_listed_reads_as_the_full_text() -> None:
    from coffer.application.mcp.gateway_instructions import _BASE, NAMED_TOOLS

    assert build_instructions(hidden_count=0, tools=NAMED_TOOLS) == _BASE
    assert build_instructions(hidden_count=0) == _BASE
