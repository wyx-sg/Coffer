# Design — redesign-channel-commands

## Context

The owner steers a channel conversation from a phone. The command set had grown
to ten entries with two ways to do one thing (`/new` and `/agent` both open a
fresh conversation), a second command for half of one choice (`/effort`),
settings that did not survive `/new`, no way back to an earlier conversation, no
control over the working directory, and a `/status` that printed a ULID. Every
text starting with `/` was swallowed, so a message that opened with a path never
reached the agent. And a reply typed on the Chat page into a conversation a
channel started stayed on the web: the phone never saw it or its answer.

## Decisions

### D1. Nine reserved words, everything else is a message

The roster is exactly `new`, `stop`, `model`, `dir`, `status`, `resume`,
`thread`, `kb`, `help` (plus the hidden alias `start`). `/agent`, `/effort`,
`/threads` and `/save` are removed with no pointer: the product has one owner
and a pointer is a shim (migrations leave no shims).

A text is a command only when its first word is `/<name>` with `<name>` made of
lowercase letters, digits and `_` and on the roster. Otherwise:

- a head within edit distance 1 (names of four letters or fewer) or 2 (longer
  names) of a roster name answers one line, `Did you mean /stop?`, and runs
  nothing;
- anything else — `/compact`, `/review`, `/Users/me/app crashes` — is an
  ordinary message for the agent (a head containing a second `/` is a path and
  never a typo).

### D2. Settings are sticky per chat thread

`channel_thread_conversations` gains `preferred_model`, `preferred_effort`,
`preferred_cwd` beside `preferred_agent`, and `chat_kind`. A conversation opened
for a thread is created with the thread's sticky agent, model, effort and
directory, falling back to — in a group thread — the group's own `thread_id=""`
row (the group defaults), then the channel's `default_agent` /
`default_agent_config`.

- `/new` keeps all four. `/new <agent>` switches the agent; the model and effort
  follow only when the agent is unchanged (a model id of one agent is not a model
  of another), the directory always follows.
- `/model <name>` sets the model on the current conversation (next turn) and on
  the thread. `/model <level>` — a word from the closed effort vocabulary
  `minimal low medium high xhigh max` — sets the effort only. `/model <name>
  <level>` sets both. `/model default` clears both. A model argument matches a
  catalogue id or its shown name, case-insensitively; an unknown one is still
  passed through verbatim (the CLI owns the namespace).
- Bare `/model` is a two-step card: the model step (paginated catalogue); a tap
  sets the model and, when that model reports levels, rewrites the same card into
  an effort step (the levels plus `Keep …`); a tap there sets the effort.
- Agent arguments are the names a user sees — the agent's display name or its
  resource-style name (`claude-code`, `codex`), matched case-insensitively with
  `-`, `_` and spaces treated alike. Keys never appear in an answer.

### D3. `/dir` only reaches allow-listed directories

A channel's configuration gains `directories: list[str]` — absolute paths, at
most 32 — edited on the Channels page (Settings) and with `coffer channel
add/edit --dir PATH` (repeatable; `--no-dirs` clears). `/dir <path|name>`
accepts an allow-listed path, a directory under one, or the basename of one; it
must exist. Setting it records the sticky directory and opens a fresh
conversation there, because an agent session is tied to its directory; the old
one stays one `/resume` away. `/dir default` clears it. Bare `/dir` shows the
directory in effect and a card of the allow-list. An empty allow-list answers
how to add one.

### D4. `/resume` reads this chat's own history

A new channel-owned table `channel_thread_history` records every conversation a
`(channel, chat, thread)` opened, with its `chat_kind`. `/resume` lists the
thread's last 20, newest first (title — agent — age), the current one ticked;
`/resume n` or a tap rebinds the thread to it. Conversations deleted since are
skipped. Nothing from the web or another chat is offered.

### D5. `/status` and `/help` are cards

`/status`: title = the conversation title (or the parallel mark); lines = agent
(display name), model (shown name), effort, directory, running / N queued; in a
private chat one line per parallel thread (`🧵#N title — agent — state`). No ids.
Buttons: Stop, New, Model, Resume, Dir. `/help`: the roster as text with the
same five buttons where the transport has buttons; sent once after pairing.
A button carries `cmd:<name>` and a tap runs exactly the typed command. `/kb`
appears in help and menus only while the knowledge feature is on.

### D6. SeaTalk group main is where group defaults are set

A SeaTalk @mention in a group's main chat roots a new thread, so a setting sent
there configured a thread nobody continues. Such a message now carries
`group_main=True`; a command in it applies to the group's `""` row — the
defaults every new thread in that group inherits — and answers "Default for new
threads in this group". `/stop` there interrupts every running turn of that
group and lists what it stopped. `/resume` there answers "reply inside a
thread". A Telegram group has no such distinction (its main chat is one
conversation) and is unchanged.

### D7. Telegram menus by scope and language

`/cmd@ourbot` is normalised to `/cmd` and counts as addressed; `/cmd@otherbot`
is not addressed to us. `setMyCommands` is called for scope `all_private_chats`
(all nine, `kb` only while knowledge is on) and `all_group_chats` (`new stop
model status resume help`), each once without `language_code` (English) and once
with `zh`. The knowledge switch is part of the adapter's configuration hash, so
toggling it re-registers the menu.

### D8. Mirroring a web reply into its channel

Chat declares a `ChannelMirrorPort`; the composition root satisfies it with the
channel kind's `ChannelMirror`. On `POST /conversations/{id}/messages` for a
conversation with a channel binding, the route asks the port first:

1. The conversation is located in `channel_thread_history` (channel, chat,
   thread, chat kind). Deliverable targets: a direct chat (any thread) and a
   group **thread**. A group main chat (`thread_id=""` in a group) never is:
   the reply stays in Coffer (`kept`).
2. The text goes to that chat/thread prefixed `(from Coffer) `. The turn is
   queued with an `on_start` sink, so the agent's answer is rendered into the
   chat exactly like a channel-driven turn's.
3. If the channel is not running or the send fails, the reply is written to
   `channel_outbox` as `pending`; the sink then collects the answer's final text
   into the outbox too. The runtime flushes a running channel's pending rows in
   order on each reconcile tick (at most once every 30 s per channel after a
   failure), marking them `delivered`.

REST: `ConversationOut.channel_binding.mirror` = `{deliverable, target, reason,
undelivered[]}` — `target` is e.g. `SeaTalk · 🧵#1 deploy check` so the page can
show "Also sends to …" before sending, and `undelivered` lists the replies not
delivered yet. `SendMessageAck.mirror` is `sent | pending | kept | null`.

Both platforms can send bot-initiated messages to these targets: every Coffer
reply is already an unsolicited `sendMessage` (Telegram, `chat_id` +
`message_thread_id`) or `single_chat`/`group_chat` POST with `message.thread_id`
(SeaTalk) — the owner is a subscriber of the bot by pairing, and the bot is a
member of any group it answers in.

## Risks

- Mirrored answers collected while offline are the final text only (no progress
  lines, no media).
- A conversation opened before this change has no `channel_thread_history` row
  until the migration back-fills the thread's active one; older ones cannot be
  resumed and are not mirrored.
