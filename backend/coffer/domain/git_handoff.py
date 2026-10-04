"""The hand-offs for a machine with no ``git``, or one too old (spec knowledge
"Keep every document's history"; the skill Git
import; spec daemon "Wait in a setup state when git is missing or too old").

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

from coffer.domain.error_base import CofferError
from coffer.domain.handoff import Handoff, render_handoff

#: ``details.reason`` of an error whose cause is that git is not installed.
GIT_MISSING = "git_missing"
#: ``details.reason`` when git is installed but older than the vault needs.
GIT_TOO_OLD = "git_too_old"
#: What the vault needs git for, as the prompts and messages word it.
VAULT_NEEDS_GIT_FOR = "keeping the vault's history and syncing it"


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
                "comes first on the PATH of a login shell, which Coffer also searches.",
                f"When you are done, run `git --version` to confirm it reports {needed} or later.",
                "Then tell me to check again in Coffer.",
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


def git_setup_message(*, found: str | None, needed: str) -> str:
    """Why the daemon is waiting in its setup state: what is wrong, why Coffer
    needs git, and what to do — the words the CLI prints and every refused
    route carries."""
    problem = (
        "Coffer needs git, and git isn't installed on this machine."
        if found is None
        else f"Coffer needs git {needed} or later, and the git on this machine is {found}."
    )
    verb = "Install" if found is None else "Update"
    return (
        f"{problem} The vault keeps its history and syncs with git. {verb} git, then "
        "check again: press Check again in Coffer, or run the command again."
    )


def git_setup_details(machine: str, *, found: str | None, needed: str) -> dict[str, object]:
    """The setup state's details: the reason, the versions and the hand-off for
    the person's agent (install when ``found`` is ``None``, else update)."""
    prompt = (
        git_install_handoff(machine, needed_for=VAULT_NEEDS_GIT_FOR)
        if found is None
        else git_update_handoff(machine, found=found, needed=needed, needed_for=VAULT_NEEDS_GIT_FOR)
    )
    return {
        "reason": GIT_MISSING if found is None else GIT_TOO_OLD,
        "found": found,
        "needed": needed,
        "handoff": {"prompt": prompt},
    }


class GitNeeded(CofferError):  # noqa: N818
    """The daemon is waiting in its setup state for git, so it refuses what
    needs the vault. Carries :func:`git_setup_message` and
    :func:`git_setup_details`, so every surface says the same thing."""

    code = "GIT_NEEDED"

    def __init__(self, message: str, details: dict[str, object]) -> None:
        super().__init__(message)
        self.error_details = details


__all__ = [
    "GIT_MISSING",
    "GIT_TOO_OLD",
    "VAULT_NEEDS_GIT_FOR",
    "GitNeeded",
    "clone_failure_details",
    "git_clone_handoff",
    "git_install_handoff",
    "git_missing_details",
    "git_setup_details",
    "git_setup_message",
    "git_update_handoff",
]
