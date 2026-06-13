# ADR-017: Industrial-Grade Harness, Built in Layers

**Status**: Proposed
**Date**: 2026-06-13
**Deciders**: Yuxing Wu
**Related**: `.specify/memory/constitution.md`, [`agents/testing.md`](../../agents/testing.md), [`agents/workflow.md`](../../agents/workflow.md), [ADR-014](ADR-014-channel-adapter-framework.md), [ADR-016](ADR-016-multi-machine-sync.md), specs `009-channels` / `010-sync`

## Context

"Harness" is the scaffolding wrapping a core execution body so it can be driven
reliably, repeatably, and observably. Three distinct things wear the name, and
conflating them has cost us clarity:

1. **Agent-runtime harness (①)** — the runtime wrapping an LLM (tools, context
   management, agentic loop, guardrails). For our coding agents this is Claude
   Code / Codex — we *consume* it, we don't build it. Coffer will one day grow
   its *own* internal one (see Consequences → deferred layers).
2. **Engineering harness (②)** — the classical scaffolding around code that makes
   it buildable/testable/runnable in a controlled, repeatable, observable way
   (Makefile `verify`, the 4 test tiers, pre-commit, CI). For humans and CI.
3. **Agent-facing harness (③)** — the scaffolding that lets a coding *agent* work
   in this repo reliably and safely (AGENTS.md, `agents/*.md`, `.specify/memory`,
   ADRs). The interface between ① and our project knowledge.

The unifying principle across all three is one line: **make the right thing the
easy thing; make feedback fast, deterministic, and legible.** The best state is
②③ converging — one set of deterministic, single-command, observable plumbing
that humans, CI, and agents all call.

Coffer's ② (feedback) and ③ (knowledge) layers are already strong: a shared
`make verify`, integration-heavy 4-tier tests with mechanically-enforced unit
purity, pre-commit (ruff/prettier/commitlint), CI, and a best-in-class knowledge
surface (AGENTS.md + `agents/*.md` + constitution/architecture/roadmap + bilingual
ADRs). Against an industrial-grade bar, four gaps remain — and they cluster, not
scatter:

- **(A) Control layer is empty.** `.claude/settings.json` is unset; there are no
  checked-in hooks, skills, or permission rules. The agent-facing harness is
  purely *documentary* (relies on the agent reading AGENTS.md) — passive, not
  enforced.
- **(B) Hermeticity leaks.** No `uv.lock` is committed (the `make lock` target
  exists but its output is not in the repo); the dev DB is a single shared
  `~/.coffer/coffer.db` that breaks across branches with divergent migrations;
  the build env depends on an unpinned host toolchain.
- **(C) The "actually works" rungs are missing.** Every tier runs against fakes.
  Specs 009 (channels), 010 (sync), and the CLI-agent chat all merged with
  fake-API coverage and *real usage left to manual, out-of-band verification* —
  a recurring debt. Green in a sealed loop ≠ works against real Telegram/SeaTalk/
  git remotes.
- **(D) No AI eval harness.** Coffer is an AI product (tool-routing aggregator +
  chat agents) whose most important behavior is non-deterministic, yet there is
  no eval suite. Exact-match assertions can't cover tool-selection quality or
  chat quality; `langsmith` is already a dependency but unused for evals.

## Decision

Treat the harness as an explicit **five-layer stack** and, in this project
(Project 1 of three — see Consequences), close the four gaps above. Each layer
is an independently shippable subtask under this ADR, sequenced **A → B → C → D**
(highest-ROI/most-independent first, determinism foundation before the loops that
depend on it). This is **tooling, not a product feature** — it is recorded as an
ADR with per-layer subtasks and is exempt from the spec-deliverable rule
(FE+BE+real-usage) that governs product specs.

```
observability  canonical log line + append-only audit            (optional follow-up)
    ↑
feedback ②     single-command verify + test pyramid + (later) DORA  (already strong)
    ↑
real           adapter→fake→contract test→scheduled smoke vs real    ← Gap C
    ↑
determinism    lockfile + pinned toolchain + devcontainer + per-branch DB  ← Gap B
    ↑
knowledge ③    single source of truth + progressive disclosure       (already strong)
    ↑
control ③      hooks + permissions + repo skills (.claude/)           ← Gap A
    +
eval (AI)      golden dataset + code/LLM-judge graders + CI regression gate  ← Gap D
```

Per-layer decisions (the *what* and *why*; the *how* lives in the implementation
plan):

