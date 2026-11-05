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
  when its policy says so. Chat tasks keep working as they do.
- A schedule MAY name an IANA **timezone**; without one it keeps the machine's
  local wall clock.
- A task MAY bind a **workflow**: a skill that declares an automation contract
  (`automation.yaml`: parameters, stages, an optional precheck and reconcile
  command, result schema), a workflow project directory, a profile name, and
  per-stage executors (agent, model, session mode). Coffer reads only the
  declaration; it never scans a skill.
- A **run policy** on the task: timezone, working windows, a holiday calendar
  file, what to do on a non-working slot (skip or move to the next working
  time), per-stage wall-clock timeouts, model-run budgets and work-item limits.
  The policy is checked when a slot comes, before every stage, and before every
  declared write.
- An optional **precheck**: the skill's own command, run through Coffer's
  controlled command entry, decides `no_change`, `wait`, `blocked` or `start`
  with the work items to act on. `no_change` ends the run before any model
  starts.
- **Work items** with a lease: one owner (task, stage, run, agent) per item at a
  time, across every task bound to the same workflow project.
- An **action ledger**: an agent declares an external write before and after it
  through turn-scoped tools; a write that began and never ended is `unknown`
  and blocks its work item until it is reconciled, whatever happens to the run,
  the lease or the agent.
- Run outcomes gain `no_change`, `deferred` (proved not started; safe to retry)
  and `unknown` (started, result not known; must be reconciled). A daemon stop
  closes an interrupted run `unknown`, not `failed`, when its stage may write.
- A **structured result** reported through a turn-scoped tool, validated against
  the flow's schema, from which Coffer writes the business checkpoint into the
  workflow project. Run completion, artifact submission, deployment and
  business verification are reported as separate milestones.
- **Cross-agent hand-over** through the checkpoint: a native session id is
  reused only by the same agent kind, for the same work item, in `continue`
  mode.
- **Unattended permissions**: an automation turn runs under the agent's own
  permission configuration with nothing auto-approved; a tool call that needs a
  person ends the stage `needs_approval`.
- **Model usage per run**: each model call with its stage, reason, agent,
  model and tokens/cost as the agent or the model proxy reports them, or
  `unknown`.
- Duplicate triggers are refused durably: one run per (task, slot), and a
  manual run takes an idempotency key.
- A new capability spec `automation` holds the runtime's requirements; the
  generic scheduled-task requirements move there from `channels`, which keeps
  what is specific to running in a chat.
- The principle "Not a second agent" is amended to state the boundary: Coffer
  runs a flow a skill defines on a trigger; it defines no flow of its own.

## Capabilities

- New: `automation`.
- Modified: `channels` (generic scheduled-task requirements move out; chat
  delivery becomes one target), `experimental-features` (the `scheduled_tasks`
  switch closes the new routes and tools too).

## Impact

- Backend: `application/channel/schedule/` and `domain/channel/schedule*.py`
  move to `application/automation/` and `domain/automation/`; chat-specific
  parts stay in `application/channel/`. New: precheck runner, policy, work-item
  leases, action ledger, result tool, checkpoint writer, usage capture.
  Adapters: an unattended permission mode for Claude Code and Codex.
- Storage: migrations extending `scheduled_task_runs`; new
  `automation_work_items`, `automation_actions`, `automation_model_calls`.
- Contracts: `/api/v1/scheduled-tasks` (target, workflow, policy, executors,
  run detail), new reconcile and work-item routes; `coffer task` gains
  `items`, `actions`, `reconcile`, `precheck`.
- Web UI: task dialog (target, workflow, policy, executors), run detail
  (stages, usage, actions), work items; Run canvas.
- Docs (en, zh): scheduled-tasks guide, a workflow-automation guide,
  architecture principles and daemon/chat pages; ADR
  `automation-runs-flows-skills-define`.
