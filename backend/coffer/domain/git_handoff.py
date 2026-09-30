"""The hand-off for a machine with no ``git`` (spec knowledge "Keep every
document's history and undo a pass as a whole"; the skill Git import).

Coffer reads git history and Git repositories with the machine's own ``git``
and does not install it: how git is installed depends on the machine, so the
chore is written up for the person's agent (``domain/handoff.py``). The prompt
names the machine and what needed git, and never an install command — the
agent picks the method that fits.

A missing git travels on the refusing error as ``details.reason ==
"git_missing"`` and ``details.handoff == {"prompt": …}`` (:func:`git_missing_details`),
so the page that shows the error can offer the prompt beside it.
"""

from __future__ import annotations

from coffer.domain.handoff import Handoff, render_handoff

#: ``details.reason`` of an error whose cause is that git is not installed.
GIT_MISSING = "git_missing"


def git_install_handoff(machine: str, *, needed_for: str) -> str:
    """The prompt asking the person's agent to install git on ``machine``;
    ``needed_for`` says what in Coffer needed it, as a noun phrase."""
    return render_handoff(
        Handoff(
            task="Please install git on this machine.",
            facts=(
                f"This machine: {machine}.",
                f"Coffer needs git for {needed_for}, and no `git` command was found on "
                "the PATH the Coffer daemon uses.",
            ),
            steps=(
                "Install it the way that fits this machine, for example with the "
                "platform's developer tools or a package manager.",
                "When you are done, run `git --version` to confirm it works.",
                "Then tell me to try again in Coffer.",
            ),
        )
    )


def git_missing_details(machine: str, *, needed_for: str) -> dict[str, object]:
    """The error ``details`` that carry the install hand-off."""
    return {
        "reason": GIT_MISSING,
        "handoff": {"prompt": git_install_handoff(machine, needed_for=needed_for)},
    }


__all__ = ["GIT_MISSING", "git_install_handoff", "git_missing_details"]
