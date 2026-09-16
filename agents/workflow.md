# Workflow — Branches, Commits, PRs, Merge Policy

Covers: branch naming, Conventional Commits, AI co-author signatures, pull-request flow, merge policy.

## Branches

### Allowed Prefixes

| Prefix | Purpose | Example |
|---|---|---|
| `feature/<short-name>` | New functionality scoped to a spec | `feature/mcp-gateway-crud` |
| `fix/<short-name>` | Bug fix scoped to a spec | `fix/mcp-gateway-list-cursor` |
| `docs/<short-name>` | Documentation only | `docs/contributing-rewrite` |
| `refactor/<short-name>` | Internal restructuring, no behavior change | `refactor/extract-credential-port` |
| `chore/<short-name>` | Deps, tooling, CI, project meta | `chore/upgrade-fastapi-to-0.115` |

Rules:

- Kebab-case throughout.
- The short name typically mirrors (or describes) the affected spec folder (`specs/mcp-gateway/` → `feature/mcp-gateway-...`).
- Branch from up-to-date `main`: `git checkout main && git pull --ff-only && git checkout -b <prefix>/<name>`.
- Branch deleted automatically after merge (squash merge strategy).

## Commits

### Conventional Commits 1.0

```
<type>(<scope>): <subject>

<body>

<footer>
```

[`.commitlintrc.yaml`](../.commitlintrc.yaml) is the source of truth for every
rule below — it runs as a `commit-msg` pre-commit hook and is what actually
rejects a message. Read it before asserting a limit.