- **A — Control (`.claude/`, checked in).** `settings.json` with `permissions`
  (allow common safe commands to cut approval friction; deny destructive ones as
  defense-in-depth) plus `hooks`: `PostToolUse` auto-formats edited `*.py`/`*.ts`
  with the same tools pre-commit uses; `PreToolUse` blocks dangerous Bash and
  guards commits against a stale `make verify`; `SessionStart` injects
  branch/spec/worktree context (mirrors the AGENTS.md session protocol). Repo
  `skills/` (`/coffer-verify`, `/coffer-spec`) — *skills*, because
  `.claude/commands/` is gitignored. A new `agents/harness.md` (+ `.zh`) documents
  the layer; AGENTS.md/CLAUDE.md point to it (single source of truth).
- **B — Hermeticity.** Commit `uv.lock` + `.python-version`; add a
  `.devcontainer/` (uv + node + playwright) to kill "works on my machine" and the
  internal-mirror trap; derive the dev/test DB path per branch so switching
  branches can't corrupt it.
- **C — Real-world.** Confirm an owned adapter at each external boundary
  (Telegram, SeaTalk, git-sync remote, each upstream MCP server); add **contract
  tests** that run one behavior suite against both the fake and the real client
  to keep fakes honest; add `make smoke` + a scheduled/manual `smoke.yml` that
  round-trips real services with throwaway accounts (VCR cassettes with a
  re-record interval where HTTP-shaped). This converts the three "real usage
  pending" debts from manual chores into one runnable command. Real
  accounts/secrets remain the user's to provide.
- **D — AI eval.** An `evals/` golden dataset (20–50 tasks: tool-routing
  correctness over the aggregated MCP catalog, chat-response quality, channel
  command handling); code-based graders where an objective signal exists,
  LLM-as-judge only where necessary; `make eval` + an `evals.yml` that gates
  PRs touching prompts/agents on *relative regression vs a baseline* (absolute
  green is the wrong bar for non-deterministic output), using pass@k. Reuse the
  existing `langsmith` dependency.

## Consequences

- The agent-facing harness becomes **enforced, not just documented** — correct
  behavior is the default path, destructive actions are blocked, and approval
  friction drops.
- A fresh clone becomes reproducible (lockfile + devcontainer), removing a class
  of flaky/"green here, red there" failures and the two standing env debts.
- The three "real usage pending" debts gain a **runnable** closing command;
  what stays on the user shrinks to providing throwaway credentials.
- Coffer gains a regression net for **non-deterministic** behavior — prompt/agent
  changes can no longer silently degrade tool-routing or chat quality.
- New obligations: hooks/CI must stay fast (a slow hook trains people to bypass
  it); the eval baseline and judge quality need periodic maintenance; smoke
  secrets need secure CI storage.
- **Deferred layers (explicitly out of scope here, anchored for later):**
  - *Project 2* — Coffer's own **internal agent runtime harness (①)**: the
    tools/context/agentic-loop/guardrails wrapping Coffer's built-in agent.
  - *Project 3* — **Loop engineering**: the layer *above* the harness. Boundary —
    the **harness decides what the agent CAN do** (static: tools, context,
    guardrails, sandbox); the **loop decides what it DOES NEXT and WHEN IT STOPS**
    (dynamic: verification timing, replanning, escalation, termination/budget).
    Its mechanics (ReAct, Reflexion, evaluator-optimizer, the eval flywheel,
    inner/outer dev loops) are established even though "loop engineering" is still
    nascent terminology. It *consumes* this harness's output: Gap D's evals are
    the flywheel's measurement instrument; Gaps A/C are its verify/check gates —
    which is why harness precedes loop.
- Observability (canonical log lines + append-only audit for credential/sync ops)
  is intentionally **not** one of the four gaps; it is a named optional follow-up.

## Alternatives Considered

- **Do nothing / keep the documentary agent harness.** Rejected: documentation
  is passive; without hooks/permissions the agent can skip conventions and run
  destructive commands, and the real-usage and eval gaps stay open.
- **One big-bang harness PR.** Rejected: the four layers have different blast
  radii and dependencies; bundling them defeats reviewability and the
  determinism-before-loops ordering. Layered subtasks under one ADR keep each
  change small and the rationale single-sourced.
- **Model the harness as a numbered product spec (full SDD).** Rejected: harness
  is engineering tooling, not a user-facing product increment; forcing it through
  the FE+BE+real-usage spec-deliverable rule misframes it. An ADR + subtasks fits.
- **Skip the AI eval layer for now.** Rejected: for an AI product the eval harness
  *is* the test harness of the most valuable, least-deterministic behavior, and
  it is the prerequisite measurement instrument for the future loop-engineering
  project. Omitting it would leave the highest-value behavior untested.
- **Build loop engineering / the runtime harness in this project.** Rejected:
  both sit above or beside this layer and depend on it existing first; sequencing
  them as Projects 2 and 3 keeps each project coherent.
