"""The hand-offs for a machine with no ``git``, or one too old (spec knowledge
"Keep every document's history and undo a pass as a whole"; the skill Git
import; spec vault-storage "Refuse to start on a git older than 2.40").

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


def git_update_handoff(machine: str, *, found: str, needed: str, needed_for: str) -> str:
    """The prompt asking the person's agent to bring git on ``machine`` from
    version ``found`` up to at least ``needed``."""
    return render_handoff(
        Handoff(
            task=f"Please update git on this machine to version {needed} or later.",
            facts=(
                f"This machine: {machine}.",
                f"Coffer needs git {needed} or later for {needed_for}; the `git` on the "
                f"PATH the Coffer daemon uses is version {found}.",
            ),
            steps=(
                "Update it the way that fits this machine, and make sure the newer git "
                "comes first on the PATH the Coffer daemon starts with.",
                f"When you are done, run `git --version` to confirm it reports {needed} or later.",
                "Then tell me to start Coffer again.",
            ),
        )
    )


def git_clone_handoff(machine: str, *, url: str, message: str) -> str:
    """The prompt asking the person's agent to find out why ``url`` cannot be
    cloned from ``machine`` (network, VPN, proxy, credentials) and fix it."""
    return render_handoff(
        Handoff(
            task=f"Please find out why git cannot clone {url} on this machine, and fix it.",
            facts=(
                f"This machine: {machine}.",
                f"Coffer ran `git clone` for a skill source and git said: {message}",
            ),
            steps=(
                "Check the URL, the network, any VPN or proxy, and the credentials git uses.",
                f"When you are done, confirm `git ls-remote {url}` works.",
                "Then tell me to retry in Coffer.",
            ),
        )
    )


def clone_failure_details(machine: str, *, url: str, message: str) -> dict[str, object]:
    """The error ``details`` that carry the clone-failure hand-off."""
    return {"handoff": {"prompt": git_clone_handoff(machine, url=url, message=message)}}


def git_missing_details(machine: str, *, needed_for: str) -> dict[str, object]:
    """The error ``details`` that carry the install hand-off."""
    return {
        "reason": GIT_MISSING,
        "handoff": {"prompt": git_install_handoff(machine, needed_for=needed_for)},
    }


__all__ = [
    "GIT_MISSING",
    "clone_failure_details",
    "git_clone_handoff",
    "git_install_handoff",
    "git_missing_details",
    "git_update_handoff",
]
