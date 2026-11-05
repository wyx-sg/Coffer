# Design: workflow automation

Status: **draft for review** (2026-11-05). Nothing in this change is
implemented yet. Section 9 marks, for every capability, whether it is
designed, implemented, tested or verified in a real run.

Base: branch `claude/project-thread-2pufqi` at `f25c70e4`, which carries the
archived change `2026-10-29-add-scheduled-tasks` and ADR
[Scheduled tasks are turns Coffer starts in a chat](../../../docs/decisions/scheduled-tasks-are-turns-coffer-starts-in-a-chat.md).
The decision record for this change is the ADR draft
[Automation runs flows skills define](../../../docs/decisions/automation-runs-flows-skills-define.md)
(status Proposed).

## 1. What exists, what is reused, what is missing

Evidence paths are relative to `backend/coffer/` unless they start with
`openspec/` or `docs/`.

### 1.1 Reused as is

| Capability | Evidence | Use in this change |
| --- | --- | --- |
| Task resource, machine-local, never synced | `domain/channel/scheduled_task.py` (`ScheduledTaskConfig`), spec channels "Keep scheduled tasks as machine-local resources" | Stays the one task model; gains optional fields |
| Schedule shapes (once/hourly/daily/weekdays/weekly/cron/manual), DST-aware `next_slot` | `domain/channel/schedule.py` | Reused; gains an optional timezone |
| One scheduler on the wakeable loop, woken by resource writes and finished runs, ≤5 min sleep | `application/channel/schedule/scheduler.py` (`TaskScheduler`) | Reused, moved to `application/automation/` |
| Catch-up of one missed slot within grace | `scheduler.py` `_consider`, `scheduled_task.py` `grace_for` | Reused unchanged |
| Run row opened `running` before the run starts | `application/channel/schedule/runner.py` `run()` → `_runs.add` | Reused; the row is the anchor for `deferred`/`unknown` |
| Run history in `runs.db` with retention | migration `20261029_0155_scheduled_task_runs.py`, `infrastructure/channel/schedule_run_persistence.py` | Extended |
| fresh/continue session, per-task agent/model/cwd | `runner.py` `_start` (`open_conversation` with `prefer`) | Reused; becomes per-stage |
| Agent-agnostic turn orchestration, FIFO per conversation, interrupt | `application/chat/turn_orchestrator.py`, `turn_runner.py` | The workspace target drives it directly |
| Channel turn rendering | `application/channel/turn_driver.py` `submit_scheduled` | Unchanged for the chat target |
| Conversation without a chat binding | `application/chat/service.py` `create_conversation(channel_uid=None)` | The workspace target's conversations |
| Per-turn idle timeout (300 s) and interrupt | `application/chat/turn_runner.py` `DEFAULT_TURN_IDLE_TIMEOUT_SECONDS` | Kept; a stage wall-clock limit is added on top |
| Token counts on `TurnDone` from both adapters | `infrastructure/chat/claude_sdk_mapping.py:198`, `codex_mapping.py:139` | Source of per-call usage |
| Proxy-metered usage, idempotent ingest | `application/usage/ingest.py` | Second source of usage when the agent routes through the proxy |
| Turn-scoped built-in tools that know their turn | `application/channel/schedule/tools.py`, `application/channel/turn_origin.py`, `application/chat/turn_tokens.py` | Pattern for the action-ledger and result tools |
| Skill `requires:` declarations, read-only, never scanned | spec skill-manager (Purpose; "Declare the commands a skill requires") | The automation contract is one more declaration |
| `coffer run` with per-secret person grants | spec secret; memory of PR #582 | The controlled entry for precheck/reconcile commands |
| Experimental switch `scheduled_tasks` | spec experimental-features "Close the scheduled tasks feature's surfaces" | Gates everything new |
| Pause after three failures, history, Run now, `/status` | `scheduler.py` `_after`, `run_now`; `application/channel/status_tasks.py` | Reused |

### 1.2 Gaps, each with the code that shows it