- **Types**: `feat | fix | docs | refactor | perf | test | build | ci | chore | revert` (the config's `type-enum`).
- **Scope**: descriptive name of the affected spec or area (`mcp-gateway`, `clis`, `ui`, `build`, `ci`). Spec folders are named, not numbered — use the folder name.
- **Subject**: imperative present tense, no trailing period, **non-empty** (`subject-empty`), **≤ 120 chars** (`subject-max-length`), with the whole `type(scope): subject` header **≤ 150 chars** (`header-max-length`). Body lines wrap at **100** (`body-max-line-length`).
- **No case rule.** `subject-case` is set to `[0]` on purpose: Conventional Commits mandates no case, acronyms (MCP, REST, HTTP) and product names are routine, and Dependabot's Sentence-case titles would otherwise be unmergeable. A short lowercase subject is a fine house *preference* — it is not a cap, and it is not what `main` does: 49 of the last 100 subjects there run past 72 chars.

### Footer

```
Fixes #123
Refs mcp-gateway, skill-manager
BREAKING CHANGE: <description>
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### Examples

```
feat(mcp-gateway): aggregate upstream MCP tools through one stdio endpoint

Implements the coffer-as-MCP-aggregator behavior: registered upstream
MCP servers' tools are merged and re-exposed on the daemon's MCP HTTP
endpoint. Satisfies the mcp-gateway acceptance scenarios "aggregate tools
across servers in one client" and "route a tool call to the correct upstream".

Refs mcp-gateway
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

```
fix(mcp-gateway): route a tool call to the upstream that owns it

Added a regression test under the mcp-gateway spec.md acceptance
scenario "route a tool call to the correct upstream".

Fixes #42
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### AI Co-author Footers

When an AI agent participates substantively in a commit, add a `Co-Authored-By`
footer. **Name the model, not just the product** — that is the form `main`
carries (`Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`), and it is
what makes the history say which model actually wrote a change. The email is a
non-official convention (GitHub renders the footer as multi-author attribution;
the email need not exist):

| Agent | Co-author line |
|---|---|
| Claude (Anthropic) | `Co-Authored-By: Claude <model> <noreply@anthropic.com>` |
| Codex (OpenAI) | `Co-Authored-By: Codex <model> <noreply@openai.com>` |

The table mirrors the agents Coffer supports — `claude_code` and `codex`
(`backend/coffer/domain/agent/types.py`). If Coffer ever supports another, add
its row here with the agent's documented address, otherwise the vendor's.

If multiple AIs collaborated on a single commit, list each `Co-Authored-By:` line.

When NOT to use:
- Pure tooling output (`pip install --upgrade`) — human commits.
- Mechanical bot commits (dependabot etc.) — those carry their own bot identity.

## Pull Requests

### Standard Flow

1. Open PR from feature branch to `main`.
2. PR title follows Conventional Commits, under the same limits as a commit subject (≤ 120 chars of subject, ≤ 150 for the whole header) — no case constraint. The `pr-title` workflow lints it with the very same `.commitlintrc.yaml`, so the two can't drift.
3. PR description:
   - **What** changed.
   - **Why**.
   - **How to test** (or: "covered by `spec.md` acceptance scenarios X, Y").
   - **Spec references**.
   - **Screenshots** for UI changes.
   - **Breaking changes** explicit.
4. CI green (every parallel job must pass before review).
5. **Squash merge** — keeps `main` linear.
6. Branch auto-deleted.

### Hygiene Rules

- **One commit per PR** — squash before final push (`git reset --soft main && git commit -m "<final-subject>"`).
- **Subject + PR title obey `.commitlintrc.yaml`** (≤ 120 subject / ≤ 150 header) — and stay aligned with each other.
- **`gh pr edit --title` BEFORE `git push --force-with-lease`** — keep title in sync with the squashed commit at every snapshot.
- **PR title and body stay in sync with the squashed commit** — re-check before every force push.

### Self-checklist before every force-push

1. Does the PR title still match the squashed commit subject?
2. Does the PR body still describe what the diff actually contains?
3. Is the test plan accurate?

If ANY answer is "no", fix BEFORE force-pushing. Combine title + body updates into one batch.

### Author Workflow Cheatsheet

```bash
git checkout main && git pull --ff-only
git checkout -b feature/<short-name>
git add <files> && git commit -m "feat(<scope>): <subject>"
make verify
git reset --soft main && git commit -m "<final-subject>"   # squash
git push -u origin feature/<short-name>
gh pr create --fill --base main
```

## Merge Policy

### Default: Stop at PR-opened

When a PR is opened, the agent stops and reports. The agent does NOT merge the PR autonomously — it waits for a human to authorize.

### Exception: Explicit User Authorization

The agent MAY `gh pr merge --squash` ONLY when ALL of the following hold:

1. The user has given **explicit, direct authorization** in conversation (e.g., "merge it", "merge PR #N", "ship it AND merge"). Implicit signals such as "looks good" or "this is ready" are NOT authorization on their own.
2. CI is green (every parallel job).
3. A self-review pass found zero open issues. "Approve with one fix" is NOT zero issues.
4. PR title + body still match the squashed commit subject + diff.

If any condition is ambiguous → ASK before merging. Default to stopping.

### Self-Review Convergence

PR self-review converges in ≤ 4 rounds with diminishing returns:

- **Round 1**: real bugs, dead code, spec drift, test gaps, security items.
- **Round 2**: doc drift introduced by round-1 fixes, edge-case fragility.
- **Round 3**: nits introduced by round-2 fixes (typing, placement, naming).
- **Round 4**: style nits (inline imports, forward-promise wording).

Stop at round 3 if remaining items are cosmetic only AND CI green AND user signalled merge intent. Don't push for theoretical perfection (round 5+ surfaces nothing).

### Force-Merge / Direct-Push Forbidden

Even with user authorization, NEVER:

- Force-push to `main`.
- Direct push to `main` (every change goes through PR).
- Merge a red-CI PR.
- Merge a PR whose subject violates [`.commitlintrc.yaml`](../.commitlintrc.yaml) — the config's rules, not a stricter house preference.

### Recovery

If a merged commit on `main` has a defect:

1. Open a new PR (revert via `git revert -m 1 <merge-sha>`).
2. Attach the original PR # in the description for context.
3. Run through normal review.

NEVER force-push to `main` to "undo" a merge.

## Dependency Updates

Coffer runs **Dependabot security updates only**. There is no
`.github/dependabot.yml`, so no routine version-bump PRs are opened.

Why: the repository requires branches to be up to date before merging and does
not allow auto-merge, so every bot PR costs a manual branch update, a full CI
round, and a merge — and merging any one of them invalidates the rest, forcing
them through strictly serially. For a single-maintainer, local-first tool, that
recurring cost is not repaid by patch and minor bumps. Major upgrades that
actually matter (the mcp 2.x SDK, for instance) are done by hand against the
changelog anyway.

Security updates are unaffected: they are a separate repository setting
(Settings → Code security), not driven by the deleted config file, so a real
advisory still opens a PR.

Bumping a dependency by hand is an ordinary `chore(deps)` PR.
