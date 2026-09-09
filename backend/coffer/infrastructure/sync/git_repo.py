"""Git transport over the sync workspace working tree (spec 010).

A thin wrapper over the ``git`` subprocess. This is the sync feature's only
network egress; it uses the user's ambient git credentials (SSH key / token),
exactly like a normal ``git push`` — Coffer never handles the remote secret.

The adapter sets a local commit identity so commits succeed even on a machine
whose global git config has no ``user.name``/``user.email``.
"""

from __future__ import annotations

import os
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

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
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
        # Non-ASCII paths (Chinese filenames) must come back verbatim from
        # `git diff --name-only`, never C-quoted — a quoted path round-trips
        # into checkout/rm as a literal `"\350..."` string and fails, which
        # would crash auto-resolve on every conflict touching such a file.
        self._run("config", "core.quotepath", "false")
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

    def has_changes(self) -> bool:
        return bool(self._run("status", "--porcelain").stdout.strip())

    def head(self) -> str | None:
        """The workspace's current commit sha, or None before the first commit."""
        if not (self._ws / ".git").exists():
            return None
        proc = self._run("rev-parse", "--verify", "--quiet", "HEAD", check=False)
        sha = proc.stdout.strip()
        return sha or None

    def remote_head(self, remote: str, branch: str) -> str | None:
        """The remote branch head via ``git ls-remote`` — one cheap network
        round trip, no fetch, no working-tree requirement. None when the
        remote is unreachable or the branch does not exist yet."""
        self._ws.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                ["git", "ls-remote", remote, f"refs/heads/{branch}"],
                cwd=self._ws,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
                stdin=subprocess.DEVNULL,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
        except subprocess.TimeoutExpired:
            return None
        if proc.returncode != 0:
            return None
        first = proc.stdout.split()
        return first[0] if first else None

    def check_remote(self, remote: str, branch: str) -> None:
        """Reachability probe for a remote URL (save-time validation).

        Runs ``git ls-remote`` headless (no terminal prompt) and raises
        ``GitOperationFailed`` with the raw stderr on any transport failure —
        auth, unknown host, missing repository. A reachable repository whose
        branch does not exist yet is fine (a fresh vault remote).
        """
        self._ws.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                ["git", "ls-remote", remote, f"refs/heads/{branch}"],
                cwd=self._ws,
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
                stdin=subprocess.DEVNULL,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
        except subprocess.TimeoutExpired as e:
            raise GitOperationFailed("ls-remote", f"timed out probing {remote}") from e
        if proc.returncode != 0:
            raise GitOperationFailed("ls-remote", proc.stderr.strip())

    def read_blob(self, rev: str, path: str) -> bytes | None:
        # Bytes, not text: credential blobs must round-trip unmodified.
        proc = subprocess.run(
            ["git", "show", f"{rev}:{path}"],
            cwd=self._ws,
            capture_output=True,
            check=False,
        )
        return proc.stdout if proc.returncode == 0 else None

    def last_commit_ts(self, rev: str, path: str) -> int | None:
        """Unix timestamp of the last commit touching ``path`` on ``rev``;
        None when no commit on that side ever touched it."""
        proc = self._run("log", "-1", "--format=%ct", rev, "--", path, check=False)
        out = proc.stdout.strip()
        return int(out) if out.isdigit() else None

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
        # A fresh `git init` workspace shares no history with an existing remote;
        # allow that first merge to combine the two roots (same-name files still
        # conflict normally).
        merge = self._run(
            "merge", "--no-edit", "--allow-unrelated-histories", "FETCH_HEAD", check=False
        )
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
                proc = self._run("checkout", f"--{strategy}", "--", path, check=False)
                if proc.returncode != 0:
                    # Delete/modify conflict where the chosen side deleted the
                    # path (e.g. accepting a tombstoned deletion): checkout has
                    # no version to restore — accepting means removing it.
                    self._run("rm", "--force", "--", path)
                else:
                    self._run("add", "--", path)
        elif strategy == "resolved":
            for path in targets:
                self._run("add", "--", path)
        else:
            raise GitOperationFailed("resolve", f"unknown strategy {strategy!r}")
        # Finalize the merge commit if the working tree is now conflict-free.
        if not self.has_conflicts():
            self._run("commit", "--no-edit", check=False)
