# Research: Channels

> 中文版: [research.zh.md](./research.zh.md)

Background gathered before design: how mature open-source agents integrate
messaging channels, and what the Telegram and SeaTalk platforms actually
require. Sources: OpenClaw docs and channel-plugin SDK, NousResearch
hermes-agent docs and source, SeaTalk official `cs-bot` repository and
open-platform documentation mirrors.

## Prior art — OpenClaw and Hermes

Both products converge on the same architecture, which this spec adopts:

- **Thin adapters, shared core.** An adapter implements lifecycle
  (connect/disconnect), outbound send, and inbound normalization into a
  standard envelope. Session routing, command parsing, pairing/security,
  and rendering policy live in a shared core. Hermes'
  `BaseAdapter` is exactly three methods; OpenClaw's `ChannelPlugin` starts
  from `id` + `setup` and adds optional capability surfaces.
- **Capability declaration over special-casing.** OpenClaw adapters declare
  what the transport supports (editing, native streaming, media); the core
  degrades automatically. This is what lets Telegram stream by editing one
  message while SeaTalk falls back to ack-then-final without `if telegram`
  branches in the core.
- **Pairing as the default DM policy.** Both default to deny. Hermes and
  OpenClaw both use 8-character codes from an unambiguous alphabet with a
  1-hour TTL; Hermes adds per-user rate limiting and failure lockout, and has
  a recorded security incident from a fail-open setup path — channels must
  fail closed.
- **Session mapping.** Per-peer long-lived sessions keyed by
  `(channel, account, chat)` with `/new`-style reset; OpenClaw warns that
  anything coarser shares context across users.
- **Long-turn UX in three layers.** Immediate ack (typing/reaction), one
  reused editable progress message (cached `(chat_id, status_key) →
message_id`, throttled edits), final reply as its own message with
  notifications only on the final message.
- **Rendering.** Don't emit Telegram MarkdownV2 (escaping minefield). OpenClaw
  renders markdown → Telegram-safe HTML and retries as plain text when the
  platform rejects it. Tables are normalized (bullets or code blocks).
- **Busy-turn input.** Queue messages arriving mid-turn; control commands
  (`/stop`, `/new`) bypass the queue.
- **Polling vs webhook.** Both default Telegram to long polling for
  local-first deployments; webhooks are an opt-in for cloud hosting.

## Telegram Bot API facts

- `getUpdates` long polling needs no public ingress; the offset acknowledges
  processed updates, so committing it only after dispatch gives at-least-once
  handling across reconnects.
- `sendMessage` with `parse_mode: "HTML"`; 4096-character hard limit per
  message (we chunk at 4000 on paragraph boundaries).
- `editMessageText` enables the progress-message pattern; edits are
  rate-limited, so throttle to ≥ 1.5 s between edits.
- Inline keyboards (`InlineKeyboardMarkup`) deliver `callback_query` updates
  with the button's `callback_data`; `answerCallbackQuery` acknowledges the
  tap.
- `setMyCommands` registers the native command menu; `sendChatAction` shows
  the typing indicator.

## SeaTalk Open Platform facts

Verified against the official `seatalk-io/cs-bot` repository and mirrored
official docs (the doc site requires a developer login).

- **Inbound is webhook-only.** No polling or websocket. Events arrive as
  `POST` JSON: `{event_id, event_type, timestamp, app_id, event}`. Single
  chat messages are `event_type: "message_from_bot_subscriber"`; the sender
  is identified by `employee_code`.
- **Callback URL**: http or https, must be publicly reachable (intranet IPs
  fail validation). Tunnels work. On save, SeaTalk posts
  `event_verification` containing `event.seatalk_challenge`; the server must
  echo `{"seatalk_challenge": ...}` within 5 seconds. Events are retried up
  to 3 times on non-200.
- **Signature**: every callback carries a `Signature` header equal to
  `sha256(raw_body + signing_secret)` hex digest. The signing secret is
  per-app, visible and resettable in the developer portal.
- **Auth for sending**: `POST /auth/app_access_token` with app id + secret →
  token valid 7200 s (endpoint limited to 600 calls/hour). API calls use
  `Authorization: Bearer`. Error code 100 = expired token (refresh and
  retry), 101 = rate limited.
