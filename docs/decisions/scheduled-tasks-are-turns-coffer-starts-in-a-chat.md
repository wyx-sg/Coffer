# Scheduled Tasks Are Turns Coffer Starts in a Chat; Follow-Ups and the Daily Report Are Kinds of Task

**Status**: Accepted
**Date**: 2026-10-29
**Deciders**: Yuxing (owner)
**Related**: [Channels Are Machine-Local Resources, Like Agents](channels-are-machine-local-resources.md), [A Channel Answers Only Its Paired Owner, and Fails Closed in Groups](channel-owner-gate.md), [Others in a Group May Ask the Bot, Read-Only, by Instruction](others-in-a-group-may-ask-read-only.md), [A Channel Conversation Is Keyed by (Channel, Chat, Thread)](channel-conversation-identity.md), [Background Workers Wake on Events](background-workers-wake-on-events.md), [Chat Is a Single-Owner Live Mirror](chat-single-owner-live-mirror.md), spec channels, spec daemon, research note [Scheduled agent tasks](../research/scheduled-agent-tasks.md)

## Context

Every Coffer turn used to start because someone sent a message. The owner asked
for two things that need Coffer to start one itself:

- **Follow-ups.** A bot says "I'll check again once the deploy is out" and
  cannot, because nothing wakes it. It should book a turn in the same thread
  and come back to whoever asked, saying nothing if there is nothing to say.
- **A daily report.** At the end of the day, one short message to the owner
  about what happened in their channel conversations.

The owner's own direction, on reviewing the first draft: the core concept is the
**scheduled task**, and a follow-up and the daily report are each a kind of
task. They also asked to see Coffer's own background work on the same page.

Forces:

- A turn already has one road: the turn driver renders a message into the
  agent's session and streams the reply back to the chat. Anything that starts
  a turn should use it, so queuing, `/stop`, held messages and session
  takeover behave the same.
