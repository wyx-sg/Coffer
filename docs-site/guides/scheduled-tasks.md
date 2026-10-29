---
title: Scheduled tasks
description: Have an agent do something in one of your chats at a time you choose, let it come back to a thread later, and get a daily report of your channel conversations.
---

# Scheduled tasks

A **scheduled task** is a turn Coffer starts by itself: at the time you choose, it sends a prompt to an agent in one of your chats, and the reply goes there like any other. A morning summary, a weekly check, a reminder in a group thread — and, when an agent says "I'll check again after the deploy", the follow-up it books for itself. The **daily report** on a channel is a scheduled task too.

Every task is on the **Scheduled tasks** page (Run › Scheduled tasks), with its history. The same page shows Coffer's own background work, read-only.

## What a task is

A task holds:

- **When**: every day, weekdays, every week, every hour, once, a cron expression, or only when you run it by hand. Times are this Mac's local time. A repeating task runs at most every 15 minutes.
- **Chat**: one of the chats you already use with a bot — your direct chat or a group the bot is paired with. A task runs only in a chat you use with the bot.
- **Prompt**: what the agent is asked.
- **Conversation**: **Fresh each run** opens a new conversation every time, with the agent, model and directory you pick (or the channel's defaults); **Carry on the chat's** sends the run into the chat's current conversation, with everything said there so far.
- **Catch up**: on by default. See [When the Mac was asleep](#when-the-mac-was-asleep).

Tasks are kept on this Mac only and never synced: a task names a chat, an agent and a directory on this machine, and two Macs must not both run it.

## Create a task

On the Scheduled tasks page, press **New task**. Name it (left empty, it is named after the prompt), pick the chat, choose when, write the prompt, and choose how the conversation opens. **Create task** saves it and opens it.

You can also ask a bot in your chat: "every weekday at 9, list yesterday's merged pull requests". The agent creates the task, says what it set up, and the task appears on the page, where you can change or delete it.

From the command line:

```bash
coffer task chats                          # the chats a task may run in
coffer task add --data '{"config": {"schedule": {"kind": "weekdays", "time": "09:00"},
  "prompt": "List the pull requests merged yesterday",
  "chat": {"channel": "<channel uid>", "chat_id": "<chat id>"}}}'
coffer task list
```

## What a run looks like

At its time, the agent gets the prompt with a short note in front that only the agent sees: which task this is, when it was due, whether it is late or was started by hand. The reply goes to the task's chat, in its thread if it has one.

**Nothing to say is fine.** If the agent has nothing to report it starts its reply with `[SILENT]`, and nothing is sent. Write prompts that say when to stay quiet ("only if a check failed"). A run that fails always says so in the chat.

A run due while the previous one is still going is skipped and recorded. A failed run is not retried, since a turn may have done things; a repeating task that fails three runs in a row is paused, and the chat is told.

## Follow-ups an agent books

When you ask something whose answer comes later — "tell me when the deploy is live" — the agent can book a **follow-up** in the same thread: a one-off task that comes back to that conversation, with its context, and addresses whoever asked. In a group it @mentions them.

An agent acting on its own books only follow-ups, and only within limits:

- 5 minutes to 7 days ahead;
- at most 3 waiting in one thread;
- a follow-up may book the next, at most 10 in a row and within 7 days of the first.

Someone in a group who may only ask the bot (see [Others in the group](/guides/channels#others-in-the-group)) cannot make it schedule anything. A run of a repeating task cannot book more tasks.

Follow-ups are listed under **Follow-ups** on the page. Once a follow-up has run it is removed; its runs stay in Coffer's run records until retention removes them.

## See and cancel from the chat

In a direct chat, `/status` lists what waits in the conversation, soonest first — "⏰ 1. 16:00 Check the deploy" — with a **Cancel** button per task on platforms with buttons. In a group, ask the bot ("what have you scheduled here?") or open the page.

## The daily report

Once a day, a short message to you about what happened in a channel's conversations: what was asked, where it stands, and anything that went wrong. Turn it on from the channel's **Overview**: under **Daily report**, pick the time (18:00 by default) and press **Set up**. It goes to your direct chat with the bot.

The report is written by the agent from the day's conversations, read from the agents' own sessions when it runs; Coffer keeps no copy of what was said. A day with no channel conversations sends nothing. It also lists tasks that were skipped or failed that day and what waits for tomorrow.

The report is an ordinary task: on the Scheduled tasks page you can change its prompt, pause it, or delete it. The switch on the channel's Overview pauses and resumes it.

## When the Mac was asleep

Nothing runs while the Mac sleeps or Coffer is not running; Coffer does not wake the Mac. When it is back:

- the most recent missed run runs once, late, and says when it was due;
- a one-off task may run late by up to half the time it waited (at least 15 minutes, at most 2 hours) — a follow-up is worth something only while it is timely;
- a repeating task's missed run may still run until the end of that day;
- anything older is skipped and recorded in the history.

Turn **Catch up** off on a task to skip every missed run instead.

## The page

- **My tasks**: the ones you set up, the daily report among them. Each row says when it runs next, or that it is paused or failing.
- **Follow-ups**: the ones agents booked.
- **Coffer internal**: Coffer's own background work — sync, memory sync, cleaning up old records, keeping agents' config files in line, starting scheduled tasks, and more — with how each is woken and when it last ran. **Show all** lists every worker. Nothing here can be changed: these settings live on their own pages.

Open a task for its header (**Run now**, **Pause** or **Resume**, **Edit**, and **⋯ › Delete**), what it does, and **History**: every run, newest first, with how it ended — **Replied**, **Nothing to say**, **Skipped**, **Failed**, **Stopped** — and why. Runs are kept for 90 days by default; change it in Settings › Data.

## Related

- [Channels](/guides/channels): pairing a bot, groups and threads, commands.
- [Channel commands](/reference/channel-commands): `/status`.
