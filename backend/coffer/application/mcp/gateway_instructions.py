"""What Coffer tells a client at ``initialize`` (ADR-046).

The MCP ``instructions`` field is the only channel a server has into the
client's system prompt, so it is the one place the tiering contract can
actually reach the agent that has to follow it. ADR-018 documented that
contract for humans and never delivered it to the agent.

It is charged against every session's context, so it is capped and
deliberately terse — the context it spends must stay far below what tiering
saves. The server-capability declaration lives here too, so ``gateway.py``
keeps the handshake to session bookkeeping and stays under its LOC ceiling.
"""

from __future__ import annotations

from typing import Any

MAX_INSTRUCTIONS_CHARS = 800

# MCP server capabilities coffer declares to clients.
SERVER_CAPABILITIES: dict[str, Any] = {
    "tools": {"listChanged": True},
    "resources": {"listChanged": True, "subscribe": False},
    "prompts": {"listChanged": True},
}

PROTOCOL_VERSION = "2025-06-18"

_BASE = (
    "Coffer is this machine's local vault: it aggregates the user's MCP servers "
    "behind one endpoint and adds its own coffer__* tools for memory (recall, "
    "remember), knowledge (search_knowledge, ask) and skills (list_skills, "
    "load_skill). Prefer coffer__recall before asking the user something they "
    "may have already told Coffer."
)

_TIERED = (
    " The tools listed here are the ones most used on this machine; {n} further "
    "upstream tools are not listed. Call coffer__search_tools with a plain-language "
    "description of what you need to find them — it searches the full catalogue, "
    "and anything it returns is callable by name straight away."
)


def build_instructions(*, hidden_count: int) -> str:
    """Build the per-session instructions text.

    ``hidden_count`` is the number of upstream tools the last ``tools/list``
    left unlisted. At 0 nothing is hidden, so the tiering paragraph is omitted
    rather than making a claim that is not true for this session.
    """
    text = _BASE
    if hidden_count > 0:
        text += _TIERED.format(n=hidden_count)
    return text[:MAX_INSTRUCTIONS_CHARS]


def build_initialize_result(*, hidden_count: int) -> dict[str, Any]:
    """The ``initialize`` response body."""
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": SERVER_CAPABILITIES,
        "serverInfo": {"name": "coffer", "version": "0.1.0"},
        "instructions": build_instructions(hidden_count=hidden_count),
    }


__all__ = [
    "MAX_INSTRUCTIONS_CHARS",
    "PROTOCOL_VERSION",
    "SERVER_CAPABILITIES",
    "build_initialize_result",
    "build_instructions",
]
