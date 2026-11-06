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
carry a schedule, the prompt the run is given (at most 8000 characters), and a
target. The target MUST be either a chat — a channel uid and a chat that
channel has paired, with the thread it answers in — or a workspace, which names
no chat. A schedule is one of: once at a time, every hour at a minute, every
day at a time, Monday to Friday at a time, one weekday at a time, a five-field
cron expression, or manual (only Run now starts it); it MAY name an IANA
timezone, and without one its times are this machine's local wall clock. A task
MAY run `fresh`, in a new conversation each time, naming its own agent, model
and working directory; one that `continue`s runs in the chat's current
conversation and names none.

A task MUST be refused, on every path that creates or edits one, when a chat
target's chat is not paired with the channel, when its channel is not one on
this machine, when a one-off's time is being set to one that has passed, when a
repeating schedule's slots come closer than 15 minutes apart, when a named
timezone is unknown, or when a bound workflow fails "Bind a task to a flow a
skill declares". `POST /api/v1/scheduled-tasks` creates one and names it after
its prompt when no name is given; editing, renaming, pausing (switching it
off), resuming and deleting are the kind-agnostic resource routes. A channel's
removal removes the tasks that target its chats, and their history.

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
machine's when it names none, so a daily 09:00 task runs at 09:00 across a
daylight-saving change; a local time that does not exist on a day, skipped by
the change, MUST run once at the first valid time after it. The worker MUST
sleep until the earliest slot or recheck any enabled task names and no longer
than five minutes, and MUST be woken early by any resource change and by every
run that ends. A one-off task is over once its run ends: a follow-up an agent
booked is removed (its history stays), and the owner's own one-off is switched
off. A task whose previous run is still going when its next slot comes MUST
NOT start a second run; the slot is recorded skipped for that reason.

#### Scenario: a daily task runs at its time
- **GIVEN** an enabled task every day at 09:00, created yesterday
- **WHEN** the local clock reaches 09:00
- **THEN** one run starts, and its next run is tomorrow at 09:00

#### Scenario: a task in another timezone runs at that zone's time
- **GIVEN** a machine on UTC and a task every weekday at 11:00 in `Asia/Singapore`
- **WHEN** the clock reaches 03:00 UTC on a Monday
- **THEN** one run starts, due at 11:00 Singapore time

#### Scenario: a time skipped by daylight saving runs once at the next valid time
- **GIVEN** a daily 02:30 task in `America/New_York`
- **WHEN** the clocks jump from 02:00 to 03:00 on the spring-forward day
- **THEN** exactly one run starts that day, at 03:00 New York time
- **AND** its next run is 02:30 the following day

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
starting another. An item's recheck is not a slot: it MUST NOT take, move or
count as the task's next slot.

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
recorded `skipped` or `moved` as the policy says; a moved slot that lands on or
after the task's next real slot MUST be merged into that slot, so one run
starts. A stage that would start outside working time MUST be deferred; a
write declared outside it MUST be refused as outside the window. A calendar
that does not cover the slot's year, or covers it unverified, MUST defer the
run rather than treat the day as working, and MUST raise a Coffer attention
item naming the task and the year.

#### Scenario: a slot on a public holiday is skipped
- **GIVEN** a weekday task with policy "skip" and a calendar listing today as a holiday
- **WHEN** its slot comes
- **THEN** no model starts and the slot is recorded skipped as a holiday

#### Scenario: a weekly slot on a holiday moves to the next working day
- **GIVEN** a Monday 10:30 task with policy "next working" and Monday a holiday
- **WHEN** Monday 10:30 comes
- **THEN** the Monday slot is recorded `moved` and one run starts Tuesday 10:30

#### Scenario: a moved slot that reaches the next slot runs once
- **GIVEN** a daily 10:30 task with policy "next working" and a holiday on Friday
- **WHEN** Friday 10:30 comes and the next working moment is Monday 10:30, the task's next real slot
- **THEN** Friday's slot is recorded `moved` into Monday's, and exactly one run starts on Monday at 10:30

#### Scenario: a write after the window closes is refused
- **GIVEN** a running stage and a window ending at 19:00
- **WHEN** the agent declares a new write at 19:01
- **THEN** the declaration is refused as outside the window and nothing is recorded as begun

#### Scenario: an uncovered calendar year defers the run
- **GIVEN** a calendar with only 2026 verified
- **WHEN** a slot comes on 2027-01-04
- **THEN** the run is deferred because the calendar does not cover 2027
- **AND** an attention item names the task and the year 2027

