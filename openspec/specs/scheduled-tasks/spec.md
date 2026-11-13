# Scheduled Tasks

## Purpose

Let the owner have an agent run a prompt at a time they choose. A scheduled
task is a schedule, a prompt file and the agent to run it on; every run is a
new conversation of its own, and Coffer keeps a history of the runs. Coffer
provides the timing and the history only: what a run does with a chat, a
report or a flow is its prompt's
([A Scheduled Task Is a Prompt on a Schedule](../../../docs/decisions/automation-is-a-scheduled-prompt.md)).
The routes' wire contract is part of the channels family's
([`contracts/api.openapi.yaml`](../channels/contracts/api.openapi.yaml)), and
the run history's table is in its [data model](../channels/data-model.md).

## Requirements

### Requirement: Keep scheduled tasks as machine-local resources
Scheduled tasks are the experimental feature `scheduled_tasks`: every
requirement on them below holds while it is switched on, and while it is off
they are closed as [experimental-features](../experimental-features/spec.md)
"Close the scheduled tasks feature's surfaces" says.
A scheduled task MUST be a resource of kind `scheduled_task`, kept on this
machine (`local/resources/scheduled_task/<uid>.json`) and never synced, since
the agent and folder it uses are this machine's. Its config MUST carry a
schedule and the agent every run opens on (`claude_code` or `codex`), and MAY
carry the model (the agent's default otherwise) and the folder its runs work
in (`cwd`, an absolute path on this machine).
Every task MUST have a folder of its own,
`~/.coffer/content/workspace/scheduled-tasks/<uid>/`, and the prompt the run is
given MUST be the file `PROMPT.md` in it, never part
of the config, so it is read and edited like any file, on the page or in any
editor. A task that names no folder runs in its own, so what its runs write is
kept with it; a task that names one runs there, and its `PROMPT.md` stays in
its own folder. That is the whole task: it names no chat and no
template, and what it does with a chat, a report or a flow is its prompt's
(ADR automation-is-a-scheduled-prompt). A schedule is one of: once at a time, every
hour at a minute, every day at a time, one weekday at a time, a five-field
cron expression, or manual (only Run now starts it); a repeating schedule MAY
name an IANA timezone, and its times are that zone's wall clock, or this
machine's when it names none.

A task MUST be refused, on every path that creates or edits one, when it names
no agent, when a one-off's time is being set to one that has passed, when a
repeating schedule's slots come closer than 15 minutes apart, or when its
timezone is not a known IANA zone, or when the folder it names is not an
absolute path, and a config that carries a prompt MUST be
refused on every path that edits one, naming `PROMPT.md`. `POST
/api/v1/scheduled-tasks` creates one, enabled, and writes its `PROMPT.md`,
naming it after its prompt when no name is given; a task MUST be given its
prompt when it is created, and one without is refused. The prompt has no
length limit of Coffer's own. A one-off whose time has
passed MUST NOT be resumed (refused saying so: it is given a new time first); `PUT /api/v1/scheduled-tasks/{uid}/prompt` (`coffer task prompt`)
replaces the file; editing the rest, renaming, pausing (switching it off),
resuming and deleting are the kind-agnostic resource routes.

#### Scenario: a task is created
- **GIVEN** no channel at all
- **WHEN** the owner creates a task on Codex, every day at 11:00 in `Asia/Singapore`
- **THEN** it is stored under `local/` with that schedule and agent and no folder of its choosing, its prompt is its `PROMPT.md`, and it is listed with its next run at 11:00 Singapore time

#### Scenario: a task without a prompt is refused
- **WHEN** a task is created with a name and no prompt
- **THEN** it is refused, and nothing is stored

#### Scenario: a folder that is not an absolute path is refused
- **WHEN** a task is created with the folder `notes/reports`
- **THEN** it is refused saying the folder must be an absolute path, and nothing is stored

#### Scenario: a task's prompt is the PROMPT.md in its folder
- **WHEN** a task is created with a prompt
- **THEN** its config carries no prompt, and `~/.coffer/content/workspace/scheduled-tasks/<uid>/PROMPT.md` holds it

#### Scenario: a prompt in a task's file is refused on edit
- **GIVEN** a task
- **WHEN** its config is edited through the resource routes with a `prompt` in it
- **THEN** the edit is refused, naming `PROMPT.md`

#### Scenario: a task without an agent is refused
- **WHEN** a task is created naming no agent
- **THEN** it is refused, and nothing is stored

#### Scenario: a schedule closer than 15 minutes is refused
- **WHEN** a task is created with the cron expression `*/5 * * * *`
- **THEN** it is refused: a repeating task runs at most every 15 minutes

#### Scenario: an unknown timezone is refused
- **WHEN** a task is created with timezone `Mars/Olympus`
- **THEN** it is refused naming the timezone, and nothing is stored

### Requirement: Run a scheduled task at the times it names
The daemon MUST start each enabled task when its next slot comes. Slots MUST
be counted from the last slot the scheduler ran or skipped for the task, and,
for a task just created, resumed or given another schedule, from that moment:
the slots a task was paused through are not missed, and neither resuming a
task nor editing its schedule starts a run by itself. Where slots are counted
from is kept on this machine (`local/scheduled-task-anchors.json`), apart from
the run history, so pruning the history changes nothing.
Slots MUST be computed on the schedule's wall clock — its timezone's, or this
machine's when it names none — so a daily 09:00 task runs at 09:00 across a
daylight-saving change. A local time a daylight-saving change skips on one day
MUST run once, at the first valid time after it. The worker MUST sleep until
the earliest slot any enabled task names and no longer than five minutes, and
MUST be woken early by any resource change and by every run that ends. A
one-off task is over once its run ends and is switched off. A task whose
previous run is still going when its next slot comes MUST NOT start a second
run; the slot is recorded skipped for that reason.

#### Scenario: a daily task runs at its time
- **GIVEN** an enabled task every day at 09:00, created yesterday
- **WHEN** the local clock reaches 09:00
- **THEN** one run starts, and its next run is tomorrow at 09:00

#### Scenario: a task in another timezone runs at that zone's time
- **GIVEN** a machine on UTC and a task every day at 11:00 in `Asia/Singapore`
- **WHEN** its next run is computed on a Monday at 00:00 UTC
- **THEN** it is that Monday at 03:00 UTC, 11:00 Singapore time

#### Scenario: a time skipped by daylight saving runs once at the next valid time
- **GIVEN** a daily 02:30 task in `America/New_York`
- **WHEN** the clocks jump from 02:00 to 03:00 on the spring-forward day
- **THEN** that day's run is due at 03:00 New York time
- **AND** the following run is 02:30 the next day

#### Scenario: a one-off task is switched off after it runs
- **GIVEN** a task once at 14:30
- **WHEN** its run ends
- **THEN** the task is switched off and its run stays in the history

#### Scenario: a slot whose previous run is still going is skipped
- **GIVEN** an hourly task whose 10:00 run is still running at 11:00
- **WHEN** the 11:00 slot comes
- **THEN** no second run starts and the 11:00 slot is recorded skipped because the previous run was still going

#### Scenario: resuming a paused task starts nothing
- **GIVEN** a daily 10:30 task paused for three days
- **WHEN** the owner resumes it at 15:00
- **THEN** no run starts, and its next run is tomorrow at 10:30

#### Scenario: editing a task's time starts nothing
- **GIVEN** a daily 18:00 task that ran yesterday
- **WHEN** the owner changes it to 08:00 at noon
- **THEN** no run starts, and its next run is tomorrow at 08:00

#### Scenario: a one-off whose time has passed is not resumed
- **GIVEN** a paused task to run once at a time now past
- **WHEN** the owner resumes it
- **THEN** it is refused saying the time has passed, and the task stays paused

### Requirement: Catch up a missed run once, within seven days
A slot missed because the Mac slept or Coffer was not running MUST run once,
late, when the daemon notices it — if the task catches up (on by default) and
the slot was due no more than seven days ago — and the run's message MUST say, after the
prompt, when it was due, when it is really running, and that the agent should
judge whether the work still makes sense. Only the most recent missed slot MAY
run; every older one is let go. The rule is the same for a one-off and a
repeating task, whatever the time of day: whether late work still makes sense
is the agent's to judge from that message. A slot more than seven days late, or
more than a minute late on a task that does not catch up, MUST be recorded
skipped with the reason and not run.

#### Scenario: a daily task missed this morning runs late, once
- **GIVEN** a daily 09:00 task and a Mac asleep from 08:00 to 11:00
- **WHEN** the Mac wakes at 11:00
- **THEN** the task runs once, and its message says after the prompt that it was due at 09:00 and is running late at 11:00

#### Scenario: an evening task slept through overnight runs the next morning
- **GIVEN** a daily 23:00 task and a Mac asleep from 22:50 until 08:00 the next day
- **WHEN** the Mac wakes
- **THEN** the task runs once, late, for the 23:00 slot

#### Scenario: a slot missed more than seven days ago is skipped
- **GIVEN** a task to run once, and Coffer off from before its time until eight days after it
- **WHEN** Coffer starts
- **THEN** the task does not run, its slot is recorded skipped as missed, and it is switched off

#### Scenario: a task that does not catch up skips a late slot
- **GIVEN** a daily task with catch-up off whose slot passed an hour ago while the Mac slept
- **WHEN** the Mac wakes
- **THEN** the slot is recorded skipped and nothing runs

#### Scenario: a week of missed daily slots runs once
- **GIVEN** a daily task and Coffer stopped for a week
- **WHEN** Coffer starts
- **THEN** at most one run starts, for today's slot, and no run starts for the older slots

### Requirement: Run a scheduled task in a fresh conversation of its own
Every run MUST open a new conversation on the task's agent, with its model
when it names one, in the folder the task names or else the task's own folder, titled after the task; that conversation MUST be listed on the
Conversations page like any other and MUST be the run's conversation in its
history. Its one turn MUST be given the task's `PROMPT.md` as it is when the run
starts, followed only by the late note of "Catch up a missed run once, within
seven days" when the run is late; a run whose `PROMPT.md` is missing or empty,
or whose named folder is not there, MUST be closed `failed` saying so.
Nothing MUST be posted to any chat by Coffer for a run, however it ends; the
agent reaches the owner, when the prompt asks it to, the way any turn can
(`coffer__channel_notify`). The run MUST be closed `done` when its turn
finishes, `failed` with the turn's error when it fails, and `stopped` when it
is stopped; a conversation that cannot be opened MUST close it `failed` with
the reason. A repeating task whose last three runs all failed MUST be paused.

#### Scenario: a task runs in a new conversation of its own each time
- **GIVEN** a task on Claude Code
- **WHEN** its slot comes twice, on two days
- **THEN** each run opens a new Claude Code conversation, titled after the task, whose turn is the task's prompt
- **AND** each run is closed `done` with its own conversation, and no chat receives anything

#### Scenario: a task that names no folder runs in its own
- **GIVEN** a task that names no folder
- **WHEN** it runs
- **THEN** its conversation opens in `~/.coffer/content/workspace/scheduled-tasks/<uid>/`, beside its `PROMPT.md`

#### Scenario: a task runs in the folder it names
- **GIVEN** a task whose folder is a repository on this machine
- **WHEN** it runs
- **THEN** its conversation opens in that repository, and its turn is the `PROMPT.md` in the task's own folder

#### Scenario: a run whose folder is gone fails
- **GIVEN** a task whose named folder has been removed
- **WHEN** its slot comes
- **THEN** the run is `failed` saying the folder does not exist, and no conversation is opened

#### Scenario: the next run is given the prompt as edited
- **GIVEN** a task whose `PROMPT.md` was edited in another editor after it was saved on the page
- **WHEN** it next runs
- **THEN** its turn is given the file as it is on disk

#### Scenario: a run whose PROMPT.md is missing fails
- **GIVEN** a task whose `PROMPT.md` has been deleted
- **WHEN** its slot comes
- **THEN** the run is `failed` with the reason that `PROMPT.md` is missing or empty, and no conversation is opened

#### Scenario: a task whose turn fails is recorded failed
- **GIVEN** a task whose agent's turn ends with an error
- **WHEN** it runs
- **THEN** its run is `failed` with that error, and no chat receives anything

#### Scenario: a repeating task that keeps failing is paused
- **GIVEN** a daily task whose agent's turn fails every time
- **WHEN** its third run in a row fails
- **THEN** the task is switched off

### Requirement: Keep every scheduled run in the task's history
Every slot a task reached and every Run now MUST be one row in `runs.db`
(`scheduled_task_runs`), opened `running` before the run starts and closed with
how it ended: `done`, `skipped`, `failed` or `stopped`, with the reason for a
skip or failure, when it was due, when it started and finished, whether it ran
late, whether it was started by hand, and the conversation it ran in. A row a
stopped daemon left `running` MUST be closed `stopped` when the daemon next
starts: the task did nothing wrong, so it does not count towards the three
failures that pause a task. The rows are pruned by the retention worker (`scheduled_task_runs`, 90
days by default). `GET /api/v1/scheduled-tasks/{uid}/runs` and `coffer task
runs` list a task's rows, newest first, at most 200 at a time; the page shows
the latest 200 and says so when there may be more. Each listed row MUST carry the
conversation it ran in, with that conversation's title, agent, native session
and whether a turn is running on it, or none when the run started no
conversation or it has since been removed. On the Scheduled tasks page every
history row with a conversation MUST show its title as a link to the
Conversations page, which lands on that conversation in its full list and
selects it without opening it; the row's own button opens it ([chat](../chat/spec.md)
"Open a conversation in the terminal"), so the owner can read the run and carry it on. The history row has no open
button of its own: conversations open from one place.

