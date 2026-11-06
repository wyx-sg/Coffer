# A Scheduled Task Is a Prompt on a Schedule, Each Run a Conversation of Its Own

**Status**: Accepted
**Date**: 2026-11-06
**Deciders**: Yuxing (owner)
**Related**: [An Agent Notifies the Owner Through a Built-in Tool](an-agent-notifies-the-owner-through-a-built-in-tool.md), [Background Workers Wake on Events](background-workers-wake-on-events.md), [Chat Is a Single-Owner Live Mirror](chat-single-owner-live-mirror.md), spec channels, spec daemon, research note [Scheduled agent tasks](../research/scheduled-agent-tasks.md)

## Context

Every Coffer turn used to start because someone sent a message. The owner
wanted turns Coffer starts by itself at a time: recurring work such as a
morning summary, a nightly check of a repository, following their tickets to
delivery, a weekly report.

The first design (2026-10-29) put every task in a paired chat and built three
kinds on it: owner tasks, follow-ups an agent books for itself in the thread
it is answering, and a daily report of the day's channel conversations made
from a built-in template. A second (2026-11-05) added a workflow runtime for
multi-step flows. Reviewing both on 2026-11-06 under the principle that
Coffer does nothing an agent can do for itself, the owner decided:

- a task needs no chat: "就算我们想让任务跟着聊天走，自己在提示词或者skill里写清楚不就好了";
- Coffer keeps no templates: "coffer内置不要保留任何模版，都是用户自己去实现";
- "coffer只提供一个定时任务机制，怎么使用是用户的事情";
- a weekdays schedule goes: "不同国家工作日都不一样的";
- a skill is named in the prompt, not picked in the task.

## How comparable products do it

From the research note, re-read 2026-11-06:

- **Claude Code Desktop scheduled tasks.** A task is a prompt, a schedule
  (cron, a one-off time or manual), a folder and a model. Every run is a new
  session in that folder; the history lists each run and opens its session. A
  missed slot runs once, late.
- **Codex automations.** A prompt, a schedule, a model, working directories and
  a notification policy. A standalone automation opens a new thread per run;
  it can be created from a skill. No step model: what a run does is the
  prompt's.
- **OpenClaw, Hermes Agent.** Cron jobs whose payload is a message to the
  agent, in a new session by default. Both also let an agent book its own
  jobs and suppress a quiet run with a marker (`[SILENT]`, `NO_REPLY`).
- **Devin scheduled sessions, Claude Code routines.** A run is a session that
  can be opened and carried on.

None declares steps, prechecks or checkpoints, and none ships a report
template as part of the scheduler.

## Options Considered

### A — One mechanism: a prompt on a schedule, each run a new conversation (chosen)

A task is a schedule (with an optional IANA timezone), a prompt, an agent, an
optional model and directory, and catch-up. Every run opens a new
conversation on that agent, model and directory; nothing is posted anywhere.
The history row opens the run's conversation. Whatever a run should do with
a chat, a report or a skill, the prompt says; an agent reaches the owner with
`coffer__channel_notify` and can create a task with `coffer task add`.

- **Good:** the same model as Claude Code Desktop and Codex, which the owner
  already knows; one kind of task, one page, no special cases; a flow or a
  report is written once, as a prompt or skill, and runs on either agent.
- **Costs:** a reminder "back in this thread" is the prompt's to arrange; a
  task cannot carry on a chat's conversation; safety a flow needs (one owner
  per item, no blind retry, working hours) is the skill's to get right.

### B — Tasks bound to a paired chat, with follow-ups and a daily report (the 2026-10-29 design)

A task runs in a paired chat, in its conversation or a fresh one, and answers
there; `[SILENT]` suppresses a quiet run; agents book follow-ups through three
turn-scoped tools within limits (5 minutes to 7 days, 3 per thread, chains of
10); the daily report reads the day's sessions at run time; `/status` lists
and cancels tasks.

