# Competitive Research — AI Agent Evaluation & the Eval Flywheel

> English: this file · 中文版: [agent-evaluation.zh.md](./agent-evaluation.zh.md)
>
> Internal competitive-research report for Coffer's eval direction (ADR-019
> "close the eval flywheel", ADR-017 AI-eval layer). **Date:** 2026-06-16.
> **Method:** deep-research harness (this run read Coffer's repo to verify state;
> several findings 3-0 confirmed).
>
> **Correction to the brief.** The premise that Coffer's eval is "largely a
> blueprint, not yet built" is **partly outdated.** ADR-019 is **Accepted
> (2026-06-14)** and a working local-first `evals/` harness has **shipped** —
> deterministic retrieval + tool-search suites, a pluggable-model tool-routing
> suite, committed baselines with a relative-regression gate, an `evals.yml` CI
> workflow, an opt-in gitignored capture sink (`COFFER_EVAL_CAPTURE`), and an
> interactive `curate.py` promoting captured tool-search traces into golden cases.

## 1. Landscape at a glance

The 2026 eval market has **converged on one architecture**, and all eight tools
implement it to varying degrees:

> **capture** production traces → **score** them (deterministic code checks +
> LLM-as-judge, RAG faithfulness/groundedness, tool-use correctness) → **curate**
> interesting / low-scoring / negatively-rated traces into **golden datasets** →
> **gate** offline evals in CI against those datasets → redeploy → **re-measure**
> online.

| Tier                              | Tools                                                                                     | Note                                                |
| --------------------------------- | ----------------------------------------------------------------------------------------- | --------------------------------------------------- |
| **Complete commercial flywheels** | Braintrust, LangSmith                                                                     | one-click trace→dataset, online LLM-judge, CI gates |
| **OSS pillars**                   | DeepEval (Apache-2.0), Promptfoo (MIT — **OpenAI-acquired Mar 2026**), Ragas (Apache-2.0) | local-first, CI-friendly                            |
| **Observability + eval**          | Galileo, Arize Phoenix                                                                    | less directly evidenced this run                    |

### The players

- **Braintrust** — the most complete commercial flywheel. Captures every
  production trace; runs **LLM-as-judge online scoring** automatically/async with
  no app-latency impact and no ground truth; **add any trace to a dataset with
  one click**; evaluates agents end-to-end _and per-step_ including **tool-use
  correctness** (right tool, plan coherence, correct arguments); and **gates
  offline evals on every PR** via a shipped GitHub Action (`braintrustdata/
eval-action`) that blocks merges below thresholds. _Nuance:_ trace→dataset
  promotion is human-curated; online scoring is on once a scoring rule + sampling
  rate are configured, not by default. [confirmed 3-0]
- **LangSmith** — an explicitly _closed_ flywheel: "online evals surface issues →
  become offline test cases → offline evals validate fixes → online evals confirm
  production improvements." Converts production traces (incl. **negative-feedback
  runs**) into dataset examples (one-click "Add to Dataset" + auto run-rules).
  Four evaluator types — **human** (annotation queues with rubrics), **code**,
  **LLM-as-judge** (reference-free or reference-based), **pairwise** — and
  **uniquely calibrates LLM judges against human labels ("Align Evals,"** an
  alignment score = % match with human experts). [confirmed 3-0]
- **DeepEval** (`confident-ai`, Apache-2.0) — local-first, **pytest-style** eval,
  paired with the commercial Confident AI cloud. The OSS default for CI evals.
- **Promptfoo** (MIT open-core, **acquired by OpenAI March 2026**) — declarative
  prompt/agent test matrices; strong CI integration.
- **Ragas** (Apache-2.0) — **reference-free RAG metrics** (faithfulness, answer
  relevancy, context precision/recall).
- **Galileo / Arize Phoenix** — round out the commercial / OSS-observability side.

## 2. Capability comparison

