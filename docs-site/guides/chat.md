---
title: Chat
description: Talk to Claude Code or Codex from Coffer's web Chat page, and watch, steer or continue conversations started from an IM channel.
---

# Chat

The **Chat** page is where you talk to a managed agent — Claude Code or Codex — from Coffer's web UI. This guide covers starting a conversation, choosing the model and reasoning effort, what a turn looks like while it streams, stopping and queueing, and how the page relates to the agent's own sessions and to your [channels](/guides/channels).

## What Chat is for

Chat drives the agent you already use, through that agent's own runtime: Claude Code through the Claude Agent SDK, Codex through `codex app-server`. Coffer does not put a model of its own in between. The turn runs with the agent's own login and built-in model unless you pick a model for it.

The page is one window onto a conversation, and an IM channel is another. A conversation you start on your phone through Telegram or SeaTalk appears on the Chat page, where you can watch its turns stream, stop them, and keep typing. The agent cannot tell which window a turn came from.

::: info No CLI
There is no `coffer chat` command group. Conversations are reachable from the Chat page, from a channel, and over the REST API under `/api/v1/chat`.
:::

## Prerequisites

- A running daemon. Open the UI with `coffer open` or the [desktop app](/guides/desktop-app).
- At least one managed agent registered on the **Agents** page, with its CLI installed on this machine. See [Agents](/guides/agents).
- The agent logged in the way you would log in to use it in a terminal. For Claude Code, run `claude` once and complete `/login`.

You do **not** need a [model provider](/guides/providers). A provider is an optional override; without one the agent runs on its own login.

If no managed agent is available, the page shows **No managed agent available** instead of a composer.

## Start a conversation

