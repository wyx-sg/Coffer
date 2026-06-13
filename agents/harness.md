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

- `/coffer-spec` — scaffolds a new SDD spec (see `agents/sdd.md`).

## How it is tested

The hooks and settings are pinned by `backend/tests/integration/harness/`, which subprocess the real scripts with synthetic stdin. They run under `make verify-integration`, so the harness tests itself.

## Eval harness (Layer D)

Non-deterministic AI behaviour — retrieval quality and tool-routing — is measured under [`evals/`](../evals/README.md): `make eval` (local, deterministic) and `make eval-routing` (needs a local LLM). It is the regression net for prompt / model / retrieval changes; see [ADR-017](../docs/decisions/ADR-017-industrial-grade-harness-in-layers.md) for the layer model.

## The eval flywheel (loop engineering)

[ADR-019](../docs/decisions/ADR-019-close-the-eval-flywheel.md) closes the loop so the eval suite is not just a static instrument but a self-feeding cycle — the development-time loop that keeps Coffer's non-deterministic behaviour from drifting:

1. **Capture** — set `COFFER_EVAL_CAPTURE` and real `coffer__search_tools` calls record their `(query → ranked tools)` shape to a local, gitignored JSONL sink (opt-in; off by default; never tool args/results). The invocation log was made honest first (in-band `isError` → `status=error`) so failures are legible.
2. **Curate** — `make eval-curate` turns captured queries into labelled `datasets/*.jsonl` golden cases (dedup vs the existing dataset; you mark which returned tools were relevant), tagged `"source": "captured"`.
3. **Gate** — the `evals.yml` workflow runs the deterministic, model-free suites on PRs touching prompts / mcp / retrieval / catalogue and fails on **relative regression vs the committed baseline** (`evals/run.py`). The model-bearing routing suite stays on-demand (`make eval-routing`), out of CI.
4. **Feedback** — a real-usage failure becomes a captured case → a curated golden case → a baseline regression the gate catches → a fix → `python -m evals.run --update-baseline`. The dataset ratchets up from real usage; the human + Claude Code inner loop still owns the fix (the flywheel measures and guards, it does not auto-optimise — see ADR-019's deferred repair-assist).

## Conventions

- Hooks are Python (no `jq` dependency; the project guarantees Python 3.12). A hook must never break the agent — on any error it exits 0 with no decision.
- `.claude/settings.json`, `.claude/hooks/`, `.claude/skills/` are committed. `.claude/settings.local.json` is for personal overrides (gitignored).
