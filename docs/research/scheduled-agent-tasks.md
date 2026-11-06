# Scheduled agent tasks: how other products do it

**Feature**: an agent turn that starts on its own at a time — a recurring task the owner sets up, a follow-up the agent books for itself, a periodic report — and where its answer goes · **Coffer spec**: [channels](../../openspec/specs/channels/spec.md), [daemon](../../openspec/specs/daemon/spec.md) · **Related ADRs**: [scheduled-tasks-are-turns-coffer-starts-in-a-chat](../decisions/scheduled-tasks-are-turns-coffer-starts-in-a-chat.md)
**Researched**: 2026-10 · **Method**: web research of primary sources (vendor docs, repository docs and source), dated 2026-10-29; re-checked 2026-10-30 for run history, reading a run back and release status, adding Claude Code routines, Cursor Automations and Devin

## Scope and selection

Every product answers the same six questions:

1. **Who creates a task**: a form, a CLI, the agent itself from a conversation.
2. **Where it runs**: a fresh session each time, or back in the conversation it came from.
3. **What a quiet run does**: whether a run with nothing to report still notifies.
4. **Missed runs**: what happens to a slot that passed while the machine slept or the app was off.
5. **Overlap and failure**: a run still going when the next is due; a run that fails.
6. **Self-scheduling limits**: what stops an agent booking runs without end.
7. **Reading a run back**: whether a run in the history opens the session it used, to read it and carry it on.
8. **Release status**: whether the feature ships as a preview or behind a switch.

Products: the two first-party coding agents' schedulers (Claude Code Desktop scheduled tasks, Codex automations), the two most-used open personal-agent gateways (OpenClaw, Hermes Agent), and Claude in Slack, whose follow-ups come back to the thread. Heartbeat polling (OpenClaw's second mechanism) is covered as the alternative to scheduled turns.

## Claude Code Desktop — scheduled tasks

