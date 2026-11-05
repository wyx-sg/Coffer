# Add workflow automation

## Why

Scheduled tasks start a turn in a paired chat at a time. The owner now runs
real recurring work through agents — following their own developer tickets to
delivery, and (later) a weekly report — and a prototype outside Coffer showed
what that work needs beyond "a turn at a time": a deterministic check that can
end a run before any model starts, one owner per work item, a durable record
of writes whose result is unknown, working hours and holidays checked on every
step, a structured hand-over between agents, and results kept locally instead
of posted to a chat. The prototype got there by wiring one agent's native
automations and hooks together; none of it carries to another agent, and none
of it belongs in a personal project.

Coffer already owns the trigger, the agent choice, the session and the run
history. This change grows that into a general runtime that runs a flow a
skill defines, for any agent Coffer drives, without Coffer learning what any
flow is about.

## What Changes

- A scheduled task MAY target a **workspace** instead of a chat: it runs
  without a paired chat, keeps its result locally, and notifies a chat only
  when its policy says so. Chat tasks keep entering their chat as they do, with
three changes: their turns run unattended instead of with full permissions, a
run that cannot start is recorded `deferred` instead of `failed`, and the
pause rule is the one below (a run of unknown result pauses the task at once
until the owner resolves it).
- A schedule MAY name an IANA **timezone**; without one it keeps the machine's
  local wall clock.
- A task MAY bind a **workflow**: a skill that declares an automation contract
  (`automation.yaml`: parameters, stages, an optional precheck and reconcile
  command, result schema), a workflow project directory, a profile name, and
  per-stage executors (agent, model, session mode). Coffer reads only the
  declaration; it never scans a skill.
- A **run policy** on the task: working windows (read in the schedule's
  timezone), a holiday calendar file, what to do on a non-working slot (skip,
  or move to the next working time, merged into the next slot when it reaches
  it), per-stage wall-clock timeouts, model-run budgets and work-item limits.
  The policy is checked when a slot comes, before every stage, and before every
  declared write. A calendar that does not cover the year defers the run and
  raises an attention item.
- An optional **precheck**: the skill's own command, run through Coffer's
  controlled command entry, decides `no_change`, `wait`, `blocked` or `start`
  with the work items to act on. `no_change` ends the run before any model
  starts. A per-item recheck time books a recheck run that never takes the
  task's next slot.
- **Work items** with a lease: one owner (task, stage, run, agent) per item at a
  time, across every task bound to the same workflow project. The lease is
  renewed while a turn runs, and every declaration, report and checkpoint write
  carries its generation, so a stale owner is refused.
- An **action ledger**: an agent declares an external write before and after it
  through turn-scoped tools; a write that began and never ended is `unknown`
  and blocks its work item until it is reconciled — per action or per item —
  whatever happens to the run, the lease or the agent. A failed write may be
  begun again as a new attempt; one waiting on an external system answers
  `in_progress`.
- Run outcomes gain `no_change`, `moved`, `deferred` (proved not started; safe
  to retry) and `unknown` (started, result not known; must be reconciled). A
  stage counts as started once its prompt has been handed to the agent, which
  the run records. A daemon stop closes an interrupted run `unknown`, not
  `failed`, when its stage may write; a chat-target run counts as writing. A
  writing stage that ends without a report records an unknown action for each
  item it held.
- A **structured result** reported through a turn-scoped tool, validated against
  the flow's schema, from which Coffer writes the business checkpoint into the
  workflow project. Run completion, artifact submission, deployment and
  business verification are reported as separate milestones. The first valid
  report per item and stage is kept; a checkpoint left behind the run record
  is rewritten at startup.
- **Cross-agent hand-over** through the checkpoint: a native session id is
  reused only by the same agent kind, for the same work item, in `continue`
  mode.
- **Unattended permissions**: every scheduled run, chat or workspace target,
  runs under the agent's own permission configuration with nothing
  auto-approved; full permissions stay for turns a person sends from a chat.
  On Claude Code a denied tool call ends the stage `needs_approval`; on Codex
  a detectable denial is recorded as the stage's reason. A Codex executor
  names whether its sandbox has network access.
- **Model usage per run**: each model call with its stage, reason, agent,
  model and tokens/cost as the agent or the model proxy reports them, or
  `unknown`; proxy requests carry the turn's correlation header.
- **Pausing** moves to `automation`: three `failed`, `timed_out`, `unknown` or
  non-policy `deferred` runs with one reason pause a task; policy and busy-lease
  deferrals never count; a chat run of unknown result pauses its task at once
  until `coffer task reconcile --run` or Resume.
- A workspace run opens with a `[Scheduled task]` block naming the task, its
  schedule and due time, with no chat fields.
- The turn event vocabulary gains **prompt accepted**, emitted once the agent
  has accepted the prompt; it marks a stage as started.
- Duplicate triggers are refused durably: one run per (task, slot), and a
  manual run takes an idempotency key.
- A new capability spec `automation` holds the runtime's requirements; the
  generic scheduled-task requirements move there from `channels` with their
  full text and scenarios, and `channels` keeps what is specific to running in
  a chat, including the Scheduled tasks page.
- The principle "Not a second agent" is amended to state the boundary: Coffer
  runs a flow a skill defines on a trigger; it defines no flow of its own.

## Capabilities

- New: `automation`.
- Modified: `channels` (generic scheduled-task requirements move out; chat
  delivery becomes one target, run unattended), `experimental-features` (the
  `scheduled_tasks` switch closes the new routes and tools too and keeps the
  leases and ledger), `chat` (full permissions only for a turn a person sends;
  the prompt-accepted turn event).

## Impact

- Backend: `application/channel/schedule/` and `domain/channel/schedule*.py`
  move to `application/automation/` and `domain/automation/`; chat-specific
  parts stay in `application/channel/`. New: precheck runner, policy, work-item
  leases, action ledger, result tool, checkpoint writer, usage capture.
  Adapters: an unattended permission mode for Claude Code and Codex, a durable
  stage-start record, `TurnDone` cost, a usage correlation header.
- Storage: migrations extending `scheduled_task_runs` (stage start and
  `may_write` snapshot, a unique slot index after deduplicating existing
  rows); new `automation_work_items`, `automation_actions`,
  `automation_rechecks`, `automation_model_calls`.
- Contracts: `/api/v1/scheduled-tasks` (target, workflow, policy, executors,
  run detail), new reconcile (per action and per item) and work-item routes;
  `coffer task` gains `items`, `actions`, `reconcile`, `precheck`.
- Web UI: task dialog (target, workflow, policy, executors), run detail
  (stages, usage, actions), work items; Run canvas.
- Docs (en, zh): scheduled-tasks guide, a workflow-automation guide,
  architecture principles and daemon/chat pages; ADR
  `automation-runs-flows-skills-define`.
