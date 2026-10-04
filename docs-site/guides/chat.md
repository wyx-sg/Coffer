---
title: Conversations
description: Talk to Claude Code or Codex from Coffer's web Conversations page, and watch, steer or continue conversations started from an IM channel.
---

# Conversations

The **Conversations** page (formerly Chat) is where you talk to a managed agent — Claude Code or Codex — from Coffer's web UI. This guide covers starting a conversation, choosing the model, what a turn looks like while it streams, stopping and queueing, and how the page relates to the agent's own sessions and to your [channels](/guides/channels).

## What Conversations is for

The page drives the agent you already use, through that agent's own runtime: Claude Code through the Claude Agent SDK, Codex through `codex app-server`. Coffer does not put a model of its own in between. The turn runs with the agent's own login and built-in model unless you pick a model for it.

The page is one window onto a conversation, and an IM channel is another. A conversation you start on your phone through Telegram or SeaTalk appears on the Conversations page, where you can watch its turns stream, stop them, and keep typing. The agent cannot tell which window a turn came from.

::: info Web UI and REST
Conversations are reachable from the Conversations page, from a channel, and over the REST API under `/api/v1/chat`.
:::

## Prerequisites

- A running daemon. Open the UI with the [desktop app](/guides/desktop-app), or in a browser at the daemon's address.
- At least one managed agent registered on the **Agents** page, with its CLI installed on this machine. See [Agents](/guides/agents).
- The agent logged in the way you would log in to use it in a terminal. For Claude Code, run `claude` once and complete `/login`.

You do **not** need a [model provider](/guides/providers). A provider is an optional override; without one the agent runs on its own login.

If no managed agent is available, a new conversation shows **No agent connected** instead of a composer, with an **Open Agents** link to the **Agents** page, where you connect Claude Code or Codex first.

## Start a conversation

1. Open **Conversations** in the sidebar (under **Run**). The page opens on the list of conversations; there is no welcome or suggestions page.
2. Choose **New conversation** beside the page title. The draft opens at `/conversations/new`: **New conversation** in the title bar and one line in the middle saying which agent will run in which folder.
3. Pick what you need in the reply box's toolbar: the folder beside the paperclip (see [Working directory](#working-directory)), and on the right the **agent** (only agents that are installed, and connected on the Agents page are offered), and the model.
4. Type your message and press **Enter**. **Shift+Enter** inserts a new line.

A conversation can also start from **Ask an agent** elsewhere in the app — on a command the [CLIs](/guides/clis) page says is missing, for example. The same draft opens, and its message box already holds the prompt Coffer wrote for that job, with a line under the box saying **Nothing is sent until you press Send**. Read it, edit it if you like, and press **Enter**.

The first send creates the conversation. Opening the draft and leaving creates nothing. The conversation is titled after the first thing you wrote; rename it at any time and Coffer does not overwrite your name.

The open conversation is part of the URL, `/conversations/<id>`, so a refresh, a bookmark or a second tab reopens the same thread. A link to a conversation that has been deleted shows **Conversation not found** with a **Start a new conversation** button.

### Working directory

A conversation's working directory is chosen on the draft, in the folder control beside the paperclip: a recent folder, or one row for any other — type or paste an absolute path and press **Use**, or leave the field empty and press **Choose…** for the folder dialog. It opens on the folder you used last. Leave it on **Coffer’s workspace** and the turn runs in the Coffer-managed workspace, `~/.coffer/content/workspace`, which is created on first use. Once the conversation exists the folder stays in the same place as a read-only path.

A conversation's agent and working directory are fixed when it is created, because the agent's session belongs to that one directory. To work somewhere else, start a new conversation.

::: tip
The agent runs with full permissions, so it can read and write outside its working directory too; the working directory is where it starts and where its session lives.
:::

## Choose the model

The model control sits beside the agent on the right of the reply box's toolbar, both on the draft and in an open conversation. A new conversation starts from the agent's own settings (its **Model** tab), and you switch it here. Coffer has no reasoning-effort control: the agent runs at the effort its own configuration names.

The **Agent model** picker offers **Default** first, then the models the platform offers for this agent, then the conversation's current value if it is not already listed.

The model list is the agent's own catalogue, read from the installed CLI. If the agent runs on a [model provider](/guides/providers), the list is that provider's curated text models instead. The picker is a fixed dropdown and accepts no free text.

- **Default** clears the model, so the agent runs whatever its own configuration says.
- A change applies from the next turn. The model is re-read every turn; the agent and working directory are not.
- Every turn carries a short note telling the agent which model Coffer put it on, so asking the agent "which model are you?" gives the right answer.