| # | Gap | Evidence | Closed by |
| --- | --- | --- | --- |
| G1 | A task must name a paired chat; there is no way to run without one or to keep the result local | `kind.py:65` refuses an unpaired chat; `TaskChat` is required in `ScheduledTaskConfig` | §3.2 target `workspace` |
| G2 | Every reply is posted to the chat unless it opens with `[SILENT]` | spec channels "Stay silent when a scheduled run has nothing to say" | §3.6 delivery policy |
| G3 | Times are only the machine's local clock | `schedule.py` module docstring; `grace_for` uses `slot.astimezone()` | §3.3 schedule timezone |
| G4 | No working window or holiday check, and nothing checks again after the run starts | no policy in `ScheduledTaskConfig` | §3.3 policy, §4.4 |
| G5 | No step before the model: every run is a full agent turn | `runner.py` goes straight to `submit_scheduled` | §4.2 precheck |
| G6 | Duplicate-run protection is in memory only (`self._running`), lost on restart; the runs table has no uniqueness on (task, slot); Run now has no idempotency | `scheduler.py` `_running: set[str]`; migration 0155 has only a PK on `run_id` | §4.5 |
| G7 | An interrupted run is closed `failed`, which says "safe to retry" for a run that may have written | `schedule_run_persistence.py:193` `close_interrupted` → `failed` | §4.6 `unknown` |
| G8 | No distinction between "never started" and "started, result unknown" | `RunOutcome` has neither `deferred` nor `unknown` (`domain/channel/scheduled_run.py`) | §4.6 |
| G9 | No work items, no owner per item, no lease | — | §4.3 |
| G10 | No record of external writes; nothing stops a blind retry | — | §4.7 action ledger |
| G11 | No structured result, no business checkpoint, no hand-over between agents | runs keep ids/times/outcomes only (`scheduled_run.py` docstring) | §3.5, §4.8 |
| G12 | Channel and scheduled turns run with full permissions | `infrastructure/chat/claude_sdk_agent.py:189` `bypassPermissions`; `codex_agent.py:185-186` `approvalPolicy: never`, `sandbox: danger-full-access` | §5 unattended permissions |
| G13 | Usage per run is not recorded; usage is metered only at the proxy | `application/usage/ingest.py`; `TurnDone` tokens only logged | §4.9 |
| G14 | One agent/model per task, not per stage | `ScheduledTaskConfig.agent/model` | §3.4 executors |
| G15 | Only a turn's idle timeout, no wall-clock limit per stage | `turn_runner.py:52` | §4.6 |
| G16 | Principles say Coffer has "no scheduler that starts agent runs" while the branch ships one | `docs-site/architecture/principles.md:146` vs the ADR above | §7 |
| G17 | Generic scheduled-task requirements live in `channels` though the runtime will not need a channel | spec channels, eleven scheduled-task requirements | §6 |

### 1.3 The prototype, and what of it moves

The personal project `developer-workflows` (paused, business writes off) holds
a working Codex-only prototype. Its generic mechanisms are the ones this
design adopts; its Codex wiring is not carried over.

| Prototype mechanism | Where it goes |
| --- | --- |
| Event key `sha256(ticket, source, object_id, object_version)`, insert-or-ignore, checkpoint and event in one transaction | Stays in the flow's precheck (business observation); Coffer dedups on the `(item_key, version)` the precheck returns (§4.5) |
| Leases `acquired / busy / reconcile`, an expired lease never taken over | Coffer work-item lease (§4.3), same three answers |
| Actions `planned … unknown … deferred`, unknown keeps its locks, reconcile needs evidence | Coffer action ledger (§4.7) |
| `ExecutionNotStarted` → `deferred`, locks released | Run outcome `deferred` (§4.6) |
| One absolute budget shared by reads and model calls | Stage wall-clock limit plus run budget (§4.6, §4.9) |
| Calendar gate with verified holiday years, fail closed | Run policy (§3.3, §4.4) |
| Luna classifies with no tools, Sol executes | Two stages with their own executor (§3.4); no model name in the flow |
| Native automations, the `UserPromptSubmit` hook short-circuit, `codex exec` flags | Not carried over; removed from the personal project after migration (§8) |

