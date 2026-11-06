# Run scheduled tasks without a chat

## Why

A scheduled task today must name a paired chat: its run is a turn in that
chat and its reply is posted there. Most recurring work the owner wants run
(following their own tickets, a weekly summary, a nightly check of a repo)
has no chat to answer in and nothing to post; Claude Code's and Codex's own
automations run a prompt in a fresh session of a project and keep the result
in that session, posting nothing. A task should be able to do the same. Its
times are also only this machine's clock, while the owner works to a
team's timezone.

## What Changes

- A task's chat becomes optional. A task bound to no chat runs, each time, in
  a fresh conversation of its own agent, model and directory (the home folder
  when it names none). Its answer stays in that conversation, which the
  history links to; nothing is posted. To tell the owner something, the agent
  uses `coffer__channel_notify`, as any agent may. A follow-up an agent books
  still runs in the chat it was booked in, and the daily report in the owner's
  direct chat.
- A run of a task bound to no chat ends `done` (its turn finished) or
  `failed`/`stopped`; `replied` and `silent` stay for chat runs.
- A schedule may name an IANA timezone. Its times, and a repeating slot's
  grace, are read on that zone's wall clock; without one, this machine's. A
  local time a daylight-saving change skips runs once at the first valid time
  after it.
- The Scheduled tasks page and `coffer task add|update` let a task run in a
  chat or in no chat, and take a timezone.
- The draft workflow runtime (precheck, work items, action ledger,
  checkpoints, working hours, per-stage agents) is not built: a flow's steps,
  state and checks stay in its skill (ADR
  [Automation is a scheduled prompt](../../../docs/decisions/automation-is-a-scheduled-prompt.md)).

## Capabilities

- Modified: `channels` (scheduled tasks).

## Impact

- Backend: `domain/channel/scheduled_task.py` (optional chat), `schedule.py`
  and `cron.py` (timezone), `application/channel/schedule/runner.py` (a run
  in no chat through a fresh-turn port), `message.py` (the opening block names
  no chat), the HTTP and CLI surfaces.
- Web UI: the task dialog (where it runs, timezone), the task list and
  detail ("No chat").
- Docs (en, zh): scheduled-tasks guide, CLI reference, architecture chat page.
- ADR `automation-is-a-scheduled-prompt`; `principles.md` "Not a second agent".
