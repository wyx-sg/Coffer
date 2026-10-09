"""Kind-agnostic vocabulary for an agent process Coffer spawns for a turn.

The agent kind writes the Codex entry that passes the token through, the chat
kind sets it, the mcp kind reads the header; none of them may import another
(import-linter cross-kind contracts), so the names live here.
"""

from __future__ import annotations

#: Set in the environment of every agent process Coffer spawns for a turn (a
#: Coffer conversation or a channel's): a random token naming the turn. The shim
#: forwards it as the ``X-Coffer-Turn`` header, which is how the gateway knows an
#: MCP session belongs to a turn Coffer runs (spec mcp-gateway "Let an agent ask
#: the owner a question during a Coffer turn").
TURN_TOKEN_ENV = "COFFER_TURN_TOKEN"

#: The request header the shim sends it in.
TURN_HEADER = "X-Coffer-Turn"

__all__ = ["TURN_HEADER", "TURN_TOKEN_ENV"]