## 2. Four layers and what each owns

| Layer | Owns | Never owns |
| --- | --- | --- |
| **Coffer runtime** | triggers, slots, timezone and policy checks, agent/model choice per stage, conversations and session lifecycle, run records, timeouts, cancel, work-item leases, the action ledger, reconcile gating, usage records, notifications it is told to send | what a ticket, a release or a report is; any tracker read; any business rule |
| **Flow skill** | the steps, the next-step decision, evidence and completion conditions, wait conditions, the precheck/reconcile scripts, input and result schemas, examples, references | which agent or model runs it, schedules, leases, retries |
| **Team profile** | an organisation's or team's conventions (Shopee/Account delivery rules, environments, roles) as profile files the flow skill and its delegated domain skills read | anything Coffer reads |
| **Workflow project** | instance config (scope, allowlist, identity), business checkpoints, reports, artefact references, the flow's own observation state | agent transcripts (they stay in each agent's own session store) |

The flow skill reaches Coffer only through its declaration file and the
turn-scoped tools; the workflow project is a directory Coffer reads and
writes only through the checkpoint writer (§4.8) and the precheck's own
process. Coffer stores no transcript and copies no session.

Naming: only generic Coffer-owned skills carry `coffer-`; a
Shopee/Account-only behaviour lives in a profile of an existing skill.
Vendor-official skills stay with their vendor.

## 3. The contract

### 3.1 Flow definition — `automation.yaml` in the skill folder

A skill that can be automated declares it, beside `SKILL.md`. Coffer reads
this file and nothing else from the skill (spec skill-manager Purpose).

```yaml
automation:
  version: 1
  params_schema: schemas/params.json          # what a task binds
  stages:
    - name: inspect
      prompt: prompts/inspect.md              # rendered with params, items, checkpoints
      may_write: false
      result_schema: schemas/inspect-result.json
    - name: execute
      prompt: prompts/execute.md
      may_write: true
      result_schema: schemas/execute-result.json
  precheck:                                   # optional
    command: [python3, scripts/precheck.py]   # argv, relative to the skill folder
    output_schema: schemas/precheck.json
    timeout_seconds: 120
  reconcile:                                  # optional; read-only
    command: [python3, scripts/reconcile.py]
    timeout_seconds: 120
```

No agent, model or vendor command appears. A command runs through Coffer's
controlled entry (`coffer run` semantics: argv only, inside the skill folder,
its `requires:` checked, secrets only by per-secret grant), with the workflow
project as working directory, a JSON request on stdin and a JSON answer on
stdout validated against the declared schema.

**Precheck answer** (envelope fixed by Coffer, `facts` opaque):

```json
{"decision": "start | no_change | wait | blocked",
 "items": [{"key": "…", "version": "…", "stage": "inspect", "facts_ref": "…"}],
 "recheck_after": "2026-11-05T14:00:00+08:00",
 "reason": "one line"}
```

