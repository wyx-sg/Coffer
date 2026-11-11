---
title: Scheduled tasks
description: Have an agent run a prompt at a time you choose, each run in a new conversation of its own, with every run kept in the task's history.
---

# Scheduled tasks

A **scheduled task** is a prompt Coffer sends to an agent by itself, at the time you choose. Each run opens a new conversation of its own, like Claude Code's and Codex's own automations: a morning summary, a nightly build check, a weekly cleanup. Coffer provides only the timing and the history; what a run does is up to the prompt. If you want the result in a chat, a report, or a skill to run, say so in the prompt.

Every task is on the **Scheduled tasks** page (Run › Scheduled tasks), with its history.

Scheduled tasks are an [experimental feature](/guides/experimental-features): switch them on in **Settings → Features** first. While they are off, no task runs; your tasks and their history are kept.

## What a task is

A task holds:

- **When**: every day, every week, every hour, once, a cron expression, or only when you run it by hand. Times are this Mac's local time unless you name a **timezone** (an IANA name such as `Asia/Singapore`); a time that daylight saving skips runs once at the next valid time. A repeating task runs at most every 15 minutes. For working days, use a cron expression such as `0 9 * * 1-5`.
- **Prompt**: what the agent is asked. To use a skill, name it in the prompt. The prompt is a Markdown file, `PROMPT.md`, in the task's own folder (see [The task's folder](#the-task-s-folder)).
- **Agent**: Claude Code or Codex.
- **Model**: one from the agent's list, or the agent's default.
- **Directory**: where the conversation opens; left empty, the task's own folder.
- **Catch up**: on by default. See [When the Mac was asleep](#when-the-mac-was-asleep).

Tasks are kept on this Mac only and never synced: a task names an agent and a directory on this machine, and two Macs must not both run it.

## Create a task

On the Scheduled tasks page, press **New task**. Name it (left empty, it is named after the prompt), choose when, write the prompt, and pick the agent, model and directory. **Create task** saves it and opens it.

You can also ask an agent to set one up: it can run `coffer task add` like any other command.

```bash
coffer task add --data '{"prompt": "Check last night'"'"'s build",
  "config": {"schedule": {"kind": "daily", "time": "02:00", "timezone": "Asia/Singapore"},
  "agent": "codex", "cwd": "~/work/site"}}'
coffer task list
```

## The task's folder {#the-task-s-folder}

Every task has a folder of its own, `~/.coffer/content/workspace/scheduled-tasks/<uid>/` (`coffer task show` prints it as `folder`). It holds:

- **`PROMPT.md`**, the prompt. Edit it on the task's **Prompt** tab, in any editor, or ask an agent to; the next run reads the file as it is then. `coffer task prompt <task> --data '{"prompt": "…"}'` replaces it.
- **Whatever its runs write**, when the task names no directory: a run works in this folder, so a daily report the prompt asks for (say `reports/2026-11-11.md`) lands here and shows on the task's **Files** tab.

Naming the files, or keeping one file up to date instead of one per day, is the prompt's job. The folder is yours: it is not synced, and deleting the task leaves it in place.

To get a report on your phone too, ask in the prompt for a short message with the file attached, through your channel:

```bash
coffer channel notify seatalk --data '{"text": "Today'"'"'s report", "files": ["/Users/me/.coffer/content/workspace/scheduled-tasks/<uid>/reports/2026-11-11.md"]}'
```

Files are absolute paths on this Mac, up to ten, sent after the text. An agent can do the same with the `coffer__channel_notify` tool.

## What a run looks like

At its time, the agent gets the prompt in a new conversation. A run that is late, or was started by hand, gets a short note saying so, so the agent can judge whether the work still makes sense. Nothing is posted anywhere by Coffer: open the run from the history to read the reply. If the agent should tell you something, say so in the prompt; it can send you a message, and files, through your channel with `coffer__channel_notify` or `coffer channel notify`.

A run due while the previous one is still going is skipped and recorded. A failed run is not retried, since a turn may have done things; a repeating task that fails three runs in a row is paused. A one-off task is switched off after it runs.

## When the Mac was asleep

Nothing runs while the Mac sleeps or Coffer is not running; Coffer does not wake the Mac. When it is back:

- the most recent missed run runs once, late, and says when it was due;
- a one-off task may run late by up to half the time it waited (at least 15 minutes, at most 2 hours);
- a repeating task's missed run may still run until the end of that day;
- anything older is skipped and recorded in the history.

Turn **Catch up** off on a task to skip every missed run instead.

## The page

The list shows every task, soonest first; each row says when it runs next, or that it is paused or failing.

Open a task for its header (**Run now**, **Pause** or **Resume**, **Edit**, and **⋯ › Delete**) and four tabs:

- **Overview**: when it runs, its next run, agent, model, directory and catch-up.
- **Prompt**: `PROMPT.md`, rendered, with **Source** to see the Markdown. **Edit** opens it in an editor; **Save** writes the file. **Edit** in the header changes everything else.
- **History**: every run as a table — when it started, how it ended (**Done**, **Skipped**, **Failed**, **Stopped**), whether the schedule, a catch-up or you started it, and how long it took — with the reason under a skipped or failed run. Search it, filter by result and by what started it, and sort by start or duration.
- **Files**: the task's folder, read-only, with the open file beside the tree.

Each run in the history names its conversation as a link: it takes you to that conversation on the **Conversations** page, selected in the list, and opens it in your terminal, so you can read what the run did and carry the conversation on. Runs are kept for 90 days by default; change it in Settings › Data.

## Related

- [Channels](/guides/channels): pairing a bot, so an agent can message you.
