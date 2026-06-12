"""Git transport over the sync workspace working tree (spec 010).

A thin wrapper over the ``git`` subprocess. This is the sync feature's only
network egress; it uses the user's ambient git credentials (SSH key / token),
exactly like a normal ``git push`` — Coffer never handles the remote secret.

The adapter sets a local commit identity so commits succeed even on a machine
whose global git config has no ``user.name``/``user.email``.
"""

from __future__ import annotations

import pathlib
import subprocess
from collections.abc import Sequence

from coffer.application.sync.ports import PullOutcome
from coffer.domain.sync.errors import GitOperationFailed

_COMMIT_NAME = "Coffer Sync"
_COMMIT_EMAIL = "sync@coffer.local"


class GitRepo:
    """Implements ``application.sync.ports.GitPort``."""

    def __init__(self, workspace: pathlib.Path) -> None:
        self._ws = workspace

    def _run(
        self, *args: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        proc = subprocess.run(
            ["git", *args],
            cwd=self._ws,
            capture_output=True,
            text=True,
            check=False,
        )
        if check and proc.returncode != 0:
            raise GitOperationFailed(args[0] if args else "git", proc.stderr.strip())
        return proc

    def ensure_repo(self, remote: str, branch: str) -> None:
        self._ws.mkdir(parents=True, exist_ok=True)
        if not (self._ws / ".git").exists():
            self._run("init")
            self._run("symbolic-ref", "HEAD", f"refs/heads/{branch}")
        self._run("config", "user.name", _COMMIT_NAME)
        self._run("config", "user.email", _COMMIT_EMAIL)
        # Idempotently point origin at the configured remote.
        existing = self._run("remote", check=False)
        if "origin" in existing.stdout.split():
            self._run("remote", "set-url", "origin", remote)
        else:
            self._run("remote", "add", "origin", remote)

    def has_conflicts(self) -> bool:
        return bool(self.conflicted_paths())

    def conflicted_paths(self) -> list[str]:
        proc = self._run("diff", "--name-only", "--diff-filter=U")
        return [line for line in proc.stdout.splitlines() if line.strip()]

    def commit_all(self, message: str) -> bool:
        self._run("add", "-A")
        status = self._run("status", "--porcelain")
        if not status.stdout.strip():
            return False
        self._run("commit", "-m", message)
        return True

    def pull(self, branch: str) -> PullOutcome:
        # Fetch; a brand-new remote has no branch yet, which is not an error.
        fetch = self._run("fetch", "origin", branch, check=False)
        if fetch.returncode != 0:
            # No such remote branch (first push) — nothing to merge.
            if "couldn't find remote ref" in fetch.stderr or "Couldn't find" in fetch.stderr:
                return PullOutcome()
            raise GitOperationFailed("fetch", fetch.stderr.strip())
        # Does FETCH_HEAD point at anything?
        rev = self._run("rev-parse", "--verify", "--quiet", "FETCH_HEAD", check=False)
        if rev.returncode != 0 or not rev.stdout.strip():
            return PullOutcome()
        merge = self._run("merge", "--no-edit", "FETCH_HEAD", check=False)
        if merge.returncode != 0:
            conflicts = self.conflicted_paths()
            if conflicts:
                return PullOutcome(conflicted_paths=tuple(conflicts))
            raise GitOperationFailed("merge", merge.stderr.strip())
        return PullOutcome()

    def push(self, branch: str) -> None:
        self._run("push", "-u", "origin", f"HEAD:{branch}")

    def resolve(self, strategy: str, paths: Sequence[str]) -> None:
        targets = list(paths) if paths else self.conflicted_paths()
        if strategy in ("ours", "theirs"):
            for path in targets:
                self._run("checkout", f"--{strategy}", "--", path)
                self._run("add", "--", path)
        elif strategy == "resolved":
            for path in targets:
                self._run("add", "--", path)
        else:
            raise GitOperationFailed("resolve", f"unknown strategy {strategy!r}")
        # Finalize the merge commit if the working tree is now conflict-free.
        if not self.has_conflicts():
            self._run("commit", "--no-edit", check=False)
