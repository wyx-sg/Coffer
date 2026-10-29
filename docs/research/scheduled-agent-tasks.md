# Scheduled agent tasks: how other products do it

**Feature**: an agent turn that starts on its own at a time — a recurring task the owner sets up, a follow-up the agent books for itself, a periodic report — and where its answer goes · **Coffer spec**: [channels](../../openspec/specs/channels/spec.md), [daemon](../../openspec/specs/daemon/spec.md) · **Related ADRs**: [scheduled-tasks-are-turns-coffer-starts-in-a-chat](../decisions/scheduled-tasks-are-turns-coffer-starts-in-a-chat.md)
**Researched**: 2026-10 · **Method**: web research of primary sources (vendor docs, repository docs and source), dated 2026-10-29

## Scope and selection

Every product answers the same six questions:

1. **Who creates a task**: a form, a CLI, the agent itself from a conversation.
2. **Where it runs**: a fresh session each time, or back in the conversation it came from.
3. **What a quiet run does**: whether a run with nothing to report still notifies.
4. **Missed runs**: what happens to a slot that passed while the machine slept or the app was off.
5. **Overlap and failure**: a run still going when the next is due; a run that fails.
6. **Self-scheduling limits**: what stops an agent booking runs without end.

Products: the two first-party coding agents' schedulers (Claude Code Desktop scheduled tasks, Codex automations), the two most-used open personal-agent gateways (OpenClaw, Hermes Agent), and Claude in Slack, whose follow-ups come back to the thread. Heartbeat polling (OpenClaw's second mechanism) is covered as the alternative to scheduled turns.

## Claude Code Desktop — scheduled tasks

[Docs](https://code.claude.com/docs/en/desktop-scheduled-tasks).

- **Creation**: a form in the desktop app (name, prompt, schedule, folder, model), or by asking in a session; a running task can change its own schedule with a tool.
- **Where**: every run is a new session in the task's folder.
- **Schedules**: manual, hourly, daily, weekdays, weekly; the form's shortest interval is an hour.
- **Missed runs**: on wake, a slot missed within the last seven days runs **once**, late; older ones are dropped.
- **Overlap**: a run still going when the next is due makes that next one skip, and the skip is recorded with its reason.
- **Where it shows**: a Scheduled section listing every task, its history, and Run now.

## Codex — automations

[Docs](https://developers.openai.com/codex/app/automations).

- **Creation**: a form in the Codex app, or from a skill.
- **Where**: a standalone automation opens a new thread per run; a **thread automation** is attached to a conversation and runs back in it, with its context — the follow-up case.
- **Quiet runs**: only a run that produced something is marked unread; the docs tell prompt writers to say when the agent should report and when it should stop.
- **Missed runs / overlap**: not documented.

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
- **Self-scheduling**: a scheduled run is not given the cron tool by default, so a task cannot spawn tasks.

## Claude in Slack

The Slack app can come back to a thread later on its own ("I'll check again") and post the follow-up in that thread. Its mechanism is not documented publicly; what it shows is the product shape: the follow-up belongs to the thread that asked.

## Comparison

| | Who creates | Runs in | Quiet run | Missed slot | Overlap / failure | Self-scheduling limit |
| --- | --- | --- | --- | --- | --- | --- |
| Claude Code Desktop | form, session, the task itself | new session | — | once, within 7 days | skip and record | — |
| Codex | form, skill | new thread, or the thread it came from | not marked unread | — | — | — |
| OpenClaw cron | CLI | new / main / named session | — | — | exponential back-off | one-shots deleted after running |
| OpenClaw heartbeat | fixed period | main session | `HEARTBEAT_OK` suppressed | — | — | — |
| Hermes | agent tool, chat command, CLI | new session | `[SILENT]` not sent, failures always sent | once, can be off | — | no cron tool inside a cron run |

## Patterns and trade-offs

- **A scheduled turn, not polling.** Every product with a time attached starts a turn at that time; heartbeat polling is the one exception and spends a turn on every beat to find out nothing happened.
- **Follow-ups and scheduled tasks are one thing.** Codex's thread automations and OpenClaw's named-session jobs are ordinary scheduled jobs that run in an existing conversation; only *where it runs* differs.
- **Silence is a reply.** Hermes and OpenClaw both let a run say "nothing to report" with a marker that suppresses delivery, and both still deliver failures.
- **A missed slot runs once.** The two products that document it catch up a single run, late, and drop the rest.
- **Limit what a run can schedule.** Hermes withholds the scheduling tool from scheduled runs, so tasks do not breed.

## Worth borrowing / worth avoiding

- Borrow: one task model for owner tasks and agent follow-ups; a follow-up runs back in its own conversation; `[SILENT]` with failures always delivered; one late catch-up per missed slot; skip-and-record on overlap; a list with history and Run now.
- Avoid: heartbeat polling (cost with nothing to show); unbounded self-scheduling; automatic retries of a failed turn (an agent turn has side effects).