1. Open **Chat** in the sidebar (under **Agents**). The page opens on a blank draft.
2. In the bar at the top of the draft, pick the agent. An agent whose CLI is not on the daemon's `PATH` is listed as **unavailable** and cannot be chosen.
3. Optionally pick a model and a reasoning effort (see [Choose the model and reasoning effort](#choose-the-model-and-reasoning-effort)).
4. Type your message and press **Enter**. **Shift+Enter** inserts a new line.

The first send creates the conversation. Opening the draft and leaving creates nothing. The conversation is titled after the first thing you wrote; rename it at any time and Coffer does not overwrite your name.

The open conversation is part of the URL, `/chat/<id>`, so a refresh, a bookmark or a second tab reopens the same thread. A link to a conversation that has been deleted shows **Conversation not found** with a **Start a new chat** button.

### Working directory

Every Chat page turn runs in the Coffer-managed workspace, `~/.coffer/workspace`, which is created on first use. The page has no working-directory picker. A conversation's agent and working directory are fixed when it is created, because the agent's session belongs to that one directory.

::: tip
If you want the agent to work inside a particular repository, tell it the absolute path in your message. The agent runs with full permissions, so it can read and write outside its working directory.
:::

## Choose the model and reasoning effort

Two controls sit beside the agent, both on the draft and in an open conversation:

| Control | Label | What it offers |
| --- | --- | --- |
| Model | **Agent model** | **Default** first, then the models the platform offers for this agent, then the conversation's current value if it is not already listed. |
| Reasoning effort | **Reasoning effort** | **Agent default**, then the levels the chosen model reports. The control is hidden for a model that reports no levels. |

The model list is the agent's own catalogue, read from the installed CLI. If a [model provider](/guides/providers) is active for the agent, the list is that provider's curated text models instead. The picker is a fixed dropdown and accepts no free text.

- **Default** clears the model, so the agent runs whatever its own configuration says.
- A change applies from the next turn. Model and effort are re-read every turn; the agent and working directory are not.
- Every turn carries a short note telling the agent which model Coffer put it on, so asking the agent "which model are you?" gives the right answer.

Once a conversation exists, its agent is shown as a label and cannot be changed. To talk to a different agent, start a new chat.

## Watch a turn

A reply streams into the thread as the agent writes it. While it streams:

- Assistant text renders as GitHub-flavoured Markdown. Single newlines are kept as line breaks, tables render as tables, and every fenced code block has its own **Copy** control.
- Each tool call is a card between the text around it, in the order the agent made it. The card names the tool and reads **running** until its result arrives, then **done** or **error**. Open it to see **Input** and **Result**.
- A finished assistant message shows its token usage (for example `1204 in · 356 out`) and records the model that produced it.
- If you scroll up, **Jump to latest** takes you back to the live end.

The turn runs as a detached task in the daemon. Closing the tab, losing Wi-Fi or refreshing does not stop it: the reply finishes and is saved, and when you come back the page subscribes again and replays the turn in progress from its start.

## Send while a turn runs

The composer never locks. While a reply streams, the composer shows **A reply is streaming — your next message will queue.**

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

- ends the turn and keeps whatever text it had already produced, saved as a complete message;
- **pauses** the pending queue, so the next queued message does not fire straight into the turn you just stopped.

The next message you send — from the page or from a channel — resumes the paused queue. **Stop** works on any turn in the conversation, including one started from your phone. It is the same action as `/stop` in a channel.

## When a turn fails

A failed turn replaces the in-progress bubble with one error banner above the composer, carrying **Retry** (resend the message that failed) and **Dismiss**. Whatever the agent had written before the failure stays in the thread, marked **This response did not complete.**

Coffer reports three failures of its own, besides whatever the agent reports:

| Error | Meaning |
| --- | --- |
| `stream_ended` | The agent's event stream ended with no completion event — its process died or lost its connection mid-turn. |
| `turn_timeout` | The agent produced no event for the idle window: `COFFER_TURN_IDLE_TIMEOUT_SECONDS`, default 300. Set `0` to disable the watchdog. |
| `daemon_stopped` | The daemon shut down while the turn was running. |

A turn never ends silently. If the daemon is killed outright, the text streamed so far is saved at most once a second, and the next daemon start marks the unfinished reply as failed rather than showing it as still arriving.

If Claude Code is not logged in, the banner says so and tells you to run `claude` and complete `/login`.

## Attachments

A message holds up to 32,768 characters of text and up to 10 attached files. Attach a file from the composer in any of three ways:

- click the paperclip beside the message box and pick one or more files;
- drop files onto the composer;
- paste an image, for example a screenshot, into the message box.

Each file uploads the moment you add it and shows as a chip with its name and size. **Send** stays disabled while a file is uploading, and while a failed file is still attached: its chip says why it failed, and removing it with **×** lets you send the rest. A message may carry files and no text; it is stored with a short line naming the files.

| Limit | Value |
| --- | --- |
| Size of one file | 20 MB |
| Files per message | 10 |
| Accepted types | Images, audio, documents (PDF, Word, PowerPoint, Excel, RTF, EPUB, CSV) and any UTF-8 text file, such as source code, Markdown, JSON or logs |

Video, archives and other binary files are refused, because neither agent can use them from a turn.

An image's type is read from its bytes, not from its name or what the browser reported: a JPEG saved as `photo.png` is stored and shown as `image/jpeg`. A file that claims to be an image but is not PNG, JPEG, GIF or WEBP, such as a HEIC photo or an SVG, is kept as a plain file (`application/octet-stream`).

Attachments also reach a conversation through a [channel](/guides/channels): a photo, file or voice message you send to the bot. Both kinds show in the thread as chips naming the file and its type, and read the same after a reload.

How the agent receives an attachment depends on its kind, whichever way it arrived:

- **Images** — Claude Code receives a PNG, JPEG, GIF or WEBP image inline, as an image it can see, when it is at most 5 MB once encoded for sending (about 3.75 MB on disk). A larger image, or one in another format, reaches Claude Code as its file path instead, so the turn still runs. Codex always receives the file path.
- **Documents** (PDF, office formats, epub, rtf) — extracted to text and folded into the prompt, so every agent reads the content. If extraction is unavailable or fails, the agent receives the file path.
- **Audio** — transcribed to text when you have turned on **Speech to text** under **Settings → Coffer's model**. With transcription off, nothing leaves your machine and the agent receives the audio file.

The bytes stay on disk; the conversation stores only a reference, and a later turn reads the file back from there. Files you attach on the Chat page are kept in `~/.coffer/chat-media`, and files a channel received in `~/.coffer/channel-media`; both are pruned 30 days after they were last modified. After that the thread still shows the chip, but the agent can no longer open the file.

Retrying a failed turn resends the message text only. Attach the files again if the retry needs them.

## Manage conversations

The left column lists every conversation, newest activity first. A conversation moves to the top when a turn starts in it, not only when one ends.

- **Active / Archived** — switch between the two listings.
- **Search conversations** — filters the loaded list by title, case-insensitively.
- **New chat** — opens a fresh draft.
- A conversation that a channel opened carries a **via** badge naming the channel, for example `via my-telegram`.

Each row offers:

| Action | Effect |
| --- | --- |
| **Rename** | Sets a title Coffer will not overwrite. |
| **Archive** | Moves it to **Archived** without deleting anything. |
| **Restore** | Returns an archived conversation to **Active**. |
| **Delete** | Permanently removes the conversation and all its messages, and cancels a turn running in it. |

An archived conversation opens read-only: its history reads normally, the composer and the model and effort controls are disabled, and **Restore to continue** is offered in their place.

### Retention

Coffer archives a conversation with no new message for 7 days and deletes archived conversations 30 days after they were archived. Change either window, or set it to **Keep forever**, under **Settings → Data**: **Auto-archive idle chats** and **Delete archived chats**. Archiving is reversible; deletion is not.

## Chat and the agent's own sessions

A Coffer conversation is backed by one real session of the agent. Coffer stores the agent's session id on the conversation and resumes that session on every turn, so the agent keeps its own context between turns exactly as it would in a terminal. If the agent no longer recognises a stored session id, Coffer retries the turn once as a fresh session instead of failing.

There are two records of that conversation:

- **Coffer's conversation** — messages, tool calls, results, model and token usage, in Coffer's database. This is what the Chat page shows, and it is the record of what the agent did. Turns are not written to the audit log.
- **The agent's own session files** — kept by the agent itself, as for any session. The agent's detail page lists these under **Agents → *agent* → Conversations** (**Transcript sessions**), together with the sessions you ran directly in a terminal.

Each conversation has one owner — you — whichever screen you are on. Chat does not model several people sharing a conversation; the channel pairing that lets your phone drive a conversation is the same trust decision as your browser session.

## What the agent gets from the vault

A chat turn runs against the config directory of the agent that answers for its type: the first enabled agent of that type, in name order. That is the directory Coffer delivers [skills](/guides/skills) into and installs its MCP entry in, so the agent in chat has the same Coffer skills and [MCP servers](/guides/mcp-servers) it has in your terminal. When that agent's config directory is not its standard location, Coffer sets `CLAUDE_CONFIG_DIR` or `CODEX_HOME` for the turn.

On top of the agent's own system prompt, Coffer appends, in this order:

1. For a turn from a channel: a note that the agent is on a chat channel — keep replies short, and it cannot click dialogs on your computer.
2. For a turn from a channel, while the `memory` feature is on: the [memory](/guides/memory#in-channel-turns) index for the conversation's working directory and `global`, and where the notes are.
3. On every turn: the note naming the model Coffer put the agent on.

A turn you send from the Chat page gets no memory append; the agent receives memory through its own session-start hook, when memory delivery is installed.

::: danger Full permissions
Chat runs Claude Code with `bypassPermissions` and Codex with `approvalPolicy: never` and `sandbox: danger-full-access`. Coffer does not ask you to approve individual tool calls. Pairing a channel to your own account is the gate for turns that come from IM; see [Channels](/guides/channels#security).
:::

## How it works

Sending is fire-and-return: `POST /api/v1/chat/conversations/{id}/messages` starts or queues the turn and answers `202` at once. The page reads every turn's output from one server-sent-event subscription, `GET .../events`, which replays the turn in progress to a subscriber that arrives late and then follows it live. A turn you started and a turn your phone started travel the same path. A dropped subscription reconnects with a backoff and gives up after a bounded number of attempts.

Events are named `turn_start`, `text_delta`, `tool_call`, `tool_result`, `turn_done`, `turn_error` and `queue_changed`. For the design, see [Chat and turns](/architecture/chat).

## Troubleshooting

**The agent is listed as unavailable.** Its CLI is not on the daemon's `PATH`. Install it, or restart the daemon from a shell where `claude` or `codex` resolves. The desktop app passes your login shell's `PATH` to a daemon it starts.

**Every turn fails with `stream_ended`.** The agent process is exiting mid-turn. Check that the agent works in a terminal, then look at **Activity → Daemon** for the underlying error.

**Nothing streams, and the reply appears all at once.** Claude Code turns need a CLI that supports partial messages. The SDK uses its own bundled CLI; if that is missing and the `claude` on `PATH` is old, the turn fails at connect. Update Claude Code.

**The page shows a banner instead of the thread.** The daemon is not reachable. See [Web UI](/guides/web-ui#when-the-daemon-is-not-reachable).

## Related

- [Channels](/guides/channels) — drive the same conversations from Telegram or SeaTalk.
- [Agents](/guides/agents) — register Claude Code and Codex.
- [Model providers](/guides/providers) — point an agent at a different endpoint.
- [Chat and turns](/architecture/chat) — the turn platform in depth.
- [Spec: chat](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/chat/spec.md)
- [Chat Is a Single-Owner Live Mirror](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/chat-single-owner-live-mirror.md)
