# Automation

## Purpose

Coffer starts agent work on a trigger — a time, a manual run, later an event —
and runs a flow a skill declares, for whichever agent each stage names, without
knowing what the flow is about. It owns the task, the run record, the
work-item leases, the action ledger and the usage record; the flow skill owns
the steps; the workflow project owns the business checkpoints. Delivery into a
chat is one target, specified in [channels](../channels/spec.md).

## ADDED Requirements

### Requirement: Keep scheduled tasks as machine-local resources
Scheduled tasks are the experimental feature `scheduled_tasks`: every
requirement in this spec holds while it is switched on, and while it is off
they are closed as [experimental-features](../experimental-features/spec.md)
"Close the scheduled tasks feature's surfaces" says.
A scheduled task MUST be a resource of kind `scheduled_task`, kept under
`local/resources/scheduled_task/<uid>.json` and never synced. Its config MUST
carry a schedule and a target. The target MUST be either a chat — a channel uid
and a chat that channel has paired, with the thread it answers in — or a
workspace, which names no chat. A schedule is one of: once at a time, every
hour at a minute, every day at a time, Monday to Friday at a time, one weekday
at a time, a five-field cron expression, or manual; it MAY name an IANA
timezone, and without one its times are this machine's local wall clock.
A task MUST be refused, on every path that creates or edits one, when a chat
target's chat is not paired or its channel is not on this machine, when a
one-off's time has passed, when repeating slots come closer than 15 minutes
apart, when a named timezone is unknown, or when a bound workflow fails
"Bind a task to a flow a skill declares". A channel's removal removes the
tasks that target its chats, and their history.

#### Scenario: a task in a paired chat is created
- **GIVEN** a channel with one paired direct chat
- **WHEN** the owner creates a task in that chat, every weekday at 09:00, with a prompt
- **THEN** a `scheduled_task` resource is stored under `local/` with that schedule, prompt and chat
- **AND** it is listed with its next run, the coming weekday at 09:00 local time

#### Scenario: a workspace task needs no chat
- **GIVEN** no channel at all
- **WHEN** the owner creates a workspace task every weekday at 11:00 in `Asia/Singapore`
- **THEN** it is stored and listed with its next run at 11:00 Singapore time, shown in the machine's local time beside it

#### Scenario: a task in a chat the channel never paired is refused
- **GIVEN** a channel with one paired chat
- **WHEN** a task is created naming another chat id
- **THEN** it is refused with a message saying the chat is not paired, and nothing is stored
- **AND** the generic resource create refuses it the same way

#### Scenario: a schedule closer than 15 minutes is refused
- **WHEN** a task is created with the cron expression `*/5 * * * *`
- **THEN** it is refused: a repeating task runs at most every 15 minutes

#### Scenario: an unknown timezone is refused
- **WHEN** a task is created with timezone `Mars/Olympus`
- **THEN** it is refused naming the timezone, and nothing is stored

### Requirement: Run a scheduled task at the times it names
The daemon MUST start each enabled task when its next slot comes, the slot
after its last scheduled run, or after its creation for one that has not run.
Slots MUST be computed on the schedule's timezone wall clock, or this
machine's when it names none, across daylight-saving changes. The worker MUST
sleep until the earliest slot any enabled task names and no longer than five
minutes, and MUST be woken early by any resource change and by every run that
ends. A one-off task is over once its run ends: a follow-up an agent booked is
removed (its history stays), and the owner's own one-off is switched off. A
task whose previous run is still going when its next slot comes MUST NOT start
a second run; the slot is recorded skipped for that reason.

#### Scenario: a daily task runs at its time
- **GIVEN** an enabled task every day at 09:00, created yesterday
- **WHEN** the local clock reaches 09:00
- **THEN** one run starts, and its next run is tomorrow at 09:00

#### Scenario: a task in another timezone runs at that zone's time
- **GIVEN** a machine on UTC and a task every weekday at 11:00 in `Asia/Singapore`
- **WHEN** the clock reaches 03:00 UTC on a Monday
- **THEN** one run starts, due at 11:00 Singapore time

#### Scenario: a one-off follow-up is removed after it runs
- **GIVEN** a follow-up an agent booked for 14:30
- **WHEN** its run ends
- **THEN** the task is gone from the list and its run stays in the history

#### Scenario: a slot whose previous run is still going is skipped
- **GIVEN** an hourly task whose 10:00 run is still running at 11:00
- **WHEN** the 11:00 slot comes
- **THEN** no second run starts and the 11:00 slot is recorded skipped because the previous run was still going

