#!/usr/bin/env python3
"""PreToolUse(Bash) hook: deny a small set of destructive commands (defense-in-depth)."""

from __future__ import annotations

import json
import re
import sys

# (regex, human reason). Patterns are intentionally narrow to avoid false denials.
RULES: list[tuple[str, str]] = [
    (r"\brm\s+-rf?\s+(/|~|\$HOME|\*|\.\s*$|\.\.)", "recursive delete of root/home/cwd"),
    (r"\bgit\s+push\b.*(--force|\s-f\b).*\b(main|master)\b", "force-push to a protected branch"),
    (r"\bgit\s+push\s+\S+\s+(main|master)\b(?!.*--dry-run)", "direct push to a protected branch"),
    (r"\bcurl\b.*\|\s*(sudo\s+)?(ba)?sh\b", "pipe-to-shell from the network"),
    (r"\bwget\b.*\|\s*(sudo\s+)?(ba)?sh\b", "pipe-to-shell from the network"),
    (r"\bchmod\s+-R\s+777\s+/", "world-writable recursive chmod on an absolute path"),
    (r">\s*/dev/sd[a-z]", "raw write to a block device"),
]


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    command = (data.get("tool_input") or {}).get("command", "")
    for pattern, reason in RULES:
        if re.search(pattern, command):
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": f"Blocked by Coffer harness: {reason}.",
                        }
                    }
                )
            )
            return 0
    return 0  # no decision -> default permission flow


if __name__ == "__main__":
    sys.exit(main())
