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
