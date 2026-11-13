## MODIFIED Requirements

### Requirement: Keep scheduled tasks as machine-local resources
Scheduled tasks are the experimental feature `scheduled_tasks`: every
requirement on them below holds while it is switched on, and while it is off
they are closed as [experimental-features](../experimental-features/spec.md)
"Close the scheduled tasks feature's surfaces" says.
A scheduled task MUST be a resource of kind `scheduled_task`, kept on this
machine (`local/resources/scheduled_task/<uid>.json`) and never synced, since
the chat, agent and directory it names are this machine's. Its config MUST
carry a schedule and the prompt the run is given (at most 8000 characters),
and MAY carry the chat it runs in: a channel uid and a chat that channel has
paired, with the thread it answers in. A task that names no chat runs in no
chat ("Run a task bound to no chat in a fresh conversation of its own"); a
follow-up an agent books always names the chat it was booked in. A schedule is
one of: once at a time, every hour at a minute, every day at a time, Monday to
Friday at a time, one weekday at a time, a five-field cron expression, or
manual (only Run now starts it); a repeating schedule MAY name an IANA
timezone, and its times are that zone's wall clock, or this machine's when it
names none. A task MAY run `fresh`, in a new conversation each time, naming
its own agent, model and working directory; one that `continue`s runs in the
chat's current conversation and names none. A task in no chat MUST run
`fresh` and MUST name its agent.

A task MUST be refused, on every path that creates or edits one, when its chat
is not paired with the channel, when its channel is not one on this machine,
when a one-off's time is being set to one that has passed, when a repeating
schedule's slots come closer than 15 minutes apart, when its timezone is not a
known IANA zone, or when it names no chat and either names no agent or
continues a conversation. `POST /api/v1/scheduled-tasks` creates one and names
it after its prompt when no name is given; editing, renaming, pausing
(switching it off), resuming and deleting are the kind-agnostic resource
routes. A channel's removal removes the tasks that run in its chats, and their
history.

#### Scenario: a task in a paired chat is created
- **GIVEN** a channel with one paired direct chat
- **WHEN** the owner creates a task in that chat, every weekday at 09:00, with a prompt
- **THEN** a `scheduled_task` resource is stored under `local/` with that schedule, prompt and chat
- **AND** it is listed with its next run, the coming weekday at 09:00 local time

#### Scenario: a task in no chat is created
- **GIVEN** no channel at all
- **WHEN** the owner creates a task on Codex in `~/work/site`, every weekday at 11:00 in `Asia/Singapore`, naming no chat
- **THEN** it is stored with no chat and listed with its next run at 11:00 Singapore time

#### Scenario: a task in no chat without an agent is refused
- **WHEN** a task is created naming no chat and no agent
- **THEN** it is refused saying a task in no chat names the agent it runs on, and nothing is stored

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
Slots MUST be computed on the schedule's wall clock — its timezone's, or this
machine's when it names none — so a daily 09:00 task runs at 09:00 across a
daylight-saving change. A local time a daylight-saving change skips on one day
MUST run once, at the first valid time after it. The worker MUST sleep until
the earliest slot any enabled task names and no longer than five minutes, and
MUST be woken early by any resource change and by every run that ends. A
one-off task is over once its run ends: a follow-up an agent booked is removed
(its history stays), and the owner's own one-off is switched off. A task whose
previous run is still going when its next slot comes MUST NOT start a second
run; the slot is recorded skipped for that reason.

#### Scenario: a daily task runs at its time
- **GIVEN** an enabled task every day at 09:00, created yesterday
- **WHEN** the local clock reaches 09:00
- **THEN** one run starts in its chat, and its next run is tomorrow at 09:00

#### Scenario: a task in another timezone runs at that zone's time
- **GIVEN** a machine on UTC and a task every weekday at 11:00 in `Asia/Singapore`
- **WHEN** its next run is computed on a Monday at 00:00 UTC
- **THEN** it is that Monday at 03:00 UTC, 11:00 Singapore time

