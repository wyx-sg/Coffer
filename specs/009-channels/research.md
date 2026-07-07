# Research: 009 — Channels

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
- **Typing indicator**: `single_chat_typing` endpoint exists.
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
  - Group send: `POST /messaging/v2/group_chat {group_id, message}` (add
    `thread_id` to reply into a thread instead of group-main).
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
