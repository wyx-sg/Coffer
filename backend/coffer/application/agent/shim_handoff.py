"""The prompt that hands a missing ``coffer-mcp-shim`` to an agent (spec
agent-registry "Install Coffer's MCP server into an agent in one action").

Connect writes the shim's absolute path into the agent's MCP config, so it
cannot go ahead while the shim resolves nowhere. That mostly happens on a
source checkout or a half-finished install, and what fixes it depends on how
Coffer got onto this machine — so the refusal carries a hand-off naming the
places Coffer looked, rather than an environment variable to set.
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.domain.handoff import Handoff, render_handoff


def shim_handoff(binary: str, *, public: str, looked_in: Sequence[str]) -> str:
    """The prompt for a shim that resolved in none of ``looked_in``;
    ``public`` is where a deployed Coffer keeps it (``~/.coffer/bin``)."""
    return render_handoff(
        Handoff(
            task=(
                f"Please find or reinstall Coffer's `{binary}` program on this machine, so "
                "Coffer can connect my agent to it."
            ),
            facts=(
                f"`{binary}` is the program an agent starts to reach Coffer; Coffer writes its "
                "path into the agent's MCP settings when I choose Connect.",
                f"An installed Coffer keeps it at {public}.",
                "Coffer looked for it in: " + "; ".join(looked_in) + ", and found it in none.",
            ),
            steps=(
                f"Check whether Coffer is installed here and `{binary}` exists somewhere; if it "
                "does not, reinstall Coffer the way it was installed.",
                f"Make sure it is found at {public} (a link to the real program is fine) or in "
                "one of the places above, and that it is executable.",
                "When it works, tell me to choose Connect again in Coffer.",
            ),
        )
    )


__all__ = ["shim_handoff"]
