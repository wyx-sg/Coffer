"""The hand-off that upgrades Coffer on this machine (spec daemon "Hand an
upgrade of Coffer to an agent").

In the desktop app the shell checks for and installs updates itself. A browser
has nothing to install with — a page the daemon serves cannot replace the
daemon — and how Coffer is upgraded depends on how it was installed: the
installer's frozen binaries, the desktop app, or a source checkout. So the
Settings > About page hands the upgrade to the person's agent, with the facts
that pick the way: the running version and channel, how this copy was
installed and where, and the machine. The install page's Upgrade section is
the procedure the agent follows; ``domain/handoff.py`` adds the standing rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from coffer.domain.handoff import Handoff, render_handoff

#: The docs site's install page; its ``#upgrade`` section is the procedure.
INSTALL_PAGE = "https://wyx-sg.github.io/Coffer/start/install"


class InstallMethod(StrEnum):
    #: The installer's (or a release archive's) frozen binaries.
    BINARIES = "binaries"
    #: The macOS desktop app bundle.
    APP = "app"
    #: Run from a source checkout.
    SOURCE = "source"


@dataclass(frozen=True)
class InstallFacts:
    method: InstallMethod
    #: The running daemon's executable (a frozen binary, or the interpreter).
    executable: str
    #: The source checkout's root; ``None`` unless run from source in one.
    checkout: str | None = None


def _method_fact(install: InstallFacts) -> str:
    if install.method is InstallMethod.APP:
        return (
            f"It was installed as the macOS desktop app; the daemon runs from {install.executable}."
        )
    if install.method is InstallMethod.SOURCE:
        where = f"the source checkout at {install.checkout}" if install.checkout else "source"
        return f"It runs from {where}, with the interpreter {install.executable}."
    return (
        f"It was installed from the frozen binaries; the daemon runs from {install.executable} "
        "(the installer keeps them under ~/.coffer/bin)."
    )


def upgrade_handoff(version: str, channel: str, install: InstallFacts, machine: str) -> str:
    """The prompt that upgrades this Coffer the way it was installed."""
    return render_handoff(
        Handoff(
            task="Please upgrade Coffer on this machine to the latest release.",
            facts=(
                f"Running now: Coffer {version}, on the {channel} channel.",
                _method_fact(install),
                f"This machine: {machine}.",
                f"The upgrade steps for each install method are at {INSTALL_PAGE}#upgrade.",
            ),
            steps=(
                "Follow the upgrade steps for the install method above.",
                "Keep ~/.coffer exactly as it is — it holds my vault and settings; do not delete, "
                "move or reset anything in it.",
                "Restart the daemon so the new version runs, then confirm with "
                "`coffer --version` and `coffer daemon status` that both report the new version.",
            ),
        )
    )


__all__ = ["INSTALL_PAGE", "InstallFacts", "InstallMethod", "upgrade_handoff"]