### Requirement: Pause a task that keeps failing
A repeating task whose last three runs all ended `failed`, `timed_out`,
`unknown`, or `deferred` for the same reason MUST be switched off, with the
reason recorded on its last run. A deferral the policy causes — outside the
window, a holiday, the model-run budget exhausted, a calendar that does not
cover the year — and a deferral because a work item's lease was busy MUST NOT
count toward the three, nor break a count it sits between; a `timed_out` run
counts as the reason "timed out". A task with no bound flow — a chat target or
a prompt-only workspace task — whose run ends `unknown` MUST be switched off at
once, whatever its count, until the owner resolves that run — `coffer task
reconcile <task> --run <run id>` (`POST
/api/v1/scheduled-tasks/{uid}/runs/{run}/reconcile`) or Resume, either one
audited — so its next slot cannot run the same prompt blindly; a chat target's
chat is told once ([channels](../channels/spec.md) "Run a scheduled task in the
chat it names"). A task with a bound flow is held per work item instead
("Never retry an external write whose result is unknown").

#### Scenario: a workspace task that keeps failing is paused
- **GIVEN** a daily workspace task whose agent is not installed
- **WHEN** its third run in a row is deferred because the agent is unavailable
- **THEN** the task is switched off and its last run says it was paused after three runs that could not start

#### Scenario: policy deferrals never pause a task
- **GIVEN** a daily task whose calendar does not cover the year
- **WHEN** four slots in a row are deferred because the calendar is not covered
- **THEN** the task stays on

#### Scenario: busy leases never pause a task
- **GIVEN** a workflow task whose only item is leased by another task's long run
- **WHEN** four of its runs in a row are deferred because the lease is busy
- **THEN** the task stays on

#### Scenario: a timed-out run counts toward the pause
- **GIVEN** a daily task bound to a flow whose only stage may not write, and whose last two runs timed out
- **WHEN** its third run times out
- **THEN** the task is switched off and its last run says it was paused after three timeouts

#### Scenario: a prompt-only workspace run of unknown result pauses its task
- **GIVEN** a daily workspace task with no bound flow whose run was cut by a daemon stop after its prompt was handed over
- **WHEN** the daemon starts again and the next slot comes
- **THEN** the run is `unknown`, the task is switched off, no run starts for the slot and no chat is told

#### Scenario: a chat run of unknown result pauses its task until resolved
- **GIVEN** a daily chat-target task whose run was cut by a daemon stop after its prompt was handed over
- **WHEN** the daemon starts again and the next slot comes
- **THEN** the run is `unknown`, the task is switched off and no run starts for the slot
- **AND** after `coffer task reconcile <task> --run <run id> --status verified --evidence <ref>` the audit log names the owner and the task is on again

### Requirement: Bind a task to a flow a skill declares
A task MAY bind a workflow: a skill, a workflow project directory, a profile
name, parameters and a scope. The skill MUST declare its automation contract in
`automation.yaml` beside `SKILL.md` — parameter schema, stages each with a
prompt, a result schema and whether it may write, and optionally a precheck and
a reconcile command — and Coffer MUST read nothing else from the skill to run
it. Binding MUST be refused when the skill declares no contract, when the
parameters fail its schema, or when the project directory has no stable
workflow id. A task MUST name an executor per stage or a default one — an agent
kind, a model, `fresh` or `continue`, and for Codex whether the sandbox has
network access (off by default) — and no flow names an agent or a model.

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
the run recorded `no_change` with no model call; `blocked` MUST end the run
`needs_human`; `start` hands its items to the first stage. An item the answer
gives a recheck time MUST be booked for a recheck at that time, at most once
per (workflow, item, time): a recheck run MUST carry trigger `recheck` and the
item, and MUST leave the task's slots as they are. A recheck that falls outside
working time MUST be moved to the next working moment, never skipped; a moved
recheck that meets one already booked for that item and time is one recheck. A precheck that fails, times out or
answers outside its schema MUST defer the run.

#### Scenario: no change starts no model
- **GIVEN** a bound flow whose precheck answers `no_change`
- **WHEN** the task's slot comes
- **THEN** the run is recorded `no_change`, no agent is started and no model call is recorded

#### Scenario: a failing precheck defers the run
- **GIVEN** a precheck that exits non-zero
- **WHEN** the slot comes
- **THEN** the run is recorded deferred with the precheck's error and no agent is started

#### Scenario: a recheck runs beside the task's slots
- **GIVEN** a daily 09:00 task whose precheck answered `wait` for `ITEM-1` with a recheck at 14:00
- **WHEN** 14:00 comes
- **THEN** one run with trigger `recheck` for `ITEM-1` starts
- **AND** the task's next run is still tomorrow at 09:00

#### Scenario: a recheck after hours moves to the next working moment
- **GIVEN** a window 10:00–19:00 and a precheck that answered `wait` for `ITEM-1` with a recheck at 21:00
- **WHEN** 21:00 comes
- **THEN** no run starts and the recheck is booked for 10:00 the next working day
- **AND** one run with trigger `recheck` for `ITEM-1` starts at that time

### Requirement: Give every work item one owner at a time
A run MUST lease each work item before a stage acts on it, keyed by the
workflow id and the item key, so that every task bound to the same workflow
project shares the lease. A lease MUST outlast the stage's wall-clock limit and
MUST be renewed while the stage's turn runs, so it cannot expire under a live
turn. A lease held by a live run MUST make another run skip the item. An
expired lease MUST be taken over, with the lease generation raised by one, only
when the item has no action begun or of unknown result; otherwise the item MUST
wait for reconcile. The lease generation changes only on a takeover. Every
action declaration, result report and checkpoint write MUST carry the lease
generation it acts under, and one from an older lease generation MUST be
refused. An item whose key and version equal the last handled ones MUST NOT
be leased again unless its recheck is due.

#### Scenario: two tasks on one project never own one item
- **GIVEN** a daily scan task and an in-hours follow-up task bound to the same workflow project
- **WHEN** both reach item `ITEM-1` in the same minute
- **THEN** one run leases it and the other records it busy and leaves it alone

#### Scenario: an expired lease over an unknown write is not taken over
- **GIVEN** an item whose lease expired with an action of unknown result
- **WHEN** another run reaches the item
- **THEN** it is not leased and the item is shown as needing reconcile

#### Scenario: a stale owner's write is refused
- **GIVEN** a run whose lease on `ITEM-1` was taken over by another run at a newer lease generation
- **WHEN** the first run's agent declares a write or reports a result for `ITEM-1`
- **THEN** both are refused as from a stale owner, and neither the ledger nor the checkpoint changes

### Requirement: Tell a run that never started from one whose result is unknown
A stage MUST count as started once Coffer has handed its prompt to the agent —
the agent's session is connected and has accepted the prompt — and that moment
MUST be recorded on the run before the turn goes on. A run that stops before
that — policy closed, lease busy, conversation not opened, agent unavailable or
failing to connect, queue full, precheck failed, daemon stopping — MUST be
recorded `deferred`, with every lease it took released, so a later slot may
retry. In a run with a bound flow, a stage's valid result is its report; in a
run without one (a chat task or a prompt-only workspace task) a turn that ends
normally is its valid result, recorded `replied` or `silent`. A started stage
that ends without its valid result — a flow stage without a report, or any
turn that runs past its wall-clock limit, is stopped or is cut by a daemon stop
— MUST be recorded `failed`, `timed_out` or `stopped` when the stage may not
write, and `unknown` when it may; a run without a bound flow counts as one that
may write. An `unknown` flow stage MUST leave each item it leased needing
reconcile, with its lease kept and an action of unknown result recorded for it
when the stage declared none, so the item can be reconciled on its own. A row a stopped daemon
left running MUST be closed by the same rule, from what the run recorded,
when the daemon next starts.

#### Scenario: an agent that is not installed defers the run
- **GIVEN** a stage on an agent kind that is not installed
- **WHEN** the slot comes
- **THEN** the run is deferred, its leases are released, and the next slot tries again

#### Scenario: an agent that fails to connect defers the run
- **GIVEN** a writing stage whose agent session fails to connect before the prompt is handed over
- **WHEN** the slot comes
- **THEN** the run is recorded deferred, not unknown, and its leases are released

#### Scenario: a prompt-only run that ends normally is replied, not unknown
- **GIVEN** a workspace task with a prompt and no bound flow
- **WHEN** its turn ends normally without calling any automation tool
- **THEN** the run is recorded `replied`

#### Scenario: a writing stage cut by a daemon stop is unknown
- **GIVEN** a stage that may write, whose prompt was handed to the agent
- **WHEN** the daemon stops and starts again
- **THEN** the run is recorded `unknown`, not `failed`, and its item needs reconcile

#### Scenario: a writing stage that ends without a report leaves one unknown action per item
- **GIVEN** an execute stage that may write on `ITEM-1` and ends without reporting a result or declaring an action
- **WHEN** the run is closed
- **THEN** the run is `unknown` and action `stage:<run>:execute:ITEM-1` is recorded unknown
- **AND** `coffer task reconcile <task> --item ITEM-1 --status verified --evidence <ref>` resolves it and releases the item

### Requirement: Never retry an external write whose result is unknown
Inside an automation turn the agent MUST be offered
`coffer__automation_action_begin` and `coffer__automation_action_end`. A begin
MUST be recorded durably before it answers, and MUST answer `already_done` for
an action key already verified, `in_progress` for one waiting on an external
system, `reconcile` for one begun or unknown, and `outside_window` or
`budget_exhausted` when the policy or the budget forbids a new write; a begin
on a key whose last attempt failed MUST start a new attempt of it. An action
begun and never ended when its run ends MUST become `unknown`. No failure,
lease expiry, other task or change of agent MUST start an `unknown` action
again: an item with one MUST answer `reconcile` when a run tries to lease it,
and only the flow's reconcile command or the owner, with evidence, MUST resolve
it, per action or per item; only then is the item's lease released.

#### Scenario: an unknown action is refused after an agent switch
- **GIVEN** action `deploy:ITEM-1:abc` left unknown by a run on Codex
- **WHEN** the next run, on Claude Code, reaches `ITEM-1`
- **THEN** the item answers `reconcile` and is not leased, no turn starts for it, and the write does not happen

#### Scenario: a failed write is begun again as a new attempt
- **GIVEN** action `deploy:ITEM-1:abc` whose first attempt ended `failed`
- **WHEN** a later run declares `deploy:ITEM-1:abc`
- **THEN** the declaration answers `begun` and the action shows attempt 2

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
agent with the reason. The first valid report for a (run, stage, item) MUST be
the one kept: a later one MUST answer `already_reported`, and one sent after
the stage ended or under a stale lease generation MUST be refused. Each
accepted report MUST raise the item's checkpoint revision by one. From a valid
report Coffer MUST record the item's status, checkpoint revision and
milestones durably first, then write the item's checkpoint into the workflow
project atomically, with that revision and who wrote it; at startup a
checkpoint whose revision is behind the recorded one MUST be rewritten. Completion of
the run, submission of an artefact, a deployment and a business verification
are separate milestones, and none of them completes the item unless the flow
reports it done. The next stage MUST start from that checkpoint. A native
session MUST be continued only by the same agent kind, for the same item, in
`continue` mode; a different agent kind MUST start a fresh conversation from
the checkpoint.

#### Scenario: a hand-over between agents carries the checkpoint, not the session
- **GIVEN** an item inspected on Claude Code whose report names `execute` next
- **WHEN** the execute stage runs on Codex
- **THEN** a fresh Codex conversation starts with the item's checkpoint in its prompt and no Claude Code session id

#### Scenario: a merged artefact does not complete the item
- **GIVEN** a report with milestone `artifact_submitted` reached and status `waiting`
- **WHEN** it is recorded
- **THEN** the item is waiting, not done, and the milestone is listed with its evidence

#### Scenario: a second report for an item is answered already reported
- **GIVEN** a stage that has reported a valid result for `ITEM-1`
- **WHEN** the agent reports `ITEM-1` again in the same stage
- **THEN** the call answers `already_reported` and the kept result and checkpoint are unchanged

#### Scenario: a checkpoint behind the run record is rewritten at startup
- **GIVEN** a report recorded at checkpoint revision 4 whose checkpoint file still holds revision 3 because the daemon stopped in between
- **WHEN** the daemon starts
- **THEN** the checkpoint file holds revision 4, and the item's lease generation is unchanged

### Requirement: Run every scheduled turn unattended
Every turn a scheduled run starts, for a chat or a workspace target, MUST run
under the agent's own permission configuration in a mode that never asks a
person and never approves on their behalf: what the configuration allows runs,
anything else is denied. The full-permission mode MUST stay limited to turns a
person sends from a chat. On Claude Code, Coffer's own automation tools MUST
always be allowed, and a tool call denied for want of permission MUST end its
stage `needs_approval`, naming the tool. On Codex, a denial by the sandbox or
the approval policy MUST be recorded as the stage's reason where Coffer can
detect it; otherwise the stage ends by the rules above. Coffer MUST refuse to
run a scheduled turn on an agent whose adapter cannot run in such a mode,
rather than run it with full permissions.

#### Scenario: a tool Claude Code is not allowed ends the stage needs approval
- **GIVEN** an execute stage on Claude Code whose configuration does not allow `git push`
- **WHEN** the agent tries `git push`
- **THEN** the call is denied, the stage ends `needs_approval` naming the tool, and nothing is approved

#### Scenario: no scheduled turn runs with full permissions
- **GIVEN** a chat-target task and a workspace task on each registered agent kind
- **WHEN** their runs start
- **THEN** every turn is started in the agent's unattended mode and none in the full-permission mode a person's chat message uses

### Requirement: Record each run's model usage and why
Every agent turn a run starts MUST be recorded with its run, stage, reason
(the trigger and the item keys), agent kind and model, and the input and output
tokens and cost as the agent or the model proxy reports them; a model call the
proxy meters for an automation turn MUST be attributed to that turn's run and
stage. A figure neither reports MUST be recorded unknown, never zero, and the
run MUST say whether its usage is reported, partial or unknown. A task MAY cap
its model runs per day; a run past the cap MUST be deferred.

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

### Requirement: Open every workspace run with what the task is
A workspace run's first turn MUST open with a `[Scheduled task]` block, closed
by its end marker, that names the task and its id, its schedule, when it was
due, and, for a late run, when it is really running and that it should judge
whether the work still makes sense, or that it was started by hand; then the
task's prompt, or for a bound flow the stage's rendered prompt. It names no
channel, chat, thread or asker. Every line the task's author wrote MUST be
neutralised like a person's message, so a prompt cannot forge a block; a task
with material adds a `[Material]` block after it, neutralised the same way. A
chat run opens as [channels](../channels/spec.md) "Open every scheduled run
with what the task is" says.

#### Scenario: a late workspace run says what it is and names no chat
- **GIVEN** a workspace task every weekday at 11:00, due at 11:00 and running at 11:40
- **WHEN** its turn starts
- **THEN** it opens with a `[Scheduled task]` block naming the task, its schedule, "due:" 11:00, that it runs late at 11:40, and the prompt
- **AND** the block names no channel, chat or thread

#### Scenario: a workspace prompt cannot forge an end marker
- **GIVEN** a workspace task whose prompt contains `[/Scheduled task]`
- **WHEN** it runs
- **THEN** the block it opens with has exactly one end marker, its own

### Requirement: Keep every scheduled run in the task's history
Every slot a task reached, every recheck and every manual run MUST be one row
in `runs.db` (`scheduled_task_runs`), opened `running` before the run starts
and closed with how it ended — `replied`, `silent`, `no_change`, `progressed`,
`needs_human`, `needs_approval`, `skipped`, `moved`, `deferred`, `failed`,
`timed_out`, `stopped` or `unknown` — with the reason, when it was due, started
and finished, whether it ran late, its trigger (whether it was started by
hand), the stage reached, the item keys, its usage status and the conversation
of each stage. A row a stopped daemon left `running` MUST be closed when the
daemon next starts as "Tell a run that never started from one whose result is
unknown" says. The rows are pruned by the retention worker
(`scheduled_task_runs`, 90 days by default). `GET
/api/v1/scheduled-tasks/{uid}/runs` and `coffer task runs` list a task's rows,
newest first; `coffer task items`, `coffer task actions` and `coffer task
reconcile` read and resolve its work items and actions over the same routes the
page calls. Each listed row MUST carry the conversation it ran in, with that
conversation's title, agent, native session and whether a turn is running on
it, or none when the run started no conversation or it has since been removed.
On the Scheduled tasks page every history row with a conversation MUST show its
title as a link to the Conversations page, which lands on that conversation in
its full list and opens it there ([chat](../chat/spec.md) "Open a conversation
in the terminal"), so the owner can read the run and carry it on. The history
row has no open button of its own: conversations open from one place.

#### Scenario: a run's history row says how it ended
- **GIVEN** a task that ran twice: once it replied, once it was skipped as missed
- **WHEN** its history is listed
- **THEN** two rows are listed newest first, one `replied` with its conversation and one `skipped` with the reason

#### Scenario: a run's conversation opens from its history
- **GIVEN** a task with two runs: the conversation of one still exists, the other's has been removed
- **WHEN** the owner opens the task on the Scheduled tasks page
- **THEN** the first row names its conversation as a link to `/conversations?open=<conversation id>`, and the row has no Open in <terminal> button of its own
- **AND** the second row says its conversation has been removed, with nothing to open

#### Scenario: a writing run interrupted by a stop is closed unknown on the next start
- **GIVEN** a chat-target run whose prompt was handed to its agent, `running` when the daemon stopped
- **WHEN** the daemon starts again
- **THEN** that row is `unknown` with the reason that Coffer stopped while it was running

#### Scenario: an unknown action is resolved from the command line
- **GIVEN** a task with one unknown action
- **WHEN** the owner runs `coffer task reconcile <task> <action key> --status verified --evidence <ref>`
- **THEN** the action is verified, the audit log names the owner, and the item is released
