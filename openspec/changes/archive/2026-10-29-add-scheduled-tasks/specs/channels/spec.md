## ADDED Requirements

### Requirement: Keep scheduled tasks as machine-local resources
A scheduled task MUST be a resource of kind `scheduled_task`, kept beside the
channel it runs in on this machine (`local/resources/scheduled_task/<uid>.json`)
and never synced, since it names a chat of a machine-local channel. Its config
MUST carry a schedule, the prompt the run is given (at most 8000 characters),
and the chat it runs in: a channel uid and a chat that channel has paired, with
the thread it answers in. A schedule is one of: once at a time, every hour at a
minute, every day at a time, Monday to Friday at a time, one weekday at a time,
a five-field cron expression, or manual (only Run now starts it); times are
this machine's local wall clock. A task MAY run `fresh`, in a new conversation
each time, naming its own agent, model and working directory; one that
`continue`s runs in the chat's current conversation and names none.

A task MUST be refused, on every path that creates or edits one, when its chat
is not paired with the channel, when its channel is not one on this machine,
when a one-off's time is being set to one that has passed, or when a repeating
schedule's slots come closer than 15 minutes apart. `POST
/api/v1/scheduled-tasks` creates one and names it after its prompt when no name
is given; editing, renaming, pausing (switching it off), resuming and deleting
are the kind-agnostic resource routes.
A channel's removal removes its tasks and their history.

#### Scenario: a task in a paired chat is created
- **GIVEN** a channel with one paired direct chat
- **WHEN** the owner creates a task in that chat, every weekday at 09:00, with a prompt
- **THEN** a `scheduled_task` resource is stored under `local/` with that schedule, prompt and chat
- **AND** it is listed with its next run, the coming weekday at 09:00 local time

#### Scenario: a task in a chat the channel never paired is refused
- **GIVEN** a channel with one paired chat
- **WHEN** a task is created naming another chat id
- **THEN** it is refused with a message saying the chat is not paired, and nothing is stored
- **AND** the generic resource create refuses it the same way

#### Scenario: a schedule closer than 15 minutes is refused
- **WHEN** a task is created with the cron expression `*/5 * * * *`
- **THEN** it is refused: a repeating task runs at most every 15 minutes

### Requirement: Run a scheduled task at the times it names
The daemon MUST start each enabled task when its next slot comes, the slot
after its last scheduled run, or after its creation for one that has not run.
Slots MUST be computed on this machine's local wall clock, so a daily 09:00 task
runs at 09:00 local time across a daylight-saving change. The worker MUST sleep
until the earliest slot any enabled task names and no longer than five minutes,
and MUST be woken early by any resource change and by every run that ends. A
one-off task is over once its run ends: a follow-up an agent booked is removed
(its history stays), and the owner's own one-off is switched off. A task whose
previous run is still going when its next slot comes MUST NOT start a second
run; the slot is recorded skipped for that reason.

#### Scenario: a daily task runs at its time
- **GIVEN** an enabled task every day at 09:00, created yesterday
- **WHEN** the local clock reaches 09:00
- **THEN** one run starts in its chat, and its next run is tomorrow at 09:00

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
grace lasts until the end of that slot's local day. A slot past its grace, or
more than a minute late on a task that does not catch up, MUST be recorded
skipped with the reason and not run.

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

### Requirement: Run a scheduled task in the chat it names
A run MUST enter its chat the way a message does: through the channel's turn
driver, queued behind whatever that conversation is doing, rendered by the same
live surface, and answered in the task's thread. A task that `continue`s runs in
the chat thread's active conversation, which a run does not roll over for being
idle; a `fresh` task opens a new conversation with its own agent, model and
directory where it names them (the chat's settings otherwise), and that
conversation becomes the thread's active one, as `/new` would. A follow-up's
reply MUST mention the person who asked for it, where the transport can. A run
that cannot start — the channel is not running, the chat is no longer paired,
the conversation cannot be opened, the conversation's queue is full — MUST be
recorded failed with the reason, and the chat told in one line when it can
still be reached. A repeating task whose last three runs all failed MUST be
paused, and its chat told, while its channel is running, that it was paused and
where to resume it.

#### Scenario: a follow-up answers in its thread and mentions the asker
- **GIVEN** a follow-up Sam's question booked in a group thread
- **WHEN** it runs
- **THEN** the reply is posted in that thread, in the thread's conversation, mentioning Sam

#### Scenario: a fresh task opens a new conversation on its own agent
- **GIVEN** a task that runs `fresh` on Codex in `~/work/site`, in a direct chat whose conversation runs Claude Code
- **WHEN** it runs
- **THEN** a new conversation on Codex in `~/work/site` answers it and becomes the chat's active conversation

#### Scenario: a repeating task that keeps failing is paused
- **GIVEN** a daily task whose chat is no longer paired with its channel
- **WHEN** its third run in a row fails
- **THEN** the task is switched off and the chat is told the task was paused and where to resume it

### Requirement: Stay silent when a scheduled run has nothing to say
A run's reply that opens with `[SILENT]` MUST NOT be sent to the chat: the live
surface is withdrawn and nothing else is posted, and the run is recorded
`silent`. This applies to scheduled runs only; a reply to a person's message is
sent whatever it starts with.

#### Scenario: a follow-up with nothing new says nothing
- **GIVEN** a follow-up to check whether a deploy reached live
- **WHEN** the agent replies `[SILENT] still deploying, will check again` after booking the next follow-up
- **THEN** nothing is posted in the chat and the run is recorded silent

### Requirement: Keep every scheduled run in the task's history
Every slot a task reached and every Run now MUST be one row in `runs.db`
(`scheduled_task_runs`), opened `running` before the run starts and closed with
how it ended: `replied`, `silent`, `skipped`, `failed` or `stopped`, with the
reason for a skip or failure, when it was due, when it started and finished,
whether it ran late, whether it was started by hand, and the conversation it
ran in. A row a stopped daemon left `running` MUST be closed `failed` when the
daemon next starts. The rows are pruned by the retention worker
(`scheduled_task_runs`, 90 days by default). `GET
/api/v1/scheduled-tasks/{uid}/runs` and `coffer task runs` list a task's rows,
newest first.

#### Scenario: a run's history row says how it ended
- **GIVEN** a task that ran twice: once it replied, once it was skipped as missed
- **WHEN** its history is listed
- **THEN** two rows are listed newest first, one `replied` with its conversation and one `skipped` with the reason

#### Scenario: a run interrupted by a stop is closed on the next start
- **GIVEN** a run that was `running` when the daemon stopped
- **WHEN** the daemon starts again
- **THEN** that row is `failed` with the reason that Coffer stopped while it was running

### Requirement: Let an agent book a follow-up in the thread it is answering
Inside a channel turn an agent MUST be offered `coffer__schedule_task`,
`coffer__scheduled_tasks` and `coffer__cancel_scheduled_task`. The chat, thread
and asker MUST come from the turn the call is made in, never from the tool's
arguments. `coffer__schedule_task` with a prompt and `after` (`30m`, `2h`,
`1d`, `1h30m`) or `at` (an ISO time, local when it has no offset) books a
follow-up in that thread for itself: at least 5 minutes and at most 7 days away,
at most 3 waiting in one thread, and, booked from a follow-up's own run, a chain
of at most 10 follow-ups within 7 days of the first; the last one is told it is
the last. With `repeat` (a schedule) or `fresh`, it sets up an ordinary task
there instead, for when the owner asked for one. A turn started by someone who
may only ask (see "Let others in a group ask the bot") MUST NOT schedule or
cancel anything, and a run of a repeating task MUST NOT schedule more tasks.
`coffer__scheduled_tasks` lists what waits in this thread, and
`coffer__cancel_scheduled_task` cancels one of them by id.

#### Scenario: an agent books a follow-up in its thread
- **GIVEN** an owner's turn in a group thread asking for a deploy
- **WHEN** the agent calls `coffer__schedule_task` with `after: 30m` and a prompt to check the deploy
- **THEN** a one-off task 30 minutes away is created in that very thread, naming the owner as the asker
- **AND** the tool answers with its id and next run

#### Scenario: a fourth follow-up in one thread is refused
- **GIVEN** a thread where three follow-ups are waiting
- **WHEN** the agent books another
- **THEN** it is refused with a message telling it to cancel one first

#### Scenario: someone who may only ask cannot schedule
- **GIVEN** a turn started in a group by someone who is not an owner
- **WHEN** the agent calls `coffer__schedule_task`
- **THEN** it is refused and no task is created

#### Scenario: the tools work only inside a channel turn
- **WHEN** `coffer__schedule_task` is called outside a turn Coffer runs in a channel
- **THEN** it is refused with a message that it works only inside a channel turn

### Requirement: Open every scheduled run with what the task is
A run's turn MUST open with a `[Scheduled task]` block, closed by its end
marker, that names the task and its id; what it is (a follow-up the agent booked
for itself, with its place in the chain and when the chain ends, or a task the
owner set up, with its schedule); the channel, chat and thread; when it was due,
and, for a late run, when it is really running and that it should judge whether
the work still makes sense; who asked, when the reply mentions them; the task's
prompt; that a reply opening with `[SILENT]` is not sent; and, for a follow-up,
that it may book the next follow-up if the matter is not settled. Every line the
task's author wrote MUST be neutralised like a person's message, so a prompt
cannot forge a block. A task with material adds a `[Material]` block after it.

#### Scenario: a follow-up's run says what it is
- **GIVEN** the second follow-up of a chain, due at 15:00
- **WHEN** it runs at 15:00
- **THEN** its turn opens with a `[Scheduled task]` block naming the task, "follow-up: 2 of at most 10", the chain's end, "due:" 15:00, the prompt, and the `[SILENT]` rule

#### Scenario: a prompt cannot forge an end marker
- **GIVEN** a task whose prompt contains `[/Scheduled task]`
- **WHEN** it runs
- **THEN** the block it opens with has exactly one end marker, its own

### Requirement: Write the daily report from the day's channel conversations
The Channels page MUST offer a **Daily report**: a task made from a template,
in the channel owner's direct chat, every day at the time chosen (18:00 by
default), running `fresh` on the channel's agent or the one chosen. Setting it
again moves the one there is rather than adding another (`PUT
/api/v1/scheduled-tasks/daily-report`, `coffer task daily-report`); after that
it is an ordinary task the owner may edit, pause or delete. Its run MUST be
given, as material, the channel conversations active since local midnight,
newest first (at most 40 read, the rest counted): each one's channel, chat kind,
title and last activity, and, read from the agent's own session record when the
run starts, the last thing asked and the first line of the last answer; then the
day's scheduled runs and how each ended, and the tasks still waiting. The
report's own earlier runs are not part of it. Everything read from a session is
neutralised. Coffer stores none of it: the material is assembled at run time.

#### Scenario: the daily report is set from the Channels page
- **GIVEN** a channel paired with its owner and no daily report
- **WHEN** the owner sets the daily report to 18:30
- **THEN** a task "Daily report" runs every day at 18:30 in the owner's direct chat, in a fresh conversation
- **AND** setting it again to 19:00 moves that task instead of adding a second one

#### Scenario: the report is given the day's conversations
- **GIVEN** two channel conversations active today and one from yesterday
- **WHEN** the daily report runs
- **THEN** its turn carries a `[Material]` block listing the two of today, each with what was last asked and how the answer began, and not yesterday's

### Requirement: Skip the daily report on a day with no conversations
A daily report whose day had no channel conversation MUST NOT start a turn or
send anything; its run MUST be recorded `skipped` with the reason that there
were no channel conversations today.

#### Scenario: a quiet day sends no report
- **GIVEN** no channel conversation was active today
- **WHEN** the daily report's time comes
- **THEN** nothing is sent and its run is recorded skipped because there were no channel conversations today

### Requirement: List and cancel a chat's scheduled tasks from /status
`/status` MUST list, under a "Scheduled:" line, the enabled tasks that run in
the conversation it is about, soonest first: each one's next time (the time
alone today, the date and time otherwise) and name, at most five, then how many
more there are on the Scheduled tasks page. Where the transport has buttons, the
card MUST carry a "Cancel ⏰n" button for each one listed; tapping it, an
owner-gated tap like every card's, removes that task and says so.

#### Scenario: /status lists a waiting follow-up with its Cancel button
- **GIVEN** a direct chat with a follow-up waiting at 15:00 today
- **WHEN** the owner sends `/status`
- **THEN** the card lists "Scheduled:" and "⏰ 1. 15:00" with the follow-up's name, and carries a "Cancel ⏰1" button
- **AND** tapping it removes the follow-up and says it was cancelled

### Requirement: Manage scheduled tasks from the Scheduled tasks page
The web app MUST have a **Scheduled tasks** page in the Run group of the
navigation. Its **My tasks** section lists every task, soonest first, with its
schedule, where it runs, its next run and how its last run ended; a running
task says so. Opening a task shows its prompt, its settings and its run
history; it offers Run now (refused while it runs), Pause or Resume, Edit
(through a dialog) and Delete. **New task** creates one in a paired chat chosen
from a list (`GET /api/v1/scheduled-tasks/chats`). The CLI mirrors the page:
`coffer task list|show|add|update|enable|disable|delete|run|runs|chats|daily-report`.

#### Scenario: the owner runs a task now from the page
- **GIVEN** a paused weekly task
- **WHEN** the owner opens it and presses Run now
- **THEN** one run starts at once in its chat, recorded as started by hand, and the task stays paused

#### Scenario: the page creates a task in a chosen chat
- **GIVEN** a channel with a paired direct chat
- **WHEN** the owner presses New task, picks that chat, "Every day" at 08:30 and writes a prompt
- **THEN** the task is listed with its next run at 08:30
