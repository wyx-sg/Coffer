# Evals: Opt-In Capture, Hand Curation, and a Deterministic Regression Gate

**Status**: Accepted
**Date**: 2026-09-12
**Deciders**: Yuxing Wu
**Related**: [Tool Overload: List a Usage-Ranked Slice, Search the Rest](tool-overload-tier-the-list-search-the-rest.md), [Audit and Retention](audit-and-retention.md), spec mcp-gateway "Record invocations without content", spec credentials "Hold plaintext only in memory at the moment of use", research note [agent evaluation](../research/agent-evaluation.md), `evals/README.md`, `.agents/harness.md`, PR #75, PR #78, PR #79, PR #81, PR #83, PR #368

## Context

Coffer has behaviour that ordinary tests cannot pin, because there is no single
right output: which upstream tools `coffer__search_tools` ranks first for an
intent, and whether a model reading Coffer's tool descriptions picks the right
builtin. A change to the ranker, a tool description or the instructions text can
quietly make either worse while every unit test still passes.

`evals/` measures both (PR #75):

- **`tool_search`** scores the real ranker (`domain/mcp/tool_search.py`) against
  hand-written queries over a fixed catalogue (`datasets/tool_search.jsonl`,
  14 cases over `tool_search_catalog.jsonl`). It is deterministic and needs no
  model. Its primary metric is recall@3.
- **`routing`** asks a model to choose among Coffer's builtins for a request
  (`datasets/tool_routing.jsonl`), samples each case k times, and reports
  accuracy, pass@k and pass^k. It needs a model endpoint (a local Ollama model
  by default) and is non-deterministic.

`evals/run.py` compares each suite with a committed baseline
(`evals/baselines/*.json`) and fails when the primary metric falls below
`baseline − tolerance`: 0.05 for `tool_search`, 0.10 for `routing`.

The harder question is where new cases come from, and what runs where:

- Real usage is the best source of cases, but the invocation log is
  deliberately content-free (spec mcp-gateway "Record invocations without
  content"): it records target, time, duration and outcome, never arguments or
  results. It also used to be dishonest: an upstream tool that failed in-band
  (a well-formed result with `isError: true`) was logged as `ok`.
- CI must be reproducible and free. A model-bearing suite is neither.
- A retrieval suite once scored knowledge search. Knowledge became plain files
  read with ripgrep (PR #368), and scoring ripgrep would measure ripgrep, not
  Coffer, so the suite was removed.

## Options Considered

### Option A — A separate opt-in capture sink, a hand-curation CLI, and a deterministic CI gate (chosen)

**Honest outcomes.** The gateway records an in-band `isError` result as
`status=error`, storing only a fixed Coffer-written marker
(`"upstream tool returned an error result (isError)"`), never the upstream
text, which may echo secrets (`application/mcp/gateway_handlers.py`, PR #78).

**Capture.** With `COFFER_EVAL_CAPTURE` set, the gateway also emits the query
and returned tool names of each `coffer__search_tools` call to a dedicated
logger (`application/eval_capture.py`). The infrastructure side
(`infrastructure/logging/eval_capture.py`) binds a JSONL file handler to it:
`~/.coffer/eval-capture.jsonl` for a truthy flag, or the given path. Capture is
off by default, best-effort, and never touches the database or the invocation
log (PR #79).

**Curate.** `make eval-curate` (`evals/curate.py`) reads the sink, drops queries
the dataset already covers, asks the developer which returned tools were
relevant, and appends confirmed cases tagged `"source": "captured"` (PR #81).

**Gate.** `.github/workflows/evals.yml` runs `make eval` — the harness's own
tests and the `tool_search` suite — on pushes and PRs that touch `evals/`, the
MCP application or domain code, or knowledge and memory application code. It
fails on regression against the baseline (PR #83). `make eval-routing` runs the
routing suite on demand and stays out of CI. A deliberate improvement is
recorded with `python -m evals.run --update-baseline`.

Pros: real queries can become cases without widening the audit surface; the CI
gate is exact and costs nothing; the invocation log can now tell success from
failure, which is useful beyond evals; a developer decides what counts as
relevant, so no model grades itself. Cons: every step after capture is manual,
so the loop turns only when someone runs it. **So far it has not turned: no
dataset contains a captured case, and every case in `evals/datasets/` is
hand-written.** Routing quality has no automatic guard. It wins because each
piece is cheap and honest, and none of it compromises the payload-free log.

### Option B — Capture into the audit and invocation log

Store arguments and results in `mcp_invocations` and curate from there.

Pros: capture is always on, so the dataset grows without anyone opting in.
Cons: the invocation log and the audit log are content-free by design. Tool
arguments and results carry secrets, personal data and upstream content, and
the tables are retained and read from every surface ([Audit and Retention](audit-and-retention.md)).
Widening them for evals would trade a privacy guarantee for developer
convenience. It loses on that guarantee.

### Option C — LLM-as-judge in CI

Run the routing suite, or a model-graded suite, on every PR.

Pros: guards the model-facing behaviour, not just the ranker. Cons: CI would
need a model endpoint and a secret; results vary run to run, so the gate would
need wide tolerances or retries, and a flaky gate trains people to re-run it
until it passes; a judge model's own drift moves the baseline. It loses on
reproducibility. The routing suite stays available on demand.

### Option D — A hosted eval platform (Braintrust, LangSmith and similar)

Send traces and datasets to a hosted service with dashboards, judges and
experiment tracking.

Pros: mature tooling; history across runs. Cons: real queries leave the
machine, which the local-first principle forbids for user data; it adds an
account and a dependency to a single-developer project whose two suites fit in
a few hundred lines of Python. It loses on local-first and on scale.

### Option E — No evals; rely on unit tests

Pros: nothing to maintain. Cons: a ranker change that moves the right tool from
rank 2 to rank 6 passes every unit test and silently makes tiering's escape
hatch useless. The `tool_search` gate is the only check that catches that.

### Option F — Put the eval gate inside `make verify`

Run the suites as part of the main verification target.

Pros: one command. Cons: routing needs a model, so only `tool_search` could
join. A separate, path-filtered workflow keeps the main CI fast and still gates
exactly the changes that can move the score. The deterministic suite runs in
its own job for that reason.

## Decision

Evals stay a development-time instrument, outside the product. Real
`coffer__search_tools` queries can be captured only into a separate, opt-in,
local JSONL sink, never into the invocation or audit log. A developer turns
them into cases by hand with `make eval-curate`. CI gates only the
deterministic `tool_search` suite, relative to a committed baseline; the
model-bearing routing suite runs on demand. The invocation log records in-band
tool errors as errors, with a fixed marker in place of upstream text.

## Consequences

- The gateway's call path carries one best-effort capture call that is a no-op
  unless `COFFER_EVAL_CAPTURE` is set.
- The datasets are still entirely hand-written. Until someone runs capture and
  curation against real use, the gate protects the ranker against the cases a
  developer imagined, not the ones users hit.
- Changing the ranker, tool descriptions or search corpus shape means running
  `make eval` and, for an intended improvement, re-baselining in the same PR.
- A fix for a regression stays with the developer. An automated
  "make the eval pass" loop would invite overfitting to a 14-case dataset.