**Stage result** (reported through `coffer__automation_report`, envelope fixed
by Coffer, `checkpoint` validated against the stage's `result_schema`):

```json
{"items": [{
  "key": "…",
  "status": "progressed | waiting | done | needs_human | blocked",
  "next_stage": "execute | null",
  "wait": {"recheck_after": "…", "condition": "one line"},
  "milestones": [{"name": "artifact_submitted", "status": "reached", "evidence_refs": ["…"]}],
  "checkpoint": { }
}]}
```

`milestones` names are the flow's; Coffer stores and shows them and treats
none as completion. An item is done only when the flow reports `done`.

### 3.2 Automation task — the existing `scheduled_task`, extended

```yaml
schedule: {kind: weekdays, at: "11:00", timezone: Asia/Singapore}
prompt: "…"                      # chat tasks; for workflow tasks a note only
target:
  kind: workspace                # chat | workspace; chat = today's behaviour
  chat: {…}                      # chat target only (TaskChat, unchanged)
workflow:                        # optional
  skill: <skill name>
  project: <absolute path of the workflow project>
  profile: <profile name or "">
  params: { }                    # validated against params_schema
  scope: all | active            # passed to the precheck
executors:                       # per stage; falls back to "default"
  default: {agent: claude_code, model: null, session: fresh}
  execute: {agent: codex, model: <id>, session: continue}
policy:
  windows: [{days: [mon, tue, wed, thu, fri], from: "10:00", to: "19:00"}]
  calendar: <path to a holiday file>   # optional
  on_non_working: skip | next_working
  stage_timeout_seconds: {inspect: 300, execute: 1800}
  max_model_runs_per_day: 12
  max_items_per_run: 1
delivery:
  archive: local                  # always
  notify: {chat: {…}, on: [needs_human, unknown, paused]}   # optional
catch_up: true
```

Two tasks may bind the same workflow project (a daily full scan and an
in-hours follow-up of active items); leases are per (workflow project, item),
so they never both own an item.

A chat target behaves exactly as today. Field rules: `executors` and `policy`
apply to both targets; `workflow` requires a declared skill; a workspace task
without `workflow` runs its prompt in a fresh conversation in the executor's
directory.

### 3.3 Time

- `schedule.timezone` (IANA) — slots and grace are computed on that zone's wall
  clock; absent, the machine's local clock (today's behaviour).
- `policy.windows` are read in the same zone. `policy.calendar` names a JSON
  file `{years: {"2026": {verified: true, dates: [...]}}}`; a year that is
  missing or unverified fails closed (`deferred: calendar not covered`).
- `on_non_working: next_working` moves a slot that lands on a holiday, a
  weekend or outside the window to the next working moment; `skip` records it
  skipped. The weekly report uses `next_working`; developer follow-up uses
  `skip`.

### 3.4 Executors

Each stage names its agent kind (one of the registered agents), model and
session mode. A stage's turn runs in a conversation of that agent. `continue`
reuses the work item's last conversation **of the same agent kind**; a
different kind always opens a fresh one and starts from the checkpoint (§4.8).
No flow names an agent or a model.

### 3.5 Execution record

`scheduled_task_runs` keeps one row per (task, slot) or manual trigger, and
gains: `stage`, the `deferred`/`unknown`/`no_change`/`needs_approval`/`timed_out`
outcomes, `precheck_decision`, `items` (keys only), `usage_status`
(`reported | partial | unknown`). Model calls go to `automation_model_calls`.
Ids, times, outcomes and counts only — never what an agent said.

### 3.6 Business checkpoint

One JSON file per work item in the workflow project, under the directory the
task's project declares (default `state/checkpoints/<item>.json`), written only
by Coffer's checkpoint writer from a validated result: write-to-temp, fsync,
rename, with `generation`, `updated_by {task, run, stage, agent}`. The flow's
own observation state (event log, source facts) stays wherever the flow keeps
it and is the precheck's business.

## 4. Lifecycle

### 4.1 Run states

```
slot due ─► claim (task, slot)  ──dup──► skipped "already claimed"
   │
   ▼
policy check ──closed──► skipped / deferred (next working)
   │
   ▼
precheck? ──no_change──► no_change     ──wait──► no_change + recheck booked
   │        ──blocked──► needs_human    ──error──► deferred (not started)
   ▼ start (items)
lease items ──busy──► deferred         ──reconcile──► needs_human (item blocked)
   │
   ▼
per stage: policy check ─► open conversation ─► turn starts ─► report
   │  not started yet: deferred (locks released)
   │  started: replied/silent/progressed … | timed_out | stopped | failed
   │           may_write stage without a valid report ─► unknown
   ▼
write checkpoint ─► release leases (not those with unknown actions) ─► settle
```

### 4.2 Precheck

Runs before any model, with `{task, slot, trigger, scope, items_in_progress,
checkpoints_dir, policy_now}` on stdin. `no_change` and `wait` end the run
recorded `no_change`; `wait` books the item's recheck (a one-off internal slot
on the same task, still policy-checked). A failing or timed-out precheck is
`deferred`: nothing was started.

