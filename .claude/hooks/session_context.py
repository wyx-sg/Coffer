#!/usr/bin/env python3
"""SessionStart hook: inject current git context so the agent honours the session protocol.

Reports the branch, worktree status, uncommitted-file count, and — when a
`make verify` baseline exists and has gone stale — a heads-up so the agent knows
upfront it will need to re-verify before committing (the verify-before-commit
hook would otherwise only surface this at commit time).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=10, check=False
        )
        return out.stdout.strip()
    except Exception:
        return ""


def _verify_stale() -> bool:
    """True only when a verify stamp exists for the working tree and is stale.

    No stamp (fresh clone / new worktree) or any error reads as "not stale" so the
    line stays absent rather than nagging — mirroring the verify-before-commit
    hook, which is silent without a baseline.
    """
    root = _git("rev-parse", "--show-toplevel")
    if not root:
        return False
    repo = Path(root)
    scripts = repo / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        import verify_stamp  # type: ignore[import-not-found]

        if not (repo / verify_stamp.STAMP_NAME).exists():
            return False
        return not verify_stamp.is_fresh(repo)
    except Exception:
        return False
    finally:
        if sys.path and sys.path[0] == str(scripts):
            sys.path.pop(0)


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
        "Session protocol: confirm scope, work in small committable chunks, run `make verify` before opening a PR. See agents/harness.md.",
    ]
    if _verify_stale():
        lines.append(
            "`make verify` is stale (source changed since the last pass) — re-run it before committing."
        )
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