- Coffer keeps no conversation text (the agents' own sessions are the record),
  which bounds what a report can be written from.
- A Mac sleeps and Coffer may be off; nothing can be guaranteed to run on the
  minute. Waking a Mac (`pmset schedule wake`) needs root and is unreliable with
  the lid shut.
- An agent that can book its own turns must not be able to book without end,
  and someone who may only *ask* in a group (read-only) must not schedule.
- Channels, agents and their directories are machine-local; a task naming them
  is too, and two Macs must not both run it.

How other products do it is in the research note: every product with a time
attached starts a turn at that time; follow-ups are ordinary jobs that run in an
existing conversation (Codex thread automations, OpenClaw named sessions); a
quiet run is suppressed by a marker (Hermes `[SILENT]`, OpenClaw
`HEARTBEAT_OK`); a missed slot runs once, late (Claude Code Desktop, Hermes).

## Options Considered

### Option A — One task kind; a run is a turn Coffer starts in a paired chat (chosen)

A `scheduled_task` is a machine-local resource: a schedule (once, hourly,
daily, weekdays, weekly, cron, manual), a prompt, the paired chat it runs in,
and whether it carries on that chat's conversation or opens a fresh one with its
own agent, model and directory. One daemon worker sleeps until the earliest
slot and hands each due task to the turn driver, as if the message had arrived
from the chat, with a block in front saying what the task is. A follow-up is a
one-off task an agent books with a turn-scoped tool, in the thread it is
answering; the daily report is a task made from a template whose run is given
the day's conversations as material.

- Pros: one model, one list, one set of run rules (silence, catch-up, overlap,
  failure, history) for every kind; the turn path is unchanged, so every
  existing behaviour of a chat turn holds for a scheduled one; follow-ups and
  owner tasks can be listed, paused and cancelled in one place.
- Cons: the task config carries fields only some kinds use (a follow-up's
  chain and mention, the report's template); the turn driver must learn a turn
  that has no inbound message.
- Why it wins: it is what the owner asked for, and it matches every product
  surveyed; the cost is a few optional fields.

### Option B — Separate features: a follow-up tool, a report job, a task list

Each built on its own: a follow-up store keyed by thread, a fixed 18:00 job for
the report, and later a general scheduler.

- Pros: each is simpler on its own; the report needs no task UI.
- Cons: three schedulers with three sets of rules for missed runs, silence and
  failure; three places to look; the general scheduler would later have to
  absorb the other two.
- Loses because: the owner explicitly chose one concept, and the rules would
  drift apart.

### Option C — Heartbeat polling

Every N minutes the agent reads a checklist and decides whether to say
something (OpenClaw heartbeat).

- Pros: no schedule to model; the agent decides.
- Cons: a paid turn every beat, most of them empty; nothing happens at a time
  the owner chose; a follow-up "at 16:00" becomes "some beat after 16:00".
- Loses because: cost with nothing to show, and it cannot keep a time.

### Option D — External-event hooks (CI finished, deploy done)

A follow-up waits for a webhook instead of a time.

- Pros: exact; no polling at all.
- Cons: every source needs its own integration and a reachable endpoint;
  Coffer runs on a laptop behind NAT.
- Loses for now: it can be added later as another way to start the same task.

### What the report reads

- **A — read the agents' own sessions at run time (chosen).** For each of the
  day's channel conversations, the last thing asked and the first line of the
  answer are read from the session through the agent's own reader. Keeps
  "Coffer stores no conversation text"; costs two readers (Claude Code, Codex)
  and a read per conversation, capped.
- **B — store the first line of each question and answer for seven days.**
  Simplest, but breaks the principle and needs its own retention and sync story.
- **C — read the chat platform's history.** SeaTalk can; Telegram bots cannot
  read history. Not general.

### Missed runs

- **Run one missed slot once, late, within a grace; skip and record the rest
  (chosen).** A one-off's grace is half the time it waited (at least 15
  minutes, at most 2 hours): a follow-up matters only while it is timely. A
  repeating slot may run until the end of its local day. The run says it is
  late. Catch-up can be switched off per task.
- **Run every missed slot.** A week asleep would fire seven reports at once.
- **Never catch up.** A Mac that sleeps through 18:00 every day never reports.

### Reading a run back (added 2026-10-30)

The owner asked that every run show the conversation it used, and open it to
read or carry on. Comparable products split the same way:

| Product | Run row links to its session | Can carry it on |
| --- | --- | --- |
| Claude Code Desktop scheduled tasks | yes: a History row opens the session the run started | yes, it is an ordinary session |
| Claude Code routines (cloud) | yes: "click any run to read it as a full session" | yes, "keep the conversation going" |
| Devin scheduled sessions | yes: Past Sessions, each opens its session view | yes |
| Cursor Automations | a run shows its tool calls and output | not documented |
| Codex automations | standalone runs are new chats, thread automations return to their chat | the chat is ordinary |
| Hermes, OpenClaw | a CLI run list, output saved to a file | no |

- **A — the run row names its conversation and opens it in the terminal
  (chosen).** The history already keeps the conversation id; the runs route
  adds the conversation's title, agent, native session and whether a turn is
  running, and the row reuses the Conversations page's Open in <terminal>
  split button and busy dialog. Coffer has no conversation view of its own
  (the transcript stays in the agent's session), so "read it and carry it on"
  is resuming that session, exactly as from the Conversations page. A run
  whose conversation was removed says so; a skipped run started none.
- **B — a transcript view inside the page.** Would need Coffer to read and
  render agent transcripts, which it deliberately does not keep.
- **C — only link to the Conversations page filtered to the chat.** One more
  click and loses which run used which conversation (a `continue` task shares
  one).

### Rollout (added 2026-10-30)

- **Behind an experimental switch, off by default (chosen).** The owner asked
  for it. Scheduled tasks start turns nobody typed, spend tokens on a timer
  and let agents book their own follow-ups, so a person should opt in on each
  Mac. Comparable products ship the same way: Claude Code routines are a
  research preview, Cursor Automations are "still under development", Hermes
  keeps agent self-scheduling off until `allow_agent_scheduling` is set. The
  `scheduled_tasks` feature owns the `/api/v1/scheduled-tasks` routes and the
  `scheduled_task` kind; while it is off the scheduler starts nothing, the
  three tools leave every turn, `/status` lists no task, and the page and the
  Daily report card are hidden. Tasks and history are kept, and a slot missed
  while off is caught up or skipped as any missed slot.
- **Always on.** Simpler, but every Mac would carry a feature that starts
  turns on its own before it is proven.
- **A separate switch for agent follow-ups only (Hermes' split).** The whole
  feature is already opt-in; a second switch would add a state the page and
  `/status` must explain for little gain. Revisit when the feature graduates.

### Checks against comparable products (2026-10-30)

Re-reading the products' docs found the rest of the design in line, with
these choices kept on purpose:

- **Shortest repeat: 15 minutes.** Claude Code Desktop and routines refuse
  anything under an hour; Codex allows minutes. A follow-up chain and an
  hourly check are real uses, and 15 minutes keeps a runaway cron from
  spending a turn a minute.
- **No cap on tasks running at once.** Claude Code Desktop skips a run while
  other scheduled tasks are running. Coffer's runs are turns in different
  chats, which already run side by side when people write; a cap would skip
  reports for no reason the owner can see. Revisit if a busy morning shows
  load.
- **Failures.** Devin marks a schedule Error after consecutive failures and mails on failure
  only; Hermes nudges after three. Coffer pauses a repeating task after three
  failures in a row and always sends a failure to the chat.

## Decision

A scheduled task is a machine-local `scheduled_task` resource whose run is a
turn Coffer starts in a paired chat through the same turn driver a message
uses. Follow-ups and the daily report are tasks with particular values; there is
no second scheduler.

Rules a change must keep:

- **Where it runs.** Only in a chat the owner already uses with a bot (a
  paired chat). `continue` sends the run into that chat's conversation (queued
  behind a running turn); `fresh` opens a new conversation each run.
- **What the agent is told.** Every run opens with a block naming the task, the
  schedule, when it was due, whether it is late or started by hand, and — for a
  follow-up — its place in the chain and whom to address. A prompt cannot forge
  the block's end.
- **Silence.** A reply that opens with `[SILENT]` is not sent. A failure is
  always sent.
- **Missed runs.** As above: one late run within the grace, the rest skipped
  and recorded.
- **Overlap and failure.** A slot due while the previous run is still going is
  skipped and recorded. A failed run is not retried (a turn has side effects);
  a repeating task that fails three runs in a row is paused and the chat told.
- **History.** Every run is a row in `scheduled_task_runs` (runs.db): when it
  was due, started and ended, how it ended and why, and the conversation it
  used; pruned by retention. The page names that conversation and opens its
  session in the terminal, to read the run or carry it on.
- **Who may schedule.** Three turn-scoped tools —
  `coffer__schedule_task`, `coffer__scheduled_tasks`,
  `coffer__cancel_scheduled_task` — exist only inside a channel turn. In a turn
  the owner asked for, any task may be booked; an agent acting on its own books
  only a one-off follow-up in the thread it is answering, 5 minutes to 7 days
  away, at most 3 waiting per thread, and a chain of at most 10 within 7 days.
  A read-only asker's turn cannot schedule, and a run of a repeating task
  cannot book more tasks.
- **The daily report** is made from a template on the Channels page, sent to
  the owner's direct chat, written from material read at run time (option A
  above); a day with no channel conversations sends nothing.
- **Experimental.** The `scheduled_tasks` feature is off until the owner
  switches it on, per Mac; off, nothing runs, the tools are withdrawn and the
  surfaces are hidden, and nothing is deleted.
- **Coffer's own work.** Every background worker reports to the worker
  registry (a plain timer loop through `TimedWorker`), and the Scheduled tasks
  page lists them read-only beside the owner's tasks.

## Consequences

- One page, one CLI group (`coffer task`) and `/status` cover every task, owner
  or agent made; a follow-up is cancelled the same way as any task.
- The turn driver and renderer carry a turn with no inbound message, and both
  agents' session readers gain a "tail" read. Spec channels holds the
  requirements; `application/channel/schedule/` the worker, runner, tools and
  material; `domain/channel/schedule*.py` the schedule and limits.
- Nothing runs while the Mac sleeps; the docs say so, and the late run says
  when it was due.
- A task is not synced: on another Mac it does not exist, so nothing runs twice.
- Deleting a channel deletes its tasks and their history.
- External-event triggers, if added, start the same task kind; they need no new
  run rules.
- While experimental, the feature carries gates in the registry, the scheduler,
  the tool registry, `/status` and the web UI; graduating it deletes them and
  adds `scheduled_tasks` to the graduated table.