- **Send single chat**: `POST /messaging/v2/single_chat` addressed by
  `employee_code`; `tag: "text"` with `format: 1` is Markdown; ~300
  messages/minute rate limit; 4096-byte content limit.
- **Interactive cards**: `tag: "interactive_message"` with
  `button_type: "callback"` buttons carrying a custom `value`; taps come back
  as `interactive_message_click` events with the `value`, `message_id`, and
  `employee_code`.
- **Typing indicator**: `single_chat_typing` for a DM — and
  `group_chat_typing` for a group, which this line's omission once led us to
  believe did not exist. See the typing section below.
- **Org approval**: a self-built app's scopes (Send Message to Bot User,
  etc.) require organization admin approval; outbound IP allowlist is
  optional and should stay empty for machines with dynamic IPs.

## Group chat, threads & rich content (2026-07-08)

Verified live against a real SeaTalk app and a real Telegram bot while
building group/@mention/thread/forward support (feature/channel-group-mention-rich).

- **SeaTalk inbound tags/events (verified live):**
  - DM `combined_forwarded_chat_history` = `{tag,
    combined_forwarded_chat_history:{content:[{tag, sender:{email},
    message_sent_time, text:{content}|image:{content:url}|file:{filename}}]}}`.
  - DM quoted = `tag:"text"` + `quoted_message_id`.
  - DM thread = `tag:"text"` + `thread_id`.
  - Group events: `bot_added_to_group_chat` (`event.group.group_id` +
    inviter); `new_mentioned_message_received_from_group_chat` (fires **only**
    when the bot is @mentioned; `event.group_id` +
    `message.{thread_id, sender, text:{plain_text, mentioned_list:[{username,
    seatalk_id}]}}`); `new_message_received_from_thread` (non-@ thread
    chatter — ignored, since the bot never acts without an @mention).
  - **Group text lives at `text.plain_text`, not `text.content`** — the DM
    and group event shapes diverge here and it is easy to read the wrong
    field.
  - An @mention of the bot *inside* a thread still arrives as
    `new_mentioned_message_received_from_group_chat`, with `thread_id` set —
    there is no separate "mentioned in thread" event type.

- **SeaTalk Open API endpoints used:**
  - Group send: `POST /messaging/v2/group_chat {group_id, message}`. To reply
    into a thread, put `thread_id` **inside `message`** (`message.thread_id`),
    NOT as a top-level sibling — verified live that a top-level `thread_id` is
    silently ignored and the reply lands in the group main chat, whereas
    `message.thread_id` threads it and roots a new thread at that id when none
    exists yet (so a group-main @mention reply threads under the @mention).
  - Thread read: `GET /messaging/v2/group_chat/get_thread_by_thread_id
    {group_id, thread_id, page_size}` → response `{code, next_cursor,
    thread_messages:[…]}` — the list key is `thread_messages`, not `messages`
    or `content`.
  - `GET /messaging/v2/get_message_by_message_id` for resolving a single
    referenced message (quotes).
  - The group-chat **history** endpoint (fetching recent group-main
    messages, as opposed to one thread) is deliberately unused — the
    corresponding SeaTalk permission is not granted to Coffer's app, so
    recent-group-main context is never read; the @mention message plus its
    own thread (if any) is the whole context window.

- **Two platform limits worth recording:**
  - SeaTalk does not deliver emoji reactions or non-@ group-main messages to
    a bot at all — there is no event for either, so "read recent group-main
    history" is not just unimplemented, it is unbuildable without a
    permission SeaTalk does not grant self-built apps at our scope.
  - Telegram's Bot API cannot fetch chat history at all (no equivalent of
    `get_thread_by_thread_id`), so Telegram group/thread context is never
    read; the adapter still parses @mentions, replies, and forwards from the
    inbound update itself and replies into the correct forum topic. Two
    disclosed Telegram parsing caveats, both documented at the call site in
    `telegram_parse.py`: mention entity offsets are matched against plain
    Python code-point indices even though Telegram's own offsets are UTF-16
    code units — an accepted simplification that only drifts when a
    surrogate-pair character (e.g. an emoji outside the BMP) precedes the
    mention in the same message; and only `entities` on a plain text message
    is parsed for a mention — `caption_entities` on a captioned photo/file is
    not yet parsed, so an @mention inside a media caption is not recognized.

