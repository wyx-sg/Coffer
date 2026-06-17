#!/usr/bin/env python3
"""PreToolUse(Bash) hook: ask before committing when `make verify` is stale.

When a `git commit` is about to run and the repo's source has changed since the
last passing `make verify` (tracked via scripts/verify_stamp.py's fingerprint),
this asks for confirmation rather than letting a possibly-unverified commit land
silently. It never hard-blocks — `make verify` is slow, and a hook that traps
every commit just trains people to bypass it — and it never breaks the agent: on
any error or for any non-commit command it exits 0 with no decision.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# .claude/hooks/verify_before_commit.py -> repo root is parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
_GIT_COMMIT = re.compile(r"\bgit\s+commit\b")


def _is_commit(command: str) -> bool:
    return bool(_GIT_COMMIT.search(command)) and "--dry-run" not in command


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

    target = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    fresh = _is_fresh(target)
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
