#!/usr/bin/env python3
"""SessionStart hook: inject current git context so the agent honours the session protocol."""

from __future__ import annotations

import json
import subprocess
import sys


def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=10, check=False
        )
        return out.stdout.strip()
    except Exception:
        return ""


def main() -> int:
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    if not branch:
        return 0  # not a git repo (or git unavailable) -> inject nothing, never block

    dirty = _git("status", "--porcelain")
    dirty_count = len([ln for ln in dirty.splitlines() if ln.strip()])
    git_dir = _git("rev-parse", "--git-dir")
    in_worktree = "/worktrees/" in git_dir or ".git/worktrees" in git_dir

    lines = [
        f"Coffer session — branch: {branch}" + (" (worktree)" if in_worktree else ""),
        f"Uncommitted changes: {dirty_count} file(s).",
        "Session protocol: confirm scope, work in small committable chunks, run `make verify` (or /coffer-verify) before opening a PR. See agents/harness.md.",
    ]
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "\n".join(lines),
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
