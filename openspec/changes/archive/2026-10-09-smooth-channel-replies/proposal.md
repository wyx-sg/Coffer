## Why

Channel replies read badly in three ways the owner hit in daily use:

- **A SeaTalk direct chat flickers.** Its reply is a SeaTalk stream that grows a
  status line, step lines and the answer in one message. The client re-types
  the whole message whenever anything already on screen changes, so every step
  redraws it. And because that message was created when the turn began,
  finishing it notifies nobody, so a long turn also needs a separate
  "✅ Done · …" ping.
- **The reply carries the agent's narration.** The delivered reply joins every
  text segment the agent wrote between tool calls, so it opens with a pile of
  "let me check…" steps before the answer.
- **SeaTalk's details card is odd.** A `## Details` section moves behind a
  summary card with **Details** / **As file** buttons, and a tap leaves the card
  reading "Details posted in the thread."

Other IM-agent products (OpenClaw, Hermes, Devin's chat integrations) show a
running turn through typing or a status surface, and their final message holds
only the answer.

## What Changes

- **SeaTalk shows only typing while a turn runs.** The SeaTalk transport no
  longer has a live surface: the typing heartbeat is the progress, and the
  finished reply is one ordinary new message (cut at paragraphs and numbered
  when long) in a direct chat, withdrawable cards in a group as before. The
  SeaTalk streaming code is deleted.
- **A live surface is always scaffolding.** Telegram keeps its draft / status
  message, which is dropped when the reply is sent as a new message. The
  `live_text_persists` and `streams_in_groups` capabilities go, since nothing
  reads them any more.
- **BREAKING (setting removed):** the long-turn ping ("Ping the asker when a
  long turn ends", the `notify_after_seconds` channel setting, and the
  "❓ Needs you" question ping) is removed end to end — every reply is now a new
  message, so it notifies on its own. A stored config that still carries the
  key is read without it; the Channels page loses the "Ping when a long turn
  ends" field.
- **The final reply is the answer alone**, for every transport: the text the
  agent wrote after its last tool call, or the last text it wrote when nothing
  followed the last tool call. Narration still shows on a live surface.
- **No details card.** A reply's `## Details` section goes out as ordinary text
  where the transport cannot collapse it; Telegram still collapses it. The
  details card, its `details:` / `detailsfile:` callback routes and its
  temporary file store are deleted. Only a transport that collapses details is
  told to write a `## Details` section.
- A SeaTalk direct-chat text reply is not put on the withdraw record, since
  SeaTalk can rewrite only cards.

## Capabilities

### Modified Capabilities

- `channels` — live surfaces are scaffolding, the reply is the answer alone, the
  ping and the details card are removed, the agent note's details hint follows
  the transport.
- `channels/seatalk` — no stream: typing while the turn runs, then one new
  message; the stream contract, the ping, the post-stream numbering and the
  details-card thread reply are removed.
- `channels/telegram` — the scaffolding requirement no longer names the removed
  capability.

## Impact

- Backend: `application/channel/` (turn renderer, surface, finish, status,
  reply tracking, card routing, prompt note), `domain/channel/` (capabilities,
  config), `infrastructure/channel/` (SeaTalk adapter and caps, shared live-text
  base, render helpers), `infrastructure/chat/adapter_support.py`.
- Wire: the channel config schema loses `notify_after_seconds`
  (`openspec/specs/channels/contracts/api.openapi.yaml`, frontend generated
  types).
- Frontend: the Channels settings field "Ping when a long turn ends" and its
  strings are removed.
- Docs: the SeaTalk and channels guides, the chat architecture page (both
  languages), the configuration reference, the live-surface ADR.
