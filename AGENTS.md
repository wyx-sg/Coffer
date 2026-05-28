# AGENTS.md

> 中文版: [AGENTS.zh.md](./AGENTS.zh.md)

Operating manual for AI agents (Claude Code, Codex, Cursor, future ones) entering Coffer. Read at session start.

## 1. At a Glance

| Property            | Value                                                                         |
| ------------------- | ----------------------------------------------------------------------------- |
| **Project**         | Coffer — local-first AI agent vault. Single-user. OSS-bound.                  |
| **Methodology**     | Spec-Driven Development (SDD) with Speckit.                                   |
| **Languages**       | Python 3.12+ (backend), TypeScript 5.x (frontend).                            |
| **Source of truth** | `.specify/memory/constitution.md` (principles); `specs/` (product contracts). |
| **Default branch**  | `main`.                                                                       |
| **License**         | MIT.                                                                          |

## 2. Files to Read at Session Start

In order:

1. **`.specify/memory/constitution.md`** — lasting principles + invariants.
2. **`AGENTS.md`** (this file).
3. The relevant **`agents/<topic>.md`** for today's scope:
   - [`agents/sdd.md`](./agents/sdd.md) — spec folder layout, acceptance scenarios, end-to-end deliverable rule.
   - [`agents/workflow.md`](./agents/workflow.md) — branches, Conventional Commits, AI signatures, PR flow, merge policy.
   - [`agents/stack.md`](./agents/stack.md) — backend (Python / FastAPI / SQLite) + frontend (TS / React / Vite / Tailwind / shadcn). Includes file-size limits, layered-architecture import rules, wire-contract rule.
   - [`agents/testing.md`](./agents/testing.md) — 4 test tiers (unit / integration / contract / e2e), acceptance markers, mocking philosophy.
4. The relevant **`specs/<NNN>-<short-name>/spec.md`** — for any spec-touching work.

If sources disagree: **constitution wins.** Flag inconsistency to the user.

## 3. Session Protocol

```
1. confirm today's scope back to the user
2. open the right branch (see agents/workflow.md)
3. work in small, committable chunks (one logical change per commit)
4. before opening PR: make verify
5. squash to one commit before final push
6. open PR — STOP at PR-opened, wait for explicit user merge instruction
```

**Hard stops within a session:**

- 25 substantial messages with no committed checkpoint → stop and triage with the user.
- Tool failure repeating 3 times → stop, investigate root cause, do not retry blindly.
- Any conflict with the constitution or these rules → stop, ask, do not work around.

## 4. Decide vs Ask

The user has delegated architectural authority. **Default to deciding and explaining.** Don't over-ask.

| Decision                                                                    | Action                                                                                                                                                     |
| --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Architecture / scope within a spec / tech choice                            | **Decide.** Document in spec's `plan.md` or `docs/decisions/ADR-NNN.md`.                                                                                   |
| Naming / API shape within a single spec                                     | **Decide.** Document in spec's `plan.md`.                                                                                                                  |
| Adding/removing a feature spec                                              | **Pause.** User confirmation.                                                                                                                              |
| Releasing a tag                                                             | **Pause.** User confirmation.                                                                                                                              |
| Force push / rebase published branches / delete branches with unmerged work | **Pause.** Always confirm.                                                                                                                                 |
| `git push origin main` (direct)                                             | **Never.** Always go through PR.                                                                                                                           |
| Merging an open PR                                                          | **Pause** unless user explicitly authorized ("merge it" / equivalent direct instruction). See [`agents/workflow.md`](./agents/workflow.md) "Merge Policy". |

## 5. Common Commands

```bash
make install                # one-time: venv + backend + frontend deps
make verify                 # fast path (lint + unit + integration + contract)
make verify-all             # adds e2e
make dev                    # backend (:8000) + frontend (:5173) in parallel

git checkout -b feature/<short-name>
git add <files> && git commit -m "feat(<scope>): <subject>"
git push -u origin feature/<short-name>
gh pr create --fill --base main
```

Detail under [`agents/workflow.md`](./agents/workflow.md) and [`agents/testing.md`](./agents/testing.md).

## 6. Maintaining `agents/`

Split a topic file into a subfolder ONLY when **both** of these hold:

1. The file exceeds **~300 lines**.
2. It has **distinct sub-topics** a reader would bookmark separately.

Until both hit, keep flat. Example: split `stack.md` into `agents/stack/{backend,frontend}.md` only when it outgrows ~300 lines AND backend / frontend sections are independently long-form; update §2's links accordingly.

## 7. Bilingual Docs Rule

Every prose doc in this repo ships as a pair: the English source of truth next to a Chinese translation companion. Every existing English doc already has its `.zh.md` companion; new docs MUST be created in pairs.

**Path convention.** Strip the `.md` extension, append `.zh.md`. The companion lives in the same directory. NEVER append `.zh.md` to a filename that still ends in `.md` (no `CLAUDE.md.zh.md` — it is `CLAUDE.zh.md`).

```
AGENTS.md            ↔  AGENTS.zh.md
CLAUDE.md            ↔  CLAUDE.zh.md        (not CLAUDE.md.zh.md)
agents/sdd.md        ↔  agents/sdd.zh.md
docs/quickstart.md   ↔  docs/quickstart.zh.md
specs/001-…/spec.md  ↔  specs/001-…/spec.zh.md
```

**Scope — applies to.**

- `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`.
- Everything under `agents/`.
- `docs/**/*.md` (quickstart, decisions/ADRs, etc.).
- `specs/**/*.md` EXCEPT `tasks.md` (spec.md, plan.md, research.md, data-model.md, quickstart.md).
- `.specify/memory/*.md` (constitution, architecture, roadmap).

**Scope — does NOT apply to.**

- Code, code comments, identifiers, JSON/YAML config.
- Conventional Commit messages, branch names, PR titles/descriptions — stay English (see [`agents/workflow.md`](./agents/workflow.md)).
- Auto-generated artifacts (OpenAPI yaml, lockfiles, build output).
- Tool scaffolding meant to be filled in by automation, not read end-to-end as prose — e.g. `.specify/templates/*.md` (Speckit scaffold templates), `specs/*/tasks.md` (AI/coder task checklist), `.github/PULL_REQUEST_TEMPLATE.md` (GitHub auto-prefill).
- Trivial pointer / marker files with no substantive content — e.g. `CLAUDE.md` (one-liner pointing at `AGENTS.md`).
- Anything outside the repo (Claude Code skills, harness configs, etc.).

**Authoring rules.**

1. English file is the source of truth. Edit it first; translate after.
2. Any commit that adds or changes an English doc MUST update its `.zh.md` companion in the same commit. Reviewers MUST reject commits that drift the two out of sync.
3. Any commit that adds a NEW English doc MUST also add the `.zh.md` companion. No "translate later" stubs.
4. Headings, anchors, and link targets stay in sync — link to the English file from prose; readers switch languages via the companion file, not via deep links.
5. Keep code blocks, file paths, command snippets, and identifiers verbatim in the Chinese version — only translate the prose.

**Discoverability.** Cross-link the pair at the top of each file: English file says `中文版: [<name>.zh.md](./<name>.zh.md)`; Chinese file says `English: [<name>.md](./<name>.md)`.