### 4.3 Work items and leases

`automation_work_items(workflow_id, item_key)` — `workflow_id` is the stable id
in the workflow project's manifest, so two tasks on one project share it.
Fields: `state` (idle | leased | waiting | needs_reconcile | done),
`last_version`, `owner {task, run, stage, agent}`, `lease_expires_at`,
`generation`, `recheck_after`, `last_conversation_by_agent`. Acquire is one
SQLite `BEGIN IMMEDIATE` transaction returning `acquired`, `busy` or
`reconcile`. An expired lease whose item has an `unknown` action is never taken
over (`reconcile`); one without is taken over with `generation + 1`.

### 4.4 Policy checks happen four times

1. When a slot comes (skip or move).
2. Before the precheck.
3. Before each stage's turn starts (`deferred` if closed — not started).
4. In `coffer__automation_action_begin`: a write is refused with
   `outside_window` once the window has closed, so a running agent cannot
   start a new write after hours; a write already begun may finish.

### 4.5 Deduplication

- Slot: a unique index `(task_uid, due_at)` for `trigger = schedule`; the claim
  is the `running` row's insert. A second daemon, a restart mid-pass or a poke
  storm cannot open a second run.
- Manual: Run now carries an idempotency key (header or `--idempotency-key`);
  the same key within 24 h returns the existing run.
- Item: an item whose `(key, version)` equals `last_version` and is not
  `waiting`-due is dropped before any lease.
- Action: `action_key` is unique per workflow; a begin for a key already
  `verified` returns `already_done`, one already `started`/`unknown` returns
  `reconcile`.
- Report send: the weekly report's send is an action with key
  `report:<period>:<revision>`; a second send of the same revision is
  `already_done`.

### 4.6 Not started vs started

A stage is **started** once the adapter has reported the turn's first event
(the agent process accepted the prompt). Before that — policy closed, lease
busy, conversation could not open, agent not installed, queue full, precheck
failed, daemon stopping — the run is `deferred` and every lease it took is
released: retrying is safe.

After that, a turn that ends without a valid report, times out
(`stage_timeout_seconds`, wall clock, interrupts the turn), is stopped, or is
cut by a daemon stop:

- stage `may_write: false` → `failed` / `timed_out` / `stopped`; leases
  released; the next slot may retry;
- stage `may_write: true` → `unknown`; any action still `started` becomes
  `unknown`; the item goes `needs_reconcile` and keeps its lease.

`close_interrupted` on startup applies the same rule instead of closing every
row `failed`.

### 4.7 Action ledger

Two turn-scoped tools, offered only in automation turns:

- `coffer__automation_action_begin {action_key, item, kind, summary}` →
  `begun | already_done | reconcile | outside_window | budget_exhausted`
- `coffer__automation_action_end {action_key, status: verified | failed |
  waiting_external, evidence_refs}`

Begin is durable before it returns. Coffer cannot see writes an agent does not
declare; that is why a `may_write` stage that ends without its report is
`unknown` as a whole (§4.6), and why the flow's prompt and the unattended
permission configuration (§5) are the other two fences.

Reconcile: the flow's `reconcile` command reads external truth for every
`unknown` action and answers `verified | failed | still_unknown` per key with
evidence; or the owner resolves one with `coffer task reconcile <task>
<action_key> --status … --evidence …`. Only then is the lease released.
Nothing — a failure, an expired lease, another task, another agent —
re-runs an `unknown` action.

### 4.8 Hand-over

The next stage's prompt is rendered with the item's checkpoint (§3.6), the
flow's params, the profile name and the stage's result schema. A native session
id is reused only when the stage's agent kind matches the item's last
conversation of that kind and the stage is `continue`; otherwise a fresh
conversation starts from the checkpoint. A session id is never passed to
another agent kind.

### 4.9 Cost and usage

- Precheck first; `no_change` costs no model call.
- Item dedup on version; `max_items_per_run`; `max_model_runs_per_day` per
  task (a run past it is `deferred: budget exhausted`).
