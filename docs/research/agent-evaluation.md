# Agent evaluation loops: how other products do it

**Feature**: an eval loop for an agent-facing tool — capture real interactions (tool-search queries, routing decisions, agent trajectories), curate them into versioned datasets, score them with deterministic and model-graded checks, and gate CI on regressions against a baseline · **Coffer spec**: none — engineering harness · **Related ADRs**: [eval-capture-and-regression-gate](../decisions/eval-capture-and-regression-gate.md), [tool-overload-tier-the-list-search-the-rest](../decisions/tool-overload-tier-the-list-search-the-rest.md)
**Researched**: 2026-09 · **Method**: web research, primary sources (docs, repos, papers), checked 2026-09-24

The field describes one loop, in slightly different words per vendor:
**capture** traces from real use → **curate** interesting or failing ones into a
dataset (with expected outputs or rubrics) → **score** a candidate against the
dataset with code checks and/or model judges → **compare** against a baseline
run → **report or block** in CI → ship and keep capturing. The products below
differ mainly in where the traces live (vendor cloud vs local files), how the
dataset is versioned, how flaky judge scores are tamed, and whether the CI step
merely comments or actually fails the build.

Adoption, as of 2026-09 (GitHub stars): Langfuse 35.0k, Promptfoo 25.4k,
Opik 22.2k, OpenAI Evals 19.5k, DeepEval 18.4k, Ragas 15.8k, Arize Phoenix
11.6k, SWE-bench 5.9k, Inspect 2.9k, tau2-bench 2.1k, openevals 1.2k,
agentevals 0.7k, MCP-Universe 0.6k, MCP-Bench 0.5k. Braintrust, LangSmith and
Galileo are closed SaaS (Braintrust's `autoevals` scorer library is MIT, 1.0k).

---

## 1. Hosted end-to-end platforms

### Braintrust

**Data model.** An *experiment* is an immutable snapshot of one eval run; a
*dataset* is a versioned table whose rows have four fields — `input` (required),
`expected` (optional ground truth), `metadata` (key–values for filtering and
grouping) and `tags`. "Every change is tracked, so experiments can pin to
specific versions." A row's `input` may hold a *reference* to a logged trace (or
a group of traces) instead of a copied value, so production traces can be
promoted into a dataset without duplicating payloads; bulk pipelines "transform
project logs into dataset rows"
([datasets](https://www.braintrust.dev/docs/guides/datasets)).

**Running evals.** `Eval(data, task, scores)` — `data` is the dataset,
`task` is whatever is under test (one LLM call, a retrieval step, a multi-step
agent), `scores` are scorer functions or classifiers
([evals guide](https://www.braintrust.dev/docs/guides/evals)). Relevant
knobs in the Python SDK: `trial_count` ("the number of times to run the
evaluator per input … gives you both a stronger aggregate measure and a sense of
the variance"), `base_experiment_name` / `base_experiment_id` (the run is
"summarized and compared to this experiment"), `max_concurrency`, `timeout`.
The summary's `ScoreSummary` carries `improvements`, `regressions` (row counts)
and `diff` against the base
([Python SDK reference](https://www.braintrust.dev/docs/reference/sdks/python)).
Row-level improvement/regression counts, not just a mean delta, are the useful
part: they show *which* cases moved.

**Online scoring.** Scoring rules configured per project (which scorers, span
vs trace scope, sampling rate) run asynchronously on production logs, off the
request path ([online scoring](https://www.braintrust.dev/docs/evaluate/score-online)).
Nothing is scored online until a rule exists.

**CI behaviour — reports, does not block.** `braintrustdata/eval-action`
runs `braintrust eval --jsonl` (Node/Python) or `go run` (Go), then "creates or
updates a single PR comment with a Braintrust link and a result table" showing
averages, improvements and regressions per score. Inputs include
`terminate_on_failure` (stop on errors) and `report_scores`/`report_metrics`
(filter the table) and `use_proxy` (cache LLM calls through Braintrust's proxy);
there is no threshold input, so failing the build on a regression is left to the
team's own script or branch protection
([eval-action README](https://github.com/braintrustdata/eval-action)).

**Capture privacy.** A global `setMaskingFunction` receives `input`, `output`,
`expected`, `metadata` and `context` after span merge and before export; if the
masker throws, the field is replaced with a generic
"ERROR: Failed to mask field" rather than sent raw
([advanced tracing](https://www.braintrust.dev/docs/instrument/advanced-tracing)).

### LangSmith

**Traces → datasets.** Datasets are built by hand, from CSV, or from traces.
*Automation rules* do it continuously: a rule targets runs or whole threads,
applies a filter (feedback score, error status, other trace fields), a sampling
rate 0–100 %, and an ordered list of actions — add to annotation queue, add to
dataset, webhook, online evaluator, extend retention, alert. Rules can backfill
over past runs from a start date as a background job
([rules](https://docs.langchain.com/langsmith/rules)). A typical recipe is
"negative user feedback → annotation queue → human writes the reference answer
→ dataset".

**Evaluator types.** Human (annotation queues with rubrics), code,
LLM-as-judge (reference-free or with reference), and pairwise
([evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts)).

**Judge calibration (Align Evals, 2025-07-29).** Four steps: pick criteria;
select representative good *and* bad examples; human-grade them to form a golden
set; write a judge prompt and iterate while the UI shows an *alignment score*
(agreement with the human grades) for each prompt version
([announcement](https://www.langchain.com/blog/introducing-align-evals)).
Human corrections to judge outputs can also be stored as few-shot examples for
the judge ([improve judge with feedback](https://docs.langchain.com/langsmith/improve-judge-evaluator-feedback)).

**pytest integration.** `@pytest.mark.langsmith` turns a test file into a
dataset and each run into an experiment. Inside a test, `t.log_inputs()`,
`t.log_outputs()`, `t.log_reference_outputs()` and
`t.log_feedback(key, score)` record the row; pass/fail lands under a `pass`
feedback key; `t.trace_feedback()` separates judge calls from app calls.
`LANGSMITH_TEST_CACHE=tests/cassettes` caches HTTP (LLM) calls to disk so CI
reruns are cheap and deterministic; `cached_hosts` narrows it. Works with
`parametrize`, `pytest-xdist` and `pytest-asyncio`
([pytest docs](https://docs.langchain.com/langsmith/pytest)). Failing asserts
fail the build like any pytest test.

**Trajectory evaluators (OSS).** `langchain-ai/agentevals` provides
`create_trajectory_match_evaluator` with modes `strict` (same messages, same
order, same tool calls), `unordered`, `subset` (no unexpected tools) and
`superset` (required tools present), plus `tool_args_match_mode`
(`exact` / `ignore` / `subset` / `superset`) and per-tool
`tool_args_match_overrides`; and a reference-free LLM trajectory judge
([agentevals](https://github.com/langchain-ai/agentevals)).

**Capture privacy.** `LANGSMITH_HIDE_INPUTS=true` / `LANGSMITH_HIDE_OUTPUTS=true`
drop payloads entirely; regex or anonymizer-based masking redacts selectively;
per-request redaction via `tracing_context`; conditional tracing skips whole
operations ([mask inputs/outputs](https://docs.langchain.com/langsmith/mask-inputs-outputs)).

### Langfuse (MIT core, self-hostable)

Dataset items are `input`, optional `expected_output`, `metadata`, and an
optional `source_trace_id` / `source_observation_id` linking back to the
production trace they came from. Items are added by SDK, CSV, or by selecting
observations in the UI and choosing *Add to dataset* with a field mapping.
"Every `add`, `update`, `delete`, or `archive` of dataset items produces a new
dataset version", addressable by timestamp so an old experiment can be
reproduced against the exact dataset it used
([datasets](https://langfuse.com/docs/evaluation/experiments/datasets)).
Licensing: MIT outside `ee/` directories
([LICENSE](https://github.com/langfuse/langfuse/blob/main/LICENSE)).

---

## 2. Local-first, CI-oriented frameworks

### Promptfoo (MIT; joined OpenAI 2026-03)

**Config.** `promptfooconfig.yaml` holds `prompts`, `providers` (the system
under test — a model, an HTTP endpoint, a script), `tests` (each with `vars`,
`assert`, optional `threshold`) and `defaultTest` (assertions applied to every
test). An assertion is `{type, value, threshold, weight, metric}`; the test's
score is the weighted average of its assertions and passes if it meets the
test's `threshold`. Any assertion can be negated with a `not-` prefix
([assertions](https://www.promptfoo.dev/docs/configuration/expected-outputs/)).

**Assertions.** Deterministic: equals/contains/regex, JSON/SQL/HTML validity,
custom JS/Python, embedding similarity, BLEU/ROUGE, latency and cost ceilings.
Model-graded: `llm-rubric`, `g-eval`, `factuality`, `answer-relevance`,
`context-faithfulness`/`-recall`/`-relevance`. Tool-specific:
`is-valid-openai-tools-call` (calls match the tool JSON schema), `tool-call-f1`
(F1 of called vs expected tool names), and trajectory assertions
`trajectory:tool-used`, `trajectory:tool-args-match`,
`trajectory:tool-sequence` (same page).

**CI.** `promptfoo eval` exits `100` "when there is at least 1 test case
failure or when the pass rate is below the threshold set by
`PROMPTFOO_PASS_RATE_THRESHOLD`", `1` for other errors, and the failing code is
overridable via `PROMPTFOO_FAILED_TEST_EXIT_CODE`. Flakiness and cost controls:
`--repeat <n>`, on-disk response cache (`--no-cache` to bypass),
`--max-concurrency`, `--filter-failing <eval>` to rerun only previous failures;
outputs include `junit.xml`; `--share`/`--no-share` controls whether a result
URL is published ([CLI](https://www.promptfoo.dev/docs/usage/command-line/)).
The GitHub Action (`promptfoo/promptfoo-action`) runs a before/after comparison
on PRs that touch prompt files and posts a link to the diff viewer; it caches
LLM responses via `cache-path`
([GitHub Action](https://www.promptfoo.dev/docs/integrations/github-action/)).
So the action *reports*; the CLI exit code is what *blocks*.

**Status.** Promptfoo announced it is joining OpenAI on 2026-03-09 and "will
remain open source … under the current license"
([blog](https://www.promptfoo.dev/blog/promptfoo-joining-openai/)); the repo
licence is MIT. OpenAI now points users of its deprecated Evals platform at
Promptfoo (see OpenAI below).

### DeepEval (Apache-2.0, Confident AI)

**Shape.** Test cases are pytest tests (`@pytest.mark.parametrize` over a
dataset) that call `assert_test(test_case, metrics)`; any metric below its
threshold fails the assertion and the build. Run with `deepeval test run
file.py` ([CI/CD guide](https://deepeval.com/docs/evaluation-unit-testing-in-ci-cd)).

**Flags.** `-n` parallel processes; `-c` read from the local cache — results
are "keyed by test case content plus metric configuration, so a cached result is
only reused when both are unchanged"; `-r` repeat each case; `-i` ignore metric
errors; `-s` skip cases missing required fields; `-id` name the run;
`--official` marks a run as the regression reference
([flags](https://deepeval.com/docs/evaluation-flags-and-configs)).

**Tool-use metrics.** *Tool Correctness* is deterministic first: "Number of
Correctly Used Tools / Total Number of Tools Called", matching names by default,
optionally input parameters and outputs (`evaluation_params`), ordering
(`should_consider_ordering`) or full equality (`should_exact_match`); default
threshold 0.5. If `available_tools` is supplied, an LLM additionally judges
whether the choice was optimal and the final score is the minimum of the two.
*Argument Correctness* is a separate LLM-judged metric for argument quality
([tool correctness](https://deepeval.com/docs/metrics-tool-correctness)).

### Ragas (Apache-2.0)

A metric library rather than a runner. Retrieval metrics: context precision,
context recall, context entities recall, response relevancy, faithfulness —
mostly LLM-based. Agent metrics: *Tool Call Accuracy*, *Tool Call F1*,
*Agent Goal Accuracy*, *Topic Adherence*. Non-LLM metrics exist for cheap,
deterministic scoring (exact match, string presence, BLEU/ROUGE/CHRF,
non-LLM string similarity)
([metrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)).
The repository now lives at `vibrantlabsai/ragas`; latest release v0.4.3
(2026-01-13) — slower cadence than DeepEval or Promptfoo.

### Inspect (UK AISI, MIT)

**Model.** A `@task` bundles a *Dataset* (samples with `input` and `target`,
loaded from HF/CSV/JSON via `FieldSpec`), a *Solver* (from a single
`generate()` to a full multi-turn tool-using agent, or an external agent) and one
or more *Scorers* (`includes()`, `exact()`, `f1()`, `model_graded_qa()`,
`model_graded_fact()`, custom). Tools include bash/python/editor/web/computer
and MCP tools; untrusted actions run in sandboxes (Docker, Kubernetes, Modal,
Proxmox, Vagrant, pluggable) ([docs](https://inspect.aisi.org.uk/)).

**Variance handling is first-class.** Scorers report `accuracy`/`mean` *and*
`stderr` ([scorers](https://inspect.aisi.org.uk/scorers.html)). Samples run for
multiple *epochs*, and a reducer collapses the epochs per sample: `mean`,
`median`, `mode`, `max`, `at_least`, `pass_at`, … — e.g.
`--epochs 5 --epochs-reducer "mean,pass_at_5,at_least_5"`
([scorer reference](https://inspect.aisi.org.uk/reference/inspect_ai.scorer.html),
[metrics](https://inspect.aisi.org.uk/metrics.html)). Model graders can use
several grader models. Every run writes a self-contained `.eval` log that the
`inspect view` viewer opens, so a transcript is always one click from a score.

---

## 3. Model vendors and observability platforms

### OpenAI Evals (framework, API, and its deprecation)

- **`openai/evals`** (19.5k stars): the original open registry — YAML eval
  definitions plus JSONL samples in Git-LFS, templates such as match / includes /
  model-graded classification ([repo](https://github.com/openai/evals)); last
  push 2026-04.
- **Evals API / dashboard**: an eval is `data_source_config` (JSON Schema of
  a row; `include_sample_schema` exposes the model's sample to graders) plus
  `testing_criteria` (graders); runs execute a prompt/model over the rows
  ([evals guide](https://developers.openai.com/api/docs/guides/evals)). Grader
  types: `string_check` (eq/neq/like/ilike → 0/1), `text_similarity`
  (fuzzy_match, BLEU, GLEU, METEOR, cosine, ROUGE with `pass_threshold`),
  `score_model` and `label_model` (LLM judges), `python` (sandboxed `grade()`),
  and `multi` (formula over sub-graders)
  ([graders](https://developers.openai.com/api/docs/guides/graders)). *Trace
  grading* applies graders to Agents-SDK traces
  ([trace grading](https://developers.openai.com/api/docs/guides/trace-grading)).
- **Deprecated**: "Evals will become read-only for existing users on October
  31, 2026, and the platform is scheduled to shut down on November 30, 2026"
  ([evals guide](https://developers.openai.com/api/docs/guides/evals)); the
  community notice recommends Promptfoo as the migration path
  ([notice](https://community.openai.com/t/deprecation-notice-evals-will-be-shut-down-on-november-30th-2026/1385537)).
  Lesson: a hosted eval store is a dependency that can disappear; eval
  definitions kept as files in the repo survive vendor churn.

### Arize Phoenix (Elastic License 2.0, self-hostable)

OpenTelemetry-native tracing with code evaluators (exact match, regex,
heuristics) and LLM-as-judge evaluators. Judges return structured verdicts by
*function calling* — Phoenix turns the evaluator's output schema into a tool the
judge must call, instead of parsing free text; explanations are returned by
default; executors handle rate limits, retry transient errors and adapt
concurrency; every judge call is itself traced to a dedicated project so judge
reasoning can be audited. Pre-built templates cover RAG relevance, hallucination
and tool-calling ([LLM evals](https://arize.com/docs/phoenix/evaluation/llm-evals)).
Results attach back to spans as annotations; datasets and experiments sit on top.
Note the licence is ELv2, not OSI-open ([LICENSE](https://github.com/Arize-ai/phoenix/blob/main/LICENSE)).

### Galileo (now part of Cisco)

Agent metrics such as *Tool Selection Quality*: an LLM evaluator is prompted
several times with a chain-of-thought rubric; the score is the fraction of
"yes" votes, and the surfaced explanation is one that agrees with the majority.
It distinguishes *no tool needed* turns (calling a tool is wrong) from *tool
needed* turns (right tool and all required arguments correct)
([metric docs](https://docs.galileo.ai/concepts/metrics/agentic/tool-selection-quality)).
The Luna-2 small judge models are marketed for sub-200 ms scoring so online
evaluation can cover all traffic. Status: Cisco announced the acquisition on
2026-04-09 ([Cisco blog](https://blogs.cisco.com/news/cisco-announces-the-intent-to-acquire-galileo));
secondary sources report it closed on 2026-05-22 and that Galileo is being
folded into Splunk Observability
([Network World](https://www.networkworld.com/article/4156855/cisco-to-acquire-galileo-for-ai-observability.html)).

---

## 4. Claude Code `plugin eval`

Claude Code (v2.1.269+) ships an eval runner for plugins and skills
([plugin evals](https://code.claude.com/docs/en/plugin-evals)). It is the most
concrete public design for "does this agent-facing extension steer the agent
correctly", so it is described in detail.

- **Layout.** `evals/<case>/prompt.md` (frontmatter = case fields, body =
  the user prompt) + `graders/*.md` (frontmatter = type/options, body = rubric
  or pattern) + optional `case.yaml`; `evals/results/` is gitignored.
  `claude plugin eval init` interviews the author, proposes should-trigger and
  should-*not*-trigger prompts, pilots the graders once and writes the files.
- **Isolation.** Each run is a fresh non-interactive session with only the
  plugin loaded; personal MCP servers never load; only read-only tools unless
  `--allow-tools`; scaffold scripts only with `--scaffold`; defaults 10 turns /
  300 s.
- **Graders.** Deterministic: `regex` (over `last_message`, `trace`, `files`,
  a file's contents, or `mock_calls`), `tool_used` (count of calls to a tool
  whose JSON input matches `input_match`, between `min`/`max` — `0/0` asserts
  "never called"), `tool_order`, `file_exists`. Judged: `llm` (PASS if at
  least two of three judge votes pass) and `baseline` (at least as good as a
  reference transcript `.jsonl`).
- **Scoring.** 3 runs per case by default (1–50); run score = weighted fraction
  of graders passed; case score = mean over runs; case passes at `--threshold`
  (default `1.0`).
- **No-plugin baseline.** By default every case also runs *without* the plugin;
  the report shows `WITH`, `W/OUT` and `Δ`. Graders that can only pass with the
  plugin (e.g. `tool_used: Skill`) are excluded from scoring in both arms so
  they don't inflate `Δ`.
- **MCP mocks and replay.** `evals/mocks/<server>/<tool>.md` answers a tool
  from a template (`{{input.field}}`, fixture files); an `expect:` guard
  aborts the run with score 0 if the agent sends the wrong input; `_tools.json`
  replays the real server's `tools/list` so mocked tools keep real descriptions.
  Model-backed (`type: agent`) mock answers are recorded and can be adopted into
  `mocks/.replay/` so later runs answer identical calls with no model call.
- **CI.** `--json`, `--trust-plugin`, pinned `--model` and `--judge-model`
  ("so a model rollout isn't mistaken for a plugin regression"),
  `--max-cost-usd`; exit `0` all cases ≥ threshold, `1` a case below threshold
  or load error, `2` partial run (cost ceiling or auth). Result JSON is
  versioned (`schemaVersion: 1`). The docs warn that rate-limit errors mid-run
  score 0 and "can look like a regression".
- **Stable-signal advice from the docs.** Use `regex` for long outputs and
  `llm` only for short ones with concrete PASS/FAIL rubrics; give every case one
  grader on the *result* and one on the *path* (`tool_used`/`tool_order`); if
  the path grader passes but `Δ` is negative, suspect the judge first.

Anthropic's separate `skill-creator` skill runs with-skill vs without-skill
comparisons and generates trigger/non-trigger queries to tune a skill's
description, warning that negative queries must be "genuinely tricky"
([SKILL.md](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)).

---

## 5. Agent trajectory harnesses and benchmarks

### tau-bench / tau2-bench (Sierra)

Each domain (airline, retail, telecom, …) has a written policy, a tool set over
a mock database, tasks, and an LLM *user simulator*; tau2 adds "dual control",
where the user also has tools that change shared state. The reward compares the
**database state** after the conversation against the expected end state (plus
required outputs), not the wording of the transcript
([tau2-bench](https://github.com/sierra-research/tau2-bench)). The original
paper introduced **pass^k** — the probability that *all* k independent trials
of a task succeed — to measure reliability rather than best-case ability
([τ-bench paper](https://arxiv.org/abs/2406.12045)).

### SWE-bench

Each instance is a real GitHub issue; the prediction is a patch (JSONL). The
harness applies it inside a per-instance Docker image and grades by two test
sets: **FAIL_TO_PASS** (tests that must go from failing to passing) and
**PASS_TO_PASS** (tests that must keep passing — the regression guard).
Variants: Lite, Verified (500 human-confirmed solvable), Multimodal.
`swebench eval verified -p preds.jsonl --run-id X`; results are cached by run id
and instance id ([repo](https://github.com/SWE-bench/SWE-bench)).

### Anthropic's guidance on agent evals

From [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents):
a *task* has success criteria, a *trial* is one attempt, a *grader* scores
one aspect, the *transcript* is the full message/tool log, and the *outcome* is
the final environment state ("the outcome is whether a reservation exists in the
environment's SQL database"). Grade the outcome, not the exact path, so valid
but unexpected routes aren't punished. Split *capability* evals (low pass rate,
aimed at improvement) from *regression* evals (~100 % pass, protecting against
backsliding); saturated capability tasks "graduate" into the regression suite.
Start with "20-50 simple tasks drawn from real failures". Isolate each trial —
shared state produces correlated, infrastructure-caused failures. Read
transcripts, because failing scores are often grader bugs.

---

## 6. MCP and tool-retrieval evaluation

### MCP-specific agent benchmarks

- **MCP-Universe** (Salesforce, Apache-2.0): tasks against *real* MCP servers in
  six domains (location navigation, repo management, finance, 3D design, browser
  automation, web search). A task is JSON with `question`, `mcp_servers`,
  `output_format` and `evaluators`; evaluators are *format* (schema),
  *static* (extract with `json`/`get`/`len`/`foreach` and compare with
  `=`/`<`/`>`) and *dynamic* (ground truth fetched at grading time, for
  time-sensitive answers) ([repo](https://github.com/SalesforceAIResearch/MCP-Universe)).
- **MCP-Bench** (Accenture): 28 live MCP servers; tasks are generated then
  "fuzzy"-rewritten so they don't name the tools; rule-based checks (tool name
  validity, schema compliance) plus an o4-mini judge for task completion, tool
  appropriateness and planning ([repo](https://github.com/Accenture/mcp-bench)).
- **LiveMCPBench**: 95 daily tasks over a reproducible suite of 70 servers /
  527 tools with no private keys; an MCP Copilot agent must *route* to the right
  server/tool before calling it; LiveMCPEval, an LLM judge, reports 81 %
  agreement with human reviewers ([paper](https://arxiv.org/abs/2508.01780)).

### Tool retrieval (the search-then-call step in isolation)

- **ToolRet** (ACL 2025): a benchmark of query→tool relevance pairs assembled
  from existing tool datasets, scored with IR metrics (nDCG@k, Recall@k), plus a
  200k-example training set. Title and finding: "Retrieval Models Aren't
  Tool-Savvy" — general-purpose retrievers do poorly on tool descriptions
  ([repo](https://github.com/mangopy/tool-retrieval-benchmark),
  [paper](https://arxiv.org/abs/2503.01763)).
- **RAG-MCP**: retrieve relevant MCP tool descriptions before prompting; on an
  MCP stress test, tool-selection accuracy 43.13 % vs 13.62 % with all tools in
  the prompt, and over 50 % fewer prompt tokens
  ([paper](https://arxiv.org/abs/2505.03275)).
- **HumanMCP**: 2,800 tools across 308 MCP servers, each paired with queries
  written from several user personas, from precise to vague — built because
  synthetic queries that paraphrase the tool description inflate retrieval
  scores ([paper](https://arxiv.org/abs/2602.23367)).
- **Anthropic Tool Search Tool**: tools marked `defer_loading: true` are
  searchable (regex or BM25 built in, custom embeddings allowed) instead of
  loaded. On Anthropic's internal MCP evaluations, accuracy went from 49 % to
  74 % (Opus 4) and 79.5 % to 88.1 % (Opus 4.5), with ~85 % fewer upfront tokens
  ([advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use)).

**Metrics teams use for tool search.** Given a query with a set of relevant
tools R and a ranked result list:

| Metric         | Definition                                                                    | What it tells you                                          |
| -------------- | ----------------------------------------------------------------------------- | ---------------------------------------------------------- |
| Recall@k       | \|R ∩ top-k\| / \|R\|                                                         | Did the right tool make it into the slice the agent sees   |
| Hit@k          | 1 if any relevant tool in top-k                                               | Single-answer version of recall; easiest to explain        |
| MRR            | mean over queries of 1 / rank of first relevant tool                          | How high the right tool sits; sensitive to rank 1 vs 2     |
| nDCG@k         | DCG of the ranking / ideal DCG, graded relevance                              | Rank quality when several tools are partially relevant     |
| Tool-call F1   | F1 of called vs expected tool names (Promptfoo `tool-call-f1`, Ragas)         | End-to-end selection, after the model chose from results   |
| Selection acc. | fraction of tasks where the invoked tool is correct (RAG-MCP, Tool Search)    | The number that matters to the user                        |

Recall@k is chosen with k equal to the number of results actually shown to the
agent; MRR is added because an agent often takes the first plausible hit. Both
are deterministic and need only labelled (query, expected tool ids) pairs — the
cheapest eval in this whole note to gate CI on.

---

## 7. Cross-cutting concerns

### Capture privacy

- **Default off for content.** OpenTelemetry's GenAI conventions keep prompts and
  responses out of spans unless `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`
  is set; content then goes into `gen_ai.input.messages` /
  `gen_ai.output.messages` ([issue](https://github.com/open-telemetry/semantic-conventions-genai/issues/497),
  [OTel blog](https://opentelemetry.io/blog/2026/genai-observability/)).
- **Hide wholesale** (LangSmith `LANGSMITH_HIDE_INPUTS/OUTPUTS`), **mask at the
  SDK** before export (Braintrust `setMaskingFunction`, fail-closed; LangSmith
  regex/anonymizer), or **self-host** (Langfuse, Phoenix, Inspect/Promptfoo/
  DeepEval logs on disk).
- **Reference instead of copy** (Braintrust dataset rows pointing at traces,
  Langfuse `source_trace_id`) keeps one copy of sensitive text, so deleting the
  trace deletes it everywhere.
- For tool retrieval specifically, the useful capture is small: query text,
  returned tool ids and ranks, which tool the agent then called. That is far less
  than a full transcript, and the query is the only free-text field to scrub.

### Dataset curation and labelling

- **Sources**: failures and negative feedback first (LangSmith rules on feedback
  score; Anthropic's "20-50 tasks from real failures"), then sampled normal
  traffic for coverage.
- **Label with a human in the loop**: annotation queues (LangSmith), one-click
  promote (Braintrust, Langfuse), or an interactive author step
  (`claude plugin eval init` proposing cases the author accepts).
- **Include negatives**: should-not-trigger prompts (Claude Code, skill-creator),
  "no tool needed" turns (Galileo), `min: 0, max: 0` graders.
- **Avoid description-paraphrase queries**: HumanMCP and MCP-Bench's fuzzy
  rewriting exist because synthetic queries leak the tool's own wording.
- **Version the dataset** (Braintrust pins, Langfuse per-change versions) or keep
  it as a file in git — the same outcome: every score is tied to a dataset state.

### Deterministic vs LLM-judge metrics, and flakiness control

- **Layering**: deterministic checks first, judge only where code can't decide
  (DeepEval Tool Correctness takes the min of both; Claude Code pairs one
  result grader with one path grader).
- **Judge stabilisation**: majority vote over three judge calls (Claude Code
  `llm`, Galileo), structured output via function calling (Phoenix), pinned
  judge model (Claude Code `--judge-model`), short inputs and concrete PASS/FAIL
  rubrics, calibration against human labels (Align Evals; LiveMCPEval's 81 %
  agreement is the kind of number to publish).
- **System-under-test stabilisation**: repeated trials (`trial_count`,
  `--repeat`, `-r`, epochs, `runs`) reduced by mean, pass@k or pass^k; response
  caches keyed on inputs (DeepEval, Promptfoo, LangSmith cassettes); recorded
  mock answers (Claude Code replay); isolated environments per trial.
- **Statistics**: report standard error, cluster it when samples are related
  (clustered SEs can be "over three times as large as naive standard errors"),
  compare two runs with *paired* differences on the same items, and do a power
  analysis to know how many cases a threshold can actually detect
  ([Anthropic, 2024-11-19](https://www.anthropic.com/research/statistical-approach-to-model-evals)).

### Baselines and tolerances in CI

| Tool                    | Baseline notion                                   | CI outcome                                                          |
| ----------------------- | ------------------------------------------------- | ------------------------------------------------------------------- |
| Braintrust eval-action  | `base_experiment` (row improvements/regressions)  | PR comment only; no threshold input                                 |
| Promptfoo               | before/after in the Action; absolute thresholds   | Action comments; CLI exits 100 on failure / pass rate below threshold |
| DeepEval                | per-metric threshold; `--official` reference run  | pytest failure                                                      |
| LangSmith pytest        | assertions per test; experiments for comparison   | pytest failure                                                      |
| Claude Code plugin eval | no-plugin arm (`Δ`) + absolute `--threshold`      | exit 1 below threshold, exit 2 partial                              |
| SWE-bench               | PASS_TO_PASS tests                                | per-instance resolved / not                                         |

Two families: **absolute floors** (threshold per metric or per case) and
**relative-to-baseline** (diff vs a stored run). Absolute floors are simple but
must be retuned when the dataset grows; relative gates need a stored baseline
and a tolerance wide enough for run-to-run noise. None of the surveyed CI
integrations derives the tolerance from measured variance automatically; teams
pick it by hand.

---

## 8. Summary comparison

| Product            | Capture → dataset                          | Deterministic tool checks                       | Judge controls                         | Repeats / reducers               | CI gate                        | Where data lives           |
| ------------------ | ------------------------------------------ | ----------------------------------------------- | -------------------------------------- | -------------------------------- | ------------------------------ | -------------------------- |
| Braintrust         | promote traces; rows reference traces      | custom scorers, autoevals                       | online rules w/ sampling               | `trial_count`                    | comment only                   | SaaS (masking hook)        |
| LangSmith          | automation rules + annotation queues       | code evaluators, agentevals trajectory match    | Align Evals                            | via pytest/parametrize           | pytest                         | SaaS / self-host (paid)    |
| Langfuse           | add observations to dataset, source trace  | custom                                          | LLM-judge evaluators                   | experiments                      | via SDK scripts                | self-host (MIT core)       |
| Promptfoo          | files; import                              | tool-call F1, schema check, trajectory asserts  | weighted asserts, rubric               | `--repeat`, cache                | exit 100 / pass-rate env       | local files                |
| DeepEval           | files; Confident AI cloud optional         | Tool Correctness (name/args/order)              | threshold per metric                   | `-r`, cache                      | pytest                         | local / optional cloud     |
| Ragas              | —                                          | Tool Call Accuracy / F1                         | —                                      | —                                | library only                   | local                      |
| Inspect            | datasets from files/HF                     | custom scorers                                  | multiple grader models                 | epochs + reducers, stderr        | CLI + `.eval` logs             | local                      |
| OpenAI Evals       | stored completions / logs                  | string_check, python grader                     | score/label model graders              | —                                | platform (shutting down 2026-11) | SaaS                     |
| Phoenix            | spans → datasets                           | code evaluators                                 | function-calling judges, traced judges | experiments                      | via scripts                    | self-host (ELv2)           |
| Galileo            | platform                                   | —                                               | multi-vote judges, Luna-2 SLMs         | —                                | platform                       | SaaS (Cisco)               |
| Claude Code eval   | author-written cases                       | `tool_used`, `tool_order`, regex over trace     | 2-of-3 vote, pinned judge              | `runs` (default 3), mean         | exit code, cost ceiling        | local                      |

---

## Patterns and trade-offs

- **Everyone converged on the same loop; they split on custody.** Hosted
  platforms make capture→dataset one click because the traces are already in
  their store; local tools make it a file edit. The hosted path is faster to
  curate but ties the dataset to a vendor that can deprecate it (OpenAI Evals
  shuts down 2026-11-30).
- **Reporting vs blocking is a deliberate split.** Braintrust's and Promptfoo's
  Actions comment on PRs; blocking comes from a CLI exit code (Promptfoo,
  DeepEval, pytest, Claude Code). Judge-scored suites tend to report because
  their noise makes hard gates painful; deterministic suites gate.
- **Retrieval is evaluated separately from the agent.** The research community
  scores tool retrieval with IR metrics on labelled pairs (ToolRet, HumanMCP)
  and scores the agent end to end with state- or outcome-based checks
  (tau-bench, MCP-Universe). The first is cheap and deterministic; the second is
  expensive and noisy but is what users experience.
- **Outcome over path, but assert the path where the path *is* the product.**
  Anthropic's guidance says grade outcomes; yet Claude Code's own eval runner
  and every tool-selection metric grade the path, because for a routing layer
  "which tool was chosen" is the outcome.
- **Variance is handled by repetition plus reducers, not by hoping.** Trials,
  epochs and runs are universal; pass^k (tau-bench, Inspect `at_least`) is the
  reliability view, mean or pass@1 the capability view.
- **Baselines take two shapes.** A stored previous run (Braintrust
  `base_experiment`) catches drift over time; an ablation arm in the same run
  (Claude Code's no-plugin baseline) measures what the component adds and cancels
  model drift, at double the cost.

## Worth borrowing / worth avoiding

**Worth borrowing**

- Capture the minimum needed to replay the decision (query, ranked ids, chosen
  id), keep content capture opt-in, and mask fail-closed.
- Store datasets as versioned files with a back-reference to the source trace,
  so labels are reviewable in diffs and deletion is possible.
- Label with a human, and seed from failures; include hard negatives and
  persona-style or vague queries rather than description paraphrases.
- Gate CI on deterministic retrieval metrics (Recall@k at the shown k, MRR) with
  a stored baseline and a tolerance; keep judge-scored or model-bearing suites
  as report-only or scheduled runs.
- For model-bearing suites: pin the model and judge, repeat trials, reduce with
  mean *and* pass^k, report standard error, compare runs with paired
  differences, and cap cost (Claude Code's `--max-cost-usd`, exit code 2 for a
  partial run).
- An ablation arm (with vs without the component) answers "does this layer
  help at all", which an absolute score cannot.
- Mocked MCP tools with input guards and recorded replays make tool-using
  trajectories reproducible without live servers.

**Worth avoiding**

- Treating a single run of a non-deterministic agent as a regression signal;
  rate-limit errors mid-run look exactly like regressions.
- Graders that can only pass with the component under test counted in both
  arms — they inflate the measured lift.
- Long-text LLM judges with vague rubrics; judges that aren't checked against
  human labels.
- Synthetic queries generated from tool descriptions as the only test set — they
  overstate retrieval quality.
- Hard gates on absolute thresholds that were never re-derived after the dataset
  grew, and tolerances picked without looking at run-to-run variance.
- Keeping the only copy of eval definitions in a hosted product.
