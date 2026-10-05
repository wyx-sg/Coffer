---
title: Conversations
description: List the conversations your IM channels started, resume one in your terminal, and stop or answer one from a channel.
---

# Conversations {#conversations}

The **Conversations** page lists the conversations your [channels](/guides/channels) started with a managed agent, Claude Code or Codex. It is a list, not a chat client: opening a row resumes that session in your own terminal, where the agent's own interface takes over. This guide covers the list, opening a row, what a running turn or a waiting question means for opening, renaming and deleting, and where the conversation itself is kept.

## What Conversations is for {#what-conversations-is-for}

Coffer's part is the turn platform that lets an IM channel reach an agent on this machine: you message the bot from your phone, Coffer runs the turn on Claude Code through the Claude Agent SDK or on Codex through `codex app-server`, and the answer comes back to the chat. Coffer does not put a model of its own in between, and it has no chat window of its own. The Claude desktop app, the Codex app and the agents' terminals already are chat clients.

What the page adds is a way back into a conversation your phone started. You see which conversations exist, which one is running, which one waits for you, and you pick one up at your desk.

::: info Web UI and REST
The list is reachable from the Conversations page and over the REST API under `/api/v1/chat`.
:::

## Prerequisites {#prerequisites}

- A running daemon. Open the UI with the [desktop app](/guides/desktop-app), or in a browser at the daemon's address.
- At least one managed agent registered on the **Agents** page, with its CLI installed on this machine. See [Agents](/guides/agents).
- A [channel](/guides/channels) paired to you. A conversation exists because a channel message started one.
- The agent logged in the way you would log in to use it in a terminal. For Claude Code, run `claude` once and complete `/login`.

You do **not** need a [model provider](/guides/providers). A provider is an optional override; without one the agent runs on its own login.

## Open a conversation in your terminal {#open-in-terminal}

Click a row, or press its split button, which names your preferred terminal (**Open in iTerm**). Its **▾** opens the conversation in another terminal on this Mac just this once, without changing the preference. Coffer opens your preferred terminal in the conversation's directory and runs the agent's own resume command:

- Claude Code: `claude --resume <session id>`
- Codex: `codex resume <session id>`

The button's other half, **Copy command**, puts the same command on your clipboard, to run in a terminal Coffer does not know or on another shell. The command starts with a change into the session's directory.

Pick the terminal under **Settings › General › Preferred terminal**, built like **Preferred editor**:

- **System default** is the platform's own terminal.
- The terminals Coffer finds on this machine are listed by name (for example Terminal, iTerm, Warp, Orca, or GNOME Terminal and Konsole on Linux).
- **Custom command** takes a template with `{cwd}` (the directory) and `{command}` (the agent command), for a terminal Coffer does not list. The template is split into arguments and run directly, not through a shell.

The same section has **Hand-off agent**, Claude Code or Codex, which the hand-off button elsewhere in the app uses.

The daemon builds the command itself from the session id, directory and agent, so the page never sends a command line. A session id with anything beyond letters, digits and hyphens is refused. If the terminal cannot be started, a toast says why, and **Copy command** is the way out.

### One session, one place {#running-or-waiting}

A session should run in one place at a time. When a row's turn is running, or the agent is waiting for your answer, **Open in &lt;terminal&gt;** asks first:

- **Answer in *platform*** (or wait): leave the turn where it is and use the channel.
- **Stop this turn and continue in the terminal**: stops the turn exactly like **Stop**, tells the agent you stopped it, then opens the terminal.

In the other direction, when a channel message arrives for a session that is open in a terminal, Coffer does not start a turn. The chat replies that the session is open in a terminal: continue there, or send `/thread` to start a new one. Coffer finds that out by looking for a process whose arguments carry the session id, so a session you opened by picking it inside the agent's own list is not seen; Codex refuses a second writer on its own.

## Answer a question from the agent {#answer-a-question}

