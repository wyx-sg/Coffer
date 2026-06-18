#!/usr/bin/env python3
"""PreToolUse(Bash) hook: ask before committing when `make verify` is stale.

When a `git commit` is about to run and the repo's source has changed since the
last passing `make verify` (tracked via scripts/verify_stamp.py's fingerprint),
this asks for confirmation rather than letting a possibly-unverified commit land
silently. It never hard-blocks — `make verify` is slow, and a hook that traps
every commit just trains people to bypass it — and it never breaks the agent: on
any error or for any non-commit command it exits 0 with no decision.

The freshness check targets the *working tree the commit runs in* (resolved from
the command's cwd), not ``CLAUDE_PROJECT_DIR`` — which stays pinned to the main
checkout even when the commit runs in a linked worktree. Checking the main
checkout from a worktree judged every worktree commit against a baseline that is
perpetually stale during active development, so the guard nagged on every single
commit. A worktree with no stamp now reads as "unknown" and stays quiet.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# .claude/hooks/verify_before_commit.py -> repo root is parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
_GIT_COMMIT = re.compile(r"\bgit\s+commit\b")


def _is_commit(command: str) -> bool:
    return bool(_GIT_COMMIT.search(command)) and "--dry-run" not in command


def _commit_tree(payload: dict) -> Path:
    """The git working-tree root the commit will run in.

    ``git commit`` operates on the repo containing the command's cwd, so that —
    not ``CLAUDE_PROJECT_DIR`` (which points at the main checkout even in a linked
    worktree) — is the tree to check. Prefer the hook payload's ``cwd``, fall back
    to the hook process's own cwd, then resolve to the enclosing working-tree root
    so a subdirectory commit still finds the right stamp.
    """
    start = Path(payload.get("cwd") or os.getcwd())
    try:
        out = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        root = out.stdout.strip()
        return Path(root) if root else start
    except Exception:
        return start


def _is_fresh(target: Path) -> bool | None:
    """True/False from the verify stamp, or None if it can't be determined."""
    scripts = _REPO_ROOT / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        import verify_stamp  # type: ignore[import-not-found]

        # No stamp means no `make verify` baseline exists on this checkout — the
        # stamp is gitignored, so a fresh clone or a new branch never has one.
        # Treat that as "unknown" rather than "stale" so the guard stays quiet
        # until the first `make verify` writes a stamp, instead of asking on
        # every commit (doc-only commits included). The stale path below still
        # fires once a baseline exists and source has since changed.
        if not (target / verify_stamp.STAMP_NAME).exists():
            return None
        return verify_stamp.is_fresh(target)
    except Exception:
        return None
    finally:
        if sys.path and sys.path[0] == str(scripts):
            sys.path.pop(0)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    command = (data.get("tool_input") or {}).get("command", "")
    if not _is_commit(command):
        return 0

    fresh = _is_fresh(_commit_tree(data))
    if fresh is None or fresh:
        return 0  # can't tell, or genuinely fresh -> don't get in the way

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": (
                        "`make verify` has not passed since your last source change. "
                        "Run `make verify` before committing, or confirm to commit anyway."
                    ),
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
