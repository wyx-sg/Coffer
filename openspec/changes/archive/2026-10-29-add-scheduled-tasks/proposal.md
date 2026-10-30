# Add scheduled tasks

## Why

Every Coffer turn starts because someone sent a message. Two things the owner
asked for need Coffer to start one by itself:

- **Follow-ups.** The bot says "I'll check again once the deploy is out" and
  then cannot, because nothing will wake it. It should be able to book a turn
  in the same thread for later, and come back to the person who asked.
- **A daily report.** At the end of the day the owner wants one short message
  about what happened in their channel conversations, without reading every
  chat.

Both are the same thing: a turn Coffer starts in a chat when the time comes. So
the core concept is the **scheduled task**, and a follow-up and the daily
report are two kinds of task. Coffer also runs its own background work on
timers (sync, memory sync, retention…); the owner wants to see that beside
their own tasks.

## What Changes

- New machine-local resource kind `scheduled_task`: a schedule (once, hourly,
  daily, weekdays, weekly, cron, manual), the prompt, the paired chat it runs
  in, and whether it carries on the chat's conversation or opens a fresh one
  with its own agent, model and directory.
- A worker that starts each task on time, through the same turn driver a
  message uses. A run missed while the Mac slept or Coffer was off runs once,
  late, within its grace, and says it is late; older slots are skipped and
  recorded. A repeating task that fails three runs in a row is paused.
- A reply that opens with `[SILENT]` is not sent: a run with nothing to say
  says nothing.
- Every run is a row in `runs.db` (`scheduled_task_runs`): when it was due,
  when it ran, how it ended and why.
- Three turn-scoped built-in tools: `coffer__schedule_task`,
  `coffer__scheduled_tasks`, `coffer__cancel_scheduled_task`. An agent books a
  follow-up in the thread it is answering (5 minutes to 7 days away, at most 3
  waiting per thread, a chain of at most 10 within 7 days); when the owner asks
  for it there, any task. Someone who may only ask cannot schedule.
- The daily report: a task made from a template on the Channels page. Its
  material is read from the agents' own sessions at run time (Coffer keeps no
  conversation text); a day with no conversations sends nothing.
- `/status` lists what waits in its conversation, with a Cancel button each.
- A **Scheduled tasks** page in the Run group: the owner's tasks (list,
  history, Run now, edit, pause, delete, new) and, read-only, **Coffer
  internal**: every background worker the daemon reports.
- Plain timer loops report to the worker registry too (mode `timer`), so the
  daemon's status lists every background worker.
- CLI: `coffer task list|show|add|update|enable|disable|delete|run|runs|chats|daily-report`.

## Impact

- Backend: `domain/channel/schedule*.py`, `application/channel/schedule/`,
  the turn driver and renderer, the gateway's turn argument, both agents'
  session readers, the timer loops, migration 0155.
- Contracts: channels (`/api/v1/scheduled-tasks`), daemon (`WorkerOut.mode`).
- Web UI: Scheduled tasks page, Channels daily-report card, navigation.
- Docs (en, zh): scheduled tasks guide, channels guide, CLI reference,
  architecture chat and daemon pages; ADR
  `scheduled-tasks-are-turns-coffer-starts-in-a-chat`; research note
  `docs/research/scheduled-agent-tasks.md`; Run canvas.