- A cheap model for a non-writing stage is a config choice.
- Every model call is an `automation_model_calls` row: run, stage, reason
  (`precheck:start items=[…]`, `recheck`, `manual`), agent, model, input/output
  tokens and cost when `TurnDone` or the proxy reports them, otherwise
  `unknown` — never zero.

### 4.10 Wait and resume

`waiting` items carry `recheck_after`; the scheduler wakes the task's precheck
then (inside the window). Long waits (a delegated DW task, a pipeline, a
review) are a precheck question, not a running turn. Resume after a restart
reads leases, the ledger and checkpoints; nothing in memory is needed.

### 4.11 Delivery and notification

The run record and the checkpoint/report files are the result. A chat is told
only (a) for a chat-target task as today, or (b) for the events listed in
`delivery.notify.on`. A flow's own message (the weekly report to the owner) is
a business write through its action ledger, not a Coffer notification.

### 4.12 Event triggers (later)

`trigger` already distinguishes `schedule` and `manual`; `event` is the third
value. An event names a task and carries a payload passed to the precheck.
Ingress (local file watch, a polled source, a future webhook) is out of this
change.

## 5. Agents and permissions

| | Claude Code | Codex |
| --- | --- | --- |
| Turn path | `claude_sdk_agent.py` through the orchestrator | `codex_agent.py` app-server through the orchestrator |
| Today (chat turns) | `permission_mode="bypassPermissions"` | `approvalPolicy: never`, `sandbox: danger-full-access` |
| Automation turns (new) | the agent's own settings sources (`user`, `project`) with permission mode `dontAsk`: allowed rules run, anything else is denied, never prompted | the user's `config.toml` profile for sandbox/network with `approvalPolicy: never`, sandbox at most `workspace-write` unless the task's executor names a profile that allows more |
| A call needing a person | denied → the stage ends `needs_approval` with the tool name | rejected → `needs_approval` |
| Structured result | `coffer__automation_report` via the MCP gateway | same |
| Usage | `ResultMessage.usage` → `TurnDone` | `tokenUsage` → `TurnDone` |
| Session id | SDK session id → conversation row | thread id → conversation row |

Coffer never auto-approves. The exact flag names are confirmed in the real-run
acceptance (§9, R1–R2) before the adapter change merges; if an SDK lacks a
deny-don't-ask mode, the automation turn is refused for that agent rather than
run with bypass.

## 6. Where the requirements live

New capability `automation` (passes the five tests in `.agents/openspec.md`:
owns `automation_work_items`, `automation_actions`, `automation_model_calls`
and the task/run state; its own package `application/automation/`; its own
consumers — channels for chat delivery, the CLI, the page; this change's ADR;
operable alone through the workspace target). The generic scheduled-task
requirements move from `channels` to `automation`; `channels` keeps running a
task in a chat, `[SILENT]`, follow-ups, the opening block, the daily report and
`/status`. The page requirement moves when the page changes (Phase 3).

Code moves, not copies: `domain/channel/schedule.py`, `scheduled_task.py`,
`scheduled_run.py` → `domain/automation/`; `application/channel/schedule/
{scheduler,runner,kind}.py` → `application/automation/`; the chat target
becomes a delivery port the channel package implements. The import-linter
fence gets an `automation → channel` forbidden contract.

## 7. Principle alignment (needs owner approval)

`principles.md:146` currently says Coffer has "no workflow or orchestration
engine and no scheduler that starts agent runs". The branch already ships a
scheduler that starts turns, so the text and the code disagree today.
Proposed replacement for the last three sentences of "Not a second agent":

> So Coffer defines no workflow: the steps, decisions and completion of any
> multi-step work are a skill's. Coffer does run a skill's declared flow on a
> trigger — a time, a manual run, later an event — for whichever agent the
> task names, because carrying one flow across agents, keeping one owner per
> work item, refusing a blind retry of an unknown write and checking working
> hours on every step are what no single agent's own automation does. That
> runtime starts agents under their own permission configuration and never
> approves a tool call for them. Coffer's own background passes (sync rounds,
> update checks) run on timers and start no agent.