### Requirement: Catch up a missed run once, within its grace
A slot missed because the Mac slept or Coffer was not running MUST run once,
late, when the daemon notices it — if the task catches up (on by default) and
the slot is within its grace — and the run MUST say it is late, when it was due
and when it is really running. Only the most recent missed slot MAY run; every
older one is let go. A one-off's grace is half the time between its booking and
its slot, no less than 15 minutes and no more than 2 hours; a repeating slot's
grace lasts until the end of that slot's day in the schedule's timezone. A slot
past its grace, or more than a minute late on a task that does not catch up,
MUST be recorded skipped with the reason and not run.

#### Scenario: a daily task missed this morning runs late, once
- **GIVEN** a daily 09:00 task and a Mac asleep from 08:00 to 11:00
- **WHEN** the Mac wakes at 11:00
- **THEN** the task runs once, and its run says it was due at 09:00 and is running late at 11:00

#### Scenario: a follow-up missed past its grace is skipped
- **GIVEN** a follow-up booked at 10:00 for 10:30 (grace 15 minutes)
- **WHEN** Coffer was off until 11:00
- **THEN** the follow-up does not run and its slot is recorded skipped as missed

#### Scenario: a week of missed daily slots runs once
- **GIVEN** a daily task and Coffer stopped for a week
- **WHEN** Coffer starts
- **THEN** at most one run starts, for today's slot, and no run starts for the older slots

### Requirement: Start each slot at most once
Each (task, slot) MUST open at most one run, however many passes, pokes,
restarts or daemons reach it; the claim MUST be durable before the run starts.
A manual run MUST accept an idempotency key, and a second request with the same
key within 24 hours MUST return the run the first one opened instead of
starting another.

#### Scenario: a slot reached twice opens one run
- **GIVEN** a task whose 11:00 slot is due
- **WHEN** two scheduler passes and a daemon restart all reach that slot
- **THEN** exactly one run row exists for 11:00

#### Scenario: a repeated Run now returns the same run
- **WHEN** Run now is requested twice with the same idempotency key
- **THEN** the second request returns the first run's id and no second run starts

### Requirement: Check the task's working policy before every step
A task MAY carry a policy: working windows in the schedule's timezone, a
holiday calendar file, and what to do with a slot that is not working time —
skip it, or move it to the next working moment. The policy MUST be checked when
a slot comes, before the precheck, before each stage's turn starts, and when an
agent declares a new external write. A slot outside working time MUST be
recorded skipped or moved as the policy says; a stage that would start outside
it MUST be deferred; a write declared outside it MUST be refused as outside the
window. A calendar that does not cover the slot's year, or covers it
unverified, MUST defer the run rather than treat the day as working.

#### Scenario: a slot on a public holiday is skipped
- **GIVEN** a weekday task with policy "skip" and a calendar listing today as a holiday
- **WHEN** its slot comes
- **THEN** no model starts and the slot is recorded skipped as a holiday

#### Scenario: a weekly slot on a holiday moves to the next working day
- **GIVEN** a Monday 10:30 task with policy "next working" and Monday a holiday
- **WHEN** Monday 10:30 comes
- **THEN** the run is recorded moved and starts Tuesday 10:30

#### Scenario: a write after the window closes is refused
- **GIVEN** a running stage and a window ending at 19:00
- **WHEN** the agent declares a new write at 19:01
- **THEN** the declaration is refused as outside the window and nothing is recorded as begun

#### Scenario: an uncovered calendar year defers the run
- **GIVEN** a calendar with only 2026 verified
- **WHEN** a slot comes on 2027-01-04
- **THEN** the run is deferred because the calendar does not cover 2027

### Requirement: Bind a task to a flow a skill declares
A task MAY bind a workflow: a skill, a workflow project directory, a profile
name, parameters and a scope. The skill MUST declare its automation contract in
`automation.yaml` beside `SKILL.md` — parameter schema, stages each with a
prompt, a result schema and whether it may write, and optionally a precheck and
a reconcile command — and Coffer MUST read nothing else from the skill to run
it. Binding MUST be refused when the skill declares no contract, when the
parameters fail its schema, or when the project directory has no stable
workflow id. A task MUST name an executor per stage or a default one — an agent
kind, a model and `fresh` or `continue` — and no flow names an agent or a
model.

#### Scenario: a task binds a declared flow
- **GIVEN** a skill whose `automation.yaml` declares stages `inspect` and `execute`
- **WHEN** a workspace task binds it with valid parameters and executors for both stages
- **THEN** the task is stored and shows the flow, the project and each stage's agent and model

