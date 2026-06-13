# `evals/` — Coffer's AI eval harness

The deterministic test suite proves the *plumbing* works. This harness measures
the **non-deterministic AI behaviour** that ordinary tests can't pin: how good
Coffer's retrieval is, and whether a model picks the right tool. It is the
regression net for prompt/model/retrieval changes (ADR-017, Layer D).

Designed to be **local and low-cost**: the retrieval suite needs no model at
all, and the routing suite talks to a **pluggable** model — a local LLM (Ollama)
by default, or any OpenAI-compatible endpoint. The local model is a cost choice,
not a limitation: point it at a stronger model whenever you need to.

## Layout

```
evals/
├── metrics.py         # pure ranking metrics: recall@k, precision@k, MRR
├── retrieval_eval.py  # builds a real SQLite index, runs golden queries -> recall@k/MRR
├── routing_eval.py    # samples a pluggable model k× to pick a tool; accuracy + pass^k
├── run.py             # runner: scorecard + regression gate vs baselines
├── datasets/          # golden data (corpus, queries, tool catalog, routing cases)
├── baselines/         # committed baseline scores (the regression floor)
└── tests/             # unit tests for the harness itself
```

## Run it

```bash
make eval            # retrieval suite (local, deterministic) + baseline gate
make eval-routing    # also the tool-routing suite (needs a model endpoint; Ollama by default)
```

Under the hood:

```bash
python -m evals.run                    # retrieval only
python -m evals.run --routing          # + routing
python -m evals.run --update-baseline  # record current scores as the new floor
```

`run.py` exits non-zero if a suite scores below `baseline - tolerance`, so the
same command is the gate. Run it on demand (and after changing prompts, the tool
catalog, or the retrieval stack), not on every CI push — the routing suite needs
a model and is intentionally out of the core `make verify`.

## The two suites

**Retrieval** (`retrieval_eval.py`) — ingests `datasets/corpus.jsonl` into a
throwaway copy of Coffer's real `SqliteKnowledgeIndex`, runs the
`datasets/retrieval.jsonl` queries through `keyword_search`, and scores
**recall@k** and **MRR** at the document level. Keyword/FTS mode needs no
embedding model, so it is fully deterministic and free.

**Tool routing** (`routing_eval.py`) — gives the model the tool catalogue
(`datasets/tool_catalog.jsonl`) plus a user request and asks for the single best
tool, graded against `datasets/tool_routing.jsonl`. Because tool choice is
non-deterministic, each case is sampled `k` times (default 3) and reported as
**accuracy** (mean correctness), **pass^k** (correct on *every* attempt — the
reliability bar for a production agent) and **pass@k** (correct at least once).

The model is **pluggable** — local by default to keep it free, swappable to any
model on demand:

| env var | default | meaning |
| --- | --- | --- |
| `COFFER_EVAL_PROVIDER` | `ollama` | `ollama`, or `openai` for any OpenAI-compatible API |
| `COFFER_EVAL_MODEL` | `qwen2.5:0.5b` | model name |
| `COFFER_EVAL_BASE_URL` | provider default | endpoint base URL (LM Studio, vLLM, OpenAI, …) |
| `COFFER_EVAL_API_KEY` | — | bearer token for OpenAI-compatible endpoints |

A small local model gets some cases wrong — an honest score; point
`COFFER_EVAL_*` at a stronger model and the harness tracks the gain.

## Extending

- **Add cases:** append lines to the relevant `datasets/*.jsonl`, then
  `make eval` (or `--update-baseline` to re-record the floor).
- **Local vector embeddings (optional):** the retrieval suite uses keyword mode.
  Coffer's vector path uses `fastembed` (in-process, no network) but needs a
  Python 3.12 environment with `onnxruntime` wheels — it does **not** install on
  3.14. On 3.12 you can extend `retrieval_eval.py` to also score `mode="vector"`.
- **A stronger judge / more suites:** the `run.py` scorecard + baseline pattern
  generalises — add a suite that returns the same `{suite, primary, n, cases}`
  shape and it slots into the gate.
