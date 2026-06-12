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
  approval handling, and rendering policy live in a shared core. Hermes'
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
  tap. This is the approval prompt mechanism.
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
  `employee_code` — a complete approve/deny loop.
- **Typing indicator**: `single_chat_typing` endpoint exists.
- **Org approval**: a self-built app's scopes (Send Message to Bot User,
  etc.) require organization admin approval; outbound IP allowlist is
  optional and should stay empty for machines with dynamic IPs.

## Decisions taken from research

| Decision | Choice | Rationale |
| --- | --- | --- |
| Telegram transport | long polling via raw httpx | local-first, no ingress; the API surface used is 7 small methods — an SDK dependency buys nothing and adds an import-confinement contract |
| SeaTalk transport | webhook → separate listener process + user-run tunnel | webhook is the only option; the constitution requires public-reachable surfaces to be a separate process limited to signed callback paths |
| SeaTalk SDK | none (raw httpx) | the official repo itself is a thin httpx-equivalent; token caching is ~20 lines |
| Pairing parameters | 8 chars, no `0O1I`, 1 h TTL, bounded guesses, fail closed | matches both prior arts and Hermes' post-incident hardening |
| Telegram rendering | markdown → HTML, plain-text retry on rejection | OpenClaw-proven; MarkdownV2 escaping is a known bug farm |
| Progress UX | one editable status message, throttled; ack first; final reply separate | both prior arts; degrades naturally on SeaTalk via capability flags |
| Mid-turn input | bounded FIFO queue, control commands bypass | predictable; avoids Hermes' interrupt-by-default surprise |
| Session scope | one long-lived conversation per `(channel, chat)`, `/new` resets | matches the 1:1 product decision; group chats become new rows later |