#### Scenario: a skill without a contract cannot be bound
- **WHEN** a task binds a skill that has no `automation.yaml`
- **THEN** it is refused saying the skill declares no automation contract

### Requirement: End a run before any model when the precheck finds nothing
When a bound flow declares a precheck, every run MUST run it first, through
Coffer's controlled command entry, before any agent turn starts. Its answer
MUST be validated against the declared schema. `no_change` and `wait` MUST end
the run recorded `no_change` with no model call; `wait` MUST book the item's
recheck at the time it names, still subject to the policy; `blocked` MUST end
the run `needs_human`; `start` hands its items to the first stage. A precheck
that fails, times out or answers outside its schema MUST defer the run.

#### Scenario: no change starts no model
- **GIVEN** a bound flow whose precheck answers `no_change`
- **WHEN** the task's slot comes
- **THEN** the run is recorded `no_change`, no agent is started and no model call is recorded

#### Scenario: a failing precheck defers the run
- **GIVEN** a precheck that exits non-zero
- **WHEN** the slot comes
- **THEN** the run is recorded deferred with the precheck's error and no agent is started

### Requirement: Give every work item one owner at a time
A run MUST lease each work item before a stage acts on it, keyed by the
workflow id and the item key, so that every task bound to the same workflow
project shares the lease. A lease held by a live run MUST make another run skip
the item. An expired lease MUST be taken over only when the item has no action
of unknown result; otherwise the item MUST wait for reconcile. An item whose
key and version equal the last handled ones MUST NOT be leased again unless its
recheck is due.

#### Scenario: two tasks on one project never own one item
- **GIVEN** a daily scan task and an in-hours follow-up task bound to the same workflow project
- **WHEN** both reach item `ITEM-1` in the same minute
- **THEN** one run leases it and the other records it busy and leaves it alone

#### Scenario: an expired lease over an unknown write is not taken over
- **GIVEN** an item whose lease expired with an action of unknown result
- **WHEN** another run reaches the item
- **THEN** it is not leased and the item is shown as needing reconcile

### Requirement: Tell a run that never started from one whose result is unknown
A stage MUST count as started once its agent turn has produced its first event.
A run that stops before that — policy closed, lease busy, conversation not
opened, agent unavailable, queue full, precheck failed, daemon stopping — MUST
be recorded `deferred`, with every lease it took released, so a later slot may
retry. A started stage that ends without a valid result, runs past its
wall-clock limit, is stopped or is cut by a daemon stop MUST be recorded
`failed`, `timed_out` or `stopped` when the stage may not write, and `unknown`
when it may; an `unknown` run MUST leave its items needing reconcile and keep
their leases. A row a stopped daemon left running MUST be closed by the same
rule when the daemon next starts.

#### Scenario: an agent that is not installed defers the run
- **GIVEN** a stage on an agent kind that is not installed
- **WHEN** the slot comes
- **THEN** the run is deferred, its leases are released, and the next slot tries again

#### Scenario: a writing stage cut by a daemon stop is unknown
- **GIVEN** a running stage that may write
- **WHEN** the daemon stops and starts again
- **THEN** the run is recorded `unknown`, not `failed`, and its item needs reconcile

### Requirement: Never retry an external write whose result is unknown
Inside an automation turn the agent MUST be offered
`coffer__automation_action_begin` and `coffer__automation_action_end`. A begin
MUST be recorded durably before it answers, and MUST answer `already_done` for
an action key already verified, `reconcile` for one begun or unknown, and
`outside_window` or `budget_exhausted` when the policy or the budget forbids a
new write. An action begun and never ended when its run ends MUST become
`unknown`. No failure, lease expiry, other task or change of agent MUST start
an `unknown` action again; only the flow's reconcile command or the owner,
with evidence, MUST resolve it, and only then is the item's lease released.

#### Scenario: an unknown action is refused after an agent switch
- **GIVEN** action `deploy:ITEM-1:abc` left unknown by a run on Codex
- **WHEN** the next run on Claude Code declares the same action
- **THEN** the declaration answers `reconcile` and the write does not happen

#### Scenario: reconcile with evidence releases the item
- **GIVEN** an unknown action and a reconcile command that finds it verified
- **WHEN** reconcile runs
- **THEN** the action is verified with the evidence, the item's lease is released and the next run proceeds

#### Scenario: a report revision is sent once
- **GIVEN** action `report:2026-W45:1` verified
- **WHEN** a later run declares `report:2026-W45:1` again
- **THEN** the declaration answers `already_done` and nothing is sent

