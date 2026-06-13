# ADR-019: Close the Eval Flywheel (Loop Engineering)

**Status**: Accepted
**Date**: 2026-06-14
**Deciders**: Yuxing Wu
**Related**: [ADR-017](ADR-017-industrial-grade-harness-in-layers.md) (harness in layers), [ADR-018](ADR-018-tool-retrieval-for-overload.md) (tool retrieval), `evals/README.md`, `.specify/memory/roadmap.md`

## Context

ADR-017 built the harness in layers and anchored **loop engineering** as the
project *above* it: the harness decides what the agent CAN do (static — tools,
context, guardrails); the loop decides what it DOES NEXT and WHEN IT STOPS
(dynamic — verification timing, replanning, termination). For Coffer, "loop
engineering" is concretely the **AI-assisted development-time loop that builds
Coffer's own code** — not a runtime agent loop.

That development loop already has a strong deterministic spine: `/coffer-spec`
(frame) → `writing-plans` (plan) → TDD (set the bar) → Claude Code (act) →
`make verify` (4 tiers + import-linter + acceptance audit) → `/code-review` →
CI-gated PR (integrate). The inner edit-verify loop and the loop-control
(replan / escalate / stop / budget) are **deliberately delegated to Claude Code +
superpowers** — building a bespoke implement-until-green driver would be
cargo-cult for a solo project.

The part that is **open** is the quality flywheel for Coffer's *non-deterministic*
behaviour — tool-routing, retrieval, chat. ADR-017's Layer D shipped `evals/` as
a **regression instrument**: ~8 hand-authored cases per suite, a committed
baseline, and a relative-regression gate (`evals/run.py`). But it is only an
instrument; the flywheel around it is not connected:

- **Capture is missing.** Nothing turns real usage into eval cases. Worse, the
  capture source that *should* exist — the `mcp_invocations` log — was dishonest:
  an upstream **in-band tool error** (a well-formed `CallToolResult` with
  `isError: True`, which does not raise) was recorded as `status=ok`. A log that
  cannot tell success from failure is useless as a capture source.
- **Curation is missing.** No path turns a captured trace into a golden case.
- **The gate is off the dev path.** `make eval` lives outside `make verify` and
  CI; there is no `evals.yml`.
- **Feedback is undocumented.** The loop that turns a production failure into a
  permanent regression test does not close.

## Decision

Close the eval flywheel for Coffer's non-deterministic surfaces, as an
ADR-tracked engineering project (tooling, not a product spec — exempt from the
FE+BE+real-usage spec-deliverable rule, like ADR-017). Build it in **ordered,
independently shippable slices**:

```
real usage ─▶ [honest invocation log] ─▶ [capture sink] ─▶ [curate] ─▶ datasets
                                                                          │
   quality ◀── re-baseline ◀── fix ◀── regression caught ◀── [eval gate] ◀┘
```

- **Slice 1 — Honest capture foundation.** Make the invocation log truthful: an
  in-band `isError` tool result is recorded as `status=error`, not `ok`. The
  error text is upstream-controlled (may echo secrets) so only a fixed
  Coffer-authored marker is persisted, never the result content (preserves
  SC-010 and the roadmap non-goal "argument/result content stays out of the DB").
  *Shipped with this ADR.*
- **Slice 2 — Capture sink.** An **opt-in, dev-only, local** capture path that
  records the eval-relevant shape of real interactions (tool-routing: intent +
  catalogue snapshot + chosen tool + outcome; retrieval: query + returned doc
  ids). It is a **separate sink from the shared `~/.coffer/coffer.db`** — that
  database deliberately stores no payloads; eval curation needs the request text,
  so it gets its own gitignored local file rather than widening the audit log.
- **Slice 3 — Curate.** A small `evals` CLI that reads the sink, lets the
  developer confirm the expected answer (pre-filled from the deterministic ranker
  where one exists), and appends labelled cases to `datasets/*.jsonl`, tagged by
  provenance (real-trace vs hand-authored) and de-duplicated.
- **Slice 4 — Gate + feedback.** Put the deterministic suites (retrieval-keyword,
  tool-search — no model, free) on the dev path; add an `evals.yml` that runs the
  model-bearing routing suite on PRs touching prompts/agents/retrieval/catalogue,
  gating on **relative regression vs baseline** (reusing `run.py`). Document the
  closed loop (production failure → capture → curate → regression caught → fix →
  re-baseline) in `agents/harness.md`.
- **Adjuncts (parallelisable).** The verify-before-commit hook ADR-017 promised
  but did not build; per-branch dev DB path (fixes the cross-branch
  `~/.coffer/coffer.db` corruption).

## Consequences

- The invocation log becomes an **honest** record — the prerequisite for using it
  (and the capture sink) as eval-case sources, and a correctness fix in its own
  right.
- The eval suite stops being a static instrument and becomes a **flywheel**: real
  usage grows the dataset, and the gate prevents silent regression of the
  highest-value, least-deterministic behaviour.
- The flywheel's product is a **trustworthy "what to fix" signal plus a
  regression guardrail** — not an autopilot. The optimisation act (decide the
  fix, implement, ship) stays with the human + Claude Code inner loop.
- **Deferred, anchored: regression→repair assist.** A future, **human-triggered**
  command could hand a caught regression (failing case + context) to Claude Code
  in a worktree to attempt a fix, with the human reviewing and merging. It is
  *not* built here: auto-"making the eval pass" invites overfitting to the metric
  (gaming), and unattended merge violates the no-AI-merge rule. The capture/gate
  built here is its prerequisite, so the seam is left clean.

## Alternatives Considered

- **Build the semi-autonomous repair loop now.** Rejected: it consumes the
  flywheel's signal, so the measurement flywheel must exist first regardless; and
  auto-greening a non-deterministic eval risks metric gaming — a dishonest
  portfolio artifact. Anchored as a deferred, human-triggered follow-up instead.
- **Capture into the existing `mcp_invocations` table.** Rejected: that table is
  a privacy-bounded audit log (who/when/how-long/outcome, no payloads). Eval
  curation needs the request content, so it gets a separate opt-in local sink
  rather than widening a deliberately-narrow audit surface.
- **Put the routing eval in core `make verify` / CI.** Rejected: it needs a model
  endpoint and is non-deterministic; the determinism-free suites join the dev
  path, routing rides a separate, narrowly-triggered `evals.yml`.
- **Model loop engineering as a numbered product spec.** Rejected: it is
  engineering tooling like ADR-017, not a user-facing increment; an ADR with
  ordered slices fits.
