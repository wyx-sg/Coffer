# A Scheduled Task's Slots Are Counted From an Anchor, and a Missed Run Is Caught Up Within Seven Days

**Status**: Accepted
**Date**: 2026-11-13
**Deciders**: Yuxing (owner)
**Related**: [A Scheduled Task Is a Prompt on a Schedule](automation-is-a-scheduled-prompt.md), [A Scheduled Task's Prompt Is a File in Its Own Folder](a-scheduled-task-s-prompt-is-a-file-in-its-own-folder.md), [Storage Is Five Classes by Nature](storage-is-five-classes-by-nature.md), spec scheduled-tasks, research note [Scheduled agent tasks](../research/scheduled-agent-tasks.md)

## Context

A review of scheduled tasks on 2026-11-13 found the scheduler deciding "which
slot is due" from the wrong starting point, and deciding "is a late slot still
worth running" with two formulas that gave surprising answers:

- Slots were counted from the task's last recorded run, or from its
  `updated_at`. Resuming a task that had been paused for three days therefore
  found three missed slots and ran one at once. Changing a daily 18:00 task to
  08:00 at noon found "today's 08:00" missed and ran at once. Pruning the run
  history moved the starting point back to `updated_at`.
- A late slot ran only inside a grace: for a one-off, half the time it had
  waited (15 minutes to 2 hours); for a repeating task, until the end of that
  local day. A daily 23:00 task on a Mac that slept from 22:50 to 08:00 had
  one hour of grace and never ran. A daily 00:30 task had almost a full day.

## Comparable products

- **Claude Code Desktop scheduled tasks.** On wake, the most recent slot missed
  within the last seven days runs once, late; older ones are dropped. A
  notification says a catch-up run started.
- **Codex automations.** After a restart a missed job runs once; this can be
  switched off per job. No documented window.
- **Hermes.** A missed job runs if it is late by no more than half its period,
  between 2 minutes and 2 hours (the formula the one-off grace was copied from).
- **cron / launchd.** cron never catches up; launchd coalesces everything
  missed during sleep into one run on wake, with no window.
- **systemd timers** (`Persistent=true`). One run on boot for a missed slot,
  counted from a stamp file the timer keeps apart from the unit and its logs.

Two patterns: the starting point is the scheduler's own small record (systemd's
stamp), and the window, where there is one, is long and the same for every
schedule (Claude Code's seven days).

## Options Considered

### Where slots are counted from

#### A — An anchor per enabled task, kept by the scheduler (chosen)

For every enabled task the scheduler keeps the moment slots are counted from:
the last slot it ran or skipped, or, when it first sees the task enabled with
its current schedule, that moment. A paused or deleted task has no anchor. The
anchors are one small JSON file, `local/scheduled-task-anchors.json`.

- **Good:** resuming and editing a schedule start nothing, because both make a
  new anchor at "now"; pruning the history changes nothing; a slot missed while
  Coffer was off is still found, because the anchor outlives the process.
- **Costs:** one more file; a task enabled while the daemon is stopped is
  anchored when the daemon next starts, so a slot between the two is not seen
  as missed.

#### B — Keep deriving it from the last run and `updated_at`

- **Lost because:** `updated_at` moves for a rename as well as a resume, and
  does not move for a resume in a way that separates "paused through" from
  "missed"; every fix was another special case.

#### C — A column on the task, or a table in `runs.db`

- **Lost because:** the task file is the owner's config and would be rewritten
  on every run; `runs.db` holds history that retention may prune, and the
  anchor must survive pruning ([Storage Is Five Classes by Nature](storage-is-five-classes-by-nature.md)).

### How late a missed slot may run

#### A — The most recent missed slot, if due within seven days (chosen)

One rule for every schedule. The run's message says when it was due and that
the agent should judge whether the work still makes sense.

- **Good:** the rule fits in a sentence; the evening task runs the next
  morning; it is Claude Code's rule, which the owner already knows.
- **Costs:** a "good morning" prompt may run in the afternoon; the prompt has
  to say what to do when late, or switch catch-up off.

#### B — Keep the two graces

- **Lost because:** when a slot is lost depends on its time of day, which no
  owner would guess, and the case that most needs catching up (a slot slept
  through overnight) is the one it drops.

#### C — A grace the owner sets per task

- **Lost because:** one more field for a judgement the agent can make from the
  late note; no comparable product offers it.

#### D — No window: always run the most recent missed slot

- **Lost because:** a Mac switched on after a month would run a one-off that
  was about a day long past.

## Decision

Slots are counted from a per-task anchor the scheduler keeps in
`local/scheduled-task-anchors.json`; the most recent missed slot runs once,
late, if the task catches up and the slot was due within seven days.

Rules a change must keep:

- **An anchor exists only while the task is enabled with that schedule.** A
  new anchor is "now". Resuming, creating and changing the schedule never
  start a run.
- **Only the scheduler moves an anchor**, to the slot it just ran or skipped.
  Run now does not move it.
- **One window, one constant** (`CATCH_UP_WINDOW`). With catch-up off, a slot
  more than a minute late is skipped.
- **A late run says so.** The note after the prompt is the only thing Coffer
  adds to a run's message; a manual run adds nothing.
- **A paused one-off whose time has passed is not resumed**; it is given a new
  time first.

## Consequences

- A run a stopped daemon left running is closed `stopped`, not `failed`: the
  task did nothing wrong, and three of them must not pause it.
- A repeating task paused after three failures is listed in the Overview
  page's "Needs you" until it is resumed; Coffer sends no other notice of a
  run. Options were a channel message on failure (Devin emails; Coffer would
  be choosing a channel and wording for the owner, which a prompt can do) and
  a system notification per catch-up (Claude Code; noise for a run the history
  already marks late). The one case a prompt cannot cover is the task whose
  agent is what fails, and the Overview already lists what needs the owner.
- The first start after upgrading anchors every enabled task at that moment;
  a slot missed just before the upgrade is not caught up.