## SeaTalk streaming messages (re-read 2026-09-11)

The first implementation of FR-037's SeaTalk surface was written from these docs
but never verified against the live API, and no summary of them was recorded
here — so a payload missing two mandatory fields shipped, its unit tests pinned
the invented shape, and the platform refused every stream with a bare
`code=102`. This section exists so the next reader can check the code against
the contract instead of against our memory of it.

Source: Send Streaming Messages, open.seatalk.io (login required).

- **Both endpoints take the target.** `init_stream` and `update_stream` each
  need `employee_code` (1-on-1) or `group_id` (group). A `stream_id` alone does
  not identify the destination.
- **`init_stream` takes a mandatory `message`.** It posts a real placeholder
  message to the chat and returns `stream_id`. The message names the kind:
  `tag` is `"text"` or `"interactive_message"` — so a stream can be a CARD, not
  only text.
- **`update_stream`'s message carries content only** — `text` or
  `interactive_message`, no `tag`. The kind was fixed when the stream opened.
- `seq` starts at 1 on the first `update_stream` and increments by one.
  `init_stream` consumes none.
- Every update carries the WHOLE accumulated content, never a delta; the client
  renders the latest snapshot it received.
- `format` is `1` for Markdown (the default) and `2` for plain text.
- `thread_id` and `quoted_message_id` go INSIDE the message object, matching the
  placement already verified for ordinary sends. `quoted_message_id` is group
  only.
- **No extra permission.** Streaming rides the same Send Message to Bot User /
  Send Message to Group Chat grant as an ordinary reply; the app needs the bot
  capability and Online status.
- Limits: consecutive `update_stream` calls less than 30 s apart or the stream
  is terminated; 4096 characters total; once terminated (finished, timed out,
  errored) any request naming that `stream_id` is rejected. The docs advise
  buffering to roughly one call per 200 ms rather than per token.
  - **The typewriter effect is update frequency, and nothing else.** The docs
    say the client "renders progress by displaying the latest snapshot
    received" — it REPLACES the text rather than animating towards it. Measured
    against the real Claude SDK, text deltas arrive about every 25 ms carrying
    ~4 characters, so buffering at the suggested 200 ms folds roughly eight of
    them into one visible jump of ~30 characters: a sentence at a time, which
    reads as chunks rather than typing. Coffer buffers at 100 ms instead
    (`COFFER_SEATALK_STREAM_INTERVAL` retunes it without a rebuild). No rate
    limit is published for `update_stream` at all — only the advice to buffer
    "approximately every 200 ms" — so this spends an undocumented allowance on a
    visibly better reply, and a platform that pushes back answers 429/code=101,
    which the transport backs off from and logs.
- Recipients on SeaTalk older than 3.67 see only the final message once the
  stream closes.
- Open question, not resolved by the docs: the parameter table marks `thread_id`
  optional, but the group-chat request sample is annotated "thread_id required".
  Whether a group-MAIN stream (an @mention outside a thread) is accepted without
  one is unverified.

### Typing indicator, both surfaces (2026-09-11)

Two endpoints, not one — `messaging/v2/single_chat_typing` takes
`employee_code`, `messaging/v2/group_chat_typing` takes `group_id` plus an
OPTIONAL `thread_id`. Coffer suppressed the group cue for a while on the belief
that no group endpoint existed; it does.

- The indicator shows for 4 s, so it is re-sent on a heartbeat while a turn
  runs. Rate limit 300/min.
- In a group, pass the thread the turn is answering in and the cue appears
  there; omit it and it shows in the main channel. To type against an unthreaded
  root message, pass that message's id as `thread_id` — the root must be less
  than 7 days old.
- Requires SeaTalk 3.55 or later.
- Error 7003 — "group chat too large" — means over 200 members, where the
  platform has no indicator at all. Nothing to do about it; the turn's live
  surface carries the progress instead.

## Decisions taken from research

