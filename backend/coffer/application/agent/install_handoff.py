"""The prompt that hands installing an agent to the person (spec web-ui "Hand
installing an agent to the person when none is found").

With no supported agent installed on this machine there is nothing Coffer can
connect, and installing one depends on the machine — so Coffer does not name an
installer or a package manager. It writes the chore up as a hand-off
(``domain/handoff.py``) for the person to paste into whatever assistant they
use. There is no agent of Coffer's to ask, which is why the web UI offers this
prompt to copy only.
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.application.agent.auto_detect import AgentTypeDetection
from coffer.domain.handoff import Handoff, render_handoff


def agent_install_handoff(rows: Sequence[AgentTypeDetection]) -> str | None:
    """The install prompt while no supported type is installed; ``None`` once one is."""
    if not rows or any(row.state.installed for row in rows):
        return None
    names = [row.display_name for row in rows]
    either = " or ".join(names)
    return render_handoff(
        Handoff(
            task=f"Please install {either} on this Mac, so Coffer can connect it.",
            facts=(
                "Coffer supports these agents: "
                + "; ".join(
                    f"{row.display_name} (its settings live in {row.standard_config_dir})"
                    for row in rows
                )
                + ".",
                "None of them was found on this Mac.",
            ),
            steps=(
                "Ask me which one I want if I have not said, then install it the way its "
                "maker recommends for this machine.",
                "Run it once so it creates its settings folder, and confirm it starts.",
                "Then tell me to open Coffer's Overview and choose Scan again.",
            ),
        )
    )


__all__ = ["agent_install_handoff"]