This change edits `principles.md` (en, zh) with that text only after the owner
approves it; until then the branch is knowingly inconsistent and the PR says
so.

## 8. Migration of the developer follow-up prototype

### 8.1 Where the flow goes (decision needed)

The prototype's scripts live in the vault skill `coffer-delegating-work`
(`scripts/follow_delivery*`). Recommendation: move the flow into its own skill
(working name `coffer-following-delivery`) that composes the existing domain
skills (delegating-work, submitting-review, deploying-service, testing-change)
through the `shopee-account` profile, and delete from it what Coffer now
provides (leases, calendar, reconcile bookkeeping, budget, Codex launcher).
`coffer-delegating-work` keeps delegating and checking one task. Alternative:
leave it in `coffer-delegating-work` — no new skill, but one skill would own
two jobs.

### 8.2 Order

| Step | What | Done when | Rollback |
| --- | --- | --- | --- |
| M0 | Freeze: both Codex automations stay paused, `business_writes_enabled=false`; record a runtime owner marker `runtime: codex-native` in the project manifest | marker read back | — |
| M1 | Flow skill: `automation.yaml`, precheck = the prototype's collector (Jira/DW/MR readers + event keys, unchanged keys), reconcile = the prototype's evidence check made read-only; prompts without Luna/Sol names | the 46 prototype tests that remain flow-level pass in the skill; Coffer-level ones re-homed (§9) | skill version pinned |
| M2 | State: keep `followup.sqlite3` tickets/events as the flow's state; import in-flight actions into Coffer's ledger as `unknown`; leases are not imported | import report lists every action; counts match | delete imported rows; prototype store untouched |
| M3 | Shadow: a Coffer workspace task, precheck only (`stages` disabled), runtime marker still `codex-native`; compare event keys with the prototype's last two scans | same keys, `no_change` runs start no model | disable task |
| M4 | Switch owner: marker → `coffer`; the prototype's entry checks the marker and refuses | old entry refuses on a test prompt | marker back |
| M5 | Dry run with writes off: stages run; the flow's write switch keeps every `action_begin` refused | checkpoints written, no external write, usage recorded | pause task |
| M6 | One ticket, writes on, owner-approved | one real chain with milestones and evidence | pause; reconcile |
| M7 | Full allowlist | a week of runs without `unknown` left unreconciled | pause |
| M8 | Remove this workflow's Codex automations and hook entries; keep other Codex uses | `.codex/hooks.json` no longer intercepts; automations deleted | restore from the project's git |

The old and new runtimes never both advance the workflow: the marker is
checked by both entries, and M4 happens only after M3 passes and the Codex
automations are confirmed paused.

### 8.3 Personal data stays out

Ticket keys, allowlists, DW ids, identity fields, machine paths, holiday files,
model ids and the 10:00–19:00 window live in the workflow project. Coffer's
tests use a generic sample flow (§9).

## 9. Acceptance

### 9.1 Status legend

**Designed** = in this document · **Implemented** = code merged on the branch ·
**Tested** = covered by an `acceptance(...)` test that passes in `make verify` ·
**Verified** = observed in a real run with a real agent and model, receipt kept.

| Capability | Designed | Implemented | Tested | Verified |
| --- | --- | --- | --- | --- |
| Chat-target scheduled tasks (existing) | ✓ | ✓ (branch) | ✓ 89 scheduled-task unit+integration tests re-run 2026-11-05 (full `make verify` not run) | not recorded |
| Workspace target, timezone, policy | ✓ | — | — | — |
| Precheck, no-model `no_change` | ✓ | — | — | — |
| Leases, action ledger, reconcile | ✓ | — (prototype only) | — (prototype 46 tests) | — |
| Structured result, checkpoint, hand-over | ✓ | — | — | — |
| Unattended permissions (both agents) | ✓ | — | — | — |
| Usage per run | ✓ | — | — | — |
| Developer follow-up on Coffer | ✓ | — | — | — |
| Weekly report | ✓ (shape only) | — | — | — |