| Capability                | Braintrust  | LangSmith          | DeepEval  | Promptfoo | Ragas    | **Coffer evals/**                          |
| ------------------------- | ----------- | ------------------ | --------- | --------- | -------- | ------------------------------------------ |
| Deterministic checks      | ✅          | ✅                 | ✅        | ✅        | —        | **✅ retrieval + tool-search suites**      |
| LLM-as-judge              | ✅ online   | ✅ 4 types         | ✅        | ✅        | ✅ (RAG) | **❌ not yet**                             |
| RAG faithfulness metrics  | ✅          | ✅                 | ✅        | partial   | **✅**   | **❌**                                     |
| Tool-use correctness      | ✅ per-step | ✅                 | ✅        | ✅        | —        | **✅ tool-routing suite**                  |
| Golden datasets           | ✅          | ✅                 | ✅        | ✅        | ✅       | **✅ committed baselines**                 |
| CI regression gate        | ✅ Action   | ✅                 | ✅ pytest | ✅        | ✅       | **✅ `evals.yml` + relative gate**         |
| Online → dataset capture  | ✅ 1-click  | ✅ 1-click + rules | via cloud | —         | —        | **✅ `COFFER_EVAL_CAPTURE` + `curate.py`** |
| Human annotation queues   | partial     | ✅                 | via cloud | —         | —        | **❌**                                     |
| Judge↔human calibration  | —           | **✅ Align Evals** | —         | —         | —        | **❌**                                     |
| Local-first / no-payloads | cloud       | cloud              | **✅**    | **✅**    | **✅**   | **✅ local-first, no payloads**            |
| OSS                       | Action only | ❌                 | ✅        | ✅        | ✅       | ✅                                         |

## 3. How Coffer compares

**Coffer has independently built a minimal version of exactly the loop these
tools sell.** The shipped `evals/` harness already does capture
(`COFFER_EVAL_CAPTURE`) → curate (`curate.py` promotes traces to golden cases) →
dataset (committed baselines) → gate (`evals.yml` + relative-regression), scoped
**local-first and no-payloads** (consistent with the invocation log's
who/when/duration/outcome, no args/results). That is the Braintrust/LangSmith
flywheel, deliberately privacy-scoped.

**Where Coffer is already aligned.**

1. **The flywheel shape matches.** capture → curate → golden → CI-gate is exactly
   the converged architecture; Coffer built it without the cloud.
2. **Deterministic + tool-use suites** (retrieval, tool-search, tool-routing)
   mirror the deterministic and tool-use-correctness checks the leaders run.
3. **No-payloads is a principled differentiator** — the commercial tools capture
   full traces (prompts/outputs) to the cloud; Coffer's metadata-only capture is
   on-mission for a local-first vault.

**Where Coffer lags — concrete borrows.**

1. **No LLM-as-judge.** Every leader uses LLM-as-judge for open-ended quality
   (chat answers, RAG faithfulness) where deterministic checks can't reach.
   Coffer's internal model (ADR-024) could run a **local LLM-judge** over chat /
   `ask` outputs — no cloud needed.
2. **No RAG-faithfulness metrics.** Ragas-style reference-free metrics
   (faithfulness, context precision) fit Coffer's KB directly and need no golden
   answers.
3. **No human-feedback loop / judge calibration.** LangSmith's Align Evals
   (calibrate the judge against human labels) and negative-feedback-driven
   capture are the strongest patterns to borrow — a thumbs-down in chat could
   auto-capture the trace into the eval sink.
4. **Invocation log + transcript distillation are an untapped capture source.**
   ADR-020 transcript distillation already reads local transcripts; feeding the
   invocation log + distilled transcripts into the same `COFFER_EVAL_CAPTURE`
   sink would widen the flywheel beyond tool-search.

## 4. Key takeaways for Coffer

1. **Update the framing: the flywheel is shipped, not a blueprint.** ADR-019 is
   Accepted and `evals/` implements capture→curate→golden→gate locally — lead
   with "we built the privacy-scoped version of Braintrust/LangSmith's loop."
2. **Add a local LLM-as-judge** (via the ADR-024 internal model) for open-ended
   quality where deterministic checks can't reach — the single biggest gap.
3. **Add Ragas-style reference-free RAG metrics** for the KB / `ask` — no golden
   answers required, directly applicable.
4. **Borrow negative-feedback capture + judge calibration** (LangSmith): a chat
   thumbs-down auto-captures into the eval sink; calibrate the local judge against
   the user's own labels.
5. **Wire the invocation log + ADR-020 transcripts into the capture sink** to
   broaden the flywheel beyond tool-search.

## 5. Sources

Primary:

- braintrust.dev — articles/how-to-eval, docs/evaluate, docs/evaluate/score-online, docs/best-practices/agents · github.com/braintrustdata/eval-action
- docs.langchain.com/langsmith — evaluation-concepts, manage-datasets-in-application · langchain.com/langsmith/evaluation · langchain.com/resources/llm-evals
- github.com/confident-ai/deepeval · promptfoo.dev (OpenAI acquisition, Mar 2026) · github.com/explodinggradients/ragas
- Galileo (galileo.ai) · Arize Phoenix (docs.arize.com/phoenix)

Coffer repo verified: `evals/` (suites, baselines, `curate.py`), `.github/workflows/evals.yml`, ADR-019, ADR-017.

## Verification update (2026-06-19)

> Re-verification pass: Coffer's local eval-flywheel claims all check out against
> the repo; web claims are mostly confirmed, with one correction (Braintrust's
> `eval-action` reports rather than gates) and two coverage adds (Galileo,
> Arize Phoenix).

### ✅ Confirmed

- **The shipped eval flywheel.** `evals/` holds deterministic suites
  (`retrieval_eval.py`, `tool_search_eval.py`) plus a model-bearing routing suite
  (`routing_eval.py`, kept out of CI); the `COFFER_EVAL_CAPTURE` JSONL sink is
  off by default — emit side `record_tool_search` in
  `repo:backend/coffer/application/eval_capture.py`, handler in
  `repo:backend/coffer/infrastructure/logging/eval_capture.py`, wired into
  `coffer__search_tools` via `repo:backend/coffer/application/mcp/gateway_builtin.py`;
  interactive `repo:evals/curate.py` promotes captured traces into
  `datasets/tool_search.jsonl`.
- **Committed baselines + relative-regression CI gate.**
  `evals/baselines/{retrieval,tool_search,routing}.json` exist; `repo:evals/run.py`
  gates on `floor = baseline - tolerance` (retrieval 0.01 / tool_search 0.05 /
  routing 0.10) with non-zero exit on regression; `repo:.github/workflows/evals.yml`
  runs the deterministic model-free retrieval + tool-search gate on PRs,
  path-filtered (routing suite is on-demand only).
- **ADR statuses underpinning the borrows.** ADR-019 (close the eval flywheel)
  Accepted, 2026-06-14; ADR-020 (transcript distillation) Accepted — borrow #4 /
  takeaway #5; ADR-024 (built-in agent is internal capability) Accepted,
  2026-06-14 — local LLM-judge borrow #1.
  `repo:docs/decisions/ADR-019-close-the-eval-flywheel.md`,
  `repo:docs/decisions/ADR-020-transcript-distillation.md`,
  `repo:docs/decisions/ADR-024-builtin-agent-is-internal-capability.md`
- **Promptfoo — MIT, OpenAI-acquired Mar 2026.** Acquisition announced 2026-03-09;
  Promptfoo "will remain open source ... under the current license." MIT is
  confirmed from the repo license (the announcement affirms open-source continuity
  without naming the license). https://www.promptfoo.dev/blog/promptfoo-joining-openai/ ;
  https://github.com/promptfoo/promptfoo
- **LangSmith Align Evals.** Calibrates LLM judges against human labels; alignment
  score = % of examples where the evaluator matches the human expert; UI
  corrections are stored as few-shot examples feeding future prompts — confirmed
  verbatim. https://blog.langchain.com/introducing-align-evals/ ;
  https://docs.langchain.com/langsmith/improve-judge-evaluator-feedback
- **Braintrust online scoring is opt-in.** Online scoring rules are created at the
  project level (scorers, span/trace scope, sampling rate) and run async on
  production traces with no app-latency impact — confirms "on once a scoring rule +
  sampling rate are configured, not by default."
  https://www.braintrust.dev/docs/evaluate/score-online ;
  https://www.braintrust.dev/foundations/online-scoring

### ✏️ Corrected

- **Braintrust `eval-action` reports, it does not gate.** Old: "gates offline evals
  on every PR ... that blocks merges below thresholds." → Corrected: the
  `braintrustdata/eval-action` runs evals in CI and posts an experiment-comparison
  **comment** on the PR (score deltas, regression indicators); it does **not** itself
  block merges on thresholds — merge-gating needs separate workflow/branch-protection
  controls. The per-PR offline-eval run is real; the auto-block-below-threshold claim
  is overstated. https://github.com/braintrustdata/eval-action

### ❓ Still uncertain

- **ADR-017 status nuance.** ADR-017 (industrial-grade harness in layers) is
  Status: **Proposed** (Date 2026-06-13), **not** Accepted. The report references it
  only as the "AI-eval layer" related context and never asserts it is Accepted, so
  no in-text fix is needed — flagged here per the verification brief.
  `repo:docs/decisions/ADR-017-industrial-grade-harness-in-layers.md`
- **Promptfoo license naming.** MIT is confirmed only from the repo license itself;
  the OpenAI/Promptfoo statements say "remain open source under the current license"
  without naming MIT.

### ➕ Coverage added

- **Galileo** (commercial) — Agent Reliability platform: observe / evaluate /
  guardrail / improve agents, with purpose-built agentic metrics (tool selection
  quality, tool error rate, action advancement/completion, flow adherence) and
  **Luna-2** small-LM judges (sub-200ms, ~0.95 accuracy) that make 100%-traffic
  online scoring economically feasible. **Material update the report's bare
  "Galileo (galileo.ai)" line omits: Cisco completed its acquisition of Galileo on
  2026-05-22.** https://galileo.ai/ ;
  https://blogs.cisco.com/news/cisco-announces-the-intent-to-acquire-galileo
- **Arize Phoenix** (OSS) — Apache-2.0 LLM observability + evaluation built on
  OpenTelemetry; runs locally / self-hosted / in a notebook (or Arize cloud), with
  LLM-as-judge evals (relevance, toxicity, hallucination, RAG, tool-calling). Widely
  framed as "LangSmith-level features without sending data to a third party" — the
  closest external analog to Coffer's local-first, no-payloads stance, though
  Phoenix captures full traces whereas Coffer keeps metadata-only.
  https://github.com/Arize-ai/phoenix ; https://arize.com/phoenix/
