"""Kind-agnostic vocabulary: the mark on an agent process Coffer spawned for a
channel turn (spec memory "Deliver to channel turns through the system prompt").

Coffer drives a channel turn itself, through the Agent SDK or ``codex
app-server``, and composes that turn's memory itself: the index in the system
prompt, the notes the prompt names after the prompt. The process it spawns
still loads the agent's own settings, though, so Coffer's installed memory hook
fires inside it too, and without a mark the same index and the same notes would
arrive twice, and be counted twice. The ``chat`` kind sets the mark on the
spawned process's environment; the agent hands its environment to every hook it
runs; the ``memory`` kind's hook reads the mark and leaves the two moments the
turn already carries to the turn. Neither kind may import the other
(import-linter cross-kind contracts), so the name lives here.
"""

from __future__ import annotations

from collections.abc import Mapping

#: Set, to ``"1"``, in the environment of an agent process Coffer spawned to
#: answer a channel turn.
CHANNEL_TURN_ENV = "COFFER_CHANNEL_TURN"


def channel_turn_env(channel_uid: str) -> dict[str, str]:
    """The mark for a turn: set when the conversation is bridged to a channel,
    empty otherwise."""
    return {CHANNEL_TURN_ENV: "1"} if channel_uid else {}


def is_channel_turn(environ: Mapping[str, str]) -> bool:
    """Whether ``environ`` is that of a process Coffer spawned for a channel turn."""
    return environ.get(CHANNEL_TURN_ENV) == "1"


#: Set in the environment of every agent process Coffer spawns for a turn (a
#: Coffer conversation or a channel's): a random token naming the turn. The shim
#: forwards it as the ``X-Coffer-Turn`` header, which is how the gateway knows an
#: MCP session belongs to a turn Coffer runs (spec mcp-gateway "Let an agent ask
#: the owner a question during a Coffer turn"). Kind-agnostic for the same reason
#: as the mark above: the agent kind writes the Codex entry that passes it
#: through, the chat kind sets it, the mcp kind reads the header.
TURN_TOKEN_ENV = "COFFER_TURN_TOKEN"

#: The request header the shim sends it in.
TURN_HEADER = "X-Coffer-Turn"

__all__ = [
    "CHANNEL_TURN_ENV",
    "TURN_HEADER",
    "TURN_TOKEN_ENV",
    "channel_turn_env",
    "is_channel_turn",
]
