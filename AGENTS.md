# AGENTS.md

Operating manual for AI agents (Claude Code, Codex, future ones) entering Coffer. Read at session start.

## 1. At a Glance

| Property            | Value                                                                                              |
| ------------------- | -------------------------------------------------------------------------------------------------- |
| **Project**         | Coffer — local-first AI agent vault. Single-user, one vault across the user's machines. OSS-bound. |
| **Methodology**     | [OpenSpec](https://github.com/Fission-AI/OpenSpec).                                                |
| **Languages**       | Python 3.12+ (backend); TypeScript / React (frontend).                                             |
| **Source of truth** | `docs/principles.md` (principles); `openspec/specs/` (product contracts).                          |
| **Default branch**  | `main`.                                                                                            |
| **License**         | MIT.                                                                                               |

## 2. Files to Read at Session Start

In order:

1. **`docs/principles.md`** — lasting principles + invariants.
2. **`AGENTS.md`** (this file).
3. The relevant **`.agents/<topic>.md`** for today's scope:
   - [`.agents/openspec.md`](./.agents/openspec.md) — OpenSpec layout, the change workflow, acceptance scenarios, end-to-end deliverable rule.
   - [`.agents/workflow.md`](./.agents/workflow.md) — branches, Conventional Commits, AI signatures, PR flow, merge policy.
   - [`.agents/stack.md`](./.agents/stack.md) — backend (Python / FastAPI / SQLite). Includes file-size limits, layered-architecture import rules, wire-contract rule.
   - [`.agents/frontend.md`](./.agents/frontend.md) — frontend (React / TypeScript / Vite). State management, API layer, query keys, hooks, design-system and i18n conventions.
   - [`.agents/visual-language.md`](./.agents/visual-language.md) — the UI's visual language: the Tailwind-config tokens for spacing, colour, radius, typography and container width, and the conventions for reusing them instead of ad-hoc values.
   - [`.agents/testing.md`](./.agents/testing.md) — 4 test tiers (unit / integration / contract / e2e), acceptance markers, mocking philosophy.
   - [`.agents/harness.md`](./.agents/harness.md) — agent control layer: `.claude/` hooks, permissions, and the OpenSpec commands and skills.
4. The relevant **`openspec/specs/<capability>/spec.md`** — for any work that touches a capability.

If sources disagree: **principles win.** Flag inconsistency to the user.

## 3. Session Protocol

```
1. confirm today's scope back to the user
2. open the right branch (see .agents/workflow.md)
3. behaviour change? start an OpenSpec change first (/opsx:propose)
4. work in small, committable chunks (one logical change per commit)
5. archive the change (/opsx:archive) in the same PR, before it merges
6. before opening PR: make verify
7. squash to one commit before final push
8. open PR — STOP at PR-opened, wait for explicit user merge instruction
```

**Hard stops within a session:**

- 25 substantial messages with no committed checkpoint → stop and triage with the user.
- Tool failure repeating 3 times → stop, investigate root cause, do not retry blindly.
- Any conflict with the principles or these rules → stop, ask, do not work around.

## 4. Decide vs Ask

The user has delegated architectural authority. **Default to deciding and explaining.** Don't over-ask.

| Decision                                                                    | Action                                                                                                                                                     |
| --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Architecture / scope within a spec / tech choice                            | **Decide.** Document in the change's `design.md` or `docs/decisions/<short-kebab-case-title>.md`.                                                          |
| Naming / API shape within a single capability                               | **Decide.** Document in the change's `design.md`.                                                                                                          |
| Adding/removing a feature spec                                              | **Pause.** User confirmation.                                                                                                                              |
| Releasing a tag                                                             | **Pause.** User confirmation.                                                                                                                              |
| Force push / rebase published branches / delete branches with unmerged work | **Pause.** Always confirm.                                                                                                                                 |
| `git push origin main` (direct)                                             | **Never.** Always go through PR.                                                                                                                           |
| Merging an open PR                                                          | **Pause** unless user explicitly authorized ("merge it" / equivalent direct instruction). See [`.agents/workflow.md`](./.agents/workflow.md) "Merge Policy". |

## 5. Common Commands

```bash
make install                # one-time: venv + backend deps
make verify                 # fast path (lint + unit + integration + contract + acceptance)
make verify-all             # adds e2e
make dev                    # backend (:8000) + frontend (:5173)

git checkout -b feature/<short-name>
git add <files> && git commit -m "feat(<scope>): <subject>"
git push -u origin feature/<short-name>
gh pr create --fill --base main
```

Detail under [`.agents/workflow.md`](./.agents/workflow.md) and [`.agents/testing.md`](./.agents/testing.md).

## 6. Maintaining `.agents/`

Split a topic file into a subfolder ONLY when **both** of these hold:

1. The file exceeds **~300 lines**.
2. It has **distinct sub-topics** a reader would bookmark separately.

Until both hit, keep flat. Example: split `stack.md` into a subfolder only when it outgrows ~300 lines AND its sections are independently long-form; update §2's links accordingly.

## 7. Docs Language

Every doc in this repo is written in **English only**. There are no translation
companions: no `.zh.md` files, no per-language mirror under `docs-site/`. A doc
that needs to change is changed in place, in English.

This applies to prose docs (`README.md`, `AGENTS.md`, `CONTRIBUTING.md`,
`SECURITY.md`, `.agents/**`, `docs/**`, `openspec/**`) and to
the published site (`docs-site/**`). It does **not** apply to the Coffer web
UI's own interface copy — the app ships English and 中文 through
`frontend/src/i18n/locales/`, and that language switcher is a product feature
(see [`.agents/frontend.md`](./.agents/frontend.md)).
