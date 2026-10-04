# AGENTS.md

Operating manual for AI agents (Claude Code, Codex, future ones) entering Coffer. Read at session start.

## 1. At a Glance

| Property            | Value                                                                                              |
| ------------------- | -------------------------------------------------------------------------------------------------- |
| **Project**         | Coffer — local-first AI agent vault. Single-user, one vault across the user's machines. OSS-bound. |
| **Methodology**     | [OpenSpec](https://github.com/Fission-AI/OpenSpec).                                                |
| **Languages**       | Python 3.12+ (backend); TypeScript / React (frontend).                                             |
| **Source of truth** | `docs-site/architecture/principles.md` (principles); `openspec/specs/` (product contracts).        |
| **Default branch**  | `main`.                                                                                            |
| **License**         | MIT.                                                                                               |

## 2. Files to Read at Session Start

In order:

1. **`docs-site/architecture/principles.md`** — lasting principles + invariants.
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
4. work in small, committable chunks (one logical change per commit);
   make verify before each commit — the commit hook asks when it is stale
5. archive the change (/opsx:archive) in the same PR, before it merges
6. squash to one commit before final push
7. open PR — STOP at PR-opened, wait for explicit user merge instruction
```


**Hard stops within a session:**

- 25 substantial messages with no committed checkpoint → stop and triage with the user.
- Tool failure repeating 3 times → stop, investigate root cause, do not retry blindly.
- Any conflict with the principles or these rules → stop, ask, do not work around.

### Four-way sync: spec · code · docs · design canvas

Four things describe the product, and **changing one means changing the others in the same work item** — never as a follow-up, never "cleaned up later":

| Surface | Where |
| --- | --- |
| Spec | `openspec/specs/**` (requirements, scenarios, `data-model.md`, contracts) |
| Code | `backend/`, `frontend/`, `desktop/` (and their tests) |
| Docs, external | `README.md` + `README.zh-CN.md`, `docs-site/**` (English + `zh/`) |
| Docs, internal | `docs/decisions/` ADRs, `docs/research/`, `.agents/*`, `AGENTS.md`, `CONTRIBUTING.md` |
| Design canvas | the Claude Design canvases listed below (UI boards, kept outside the repo; see `DesignSync`) |

- A UI change (layout, copy, states, navigation, a new or removed screen) redraws the affected canvas boards in the same work item. If the code is the one that is wrong, change the code back to match the board instead.
- A change that starts in the spec, the docs or the canvas lands in the code too, and the other two.
- The canvas shows the final product only: no version labels and no planning material. The "Experimental" mark on the four experimental features (knowledge, memory, sync, model switching) is part of the product and is drawn.
- A work item is not done while any of the four disagrees with the others. Give this rule to subagents explicitly. Report a canvas change you could not make as an open item for the user rather than skipping it silently.

**The canvases** — one Claude Design artifact per sidebar group, plus one each for Foundations, the Shell and the docs site, plus the design system. A new screen goes on the canvas of the sidebar group its page sits in; anything outside the sidebar (the frame, Overview, the menu bar, the Settings modal) is the Shell canvas. Boards are numbered `<canvas>.<page>.<nn>`, so a board's number names its canvas. Read the board you are about to change before you design or change a screen, and reuse its components, spacing, colour and copy so every screen keeps one visual style; the design system canvas and [`.agents/visual-language.md`](./.agents/visual-language.md) are the style source of truth.

| # | Canvas | Covers | Link |
| --- | --- | --- | --- |
| 0 | Foundations | principles, tokens and every shared component, in seven pages (below) | <https://claude.ai/artifact/NicV38VfXwViA294jgRfBV> |
| 1 | Shell | app shell and global states, Overview, menu bar, Settings modal | <https://claude.ai/artifact/Jz7f6MqShmdWx4N7YTRm49> |
| 2 | Agents | Agents, Model providers | <https://claude.ai/artifact/NdBb9YeJXQSLq3ynUDC2Yr> |
| 3 | Run | Conversations, Channels, channel messages in SeaTalk / Telegram | <https://claude.ai/artifact/UXVgGBZBtrDx3Uqnc3ke82> |
| 4 | Capabilities | MCP servers, Custom tools, Skills, CLIs | <https://claude.ai/artifact/5bMJNV8g8TQz3CrvMEBS55> |
| 5 | Context | Knowledge, Memory | <https://claude.ai/artifact/SiJTKEXTJWKxEmT3yNJkcR> |
| 6 | System | Secrets, Activity, Usage, Sync | <https://claude.ai/artifact/GgTRNb7Ydtk3ZaTyK3vufH> |
| 7 | Docs site | docs-site pages | <https://claude.ai/artifact/LycoMx54recg7ACG1x212D> |
| — | Design System | tokens and shared components | <https://claude.ai/artifact/78ViLn9YyUszUNWhC8fyJh> |

**Foundations pages** — the Foundations canvas groups shared components by what they do, one canvas page each: 0.1 Basics (global rules and tokens: principles, brand, colour and themes, type, space, motion, focus), 0.2 Inputs & actions, 0.3 Status & feedback, 0.4 Overlays, 0.5 Layout & navigation, 0.6 Data display, 0.7 Coffer patterns (pieces that only make sense with Coffer's agents, built from the others). Place a new component by taking the first rule that fits: a global rule or token → 0.1; meaningless without Coffer's agents → 0.7; floats above the page → 0.4; lays out the page or moves between pages → 0.5; the user enters a value or triggers something → 0.2; the system reports a state → 0.3; anything else that shows data → 0.6. A new board goes at the end of its page; a board number is never changed or reused.

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
make install                # one-time: .venv from uv.lock + frontend, OpenSpec CLI and e2e npm deps
make verify                 # fast path (lint + unit + integration + contract + acceptance)
make verify-all             # adds e2e
make dev                    # backend (:38470) + frontend (:5173)

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

Two places are bilingual, English and Simplified Chinese; every other doc is
English only.

- **The docs site** (`docs-site/**`). English lives at the root and Chinese under
  `docs-site/zh/`, page for page, with the same headings and anchors. A change to
  an English page changes its `zh/` twin in the same commit.
  `scripts/check_docs_locales.py` (in `make lint`) fails when a page, a sidebar
  entry or a heading anchor exists in one tree and not the other. See
  [Contributing › Docs site in two languages](./docs-site/contributing/index.md#docs-site-in-two-languages).
- **The README**: `README.md` (English) and `README.zh-CN.md` (Chinese), each
  linking the other at the top. Change both together.

Everything else stays English only, with no translation companion: `AGENTS.md`,
`CONTRIBUTING.md`, `SECURITY.md`, `.agents/**`, `docs/**` (ADRs, research) and
`openspec/**` (specs and changes). The Coffer web UI's own interface copy is a
separate matter — the app ships English and 中文 through
`frontend/src/i18n/locales/`, and that language switcher is a product feature
(see [`.agents/frontend.md`](./.agents/frontend.md)). Use the app's Chinese terms
(`zh.json`) in the Chinese docs.