### 9.2 Automated (generic sample flow, fake agents)

A fixture flow skill `sample-counter` in `backend/tests/fixtures/`: a local
JSON "tracker" is the external system, a precheck reads it, an execute stage
appends to a local "outbox" through declared actions. Every scenario below is
a scenario in `specs/automation/spec.md` and gets an acceptance test:

| # | Scenario | Assertion |
| --- | --- | --- |
| A1 | No change starts no model | precheck `no_change` → run `no_change`, zero adapter calls, zero `automation_model_calls` |
| A2 | Duplicate trigger | two passes and a restart for one slot → one run row; second Run now with the same key → same run |
| A3 | Interrupted run recovers | daemon stop mid `may_write` stage → row `unknown`, action `unknown`, item `needs_reconcile`; next slot does not run the item |
| A4 | Unknown is never retried | lease expiry, a second task, a switch to another agent → `action_begin` returns `reconcile`; outbox unchanged |
| A5 | Proven not started is deferred | agent missing / queue full / precheck failure → `deferred`, leases released, next slot runs |
| A6 | Cross-agent hand-over | inspect on agent A, execute on agent B → B's conversation is fresh, its prompt carries A's checkpoint, no session id crosses |
| A7 | Holiday and out-of-hours | slot on a calendar holiday → skipped (`skip`) or moved (`next_working`); window closing mid-run → `action_begin` refused `outside_window`; uncovered year → deferred |
| A8 | Report send dedup | same `report:<period>:<rev>` twice → second `already_done`; a revision sends once |
| A9 | Permission needed | a denied tool → stage `needs_approval`, nothing approved |
| A10 | Usage unknown | adapter without tokens → call row `unknown`, run `usage_status = unknown` |

### 9.3 Real runs (receipts kept outside the repo)

| # | Run | Pass condition |
| --- | --- | --- |
| R1 | `sample-counter` on Claude Code, real model, workspace target | report validated, checkpoint written, usage reported, a denied tool shows `needs_approval` |
| R2 | Same on Codex | same |
| R3 | inspect on Claude Code → execute on Codex, and the reverse | A6 holds with real sessions |
| R4 | Kill the daemon mid execute | A3 holds; reconcile command resolves it |
| R5 | Scheduler on a real clock over a weekday boundary in Asia/Singapore with a machine in another zone | slots at the zone's times; out-of-window slot skipped |
| R6 | Developer follow-up M3 shadow, then M5 dry run | §8.2 pass conditions |

The weekly report is validated as a design against A1, A2, A7, A8 and §10; its
real integration and any send stay deferred.

## 10. The weekly report against the design

| Need | Where it sits |
| --- | --- |
| Monday 10:30, previous Mon–Sun, Asia/Singapore, holiday → next working | `schedule {weekly mon 10:30, timezone}`, `policy.on_non_working: next_working` |
| Collect personal activity, bot Q&A, DW work by event time and actor | the flow's precheck/collect stage; sources are its own skills |
| Cursors per source, incomplete sources, late additions, revisions | the flow's state in its workflow project (cursor per source, period, revision) |
| Send once per revision, reconcile a send of unknown result | action ledger key `report:<period>:<revision>`; reconcile reads the chat's sent message |
| Independent of delivery state | its own workflow project and `workflow_id`; no shared item keys |
| Private SeaTalk to the owner later | a business write by the flow; not a Coffer notification; off this round |

## 11. Rejected

- **A flow DSL or visual orchestrator.** Stages, a precheck and a result
  schema cover both flows; a DSL would make Coffer understand flows.
- **Coffer reading Jira/DW itself.** Business observation stays in the flow's
  precheck.
- **Copying the Codex launcher into Coffer.** Agent-specific and replaced by
  the orchestrator.
- **Business checkpoints in `runs.db`.** They are the workflow's data and must
  survive moving the workflow between runtimes; Coffer keeps only the
  runtime-safety state (leases, ledger, runs).
- **Storing full sessions.** Each agent keeps its own.
- **A second scheduler for workflows.** The existing `scheduled_task` is
  extended.