| Decision           | Choice                                                                  | Rationale                                                                                                                                 |
| ------------------ | ----------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Telegram transport | long polling via raw httpx                                              | local-first, no ingress; the API surface used is 7 small methods — an SDK dependency buys nothing and adds an import-confinement contract |
| SeaTalk transport  | webhook → separate listener process + user-run tunnel                   | webhook is the only option; the constitution requires public-reachable surfaces to be a separate process limited to signed callback paths |
| SeaTalk SDK        | none (raw httpx)                                                        | the official repo itself is a thin httpx-equivalent; token caching is ~20 lines                                                           |
| Pairing parameters | 8 chars, no `0O1I`, 1 h TTL, bounded guesses, fail closed               | matches both prior arts and Hermes' post-incident hardening                                                                               |
| Telegram rendering | markdown → HTML, plain-text retry on rejection                          | OpenClaw-proven; MarkdownV2 escaping is a known bug farm                                                                                  |
| Progress UX        | one editable status message, throttled; ack first; final reply separate | both prior arts; degrades naturally on SeaTalk via capability flags                                                                       |
| Mid-turn input     | bounded FIFO queue, control commands bypass                             | predictable; avoids Hermes' interrupt-by-default surprise                                                                                 |
| Session scope      | one long-lived conversation per `(channel, chat)`, `/new` resets        | matches the 1:1 product decision; group chats become new rows later                                                                       |

## Channels as a management plane — build-vs-adopt & landscape (2026-07-08)

Gathered while deciding whether to extend Coffer's own SeaTalk/Telegram adapters
(FR-028…FR-041) or adopt an agent-native gateway wholesale.

- **Build-vs-adopt decision.** Do NOT fork OpenClaw or Hermes channel code. Both
  are TypeScript/Node monorepos (MIT) whose channel layers are coupled to their
  own agent/session/MCP/memory runtimes; extracting the transport and re-wiring it
  to Coffer's Python agents — plus running a Node process and carrying fork
  maintenance — costs more than incrementally improving Coffer's own SeaTalk /
  Telegram adapters, especially since neither supports SeaTalk (Coffer's primary
  channel) and Coffer already has Telegram. Decision: reference-and-port the good
  patterns (album debouncing, edit-to-stream, ack reactions, event dedup) into
  Coffer's own clean adapters, not the code.

- **Official-channel landscape (2026-07).** Claude Code "Channels" are official
  **local** plugins for Telegram/Discord/iMessage but are a **research preview**,
  personal-only (no groups), require the session to stay open, and cannot
  transcribe voice
  ([code.claude.com/docs/en/channels](https://code.claude.com/docs/en/channels)).
  Claude-in-Slack, Codex-in-Slack, and Cursor-in-Slack are official but
  **Slack-only**, **cloud-hosted**, and single-agent
  ([code.claude.com/docs/en/slack](https://code.claude.com/docs/en/slack),
  [developers.openai.com/codex/integrations/slack](https://developers.openai.com/codex/integrations/slack),
  [cursor.com/docs/integrations/slack](https://cursor.com/docs/integrations/slack)).
  Codex/Gemini/OpenCode have **no** official Telegram; Gemini CLI has no official
  IM channel at all. **SeaTalk is supported by none of them (no official
  competition for any agent).**

- **Single-track channel-management-plane model.** Coffer's channel plane
  manages only what Coffer hosts — the **Coffer-hosted channel** (SeaTalk
  always, plus Telegram for the agents/uses the official bridges don't cover),
  the one-bot-controls-all-agents moat, managed the same way Coffer manages MCP
  servers, memory, and skills. **Externally-hosted channels — agent-native
  gateways (OpenClaw/Hermes standalone) and official integrations
  (Claude/Codex/Cursor-in-Slack, Claude Code's official plugins) — are a
  non-goal:** Coffer neither proxies nor manages them (stacking gateways
  conflicts with their runtime; a token handed to an external process's config
  defeats the vault; official cloud integrations have no local credential to
  hold). Users set those up through the tool's own flow; Coffer's docs point the
  way. (Earlier framing considered a second "manage external channels" track —
  dropped as over-engineering / YAGNI.)

- **North star.** One paired bot drives any managed agent, switchable per
  conversation and per thread (each thread is its own conversation, FR-032).