- **Good:** an answer lands where the question was asked; a follow-up keeps its
  thread's context.
- **Lost because:** each piece is something the agent can do from a prompt
  (send a message, read sessions, write a report), so Coffer carried a chat
  picker, session modes, mentions, a turn block, a silence marker, booking
  limits, a template and material readers for behaviour a prompt already
  gives. It also tied a task to a channel's lifetime.

### C — A workflow runtime in Coffer (the 2026-11-05 draft)

A task binds a flow the skill declares: a precheck command, work items with
leases, a ledger of writes whose result is unknown, checkpoints, working hours,
a different agent per stage and an unattended permission mode.

- **Lost because:** every recurring task is different, so the declaration
  either grows into a language or fits only the first flow; each mechanism is
  a step the skill can take (run a check script, keep a lock, read the clock);
  no comparable product builds one.

### D — Leave recurring work to each agent's own automations

- **Lost because:** a task would be rebuilt per agent, could not run on the
  other one, and would not appear in Coffer's Conversations.

## Decision

Option A. Coffer runs a prompt on a schedule, each run in a new conversation of
its own, and keeps every run in the task's history. It defines no flow, no
chat binding and no template.

Rules a change must keep:

- **Schedule.** Once, daily, weekly, hourly, cron or manual; each may name an
  IANA timezone, otherwise the computer's local time. A repeating task runs at
  most every 15 minutes (Claude Code refuses under an hour, Codex allows
  minutes; 15 keeps a runaway cron from spending a turn a minute).
- **Missed runs.** The most recent missed slot runs once, late, within a grace,
  and the run's prompt says it is late; the rest are skipped and recorded. A
  one-off's grace is half the time it waited (at least 15 minutes, at most 2
  hours); a repeating slot may run until the end of its local day. Catch-up
  can be switched off per task. Running every missed slot would fire a week
  of runs at once; never catching up would starve a Mac that sleeps through
  the slot every day.
- **Overlap and failure.** A slot due while the previous run is still going is
  skipped and recorded. A failed run is not retried (a turn has side effects);
  a repeating task that fails three runs in a row is paused. A one-off is
  switched off after it runs. No cap on tasks running at once.
- **History.** Every run is a row in `scheduled_task_runs` (runs.db): when it
  was due, started and ended, how it ended (`done`, `skipped`, `failed`,
  `stopped`) and why, and the conversation it used; pruned by retention. The
  page names that conversation as a link to the Conversations page, which
  selects it and opens its session in the terminal (`/conversations?open=<id>`);
  Coffer has no transcript view of its own, so conversations open from one
  place.
- **Machine-local.** A task is a `scheduled_task` resource on this Mac only,
  never synced, so nothing runs twice.
- **Experimental.** The `scheduled_tasks` feature is off until the owner
  switches it on, per Mac: a feature that starts turns nobody typed and spends
  tokens on a timer is opted into. Off, the routes close, the scheduler starts
  nothing and the page is hidden; tasks and history are kept.

## Consequences

- A task file an older Coffer wrote is read without its chat, session mode,
  mention or template: it keeps its schedule and prompt, a weekdays schedule
  becomes the cron `M H * * 1-5` in the same timezone, and a task without an
  agent runs on Claude Code. Follow-ups an agent booked are deleted at
  startup. Migration 0156 drops the runs' chat columns and maps the old
  `replied` and `silent` outcomes to `done`.
- The turn-scoped scheduling tools, `/status`'s task list, the Daily report
  card and the `coffer task chats` and `coffer task daily-report` commands are
  gone.
- The principle "Not a second agent" holds: Coffer runs a prompt on a schedule
  and leaves the steps to the prompt and its skills.
- Nothing runs while the Mac sleeps; the late run says when it was due.
- Option C is reconsidered only for a mechanism several real skills need and
  none can do for itself; Option B's pieces only if a prompt demonstrably
  cannot do them.
