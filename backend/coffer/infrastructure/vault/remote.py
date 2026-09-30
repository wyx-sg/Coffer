"""Fetching from and pushing to the one user-owned remote
(ADR sync-applies-clean-merges-and-stops-on-any-conflict, ADR credentials-across-machines).

Sync only adds a remote to a repository that already exists: ``origin``,
whose URL is the user's and carries no secret. The push token reaches git per
invocation through the credential helper in ``git.run``; stderr is redacted of
it before anything is raised. Failures are classified by what a person can do
about them — the network, the credential, or the remote's refusal of a push —
because that is what the Sync page offers.
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.domain.sync.remote import RemoteFailed, RemoteProblem
from coffer.infrastructure.vault import git
from coffer.infrastructure.vault.repository import VaultRepository

REMOTE = "origin"


_AUTH = (
    "authentication failed",
    "permission denied",
    "could not read username",
    "could not read password",
    "invalid username or password",
    "access denied",
    "401",
    "403",
    "repository not found",
)
_NETWORK = (
    "could not resolve host",
    "network is unreachable",
    "connection timed out",
    "connection refused",
    "operation timed out",
    "failed to connect",
    "could not connect",
    "no route to host",
    "timed out after",
)


def classify(detail: str) -> RemoteProblem:
    text = detail.lower()
    if any(k in text for k in _NETWORK):
        return RemoteProblem.UNREACHABLE
    if any(k in text for k in _AUTH):
        return RemoteProblem.AUTH_FAILED
    if "rejected" in text or "protected branch" in text or "non-fast-forward" in text:
        return RemoteProblem.PUSH_REJECTED
    return RemoteProblem.OTHER


@dataclass(frozen=True)
class FetchResult:
    #: The remote branch's tip, or ``None`` for an empty remote.
    tip: str | None


def set_remote(repo: VaultRepository, url: str) -> None:
    repo.ensure()
    current = git.run(repo.root, "remote", "get-url", REMOTE, check=False)
    if current.returncode == 0:
        if git.text(current).strip() != url:
            git.run(repo.root, "remote", "set-url", REMOTE, "--", url)
    else:
        git.run(repo.root, "remote", "add", REMOTE, "--", url)


def clear_remote(repo: VaultRepository) -> None:
    if repo.exists():
        git.run(repo.root, "remote", "remove", REMOTE, check=False)


def tracking_ref(branch: str) -> str:
    return f"refs/remotes/{REMOTE}/{branch}"


def fetch(repo: VaultRepository, branch: str, token: str | None) -> FetchResult:
    args = (
        "fetch",
        "--no-tags",
        "--prune",
        "--quiet",
        REMOTE,
        f"+refs/heads/{branch}:{tracking_ref(branch)}",
    )
    done = git.run(repo.root, *args, token=token, timeout=git.NETWORK_TIMEOUT_S, check=False)
    if done.returncode != 0:
        detail = git.failure_message(args, done, token)
        if "couldn't find remote ref" in detail.lower():
            git.run(repo.root, "update-ref", "-d", tracking_ref(branch), check=False)
            return FetchResult(None)
        raise RemoteFailed(classify(detail), detail)
    return FetchResult(repo.resolve(tracking_ref(branch)))


def push(repo: VaultRepository, commit: str, branch: str, token: str | None) -> None:
    args = ("push", "--quiet", REMOTE, f"{commit}:refs/heads/{branch}")
    done = git.run(repo.root, *args, token=token, timeout=git.NETWORK_TIMEOUT_S, check=False)
    if done.returncode != 0:
        detail = git.failure_message(args, done, token)
        problem = classify(detail)
        raise RemoteFailed(
            problem if problem is not RemoteProblem.OTHER else RemoteProblem.PUSH_REJECTED, detail
        )
    git.run(repo.root, "update-ref", tracking_ref(branch), commit, check=False)


def probe(repo: VaultRepository, url: str, branch: str, token: str | None) -> str | None:
    """The remote branch's tip without fetching (``ls-remote``); ``None`` for
    an empty remote. For the setup form's "Check repository"."""
    args = ("ls-remote", "--heads", "--", url, f"refs/heads/{branch}")
    done = git.run(repo.root, *args, token=token, timeout=git.NETWORK_TIMEOUT_S, check=False)
    if done.returncode != 0:
        detail = git.failure_message(args, done, token)
        raise RemoteFailed(classify(detail), detail)
    line = git.text(done).strip().split("\n")[0]
    return line.split()[0] if line else None


__all__ = [
    "REMOTE",
    "FetchResult",
    "RemoteFailed",
    "RemoteProblem",
    "classify",
    "clear_remote",
    "fetch",
    "probe",
    "push",
    "set_remote",
    "tracking_ref",
]