Once a conversation exists, its agent is shown by its mark and name, as plain text, and cannot be changed. To talk to a different agent, start a new conversation.

## Watch a turn

A reply streams into the thread as the agent writes it, under the agent's mark, name, the time and its state: **10:14 · 42s** once finished, **Working · 1m 12s** (counting up) while it runs, **Stopped after 12s** or **Failed after 38s** when it did not finish. The conversation and the reply box use the full width of the page. While it streams:

- Assistant text renders as GitHub-flavoured Markdown. Single newlines are kept as line breaks, tables render as tables, and every fenced code block has its own **Copy** control.
- Each tool call is a card between the text around it, in the order the agent made it. The card names the tool and what it was called on — the file, the pattern, the command — and reads **Running** until its result arrives, then **Done · 0.3s** (with how long the call took) or **Error**. Open it to see **Input** and **Result**.
- When the reply is complete, **Files changed** lists every file the reply wrote, with the lines each added and removed, at the end of the reply after its text. Coffer records a diff of each file as the reply runs, so a row with a diff opens it: a drawer slides in from the right, under the title bar, showing that reply's changes to the file with old and new line numbers, hunk headers and added and removed lines marked. The header shows the path and its counts, **1 of 2** with **Previous file** and **Next file** to walk the reply's changed files, and a close button; Esc closes it too. A file that is binary or over 1 MB is listed with its counts but has no diff to open. Replies from before diffs were recorded keep an estimated list that does not open.
- A finished assistant message ends with a **Copy reply** button (it copies what the agent wrote, without the tool calls), and records the model and token usage that produced it; the counts are not shown in the thread.
- If you scroll up, **Jump to latest** takes you back to the live end.

The turn runs as a detached task in the daemon. Closing the tab, losing Wi-Fi or refreshing does not stop it: the reply finishes and is saved, and when you come back the page subscribes again and replays the turn in progress from its start. If the live stream drops mid-turn, the page reconnects on its own; after five failed attempts a warning inside the reply says **Lost the live stream from the daemon** with **Reload conversation**, which shows everything the turn has written so far. A tool call that had not returned reads **Unknown**, because the page cannot tell whether it finished.

## Answer a question from the agent {#answer-a-question}