#### Scenario: a run's history row says how it ended
- **GIVEN** a task that ran twice: once it finished, once it was skipped as missed
- **WHEN** its history is listed
- **THEN** two rows are listed newest first, one `done` with its conversation and one `skipped` with the reason

#### Scenario: a run's conversation opens from its history
- **GIVEN** a task with two runs: the conversation of one still exists, the other's has been removed
- **WHEN** the owner opens the task on the Scheduled tasks page
- **THEN** the first row names its conversation as a link to `/conversations?open=<conversation id>`, and the row has no Open in <terminal> button of its own
- **AND** the second row says its conversation has been removed, with nothing to open

#### Scenario: a run interrupted by a stop is closed on the next start
- **GIVEN** a run that was `running` when the daemon stopped
- **WHEN** the daemon starts again
- **THEN** that row is `stopped` with the reason that Coffer stopped while it was running

### Requirement: Manage scheduled tasks from the Scheduled tasks page
The web app MUST have a **Scheduled tasks** page in the Run group of the
navigation. It lists every task, soonest first, with its schedule, its agent,
its next run and how its last run ended; a running task says so. Opening a
task shows two tabs, each at its own path: **Overview** (when it runs, its
next run, agent, model, the folder its runs work in and catch-up, and under
them the task's prompt: `PROMPT.md` shown as a Markdown file with Preview and
Source, an Edit that saves the file, and Reveal in Finder, which is how the
owner reaches whatever else the task keeps in its folder) and **History** (its
runs as a table:
when each started, as a date and time, how it ended, what started it, how long
it took and its conversation, searchable and filtered by outcome and by what
started it). It offers Run now (refused while it runs), Pause or Resume, Edit
(through a dialog, for everything but the prompt) and Delete. **New task** asks
for a name, the prompt, the schedule (with a timezone for a repeating one), the
agent, the model — the agent's default or one of the models the agent offers —
and, optionally, the folder its runs work in, picked with the folder picker;
once created, the task is open on its Overview. The CLI
mirrors the page: `coffer task
list|show|add|prompt|update|enable|disable|delete|run|runs`.