#### Scenario: a time skipped by daylight saving runs once at the next valid time
- **GIVEN** a daily 02:30 task in `America/New_York`
- **WHEN** the clocks jump from 02:00 to 03:00 on the spring-forward day
- **THEN** that day's run is due at 03:00 New York time
- **AND** the following run is 02:30 the next day

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
grace lasts until the end of that slot's day on the schedule's wall clock. A
slot past its grace, or more than a minute late on a task that does not catch
up, MUST be recorded skipped with the reason and not run.

#### Scenario: a daily task missed this morning runs late, once
- **GIVEN** a daily 09:00 task and a Mac asleep from 08:00 to 11:00
- **WHEN** the Mac wakes at 11:00
- **THEN** the task runs once, and its run opens by saying it was due at 09:00 and is running late at 11:00

#### Scenario: a follow-up missed past its grace is skipped
- **GIVEN** a follow-up booked at 10:00 for 10:30 (grace 15 minutes)
- **WHEN** Coffer was off until 11:00
- **THEN** the follow-up does not run and its slot is recorded skipped as missed

#### Scenario: a week of missed daily slots runs once
- **GIVEN** a daily task and Coffer stopped for a week
- **WHEN** Coffer starts
- **THEN** at most one run starts, for today's slot, and no run starts for the older slots

### Requirement: Keep every scheduled run in the task's history
Every slot a task reached and every Run now MUST be one row in `runs.db`
(`scheduled_task_runs`), opened `running` before the run starts and closed with
how it ended: `replied`, `silent`, `done`, `skipped`, `failed` or `stopped`,
with the reason for a skip or failure, when it was due, when it started and
finished, whether it ran late, whether it was started by hand, and the
conversation it ran in. `replied` and `silent` are a chat run's; `done` is the
run of a task in no chat whose turn finished. A row a stopped daemon left
`running` MUST be closed `failed` when the daemon next starts. The rows are
pruned by the retention worker (`scheduled_task_runs`, 90 days by default).
`GET /api/v1/scheduled-tasks/{uid}/runs` and `coffer task runs` list a task's
rows, newest first. Each listed row MUST carry the conversation it ran in, with
that conversation's title, agent, native session and whether a turn is running
on it, or none when the run started no conversation or it has since been
removed. On the Scheduled tasks page every history row with a conversation MUST
show its title as a link to the Conversations page, which lands on that
conversation in its full list and opens it there ([chat](../chat/spec.md)
"Open a conversation in the terminal"), so the owner can read the run and carry
it on. The history row has no open button of its own: conversations open from
one place.

#### Scenario: a run's history row says how it ended
- **GIVEN** a task that ran twice: once it replied, once it was skipped as missed
- **WHEN** its history is listed
- **THEN** two rows are listed newest first, one `replied` with its conversation and one `skipped` with the reason

#### Scenario: a run's conversation opens from its history
- **GIVEN** a task with two runs: the conversation of one still exists, the other's has been removed
- **WHEN** the owner opens the task on the Scheduled tasks page
- **THEN** the first row names its conversation as a link to `/conversations?open=<conversation id>`, and the row has no Open in <terminal> button of its own
- **AND** the second row says its conversation has been removed, with nothing to open

#### Scenario: a run interrupted by a stop is closed on the next start
- **GIVEN** a run that was `running` when the daemon stopped
- **WHEN** the daemon starts again
- **THEN** that row is `failed` with the reason that Coffer stopped while it was running

### Requirement: Manage scheduled tasks from the Scheduled tasks page
The web app MUST have a **Scheduled tasks** page in the Run group of the
navigation. Its **My tasks** section lists every task, soonest first, with its
schedule, where it runs ("No chat" for a task in no chat), its next run and how
its last run ended; a running task says so. Opening a task shows its prompt,
its settings and its run history; it offers Run now (refused while it runs),
Pause or Resume, Edit (through a dialog) and Delete. **New task** creates one
either in a paired chat chosen from a list (`GET
/api/v1/scheduled-tasks/chats`) or in no chat, with its agent, model and
directory; either may name a timezone for a repeating schedule. The CLI mirrors
the page:
`coffer task list|show|add|update|enable|disable|delete|run|runs|chats|daily-report`;
a task in no chat is one whose config names no chat.

