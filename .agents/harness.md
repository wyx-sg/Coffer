# Harness — Agent Control Layer

Coffer ships a checked-in control layer so the agent-facing harness is enforced, not just documented: the right thing is the default path, destructive commands are blocked, and feedback is fast, deterministic and legible to humans, CI and agents alike.

## The layers

The harness around this repo is a stack, and each layer has one home:

| Layer         | What it gives                                                                                  | Where it lives                                                                                                                                  |
| ------------- | ---------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Control       | Hooks and permission rules that act on the agent's tool calls, not just advise it             | `.claude/` — this page                                                                                                                          |
| Knowledge     | What an agent reads before working                                                             | `AGENTS.md`, `.agents/*.md`, the principles, the architecture pages, `docs/decisions/`, `openspec/specs/`                                      |
| Hermeticity   | The same dependency set on every machine and in CI                                             | `.python-version` (3.12) and `backend/uv.lock`, installed with `uv sync --frozen` by CI and the release workflow; `make lock` refreshes the lock |
| Feedback      | One command that says whether the tree is good                                                 | `make verify` and the test tiers ([`testing.md`](./testing.md)), pre-commit, the CI workflows                                                   |
| Eval          | A regression net for non-deterministic behaviour that exact-match tests cannot pin             | `evals/`, `make eval`, `.github/workflows/evals.yml` — see [Eval harness](#eval-harness) below                                                  |

A hook or gate must stay fast: a slow one trains people to bypass it.

## What is wired (`.claude/`)

| File                                    | Role                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `.claude/settings.json`                 | Permissions (allow safe commands, deny destructive ones) + hook wiring. Committed, team-shared.                                                                                                                                                                                                                                                                                                                                      |
| `.claude/hooks/auto_format.py`          | PostToolUse on Edit/Write — formats the edited file. Python: `ruff check --fix` then `ruff format` (lint-fix first, formatter has the final say), repo-wide. Prettier (`.ts/.tsx/.js/.jsx/.css/.json/.md`): only under `frontend/`; the rest of the repo's prettier types are owned by the pinned pre-commit pass (different prettier version), so the hook leaves them alone to avoid CI-fighting churn. Best-effort, never blocks. |
| `.claude/hooks/block_dangerous_bash.py` | PreToolUse on Bash — denies a narrow set of destructive commands (recursive root/home delete incl. reversed flags & quoted targets, force/direct push to protected branches, pipe-to-shell, `dd of=/dev/<disk>` and raw redirects to block devices incl. macOS `disk`/`rdisk` and `nvme`).                                                                                                                                           |
| `.claude/hooks/verify_before_commit.py` | PreToolUse on Bash — when a `git commit` runs while `make verify` is stale (source changed since the last passing verify, per `scripts/verify_stamp.py`'s content fingerprint), asks for confirmation. Checks the working tree the commit runs in (resolved from the command's cwd), not `CLAUDE_PROJECT_DIR` — so a linked worktree is judged on its own stamp, not the main checkout's. Never hard-blocks; never breaks the agent. **Never asks in a session that turned prompts off** (`permission_mode` of `bypassPermissions` or `dontAsk`) — there it reports the staleness to the agent as a `systemMessage` instead, so the fact survives without overriding a choice the user made about their own session. A CLI old enough not to send the field keeps the prompt. |
| `.claude/hooks/session_context.py`      | SessionStart — injects branch, worktree status, dirty-file count, a stale-`make verify` heads-up (only when a baseline exists and has gone stale), and the session protocol reminder.                                                                                                                                                                                                                                                |

## Commands and Skills

- OpenSpec's six commands — `/opsx:explore`, `/opsx:propose`, `/opsx:apply`,
  `/opsx:update`, `/opsx:sync` and `/opsx:archive` — live in
  `.claude/commands/opsx/*.md`, and the six matching skills in
  `.claude/skills/openspec-*/SKILL.md`. Both are generated by
  `openspec init --tools claude` and refreshed by `npx openspec update`; do not
  hand-edit them. `backend/tests/integration/harness/test_skills.py` pins that
  exactly those six skills are checked in and carry the required frontmatter.
  Read [`openspec.md`](./openspec.md) for the change workflow they drive.
- Whatever a change adds, a capability is **named, never numbered**:
  `scripts/check_doc_numbering.py` (run by `make lint`) fails on a spec
  directory starting with a digit and on any `spec <digits>` token, in any
  case, so a numbered spec cannot be committed. A requirement is cited by
  title, and `scripts/check_spec_citations.py` (also `make lint`) fails on a
  citation whose capability or title does not exist in `openspec/specs/`.

## How it is tested

The hooks and settings are pinned by `backend/tests/integration/harness/`, which subprocess the real scripts with synthetic stdin. They run under `make verify-integration`, so the harness tests itself.

## Eval harness

Non-deterministic AI behaviour — tool-search ranking and tool routing — is measured under [`evals/`](../evals/README.md): `make eval` (local, deterministic) and `make eval-routing` (needs a local LLM). It is the regression net for prompt / model / catalogue changes; the design is recorded in [Eval Capture and Regression Gate](../docs/decisions/eval-capture-and-regression-gate.md).

## The eval flywheel (loop engineering)

[Eval Capture and Regression Gate](../docs/decisions/eval-capture-and-regression-gate.md) closes the loop so the eval suite is not just a static instrument but a self-feeding cycle — the development-time loop that keeps Coffer's non-deterministic behaviour from drifting:

1. **Capture** — set `COFFER_EVAL_CAPTURE` and real `coffer__search_tools` calls record their `(query → ranked tools)` shape to a local, gitignored JSONL sink (opt-in; off by default; never tool args/results). The invocation log was made honest first (in-band `isError` → `status=error`) so failures are legible.
2. **Curate** — `make eval-curate` turns captured queries into labelled `datasets/*.jsonl` golden cases (dedup vs the existing dataset; you mark which returned tools were relevant), tagged `"source": "captured"`.
3. **Gate** — the `evals.yml` workflow runs the deterministic, model-free suites on PRs touching prompts / mcp / retrieval / catalogue and fails on **relative regression vs the committed baseline** (`evals/run.py`). The model-bearing routing suite stays on-demand (`make eval-routing`), out of CI.
4. **Feedback** — a real-usage failure becomes a captured case → a curated golden case → a baseline regression the gate catches → a fix → `python -m evals.run --update-baseline`. The dataset ratchets up from real usage; the human + Claude Code inner loop still owns the fix (the flywheel measures and guards, it does not auto-optimise — see [Eval Capture and Regression Gate](../docs/decisions/eval-capture-and-regression-gate.md)).

## Conventions

- Hooks are Python (no `jq` dependency; the project guarantees Python 3.12). A hook must never break the agent — on any error it exits 0 with no decision.
- `.claude/settings.json`, the four `.claude/hooks/` scripts, the six `.claude/commands/opsx/*.md` commands and the six `.claude/skills/openspec-*/SKILL.md` skills are the tracked files under `.claude/` — that is the whole harness. The repo's `.gitignore` ignores `.claude/settings.local.json` (personal overrides), every other `.claude/commands/*` entry (it un-ignores only `opsx/`), `.claude/worktrees/` and the loop/scheduler state files.