When an agent needs a decision it asks through `coffer__ask` (or Claude Code's own `AskUserQuestion`), and its turn pauses until you answer. The reply's header reads **Waiting for you**, the conversation's row in the list shows **Needs you**, and Overview lists it under **Needs you**.

A **Needs you** card sits at the end of the reply, above the reply box. It shows the agent's context (Markdown — a summary, a diff, a path), the question, and up to four options as equal buttons, each with its description under the label, and the line "Claude Code is waiting for your answer." In a channel conversation it adds that the question was also asked in that chat.

- **Single choice**: tap an option; that is the answer.
- **Several choices**: the options toggle (a check marks the ones picked), then press **Submit**.
- **Your own words**: type in the reply box, whose placeholder reads **Reply, or answer with the buttons above**, and press Send. While a question waits, text sent there answers it instead of joining the queue; no message is added to the conversation. Files cannot be sent along with an answer.
- **Several questions in one ask** appear one at a time, marked **Question 2 of 3**.

Whoever answers first wins, here or in the channel's chat. Once answered the card shrinks to one line: **✓ Restart the channel now? · Answered: Yes · 10:16**, with **· in SeaTalk** when the answer came from the chat. If you stop the turn, or it ends without an answer, the line reads **Not answered**. An answer to a question that already closed is refused, and the page just shows the closed line.

## Send while a turn runs

The composer never locks. While a reply streams, its placeholder reads **Reply — it queues until this turn finishes**.

1. Send another message. It joins the conversation's pending queue and appears as its own row under **Queued:**.
2. Each queued message runs as its own turn, in order, after the current one ends. Messages are never merged.
3. To change a queued message, choose **Edit queued message**. It leaves the queue and returns to the composer; sending it again puts it at the **end** of the queue.
4. To drop one, choose **Remove from queue**.

The queue is shared by every surface. A message your phone sends mid-turn shows up in the same queued rows, and the channel's `/status` counts messages you queued from the browser.

::: warning
The pending queue lives in the daemon's memory. Restarting the daemon drops messages that had not started yet.
:::

## Stop a turn

While a turn runs, **Send** becomes **Stop**. Stopping:

- ends the turn and keeps whatever text it had already produced, saved as a stopped reply that ends with **Stopped by you.** — and, when an edit or a command was still running, a note that it was not finished and that sending a message continues;
- **pauses** the pending queue, so the next queued message does not fire straight into the turn you just stopped.

The next message you send — from the page or from a channel — resumes the paused queue. **Stop** works on any turn in the conversation, including one started from your phone. It is the same action as `/stop` in a channel.

## When a turn fails

A failed turn replaces the in-progress bubble with one error banner inside the reply that failed, lined up with its text: **The turn failed:** and the reason, carrying **Retry** (resend the message that failed, with its attachments) and **Dismiss**. Whatever the agent had written before the failure stays in the thread above it, and the reply's header reads **Failed after 38s**.

A message the daemon refuses before it runs, for example because an attached file is no longer available, is not a failed turn: the banner gives the reason without **Retry**, and the message stays in the composer with its text and files so you can fix it and send again. This holds for the first message of a new conversation too.

Coffer reports three failures of its own, besides whatever the agent reports:

| Error | Meaning |
| --- | --- |
| `stream_ended` | The agent's event stream ended with no completion event — its process died or lost its connection mid-turn. |
| `turn_timeout` | The agent produced no event for the idle window: `COFFER_TURN_IDLE_TIMEOUT_SECONDS`, default 300. Set `0` to disable the watchdog. |
| `daemon_stopped` | The daemon shut down while the turn was running. |

A turn never ends silently. If the daemon is killed outright, the text streamed so far is saved at most once a second, and the next daemon start marks the unfinished reply as failed rather than showing it as still arriving.

If Claude Code is not logged in, the banner says so and tells you to run `claude` and complete `/login`.

## Replying to a channel's conversation

A conversation a [channel](/guides/channels) opened is one conversation, whichever screen you type on. When you reply to it from the Conversations page, the reply also goes back to the chat it came from, so your phone shows the whole exchange and not only its own half.

- The title bar shows where the conversation came from, for example **SeaTalk · coffer-dev › thread**; a reply typed here also goes there. When a reply cannot go back to the chat it says **Replies stay in Coffer** with a **?** that says why.
- The reply is posted in that chat or thread under a first line `<your name> · from Coffer`, and the agent's answer follows it there, exactly like the answer to a message you typed on your phone.
- A reply goes only to the chat and thread the conversation belongs to, never anywhere else.

A conversation that lives in a **group's main chat** is never mirrored: the composer says the reply stays in Coffer. A main chat is where the whole room reads, and a reply you typed at your desk, with an answer the room did not ask for, is not something to drop in front of everyone. A direct chat, its parallel threads and a group thread are yours to continue, so they are mirrored.

When the channel cannot send right now — it is not running on this machine, or the platform refused — the reply is not lost. It is marked **Not delivered to *platform* yet · will retry** (for example **Not delivered to SeaTalk yet · will retry**) under the message, the agent still answers on the page, and the reply and the answer are sent to the chat, in order, once the channel runs again. The mark disappears when they arrive.

Only sending mirrors. **Retry** after a failed turn runs it again on the page but does not post the message to the chat a second time.

## Attachments

A message holds up to 32,768 characters of text and up to 10 attached files. Attach a file from the composer in any of three ways:

- click the paperclip beside the message box and pick one or more files;
- drop files onto the composer — while you drag, only the composer changes: its border takes the accent colour and it reads **Drop to attach**;
- paste an image, for example a screenshot, into the message box.

Each file uploads the moment you add it and shows as a chip with its name and size. A file over the size limit, or past the tenth, is not attached at all: one line under the reply box says which file and why. **Send** stays disabled while a file is uploading, and while a file the daemon refused is still attached: its chip says why it failed, and removing it with **×** lets you send the rest. A message may carry files and no text; it is stored with a short line naming the files.

| Limit | Value |
| --- | --- |
| Size of one file | 20 MB |
| Files per message | 10 |
| Accepted types | Images, audio, documents (PDF, Word, PowerPoint, Excel, RTF, EPUB, CSV) and any UTF-8 text file, such as source code, Markdown, JSON or logs |

Video, archives and other binary files are refused, because neither agent can use them from a turn.

An image's type is read from its bytes, not from its name or what the browser reported: a JPEG saved as `photo.png` is stored and shown as `image/jpeg`. A file that claims to be an image but is not PNG, JPEG, GIF or WEBP, such as a HEIC photo or an SVG, is kept as a plain file (`application/octet-stream`).

Attachments also reach a conversation through a [channel](/guides/channels): a photo, file or voice message you send to the bot. Both kinds show in the thread as chips naming the file and its type (and its size, for a file you attached on the page), and read the same after a reload. An image you attached on the page shows as a thumbnail instead of a chip, for as long as the file is kept; once it is pruned, or for a file a channel received, the chip is shown.

How the agent receives an attachment depends on its kind, whichever way it arrived:

- **Images** — Claude Code receives a PNG, JPEG, GIF or WEBP image inline, as an image it can see, when it is at most 5 MB once encoded for sending (about 3.75 MB on disk). A larger image, or one in another format, reaches Claude Code as its file path instead, so the turn still runs. Codex always receives the file path.
- **Documents** (PDF, office formats, epub, rtf) — extracted to text and folded into the prompt, so every agent reads the content. If extraction is unavailable or fails, the agent receives the file path.
- **Audio** — transcribed to text when you have turned on **Speech to text** under **Settings › General → Speech to text**. With transcription off, nothing leaves your machine and the agent receives the audio file.

The bytes stay on disk; the conversation stores only a reference, and a later turn reads the file back from there. Files you attach on the Conversations page are kept in `~/.coffer/content/chat-media`, and files a channel received in `~/.coffer/content/channel-media`; both are pruned after the **Attachments** retention window (30 days after they were last modified by default; change it, or keep them forever, under **Settings → Data → Local content**). After that the thread still shows the chip, but the agent can no longer open the file.

Retrying a failed turn resends the message with its attachments. If a file it carried has since been pruned, the retry is refused with an error saying so, and nothing is sent: attach the file again and send a new message.

## Manage conversations

`/conversations` lists every conversation, whatever opened it, newest activity first, as one list with no header row, grouped under **Today**, **Yesterday** and **Earlier**. A conversation moves to the top when a turn starts in it, not only when one ends. The list reads 30 conversations and loads more as you scroll. Each row shows:

- the title, then a status word — **Running** (a green dot) while a turn is in progress, **Needs you** (an amber dot) while the agent is waiting for your answer — and the latest message's first line under it;
- on the right, its **source** — the Coffer mark and **Coffer** for a conversation started on this page, or the platform's logo and the place in its chat for one a [channel](/guides/channels) opened: `SeaTalk · DM`, `SeaTalk · DM · Thread 2` for a parallel thread, `SeaTalk · coffer-dev › thread`, `Telegram · Group › topic` — then the agent and the time of the last activity (the clock for today and yesterday, a date such as `Sep 22` for earlier).

Above the list, from left to right: an **Active / Archived** switch, a search box over titles and message text (press `/` to jump to it), a **Source** pill, an **Agent** pill, and **Clear filters** once anything narrows the list. Source lists **Coffer** and each of your channels (`SeaTalk · Team bot`) and takes several at once; Agent does the same. The server applies both, so scrolling pages through matches only. The list shows no count. The filters are part of the URL, so a filtered list is a link:

- Search — `?q=sentry`.
- Sources — `?source=coffer,<channel uid>`. A channel's **Conversations from *name*** link on the Channels page opens `?source=<uid>`, with that channel ticked in the Source pill.
- Agents — `?agent=codex`.
- **Archived** — `?archived=1`.

Hover a row for a checkbox on its left and a **⋯** menu on its right. **Rename** opens the conversation with its title ready to edit; **Archive** (**Unarchive** in the archived view) acts at once and a toast offers **Undo**; **Delete…** asks first. The first day group has a **Select all** box in the same column: it ticks every conversation in the view — reading the ones not loaded yet — and is half-ticked while only some are. Tick rows (shift-click ticks a range) and the filter row gives way to a bar — `3 of 8 selected`, **Archive**, **Delete…**, **Clear**. A bulk delete lists the titles it will remove, five at a time with **Show all**.

When there is no conversation yet, the page is its header and one message. When filters match nothing, **No conversations match** offers **Clear filters**; if the list cannot be read it says so, with **Retry**.

Opening a conversation puts the list beside it, with the same filters and a **Search conversations** box that filters the loaded list by title. The divider between them can be dragged. The conversation's title sits in the window title bar (in a browser, a bar at the top of the page) with a **⋯** menu on its right:

| Action | Effect |
| --- | --- |
| **Rename** | Turns the title into an input in place: **Enter** saves, **Esc** cancels. Coffer will not overwrite the name you set. |
| **Archive** | Moves it to **Archived** at once, without deleting anything. |
| **Restore** | Returns an archived conversation to the active list. |
| **Delete…** | Asks first (**Delete “title”?**), then removes Coffer's copy of the conversation and its messages and cancels a turn running in it. The agent's own session files are left alone; archive a conversation to keep it. |

An archived conversation opens read-only: its history reads normally, the composer and the model control are disabled, and **Restore to continue** is offered in their place.

### Retention

Coffer archives a conversation with no new message for 7 days and deletes archived conversations 30 days after they were archived. Change the deletion window, or set it to **Keep forever**, under **Settings → Data → History → Conversations**; the 7-day archive window has no control in the web UI (it is the `conversations_archive` policy, set through `/api/v1/retention/policies`). Archiving is reversible; deletion is not.

## Chat and the agent's own sessions

A Coffer conversation is backed by one real session of the agent. Coffer stores the agent's session id on the conversation and resumes that session on every turn, so the agent keeps its own context between turns exactly as it would in a terminal. If the agent no longer recognises a stored session id, Coffer retries the turn once as a fresh session instead of failing.

There are two records of that conversation:

- **Coffer's conversation** — messages, tool calls, results, model and token usage, in Coffer's history database, `runs.db`. This is what the Conversations page shows, and it is the record of what the agent did. Turns are not written to the audit log.
- **The agent's own session files** — kept by the agent itself, as for any session. The agent's detail page lists these under **Agents → *agent* → Sessions**, together with the sessions you ran directly in a terminal.

Each conversation has one owner — you — whichever screen you are on. Chat does not model several people sharing a conversation; the channel pairing that lets your phone drive a conversation is the same trust decision as your browser session.

## What the agent gets from the vault

A chat turn runs against the config directory of the registered agent of its type (there is one per type). That is the directory Coffer delivers [skills](/guides/skills) into and installs its MCP entry in, so the agent in chat has the same Coffer skills and [MCP servers](/guides/mcp-servers) it has in your terminal. When that agent's config directory is not its standard location, Coffer sets `CLAUDE_CONFIG_DIR` or `CODEX_HOME` for the turn.

On top of the agent's own system prompt, Coffer appends, in this order:

1. For a turn from a channel: a note that the agent is on a chat channel — keep replies short, and it cannot click dialogs on your computer.
2. For a turn from a channel: the [memory](/guides/memory#in-channel-turns) index for the conversation's working directory and `global`, and where the notes are.
3. On every turn: the note naming the model Coffer put the agent on.

A turn you send from the Conversations page gets no memory append; the agent receives memory through Coffer's memory hook in its own settings, when the agent is connected to Coffer.

::: danger Full permissions
Chat runs Claude Code with `bypassPermissions` and Codex with `approvalPolicy: never` and `sandbox: danger-full-access`. Coffer does not ask you to approve individual tool calls. Pairing a channel to your own account is the gate for turns that come from IM; see [Channels](/guides/channels#security).
:::

## How it works

Sending is fire-and-return: `POST /api/v1/chat/conversations/{id}/messages` starts or queues the turn and answers `202` at once. The page reads every turn's output from one server-sent-event subscription, `GET .../events`, which replays the turn in progress to a subscriber that arrives late and then follows it live. A turn you started and a turn your phone started travel the same path. A dropped subscription reconnects with a backoff and gives up after a bounded number of attempts.

Events are named `turn_start`, `text_delta`, `tool_call`, `tool_result`, `turn_done`, `turn_error` and `queue_changed`. For the design, see [Chat and turns](/architecture/chat).

## Troubleshooting

**The agent is listed as unavailable.** Either its CLI is not on your `PATH` (your login shell's `PATH` merged with the daemon's own), or no agent of that type is registered. Install the CLI, then choose **Connect** on the Agents page. Chat runs only agents Coffer manages.

**Every turn fails with `stream_ended`.** The agent process is exiting mid-turn. Check that the agent works in a terminal, then look at **Activity → Daemon** for the underlying error.

**Nothing streams, and the reply appears all at once.** Claude Code turns need a CLI that supports partial messages. The SDK uses its own bundled CLI; if that is missing and the `claude` on `PATH` is old, the turn fails at connect. Update Claude Code.

**The page shows a banner instead of the thread.** The daemon is not reachable. See [Web UI](/guides/web-ui#when-the-daemon-is-not-reachable).

## Related

- [Channels](/guides/channels) — drive the same conversations from Telegram or SeaTalk; replies from this page are mirrored back.
- [Agents](/guides/agents) — register Claude Code and Codex.
- [Model providers](/guides/providers) — point an agent at a different endpoint.
- [Chat and turns](/architecture/chat) — the turn platform in depth.
- [Spec: chat](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/chat/spec.md)
- [Chat Is a Single-Owner Live Mirror](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/chat-single-owner-live-mirror.md)
