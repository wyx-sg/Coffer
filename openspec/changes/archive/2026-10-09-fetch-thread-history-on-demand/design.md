## Context

`fold_turn_context` read every page of a thread on every turn that landed in
one, downloaded all of its media and folded all of it into the turn. The
conversation behind the turn keeps its own session, so from the second turn on
almost all of that was a repeat. The product decision is a hybrid: a bounded
seed on a conversation's first turn in a thread, only the news afterwards, and a
tool for the rest.

## Goals / Non-Goals

**Goals:** bound what one turn folds; never repeat what the conversation already
saw; keep older messages reachable; keep the quote and the 7-day note as they
are; keep the place across a restart.

**Non-Goals:** reading a chat's main history (still never done); a history API
for Telegram (it has none); paging the SeaTalk endpoint from the newest end (it
pages oldest-first, see D5).

## Decisions

### D1. The cursor is per conversation and per platform thread

A cursor row is keyed by `(channel uid, chat id, platform thread id,
conversation id)` and holds the id of the message that triggered that
conversation's latest turn in that thread, the time it was sent, and when the row
was written. It lives in a new `runs.db` table, `channel_thread_cursors`
(migration `0152`), not on `channel_thread_conversations`: that table is keyed by
the *conversation* thread (a SeaTalk direct chat's casual reply-in-thread keys to
the chat's `""` row), one row there can stand for many platform threads, and a
thread row outlives each conversation it opens. A row per (conversation, thread)
also means `/resume` back to a conversation that already saw this thread picks
up where it left off.

The platform thread id, not the conversation thread, is the key because the
cursor is a place in the platform's message list.

### D2. What counts as a conversation's "first turn in a thread"

The conversation a message will run in is decided later, when the turn is
submitted (`ensure_conversation`: the thread's active conversation, unless it was
deleted or the chat sat idle past `new_conversation_after_idle_hours`, in which
case a new one opens). The fold runs before that, so it asks the same question
read-only (`predict_conversation`). The turn is a **first turn** — and gets the
seed — whenever that conversation has no cursor for this platform thread:

- a brand-new conversation (first message in the thread, after `/new`, after a
  deleted conversation, after an idle rollover);
- a conversation `/resume` switched to that never had a turn in this thread;
- any conversation that existed before this change (no rows yet).

Otherwise it is a **later turn** and gets only the news.

A conversation that does not exist yet has no id to key on, so its cursor is
written under the pending id `""` and the turn claims it once
`ensure_conversation` has opened the conversation (`TurnDriver.submit` →
`claim`): the pending row is renamed to the new id, or dropped if that
conversation already holds a cursor there. The second message of a burst that
arrives before the first is submitted therefore sees the pending cursor and
folds nothing twice. A pending row its turn never claimed (the conversation
failed to open) stops counting after ten minutes, so the next conversation is
seeded rather than started mid-thread.

### D3. What a later turn folds

The messages after the cursor's message in the thread's (oldest-first) list —
found by id while the platform still returns it, else by sent time — minus the
triggering message, minus the bot's own messages. "The bot's own" is the
transport's flag (SeaTalk marks a bot sender with `sender_type` 2) **or** a
message id the reply ledger (`channel_replies`) records as part of a bot reply,
so a platform that does not flag its bots still has them left out. Nothing new
means no thread block at all. The window note is not repeated on a later turn:
the first turn already said it.

The same 20-message bound applies to a later turn (a busy group thread can grow
a lot between two @mentions); what falls outside is named in the note (D4).

### D4. The fold's notes

The seed folds the latest 20 messages other than the triggering one, under the
existing `[Thread messages]` title; a later turn uses
`[New thread messages since your last turn in this thread]`. When messages were
left out, the block ends with one `note:` line: how many, and the exact call —
`coffer__channel_read_thread` with the channel, chat id, chat kind, thread id and
`before` set to the oldest message shown. The SeaTalk 7-day note keeps its text
and its place (after the messages, before the older-messages note).

The cursor advances on every thread message that reaches the fold, including a
message that roots a fresh thread at itself (nothing is read, but the root is
marked so the next turn there does not seed the root back in). A read that
**failed** does not advance it, so nothing posted in between is skipped.

### D5. Reads are text only; media follows what is kept

SeaTalk's thread endpoints page oldest-first, so the newest messages are only
reached by reading every page; reading text is cheap and is still done on every
thread turn. Media is the expensive part, so `ContextFetchPort.fetch_thread` now
returns a `ThreadRead` (messages oldest-first, each a `ThreadMessage` with id,
sender, time, flattened items, bot flag and an opaque handle; the window note;
whether the read failed) with nothing downloaded, and
`fetch_message_media(message)` downloads one message's images and files. The
fold downloads only the folded messages', the tool only its page's.

### D6. The tool: `coffer__channel_read_thread`

Registered by the channel kind in `BuiltinToolRegistry` as
`BuiltinTool(name="channel_read_thread", turn_scoped=True)`.

- **Inputs:** `channel` (name or uid; the origin block now has a `channel:`
  line), `chat_id`, `chat_kind` (`direct`/`group`), `thread_id` (all required,
  copied from the origin block), `before` (a message id; omitted = newest) and
  `limit` (1–100, default 20).
- **Result:** `messages` (the page, oldest first, each with `message_id`,
  `sender`, `sent_at`, `from_bot`, `text`, `files` [{path, mime, filename}]),
  `has_more`, `next_before` (the oldest id of the page when more remain) and the
  platform's window `note` when it applies.
- **Scope and security.** The channel must be running here; the chat must be a
  paired chat of that channel (a `channel_peers` row: the owner's direct chat,
  or a group the owner addressed the bot in); a thread id is required and the
  transport has no read but the thread endpoints, so a chat's main history can
  never be read. On a transport without history fetch the call fails with "…has
  no history API…". Errors are in-band `isError` results with Coffer's own
  message.
- **Turn-scoped**, like `coffer__ask`: the registry view a gateway session sees
  includes it only while the session's `X-Coffer-Turn` token names a live turn.
  An agent started in a terminal never sees it, and the "one built-in tool"
  listing (`coffer__search_tools`) outside a turn is unchanged. The handshake
  instructions do not name it; the channel note does (D7).
- **Not feature-gated:** channels are not an experimental feature.

`BuiltinTool` gains `turn_scoped`; `BuiltinToolRegistry.view(in_turn=...)`
returns the session's view, and `MCPGatewaySession._builtin` is that view.

### D7. Telling the agent

`ChannelNote` gains `reads_threads` (the running transport declares
`supports_history_fetch`); the channel note then adds one short sentence naming
the tool and pointing at the origin block. The note stays under its word budget.

## Risks / Trade-offs

- **Text pages are still read on every thread turn.** Needed to find what is new
  on an oldest-first endpoint; cheap next to the media and prompt it saves.
- **SeaTalk's bot flag is read from `sender_type`.** If a payload lacked it, the
  reply ledger still names the bot's replies for the eight days it keeps them.
- **A conversation from before this change** gets one seed of 20 on its next
  thread turn — far less than the whole thread it got before.
- **A DM's casual reply-in-thread** keys to the direct chat's conversation; its
  first turn in a given thread is seeded even though those messages were turns of
  the same conversation. Bounded at 20 and once per thread.
