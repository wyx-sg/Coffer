# Harness — Agent Control Layer

> 中文版: [harness.zh.md](./harness.zh.md)

Coffer ships a checked-in control layer so the agent-facing harness is enforced, not just documented. See [ADR-017](../docs/decisions/ADR-017-industrial-grade-harness-in-layers.md) for the five-layer model.

## What is wired (`.claude/`)

| File | Role |
| ---- | ---- |
| `.claude/settings.json` | Permissions (allow safe commands, deny destructive ones) + hook wiring. Committed, team-shared. |
| `.claude/hooks/auto_format.py` | PostToolUse on Edit/Write — formats the edited file (ruff for `.py`, prettier for `.ts/.tsx/.js/.jsx/.css/.json/.md`). Best-effort, never blocks. |
| `.claude/hooks/block_dangerous_bash.py` | PreToolUse on Bash — denies a narrow set of destructive commands (recursive root/home delete, force/direct push to protected branches, pipe-to-shell, raw block-device writes). |
| `.claude/hooks/session_context.py` | SessionStart — injects branch, worktree status, dirty-file count, and the session protocol reminder. |

## Skills

- `/coffer-verify` — runs `make verify` and reports honestly. Use before opening a PR.
- `/coffer-spec` — scaffolds a new SDD spec (see `agents/sdd.md`).

## How it is tested

The hooks and settings are pinned by `backend/tests/integration/harness/`, which subprocess the real scripts with synthetic stdin. They run under `make verify-integration`, so the harness tests itself.

## Conventions

- Hooks are Python (no `jq` dependency; the project guarantees Python 3.12). A hook must never break the agent — on any error it exits 0 with no decision.
- `.claude/settings.json`, `.claude/hooks/`, `.claude/skills/` are committed. `.claude/settings.local.json` is for personal overrides (gitignored).
