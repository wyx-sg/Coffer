"""What Coffer tells a client at ``initialize`` (ADR tool-overload-tier-the-list-search-the-rest).

The MCP ``instructions`` field is the only channel a server has into the
client's system prompt, so it is the one place the tiering contract can
actually reach the agent that has to follow it. The tool-retrieval ADR documented that
contract for humans and never delivered it to the agent.

It is charged against every session's context, so it is capped and
deliberately terse — the context it spends must stay far below what tiering
saves. That budget is why this text stopped trying to be the manual: the
``coffer-guide`` skill carries the whole of it — every tool's behaviour, the
read-it-yourself shape of the knowledge layer, and the catalogue of every
document with its path — and a skill body costs a session nothing until a
model reaches for it. So the handshake's job is narrower now: say what Coffer
is, name its tools so they are recognisable when they appear in a tool list,
and point at the skill for everything else.

"Name its tools" means every one the session's tool list carries — all four
while every experimental feature is on, never one a switched-off feature took
out of the list. The escape hatch
``coffer__search_tools`` used to be named only in the tiering paragraph, so a
session with nothing hidden was never told the hatch existed — and a later
session, whose tool list had in fact been trimmed, had no earlier mention to
fall back on. The name is therefore part of the base text; the *claim* that
tools are hidden right now is the only conditional part.

The server-capability declaration lives here too, so ``gateway.py``
keeps the handshake to session bookkeeping and stays under its LOC ceiling.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

MAX_INSTRUCTIONS_CHARS = 800

# MCP server capabilities coffer declares to clients.
SERVER_CAPABILITIES: dict[str, Any] = {
    "tools": {"listChanged": True},
    "resources": {"listChanged": True, "subscribe": False},
    "prompts": {"listChanged": True},
}

PROTOCOL_VERSION = "2025-06-18"

# Every bare tool name this text names. Kept as data so a contract test can
# hold it against the tools actually registered — the instructions are the one
# thing no caller ever validates, so a tool renamed or retired here goes
# unnoticed until an agent calls a name that no longer exists.
NAMED_TOOLS: frozenset[str] = frozenset(
    {
        "write",
        "recall",
        "diagnose",
        "search_tools",
    }
)

#: Each built-in tool's name as the handshake gives it, with its gloss, in the
#: order the text names them. A tool is named only while it is in the tool list
#: — ``coffer__write`` leaves with the ``knowledge`` feature, ``coffer__recall``
#: with ``memory`` (spec experimental-features "Close every surface of a
#: switched-off feature") — and a text naming a tool the gateway then answers
#: as unknown is the one thing this text must never do.
_TOOL_GLOSSES: tuple[tuple[str, str], ...] = (
    ("write", "file a durable fact about this environment"),
    ("recall", "locate Coffer's distilled notes"),
    ("diagnose", "Coffer's own logs"),
    (
        "search_tools",
        "describe an upstream tool you want in plain language; whatever comes "
        "back is callable by name",
    ),
)

_INTRO = (
    "Coffer is this machine's local vault: it aggregates the user's MCP servers "
    "behind one endpoint, holds what this developer has written down, and adds "
    "its own tools — "
)

_PLAIN_INTRO = (
    "Coffer is this machine's local vault: it aggregates the user's MCP servers "
    "behind one endpoint and adds its own tools — "
)

#: The knowledge sentences are said only while the knowledge layer is there
#: (its tool ``coffer__write`` is listed): the skill then carries a catalogue
#: with paths.
_KNOWLEDGE_OUTRO = (
    ". Its knowledge is markdown you read with your own file tools. The "
    "coffer-guide skill is the manual: load it for the catalogue of what is "
    "there, with paths, before asking the developer something they may already "
    "have written down."
)

_PLAIN_OUTRO = ". The coffer-guide skill is the manual: load it before relying on these tools."

_TIERED = (
    " Your tool list is a budgeted slice: {n} further upstream tools are not "
    "listed, and every one is still callable."
)


def _base(tools: Collection[str]) -> str:
    """The unconditional part, naming exactly ``tools`` (bare names)."""
    named = ", ".join(f"coffer__{name} ({gloss})" for name, gloss in _TOOL_GLOSSES if name in tools)
    if "write" in tools:
        return f"{_INTRO}{named}{_KNOWLEDGE_OUTRO}"
    return f"{_PLAIN_INTRO}{named}{_PLAIN_OUTRO}"


#: The text with every built-in listed — what a session with every feature on
#: is told.
_BASE = _base(NAMED_TOOLS)


def build_instructions(*, hidden_count: int, tools: Collection[str] | None = None) -> str:
    """Build the per-session instructions text.

    ``tools`` is the bare names of the built-ins the session's tool list
    carries right now (``coffer__search_tools`` is always among them, being
    the gateway's own); ``None`` means all of them. The text names only those,
    so a tool whose experimental feature is switched off is never advertised.

    ``hidden_count`` is the number of upstream tools the last ``tools/list``
    left unlisted. At 0 nothing is hidden, so the tiering paragraph is omitted
    rather than making a claim that is not true for this session. The base text
    still names ``coffer__search_tools``: knowing the escape hatch exists is
    unconditional, while "N tools are hidden" is a fact about this session.

    The final slice is a backstop against a malformed handshake, not the way
    the cap is met: truncating here would drop the tail of a sentence into the
    client's system prompt and say nothing about it, so the text is written to
    fit and a contract test asserts that it does, at both a 0 and an
    implausibly large ``hidden_count``.
    """
    text = _BASE if tools is None else _base({*tools, "search_tools"})
    if hidden_count > 0:
        text += _TIERED.format(n=hidden_count)
    return text[:MAX_INSTRUCTIONS_CHARS]


def build_initialize_result(
    *, hidden_count: int, tools: Collection[str] | None = None
) -> dict[str, Any]:
    """The ``initialize`` response body. ``tools`` as for :func:`build_instructions`."""
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": SERVER_CAPABILITIES,
        "serverInfo": {"name": "coffer", "version": "0.1.0"},
        "instructions": build_instructions(hidden_count=hidden_count, tools=tools),
    }


__all__ = [
    "MAX_INSTRUCTIONS_CHARS",
    "NAMED_TOOLS",
    "PROTOCOL_VERSION",
    "SERVER_CAPABILITIES",
    "build_initialize_result",
    "build_instructions",
]