When an agent needs a decision it asks through `coffer__ask` (or Claude Code's own `AskUserQuestion`), and its turn pauses until you answer. You answer in the channel, on the card or by replying in the chat, as [Channels](/guides/channels) describes. The conversation's row shows **Needs you**, and Overview lists it under **Needs you**.

The page has no answer card and no reply box. If you would rather answer at your desk, use the row's split button: it asks first, and **Stop this turn and continue in the terminal** ends the question (the agent is told you stopped it) and resumes the session in your terminal. The question itself is kept in the daemon's memory only; a daemon restart drops an open one.

## Send while a turn runs {#send-while-a-turn-runs}

Messages you send to the bot while a turn is running wait in the conversation's queue and run in order, one turn each. The channel's `/status` counts them. The queue lives in the daemon's memory, so restarting the daemon drops messages that had not started yet.

## Stop a turn {#stop-a-turn}

A running row shows an inline **Stop**. Stopping ends the turn, sends whatever the agent had produced to the chat followed by a note that you stopped it, and **pauses** the pending queue so the next queued message does not fire straight into the turn you just stopped. The next channel message resumes the queue. It is the same action as `/stop` in a channel, and it works on any conversation in the list.

## When a turn fails {#when-a-turn-fails}

A failed turn is reported in the chat the message came from. Coffer reports three failures of its own, besides whatever the agent reports:

| Error | Meaning |
| --- | --- |
| `stream_ended` | The agent's event stream ended with no completion event — its process died or lost its connection mid-turn. |
| `turn_timeout` | The agent produced no event for the idle window: `COFFER_TURN_IDLE_TIMEOUT_SECONDS`, default 300. Set `0` to disable the watchdog. |
| `daemon_stopped` | The daemon shut down while the turn was running. |

A turn never ends silently. Nothing is left half-written behind a daemon that dies: the next channel message resumes the agent's session.

If Claude Code is not logged in, the reply says so and tells you to run `claude` and complete `/login`.

## Attachments {#attachments}

A photo, file or voice message you send to the bot reaches the agent as a reference to a file Coffer downloaded to `~/.coffer/content/channel-media`; see [Channels](/guides/channels) for the limits. How the agent receives an attachment depends on its kind:

- **Images** — Claude Code receives a PNG, JPEG, GIF or WEBP image inline, as an image it can see, when it is at most 5 MB once encoded for sending (about 3.75 MB on disk). A larger image, or one in another format, reaches Claude Code as its file path instead, so the turn still runs. Codex always receives the file path.
- **Documents** (PDF, office formats, epub, rtf) — extracted to text and folded into the prompt, so every agent reads the content. If extraction is unavailable or fails, the agent receives the file path.
- **Audio** — transcribed to text when you have turned on **Speech to text** under **Settings › General → Speech to text**. With transcription off, nothing leaves your machine and the agent receives the audio file.

The files are pruned after the **Attachments** retention window (30 days after they were last modified by default; change it, or keep them forever, under **Settings → Data → Local content**). After that the agent can no longer open the file. The web page does not upload files.

## Manage conversations {#manage-conversations}

`/conversations` lists the conversations your channels started, newest activity first. A conversation moves to the top when a turn starts in it, not only when one ends. The list reads 30 conversations and loads more as you scroll. Each row shows:

- the title, with a status word — **Running** (a green dot) while a turn is in progress, **Needs you** (an amber dot) while the agent is waiting for your answer;
- the **agent**, the working **directory**, the **time of the last activity** (the clock for today and yesterday, a date such as `Sep 22` for earlier) and the **channel**: the platform's logo and the place in its chat, such as `SeaTalk · DM`, `SeaTalk · DM · Thread 2` for a parallel thread, `SeaTalk · coffer-dev › thread` or `Telegram · Group › topic`;
- an inline **Stop** while a turn runs, the split button (**Open in &lt;terminal&gt; ▾** other terminals · Copy command), and a **⋯** menu — always shown, not only on hover.

Above the list: a search box over titles and directories (press `/` to jump to it), a **Channel** pill and an **Agent** pill, each taking several at once, and **Clear filters** once anything narrows the list. The server applies the filters, so scrolling pages through matches only. They are part of the URL, so a filtered list is a link:

- Search — `?q=sentry`.
- Channels — `?source=<channel uid>`. A channel's **Conversations from *name*** link on the Channels page opens it with that channel ticked.
- Agents — `?agent=codex`.

The **⋯** menu has two actions, both carried out by the agent itself on its own session:

| Action | Effect |
| --- | --- |
| **Rename** | Renames the session in the agent (Claude Code's `rename_session`, Codex's `thread/name/set`) and then Coffer's row, so the new title shows in the agent's own list too. Coffer will not overwrite a name you set. |
| **Delete…** | Asks first, then deletes the session in the agent and removes the row. **It is permanent**: the agent's own session file goes with it, and a turn running in the conversation is cancelled. The channel's next message starts a fresh conversation. |

When there is no conversation yet, the page is its header and one message. When filters match nothing, **No conversations match** offers **Clear filters**; if the list cannot be read it says so, with **Retry**. The list refreshes when the window regains focus and as conversations change.

Conversations are not archived, and there is no Active/Archived switch or bulk bar. Conversations whose channel is gone, or that a web draft once created, no longer appear; the sessions behind them are still in **Agents › *agent* › Sessions**.

## Where the conversation lives {#chat-and-the-agent-s-own-sessions}

**Coffer keeps no copy of what was said.** A conversation is one real session of the agent. Coffer stores a small index row (the title, the channel and chat it belongs to, the directory and the agent's session id) and resumes that session on every turn, so the agent keeps its own context exactly as it would in a terminal. The agent's own session is the record: messages, tool calls and results are in the agent's files, and **Agents › *agent* › Sessions** lists them next to the sessions you ran directly in a terminal. Turns are not written to the audit log.

If the agent no longer recognises a stored session id, Coffer retries the turn once as a fresh session instead of failing.

::: warning Claude Code removes old sessions
Claude Code deletes sessions it has not touched for `cleanupPeriodDays`, **about 30 days by default**. Because Coffer keeps no copy, a conversation older than that can no longer be resumed or opened: the next message from its chat continues as a **fresh session**, without the earlier context. To keep sessions longer, raise `cleanupPeriodDays` in Claude Code's `settings.json` (`~/.claude/settings.json`, or the `settings.json` in the agent's config directory), for example `{ "cleanupPeriodDays": 365 }`, and restart Claude Code. The change only protects sessions that have not been cleaned up yet.
:::

Each conversation has one owner — you. Coffer does not model several people sharing a conversation; the channel pairing that lets your phone drive a conversation is the same trust decision as your browser session.

## What the agent gets from the vault

A channel turn runs against the config directory of the registered agent of its type (there is one per type). That is the directory Coffer delivers [skills](/guides/skills) into and installs its MCP entry in, so the agent in a channel has the same Coffer skills and [MCP servers](/guides/mcp-servers) it has in your terminal. When that agent's config directory is not its standard location, Coffer sets `CLAUDE_CONFIG_DIR` or `CODEX_HOME` for the turn.

On top of the agent's own system prompt, Coffer appends, in this order:

1. A note that the agent is on a chat channel — keep replies short, and it cannot click dialogs on your computer.
2. The [memory](/guides/memory#in-channel-turns) index for the conversation's working directory and `global`, and where the notes are.
3. The note naming the model Coffer put the agent on.

A session you open from the Conversations page runs in your terminal, outside Coffer, so it gets no memory append; the agent receives memory through Coffer's memory hook in its own settings, when the agent is connected to Coffer.

::: danger Full permissions
A channel turn runs Claude Code with `bypassPermissions` and Codex with `approvalPolicy: never` and `sandbox: danger-full-access`. Coffer does not ask you to approve individual tool calls. Pairing a channel to your own account is the gate for turns that come from IM; see [Channels](/guides/channels#security).
:::

## How it works {#how-it-works}

A channel message starts or queues a turn in the daemon. The turn's output is a stream of typed events (`turn_start`, `text_delta`, `tool_call`, `tool_result`, `turn_done`, `turn_error` and `queue_changed`) that the channel renders into the chat. The stream lives in memory while the turn runs and nothing is stored from it; the web UI does not subscribe to it. For the design, see [Chat and turns](/architecture/chat).

## Troubleshooting {#troubleshooting}

**The agent is listed as unavailable.** Either its CLI is not on your `PATH` (your login shell's `PATH` merged with the daemon's own), or no agent of that type is registered. Install the CLI, then choose **Connect** on the Agents page. Coffer runs only agents it manages.

**Every turn fails with `stream_ended`.** The agent process is exiting mid-turn. Check that the agent works in a terminal, then look at **Activity → Daemon** for the underlying error.

**Nothing streams, and the reply appears all at once.** Claude Code turns need a CLI that supports partial messages. The SDK uses its own bundled CLI; if that is missing and the `claude` on `PATH` is old, the turn fails at connect. Update Claude Code.

**Open in &lt;terminal&gt; does nothing.** Check **Settings › General › Preferred terminal**: a terminal that is not installed, or a custom template with a typo, cannot start. Use **Copy command** and paste it into a terminal.

**The terminal says there is no conversation to resume.** The agent has cleaned the session up (see [above](#chat-and-the-agent-s-own-sessions)). The channel continues as a fresh session on its next message.

**The page shows a banner instead of the list.** The daemon is not reachable. See [Web UI](/guides/web-ui#when-the-daemon-is-not-reachable).

## Related {#related}

- [Channels](/guides/channels) — drive agents from Telegram or SeaTalk.
- [Agents](/guides/agents) — register Claude Code and Codex, and list each one's sessions.
- [Model providers](/guides/providers) — point an agent at a different endpoint.
- [Chat and turns](/architecture/chat) — the turn platform in depth.
- [Spec: chat](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/chat/spec.md)
