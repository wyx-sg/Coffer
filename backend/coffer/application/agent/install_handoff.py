"""The prompts that hand installing an agent's program to the person's agent
(spec agent-registry "Hand installing an agent's program to an agent"; spec
web-ui "Hand installing an agent to the person when none is found").

Installing an agent depends on the machine, so Coffer names no installer and
no package manager. It writes the chore up as a hand-off (``domain/handoff.py``)
from what it knows: which agent, this machine, the settings folder to keep, the
program Coffer looks for and the ``PATH`` it looks on. Two prompts:

* :func:`agent_install_handoff` — while no supported type is installed, one
  prompt offering either (Overview's first run, a conversation with no agent);
* :func:`agent_program_handoff` — one type whose program is not found
  (``config_only`` or ``missing``): install it, or reinstall it beside the
  folder it left behind.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.domain.agent.descriptor import descriptor_for
from coffer.domain.agent.detection import DetectionState
from coffer.domain.agent.types import AgentType
from coffer.domain.handoff import Handoff, render_handoff

if TYPE_CHECKING:
    from coffer.application.agent.auto_detect import AgentTypeDetection


@dataclass(frozen=True)
class MachineFacts:
    """What every install prompt says about this machine."""

    #: The OS and architecture, e.g. ``"macOS 15.6, arm64"``.
    machine: str
    #: The ``PATH`` Coffer looks an agent's program up on (the login shell's
    #: entries merged with the daemon's own).
    lookup_path: str


def _machine_facts(facts: MachineFacts) -> tuple[str, ...]:
    return (
        f"This machine: {facts.machine}.",
        f"Coffer looks for programs on this PATH: {facts.lookup_path}",
    )


def _come_back(verb: str) -> str:
    return f"When it works, tell me to come back to Coffer and choose {verb}."


def agent_install_handoff(rows: Sequence[AgentTypeDetection], facts: MachineFacts) -> str | None:
    """The install prompt while no supported type is installed; ``None`` once one is."""
    if not rows or any(row.state.installed for row in rows):
        return None
    names = [row.display_name for row in rows]
    either = " or ".join(names)
    return render_handoff(
        Handoff(
            task=f"Please install {either} on this machine, so Coffer can connect it.",
            facts=(
                "Coffer supports these agents: "
                + "; ".join(
                    f"{row.display_name} (program `{descriptor_for(row.type).program}`, "
                    f"its settings live in {row.standard_config_dir})"
                    for row in rows
                )
                + ".",
                "None of them was found on this machine.",
                *_machine_facts(facts),
            ),
            steps=(
                "Ask me which one I want if I have not said, then choose the install method "
                "that fits this machine.",
                "Make sure its program is found in one of the PATH directories above, and "
                "confirm it runs with `<program> --version`.",
                "If a settings folder above already exists, keep it and everything in it.",
                "Leave signing in to the agent to me.",
                _come_back("Scan again on the Overview"),
            ),
        )
    )


def agent_program_handoff(
    agent_type: AgentType,
    *,
    config_dir: str,
    state: DetectionState,
    registered: bool,
    facts: MachineFacts,
) -> str | None:
    """The prompt that installs (or reinstalls) one type's program; ``None``
    while its program is found."""
    if state.installed:
        return None
    descriptor = descriptor_for(agent_type)
    name, program = descriptor.display_name, descriptor.program
    left_behind = state is DetectionState.CONFIG_ONLY
    verb = "reinstall" if left_behind or registered else "install"
    if left_behind:
        folder = (
            f"Its settings folder {config_dir} already exists; keep it and everything in "
            "it, so my settings carry over."
        )
    elif registered:
        folder = (
            f"Coffer has it registered at {config_dir}, which is not there any more; "
            f"{name} creates it again on its first run."
        )
    else:
        folder = f"{name} keeps its settings in {config_dir}; it creates that folder on first run."
    return render_handoff(
        Handoff(
            task=f"Please {verb} {name} on this machine, so Coffer can connect it.",
            facts=(
                f"Coffer finds {name} by its program `{program}`, which is not on the PATH below.",
                folder,
                *_machine_facts(facts),
            ),
            steps=(
                "Choose the install method that fits this machine.",
                f"Make sure `{program}` is found in one of the PATH directories above, then "
                f"confirm it runs with `{program} --version`.",
                f"Leave signing in to {name} to me.",
                _come_back("Check again"),
            ),
        )
    )


__all__ = ["MachineFacts", "agent_install_handoff", "agent_program_handoff"]
