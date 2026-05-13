# Workflow — Branches, Commits, PRs, Merge Policy

Covers: branch naming, Conventional Commits, AI co-author signatures, pull-request flow, merge policy.

## Branches

### Allowed Prefixes

| Prefix | Purpose | Example |
|---|---|---|
| `feature/<short-name>` | New functionality scoped to a spec | `feature/mcp-servers-crud` |
| `fix/<short-name>` | Bug fix scoped to a spec | `fix/mcp-servers-list-cursor` |
| `docs/<short-name>` | Documentation only | `docs/contributing-rewrite` |
| `refactor/<short-name>` | Internal restructuring, no behavior change | `refactor/extract-credential-port` |
| `chore/<short-name>` | Deps, tooling, CI, project meta | `chore/upgrade-fastapi-to-0.115` |

Rules:

- Kebab-case throughout.
- The short name typically mirrors (or describes) the affected spec folder (`specs/001-mcp-servers/` → `feature/mcp-servers-...`). The numeric prefix is not required in branch names.
- Branch from up-to-date `main`: `git checkout main && git pull --ff-only && git checkout -b <prefix>/<name>`.
- Branch deleted automatically after merge (squash merge strategy).

## Commits

### Conventional Commits 1.0

```
<type>(<scope>): <subject>

<body>

<footer>
```

- **Types**: `feat | fix | docs | refactor | perf | test | build | ci | chore | revert`.
- **Scope**: descriptive name of the affected spec or area (`mcp-servers`, `clis`, `ui`, `build`, `ci`). Don't use the numeric `NNN` prefix — keep it human-readable.
- **Subject**: imperative present tense, lowercase, no period, ≤ 72 chars.

### Footer

```
Fixes #123
Refs 001-mcp-servers, 003-skills
BREAKING CHANGE: <description>
Co-authored-by: Claude <noreply@anthropic.com>
```

### Examples

```
feat(mcp-servers): aggregate upstream MCP tools through one stdio endpoint

Implements the coffer-as-MCP-aggregator behavior: registered upstream
MCP servers' tools are merged and re-exposed on the daemon's MCP HTTP
endpoint. Satisfies 001-mcp-servers acceptance scenarios 3–5.

Refs 001-mcp-servers
Co-authored-by: Claude <noreply@anthropic.com>
```

```
fix(mcp-servers): missing pagination cursor in list endpoint

Added regression test in 001-mcp-servers spec.md acceptance scenario
"list servers with cursor".

Fixes #42
Co-authored-by: Claude <noreply@anthropic.com>
```

### AI Co-author Footers

When an AI agent participates substantively in a commit, add a `Co-authored-by` footer. The email is a non-official convention (GitHub renders the footer as multi-author attribution; the email need not exist):

| Agent | Co-author email |
|---|---|
| Claude (Anthropic) | `noreply@anthropic.com` |
| Codex (OpenAI) | `noreply@openai.com` |
| Cursor | `noreply@cursor.sh` |
| Other | use the agent's documented address; otherwise the platform vendor's |

If multiple AIs collaborated on a single commit, list each `Co-authored-by:` line.

When NOT to use:
- Pure tooling output (`pip install --upgrade`) — human commits.
- Mechanical bot commits (dependabot etc.) — those carry their own bot identity.

## Pull Requests

### Standard Flow

1. Open PR from feature branch to `main`.
2. PR title follows Conventional Commits (same 72-char cap as commit subjects).
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
- **Subject + PR title 72-char cap** — keep PR title aligned with the squashed commit.
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
- Merge a PR whose subject violates commitlint.

### Recovery

If a merged commit on `main` has a defect:

1. Open a new PR (revert via `git revert -m 1 <merge-sha>`).
2. Attach the original PR # in the description for context.
3. Run through normal review.

NEVER force-push to `main` to "undo" a merge.