[Docs](https://code.claude.com/docs/en/desktop-scheduled-tasks).

- **Creation**: a form in the desktop app (name, prompt, schedule, folder, model), or by asking in a session; a running task can change its own schedule with a tool.
- **Where**: every run is a new session in the task's folder.
- **Schedules**: manual, hourly, daily, weekdays, weekly; the form's shortest interval is an hour.
- **Missed runs**: on wake, a slot missed within the last seven days runs **once**, late; older ones are dropped.
- **Overlap**: a run still going when the next is due makes that next one skip, and the skip is recorded with its reason.
- **Where it shows**: a Scheduled section listing every task; a task's detail page has its status (Active or Paused), Run now, Edit, History, its always-allowed tools and Delete.
- **Reading a run back**: "To open the session a run started, go to the task's detail page and click that run's row in the History list." Hovering a skipped row says why: the computer was asleep, the previous run was still going, or other scheduled tasks were already running.
- **Catch-up notice**: a notification when a catch-up run starts.
- **Release status**: no preview label; needs a recent Desktop build.

## Claude Code — routines (cloud)

[DataCamp guide](https://datacamp.com/tutorial/claude-code-routines), [schedule docs](https://code.claude.com/docs/en/scheduled-tasks).

- **Where**: every run is a new cloud session on a fresh clone; minimum interval one hour.
- **History**: a run list with a status per run; green means the session ran without an infrastructure error, not that the task succeeded.
- **Reading a run back**: "Click any run to read it as a full session, where you can see what Claude did, review the diff, open a pull request, or keep the conversation going."
- **Release status**: a research preview, with hourly caps on event triggers; the API is marked experimental.
- (The in-session `/loop` scheduler, by contrast, keeps no run history and does not catch up: a missed fire runs once when the session is next idle, and tasks expire after seven days.)

## Cursor — Automations

[DataCamp guide](https://datacamp.com/tutorial/cursor-automations-hands-on-guide), [changelog](https://cursor.com/changelog/03-05-26).

- **Where**: each run in a fresh cloud sandbox; a memory tool carries state between runs.
- **History**: an automation's page has its run history; a run shows execution time, tool calls and output, and a Failed count.
- **Quiet runs**: left to the prompt ("If no high or critical issues are found, do not post to Slack at all").
- **Release status**: "still under development", on paid plans.

## Devin — scheduled sessions

[Docs](https://docs.devin.ai/product-guides/scheduled-sessions) (now marked legacy; new work is created as an automation).

- **Where**: each run is its own session; recurring or one-time (a one-time schedule switches itself off after running).
- **History**: a Past Sessions tab listing name, frequency, last run time and status.
- **Reading a run back**: "Click on any session to navigate to its full session view."
- **Failure**: a schedule shows Error after consecutive failures; email on failure only by default (or always, or never).

## Codex — automations

[Docs](https://developers.openai.com/codex/app/automations).

- **Creation**: a form in the Codex app, or from a skill.
- **Where**: a standalone automation opens a new thread per run; a **thread automation** is attached to a conversation and runs back in it, with its context — the follow-up case.
- **Quiet runs**: only a run that produced something is marked unread; the docs tell prompt writers to say when the agent should report and when it should stop.
- **Missed runs / overlap**: not documented; the app must be running for a task that needs local files.
- **Reading a run back**: a standalone run is a new chat in the sidebar, a thread automation's runs are in its chat; recent runs are listed under Scheduled.

## OpenClaw — cron and heartbeat

[Cron docs](https://docs.openclaw.ai/automation/cron-jobs), [CLI](https://docs.openclaw.ai/cli/cron.md).

- **Cron**: jobs created from the CLI with an `at`, an interval or a cron expression; each runs in a new isolated session by default, or in the main session, or in a named one. Repeated failures back off exponentially; a one-shot job is deleted after it runs.
- **Heartbeat**: every 30 minutes the agent reads a checklist file in the main session and answers `HEARTBEAT_OK` when nothing needs saying, which is suppressed. Most beats are empty turns, paid for in tokens; community guides ([example](https://lumadock.com/tutorials/openclaw-heartbeat-vs-cron-vps)) recommend cron for anything with a time.

## Hermes Agent — cron

[Docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron).

- **Creation**: the agent calls a cron tool from a conversation; `/cron add` in chat; a CLI.
- **Where**: a fresh session per run; the answer is delivered to the chat it was created from, or another named target.
- **Quiet runs**: a reply that starts with `[SILENT]` is not delivered; a failure is always delivered.
- **Missed runs**: after a restart a missed job runs once; this can be switched off per job.
- **Self-scheduling**: a scheduled run is not given the cron tool by default, so a task cannot spawn tasks; an agent scheduling at all is off until `cron.allow_agent_scheduling` is set.
- **Catch-up window**: half the job's period, clamped to 2 minutes – 2 hours. A failure streak nudges after 3; a run whose model is unreachable retries after 5, 15 and 30 minutes.
- **History**: `hermes cron runs` lists attempts and their states; output is saved to files, not linked to a session.

## Claude in Slack

The Slack app can come back to a thread later on its own ("I'll check again") and post the follow-up in that thread. Its mechanism is not documented publicly; what it shows is the product shape: the follow-up belongs to the thread that asked.

## Comparison

| | Who creates | Runs in | Quiet run | Missed slot | Overlap / failure | Self-scheduling limit |
| --- | --- | --- | --- | --- | --- | --- |
| Claude Code Desktop | form, session, the task itself | new session | — | once, within 7 days | skip and record | — |
| Codex | form, skill | new thread, or the thread it came from | not marked unread | — | — | — |
| OpenClaw cron | CLI | new / main / named session | — | — | exponential back-off | one-shots deleted after running |
| OpenClaw heartbeat | fixed period | main session | `HEARTBEAT_OK` suppressed | — | — | — |
| Hermes | agent tool, chat command, CLI | new session | `[SILENT]` not sent, failures always sent | once, within half the period (2 min – 2 h) | nudge after 3 failures | agent scheduling off by default; no cron tool inside a cron run |
| Claude Code routines | form, API | new cloud session | — | — | — | — |
| Cursor Automations | form | new sandbox | left to the prompt | — | failed count | — |
| Devin | form | new session | — | — | Error after consecutive failures | — |

| | Run row opens its session | Release status |
| --- | --- | --- |
| Claude Code Desktop | yes | no label |
| Claude Code routines | yes, and carry it on | research preview |
| Devin | yes | legacy, superseded by automations |
| Codex | runs are ordinary chats | no label |
| Cursor Automations | run detail, no session link documented | still under development |
| Hermes, OpenClaw | no (CLI list, output files) | no label; Hermes' agent scheduling opt-in |

## Patterns and trade-offs

- **A scheduled turn, not polling.** Every product with a time attached starts a turn at that time; heartbeat polling is the one exception and spends a turn on every beat to find out nothing happened.
- **Follow-ups and scheduled tasks are one thing.** Codex's thread automations and OpenClaw's named-session jobs are ordinary scheduled jobs that run in an existing conversation; only *where it runs* differs.
- **Silence is a reply.** Hermes and OpenClaw both let a run say "nothing to report" with a marker that suppresses delivery, and both still deliver failures.
- **A missed slot runs once.** The two products that document it catch up a single run, late, and drop the rest.
- **Limit what a run can schedule.** Hermes withholds the scheduling tool from scheduled runs, so tasks do not breed.
- **A run opens its session.** Every product with a session per run (Claude Code Desktop, routines, Devin) makes the history row the way into it, to read what happened and carry on.
- **Ship it as opt-in.** The newer schedulers are labelled preview or under development, and Hermes keeps agent self-scheduling off by default.

## Worth borrowing / worth avoiding

- Borrow: a history row that opens its run's session to read and carry on; opt-in while it is new;
  one task model for owner tasks and agent follow-ups; a follow-up runs back in its own conversation; `[SILENT]` with failures always delivered; one late catch-up per missed slot; skip-and-record on overlap; a list with history and Run now.
- Avoid: heartbeat polling (cost with nothing to show); unbounded self-scheduling; automatic retries of a failed turn (an agent turn has side effects).