#### Scenario: the owner runs a task now from the page
- **GIVEN** a paused weekly task
- **WHEN** the owner opens it and presses Run now
- **THEN** one run starts at once, recorded as started by hand, and the task stays paused

#### Scenario: the page creates a task
- **GIVEN** no channel at all
- **WHEN** the owner presses New task, names it, writes its prompt, picks Claude Code and "Every day" at 08:30
- **THEN** the task is listed on Claude Code, enabled, and opens on its Overview with that prompt

#### Scenario: the owner reads and edits a task's prompt on its page
- **GIVEN** a task
- **WHEN** the owner opens it, edits the prompt on its Overview and saves
- **THEN** the next run is given the saved prompt

### Requirement: Tell the owner when a task was paused for failing
A repeating task that Coffer paused because its last three runs all failed
MUST be listed in the Overview page's "Needs you"
([web-ui](../web-ui/spec.md)), named, with a link to the task, for as long as
it stays paused with those three failures as its latest runs. Coffer sends no
other notice of a run, a failure or a late run: a task that should tell the
owner something says so in its prompt.

#### Scenario: a task paused for failing is listed in Needs you
- **GIVEN** a daily task paused after its third failed run in a row
- **WHEN** the owner opens the Overview page
- **THEN** "Needs you" lists the task as paused after failing, linking to it
- **AND** once the owner resumes it, it is no longer listed
