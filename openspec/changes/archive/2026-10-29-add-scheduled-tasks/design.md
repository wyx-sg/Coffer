# Design: scheduled tasks

The decisions and the alternatives weighed are in the ADR
[Scheduled tasks are turns Coffer starts in a chat](../../../docs/decisions/scheduled-tasks-are-turns-coffer-starts-in-a-chat.md);
the research into comparable products is
[`docs/research/scheduled-agent-tasks.md`](../../../docs/research/scheduled-agent-tasks.md).
This file is the shape of the code.

## Where it lives

Inside the channel package (`application/channel/schedule/`), because every
run is a turn in a paired chat: the runner needs the channel's bindings, peers,
threads and turn driver, and a separate kind would need a cross-kind import for
each. The kind is `scheduled_task`, stored `LOCAL` (a task names a chat on this
machine's channel, which is itself machine-local).

```
domain/channel/schedule.py          Schedule union, next_slot (local wall clock, DST-aware), cron parser
domain/channel/scheduled_task.py    ScheduledTaskConfig, limits, grace_for
domain/channel/scheduled_run.py     ScheduledRun row
application/channel/schedule/
  kind.py        the Kind (validation: past one-off, <15 min repeat, unknown channel)
  scheduler.py   TaskScheduler: WakeableLoop, one decision per due task
  runner.py      TaskRunner: history row -> conversation -> QueuedInbound -> TurnDriver
  message.py     the [Scheduled task] block
  material.py    the daily report's material
  tasks.py       TaskService: create, book (agent), daily_report, list, cancel
  tools.py       the three built-in tools
application/channel/status_tasks.py  /status lines and Cancel buttons
application/channel/turn_origin.py   conversation -> where its running turn came from
infrastructure/channel/schedule_run_persistence.py  scheduled_task_runs
surfaces/http/schedule_wiring.py, schedule_routes.py
```

## A run

1. The scheduler's pass finds the task's next slot after its last scheduled
   run (or its creation). If it is due, it walks forward to the most recent
   slot at or before now; anything older is let go.
2. Still running → skipped ("the previous run was still going"). Past its grace
   (or past one minute with catch-up off) → skipped ("missed"). Otherwise run,
   marked late when more than a minute behind.
3. The runner opens a `running` row, then the conversation: `continue` is the
   thread's active conversation (no idle rollover); `fresh` opens a new one with
   the task's agent/model/directory as one-off preferences, and it becomes the
   thread's active one, like `/new`.
4. A `QueuedInbound` carrying a `ScheduledTurn` goes through
   `TurnDriver.submit_scheduled`, so it queues behind what the conversation is
   doing and renders like any turn, mentioning the asker.
5. The renderer, told the turn is scheduled, drops a clean reply that opens
   with `[SILENT]`. When the turn ends, `ScheduledTurn.on_end` closes the row
   with `replied`, `silent`, `failed` or `stopped`.
6. After the run: a one-off is over (an agent's follow-up is deleted, the
   owner's is switched off); a repeating task with three failed runs in a row
   is paused and the chat told.

The scheduler sleeps until the earliest due slot, at most five minutes (the
loop's clock stops while a Mac sleeps), and is poked by every resource write
and every finished run.

## Knowing the caller

The gateway passes a turn-scoped tool the turn token it was called under
(`TURN_ARGUMENT`); `turn_tokens.conversation_of` turns it into the
conversation, and `turn_origin` (written by the turn driver while a channel
turn renders) gives the channel, chat, thread, asker and, for a scheduled run,
the task and chain. Nothing the agent passes says where a task runs.

## Grace

- One-off: half the time between booking and the slot, clamped to 15 minutes–2 hours.
- Repeating: until the end of the slot's local day; and never past the next slot.

## The daily report's material

At run time: the channel conversations active since local midnight, newest
first (at most 40 read); for each, its channel, chat kind, title, last activity,
and — read from the agent's own session (`get_session_messages` for Claude
Code, app-server `thread/read` for Codex) — the last thing asked and the first
line of the last answer. Then today's scheduled runs and the tasks still
waiting. Everything read is neutralised. No conversations → the run is
recorded `skipped` and nothing is sent.
