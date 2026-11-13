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
- **Folder**: where every run works. Pick any folder on this Mac, such as a repository; leave it empty and runs work in the task's own folder.
- **Catch up**: on by default. See [When the Mac was asleep](#when-the-mac-was-asleep).

Tasks are kept on this Mac only and never synced: a task names an agent and a folder on this machine, and two Macs must not both run it.

## Create a task

On the Scheduled tasks page, press **New task**. Name it, write the prompt, choose when, and pick the agent and model; pick a folder if the runs should work somewhere other than the task's own folder. **Create task** saves it and it runs at its next time.

You can also ask an agent to set one up: it can run `coffer task add` like any other command.

```bash
coffer task add --data '{"prompt": "Check last night'"'"'s build",
  "config": {"schedule": {"kind": "daily", "time": "02:00", "timezone": "Asia/Singapore"},
  "agent": "codex", "cwd": "/Users/me/work/site"}}'
coffer task list
```

## The task's folder {#the-task-s-folder}

Every task has a folder of its own, `~/.coffer/content/workspace/scheduled-tasks/<uid>/` (`coffer task show` prints it as `folder`). Its `PROMPT.md` is always there. A task that names no other folder also runs there, so the prompt names its files by relative path; **Reveal in Finder** beside the prompt opens the folder.

Only `PROMPT.md` is required. The rest is a suggested layout, which Coffer does not create or check:

```text
PROMPT.md     the prompt
config/       settings and input data the task reads
state/        what it keeps between runs
output/       what each run produces, e.g. output/2026-11-11.md
scripts/      a script only this task uses
```

- **`PROMPT.md`**: edit it on the task's **Overview** tab, in any editor, or ask an agent to; the next run reads the file as it is then. `coffer task prompt <task> --data '{"prompt": "…"}'` replaces it.
- **Simple or complex**: a simple task is its prompt. For a complex one, put the *how* (steps and scripts) in a [skill](/guides/skills), which is synced, reusable and callable from any chat, and keep the prompt to one line naming it, such as `Use the release-check skill with config/release.json`. The task's folder then holds only that task's own data: `config/`, `state/`, `output/`.

Naming the files, or keeping one file up to date instead of one per day, is the prompt's job. The folder is yours: it is not synced, and deleting the task leaves it in place.

To get a report on your phone too, ask in the prompt for a short message with the file attached, through your channel:

```bash
coffer channel notify seatalk --data '{"text": "Today'"'"'s report", "files": ["/Users/me/.coffer/content/workspace/scheduled-tasks/<uid>/output/2026-11-11.md"]}'
```

Files are absolute paths on this Mac, up to ten, sent after the text. An agent can do the same with the `coffer__channel_notify` tool.

## What a run looks like

At its time, the agent gets the prompt in a new conversation. A run that is late gets a short note saying when it was due, so the agent can judge whether the work still makes sense. A run whose folder no longer exists fails without starting. Nothing is posted anywhere by Coffer: open the run from the history to read the reply. If the agent should tell you something, say so in the prompt; it can send you a message, and files, through your channel with `coffer__channel_notify` or `coffer channel notify`.

A run due while the previous one is still going is skipped and recorded. A failed run is not retried, since a turn may have done things; a repeating task that fails three runs in a row is paused, and the Overview page lists it under **Needs you** until you resume it. A one-off task is switched off after it runs. A run that was going when Coffer stopped is recorded **Stopped**, and does not count as a failure.

Resuming a paused task, or changing when a task runs, never starts a run by itself: the task waits for its next time. A paused one-off whose time has passed is given a new time before it can resume.

## When the Mac was asleep

Nothing runs while the Mac sleeps or Coffer is not running; Coffer does not wake the Mac. When it is back:

- the most recent missed run runs once, late, if it was due within the last seven days, and says when it was due;
- anything older is skipped and recorded in the history.

So a task set for 23:00 that the Mac slept through runs the next morning. Whether the work still makes sense that late is for the agent to judge; say in the prompt what it should do when it is late.

Turn **Catch up** off on a task to skip every missed run instead.

## The page

The list shows every task, soonest first; each row says when it runs next, or that it is paused or failing.

Open a task for its header (**Run now**, **Pause** or **Resume**, **Edit**, and **⋯ › Delete**) and two tabs:

- **Overview**: when it runs, its next run, agent, model, folder and catch-up, and under them the prompt, rendered, with **Source** to see the Markdown; **Edit** opens it in an editor and **Save** writes `PROMPT.md`. **Edit** in the header changes everything but the prompt.
- **History**: the latest 200 runs as a table — when it started (date and time), how it ended (**Done**, **Skipped**, **Failed**, **Stopped**), whether the schedule, a catch-up or you started it, and how long it took — with the reason under a skipped or failed run. Search it, filter by result and by what started it, and sort by start or duration.

Each run in the history names its conversation as a link: it takes you to that conversation on the **Conversations** page, selected in the list; open it in your terminal from its row to read what the run did and carry the conversation on. Runs are kept for 90 days by default; change it in Settings › Data.

## Related

- [Channels](/guides/channels): pairing a bot, so an agent can message you.
