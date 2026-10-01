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
say in one line each where its memory notes and its own logs are read, and
point at the skill for everything else (spec knowledge "Keep the handshake
instructions to what a skill cannot carry").

"Name its tools" means every one the session's tool list carries, never one a
switched-off experimental feature took out of the list. Coffer has no tool for
its memory notes or its own logs, so the text names where those are instead:
the memory root to search and the ``coffer log`` readers. The escape hatch
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

from coffer import __version__

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
NAMED_TOOLS: frozenset[str] = frozenset({"write", "search_tools"})

#: Each built-in tool's name as the handshake gives it, with its gloss, in the
#: order the text names them. A tool is named only while it is in the tool list
#: — a tool an experimental feature owns leaves with it (spec
#: experimental-features "Close every surface of a switched-off feature") —
#: and a text naming a tool the gateway then answers as unknown is the one
#: thing this text must never do.
_TOOL_GLOSSES: tuple[tuple[str, str], ...] = (
    ("write", "file a durable fact"),
    ("search_tools", "describe an upstream tool you need; results are callable by name"),
)

_INTRO = (
    "Coffer is this machine's local vault: it aggregates the user's MCP servers "
    "behind one endpoint, holds what this developer wrote down, and adds "
)

_KNOWLEDGE = " Its knowledge is markdown you read with your own file tools."

#: There is no memory tool, so the directory is the whole of what an agent
#: needs (spec memory "Expose no memory tool and name the memory root at
#: session start").
_MEMORY = " Its memory notes are Markdown under {root}/*/notes/; grep them with your own tools."

#: Coffer's own records have no tool either; the command line reads them.
_LOGS = " Its own logs: coffer log audit|mcp|daemon (files: coffer path logs)."

_OUTRO = (
    " The coffer-guide skill is the manual: load it for the catalogue, with "
    "paths, before asking the developer something they may have written down."
)

_TIERED = " Your tool list is a budgeted slice: {n} more upstream tools are unlisted, all callable."

#: The memory line for a root too long to fit the cap, or one not known: it
#: names where the root is printed instead of the root itself, so the cap is
#: met by a shorter sentence rather than by truncating the tail of the text.
_MEMORY_BY_COMMAND = (
    " Its memory notes are Markdown under the directory coffer path memory prints; "
    "grep it with your own tools."
)


def _base(tools: Collection[str], memory_line: str) -> str:
    """The unconditional part, naming exactly ``tools`` (bare names), with
    ``memory_line``."""
    glosses = [(name, gloss) for name, gloss in _TOOL_GLOSSES if name in tools]
    named = ", ".join(f"coffer__{name} ({gloss})" for name, gloss in glosses)
    own = "its own tools" if len(glosses) > 1 else "its own tool"
    return f"{_INTRO}{own}: {named}.{_KNOWLEDGE}{memory_line}{_LOGS}{_OUTRO}"


def build_instructions(
    *,
    hidden_count: int,
    tools: Collection[str] | None = None,
    memory_root: str | None = None,
) -> str:
    """Build the per-session instructions text.

    ``tools`` is the bare names of the built-ins the session's tool list
    carries right now (``coffer__search_tools`` is always among them, being
    the gateway's own); ``None`` means all of them. The text names only those,
    so a tool whose experimental feature is switched off is never advertised.
    ``memory_root`` is the absolute memory root, or ``None`` when no memory
    root was registered — the text then names the command that prints it.

    ``hidden_count`` is the number of upstream tools the last ``tools/list``
    left unlisted. At 0 nothing is hidden, so the tiering paragraph is omitted
    rather than making a claim that is not true for this session. The base text
    still names ``coffer__search_tools``: knowing the escape hatch exists is
    unconditional, while "N tools are hidden" is a fact about this session.

    The final slice is a backstop against a malformed handshake, not the way
    the cap is met: truncating here would drop the tail of a sentence into the
    client's system prompt and say nothing about it, so the text is written to
    fit and a contract test asserts that it does, at both a 0 and an
    implausibly large ``hidden_count``, with a long memory root.
    """
    named = NAMED_TOOLS if tools is None else {*tools, "search_tools"}
    tiered = _TIERED.format(n=hidden_count) if hidden_count > 0 else ""
    by_root = _MEMORY.format(root=memory_root) if memory_root else _MEMORY_BY_COMMAND
    text = _base(named, by_root) + tiered
    if len(text) > MAX_INSTRUCTIONS_CHARS:
        text = _base(named, _MEMORY_BY_COMMAND) + tiered
    return text[:MAX_INSTRUCTIONS_CHARS]


def build_initialize_result(
    *,
    hidden_count: int,
    tools: Collection[str] | None = None,
    memory_root: str | None = None,
) -> dict[str, Any]:
    """The ``initialize`` response body. Arguments as for :func:`build_instructions`."""
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": SERVER_CAPABILITIES,
        "serverInfo": {"name": "coffer", "version": __version__},
        "instructions": build_instructions(
            hidden_count=hidden_count, tools=tools, memory_root=memory_root
        ),
    }


__all__ = [
    "MAX_INSTRUCTIONS_CHARS",
    "NAMED_TOOLS",
    "PROTOCOL_VERSION",
    "SERVER_CAPABILITIES",
    "build_initialize_result",
    "build_instructions",
]