### Requirement: Keep business checkpoints in the workflow project and hand over through them
A stage MUST report its result through `coffer__automation_report`, validated
against the stage's result schema; a report outside it MUST be refused to the
agent with the reason. From a valid report Coffer MUST write each item's
checkpoint into the workflow project atomically, with a generation and who
wrote it, and MUST record the item's status and the flow's milestones —
completion of the run, submission of an artefact, a deployment and a business
verification are separate milestones, and none of them completes the item
unless the flow reports it done. The next stage MUST start from that
checkpoint. A native session MUST be continued only by the same agent kind,
for the same item, in `continue` mode; a different agent kind MUST start a
fresh conversation from the checkpoint.

#### Scenario: a hand-over between agents carries the checkpoint, not the session
- **GIVEN** an item inspected on Claude Code whose report names `execute` next
- **WHEN** the execute stage runs on Codex
- **THEN** a fresh Codex conversation starts with the item's checkpoint in its prompt and no Claude Code session id

#### Scenario: a merged artefact does not complete the item
- **GIVEN** a report with milestone `artifact_submitted` reached and status `waiting`
- **WHEN** it is recorded
- **THEN** the item is waiting, not done, and the milestone is listed with its evidence

### Requirement: Run automation turns under the agent's own permissions
An automation turn MUST run under the agent's own permission configuration in
a mode that never asks a person and never approves on their behalf: what the
configuration allows runs, anything else is denied. A turn whose tool call is
denied for want of approval MUST end its stage `needs_approval`, naming the
tool. Coffer MUST refuse to run an automation turn on an agent whose adapter
cannot run in that mode, rather than run it with full permissions.

#### Scenario: a tool that needs approval ends the stage
- **GIVEN** an execute stage whose agent configuration does not allow `git push`
- **WHEN** the agent tries `git push`
- **THEN** the call is denied, the stage ends `needs_approval` naming the tool, and nothing is approved

### Requirement: Record each run's model usage and why
Every agent turn a run starts MUST be recorded with its run, stage, reason
(the trigger and the item keys), agent kind and model, and the input and output
tokens and cost as the agent or the model proxy reports them. A figure neither
reports MUST be recorded unknown, never zero, and the run MUST say whether its
usage is reported, partial or unknown. A task MAY cap its model runs per day;
a run past the cap MUST be deferred.

#### Scenario: usage the agent does not report is unknown
- **GIVEN** an agent turn that ends without token counts and no proxy record
- **WHEN** the run is listed
- **THEN** its model call shows tokens and cost unknown and the run's usage is unknown

### Requirement: Keep a run's result local unless the policy says to notify
A workspace task's result MUST be its run record and the checkpoints and
reports in its workflow project; nothing MUST be posted to a chat for a run
unless the task's delivery policy names a paired chat and the run's outcome is
one it lists. A flow's own outbound message is an external write under
"Never retry an external write whose result is unknown", not a notification.

#### Scenario: a workspace run posts nothing by default
- **GIVEN** a workspace task with no notify policy
- **WHEN** a run ends `needs_human`
- **THEN** the run record says so and no chat receives a message

#### Scenario: a listed outcome notifies the named chat
- **GIVEN** a workspace task notifying its owner's direct chat on `unknown`
- **WHEN** a run ends `unknown`
- **THEN** one message naming the task, the item and the reconcile command is posted to that chat

### Requirement: Keep every scheduled run in the task's history
Every slot a task reached and every manual run MUST be one row in `runs.db`
(`scheduled_task_runs`), opened `running` before the run starts and closed with
how it ended — `replied`, `silent`, `no_change`, `progressed`, `needs_human`,
`needs_approval`, `skipped`, `deferred`, `failed`, `timed_out`, `stopped` or
`unknown` — with the reason, when it was due, started and finished, whether it
ran late, its trigger, the stage reached, the item keys, its usage status and
the conversation of each stage. The rows are pruned by the retention worker
(`scheduled_task_runs`, 90 days by default). `GET
/api/v1/scheduled-tasks/{uid}/runs` and `coffer task runs` list a task's rows,
newest first; `coffer task items`, `coffer task actions` and `coffer task
reconcile` read and resolve its work items and actions over the same routes the
page calls.

#### Scenario: a run's history row says how it ended
- **GIVEN** a task that ran twice: once it replied, once it was skipped as missed
- **WHEN** its history is listed
- **THEN** two rows are listed newest first, one `replied` with its conversation and one `skipped` with the reason

#### Scenario: an unknown action is resolved from the command line
- **GIVEN** a task with one unknown action
- **WHEN** the owner runs `coffer task reconcile <task> <action key> --status verified --evidence <ref>`
- **THEN** the action is verified, the audit log names the owner, and the item is released