#### Scenario: the owner runs a task now from the page
- **GIVEN** a paused weekly task
- **WHEN** the owner opens it and presses Run now
- **THEN** one run starts at once in its chat, recorded as started by hand, and the task stays paused

#### Scenario: the page creates a task in a chosen chat
- **GIVEN** a channel with a paired direct chat
- **WHEN** the owner presses New task, picks that chat, "Every day" at 08:30 and writes a prompt
- **THEN** the task is listed with its next run at 08:30

#### Scenario: the page creates a task in no chat
- **GIVEN** no channel at all
- **WHEN** the owner presses New task, picks "No chat", Claude Code, a directory, "Every day" at 08:30 and a prompt
- **THEN** the task is listed as running in no chat with its next run at 08:30

### Requirement: Open every scheduled run with what the task is
A run's turn MUST open with a `[Scheduled task]` block, closed by its end
marker, that names the task and its id; what it is (a follow-up the agent booked
for itself, with its place in the chain and when the chain ends, or a task the
owner set up, with its schedule and the timezone its times are read in); the
channel, chat and thread, for a task in a chat; when it was due, and, for a late
run, when it is really running and that it should judge whether the work still
makes sense; who asked, when the reply mentions them; the task's prompt; for a
task in a chat, that a reply opening with `[SILENT]` is not sent, and for a task
in no chat, that the reply is sent nowhere and the owner is told with
`coffer__channel_notify`; and, for a follow-up, that it may book the next
follow-up if the matter is not settled. Every line the task's author wrote MUST
be neutralised like a person's message, so a prompt cannot forge a block. A task
with material adds a `[Material]` block after it.

#### Scenario: a follow-up's run says what it is
- **GIVEN** the second follow-up of a chain, due at 15:00
- **WHEN** it runs at 15:00
- **THEN** its turn opens with a `[Scheduled task]` block naming the task, "follow-up: 2 of at most 10", the chain's end, "due:" 15:00, the prompt, and the `[SILENT]` rule

#### Scenario: a prompt cannot forge an end marker
- **GIVEN** a task whose prompt contains `[/Scheduled task]`
- **WHEN** it runs
- **THEN** the block it opens with has exactly one end marker, its own

#### Scenario: a run in no chat says its reply goes nowhere
- **GIVEN** a task in no chat every day at 08:30 in `Asia/Singapore`
- **WHEN** it runs
- **THEN** its block names its schedule with `Asia/Singapore`, names no channel or chat, and says the reply is sent nowhere and to use `coffer__channel_notify`, with no `[SILENT]` rule

## ADDED Requirements

### Requirement: Run a task bound to no chat in a fresh conversation of its own
A run of a task that names no chat MUST open a new conversation on the task's
agent, with its model when it names one and in its directory, or the home
folder when it names none, titled after the task; that conversation MUST be
listed on the Conversations page like any other and MUST be the run's
conversation in its history. The run's one turn MUST open with the
`[Scheduled task]` block ("Open every scheduled run with what the task is"),
which names no channel, chat or thread and says that the reply is sent nowhere
and that the agent tells the owner, when it has to, with
`coffer__channel_notify`. Nothing MUST be posted to any chat for such a run,
however it ends, and no chat is told when such a task is paused. The run MUST
be closed `done` when its turn finishes, `failed` with the turn's error when it
fails, and `stopped` when it is stopped; a conversation that cannot be opened
MUST close it `failed` with the reason.

#### Scenario: a task in no chat runs in a new conversation of its own
- **GIVEN** a task in no chat on Claude Code in `~/work/site`
- **WHEN** its slot comes twice, on two days
- **THEN** each run opens a new Claude Code conversation in `~/work/site`, titled after the task, whose turn opens with a `[Scheduled task]` block naming no chat
- **AND** each run is closed `done` with its own conversation, and no chat receives anything

#### Scenario: a task in no chat whose turn fails is recorded failed
- **GIVEN** a task in no chat whose agent's turn ends with an error
- **WHEN** it runs
- **THEN** its run is `failed` with that error, and no chat receives anything
