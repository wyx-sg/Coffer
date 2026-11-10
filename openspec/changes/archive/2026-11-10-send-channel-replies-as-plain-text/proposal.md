## Why

The owner asked on 2026-11-09 for channel bots to stop answering in cards and
reply in ordinary text, as a person does. On SeaTalk every group reply was an
interactive card (so it could be withdrawn by rewriting it) and the short
version of a too-long reply was a card too (its 📄 Full report button). Asked
how far to go, the owner chose to change the agent's replies only; command
cards and the Continue/Discard buttons after `/stop` stay. The options are
argued in ADR `a-channel-reply-is-plain-text`.

## What Changes

- Every agent reply is plain text with no button, in direct chats and groups,
  on every transport: the 🗑 button and the 📄 Full report button are gone.
- The short version of a too-long reply ends with one line offering the full
  report; the owner asks for it in a message.
- SeaTalk declares it cannot withdraw (text can be neither deleted nor
  rewritten), so `/del` there answers "🗑 This chat cannot withdraw bot
  replies." Telegram's `/del` is unchanged.
- The `withdraw_removes` capability and the adapters' `withdraw_message` are
  removed; withdrawing is `delete_message`. The reply ledger keeps three days.
- A tap on a 🗑 or 📄 button left on an old message does nothing.

## Impact

- `reply_tracking`, `reply_rewrite`, `turn_render`, `turn_driver`,
  `inbound_events`, `card_delivery`, `withdraw`, SeaTalk and Telegram adapters
  and capabilities; specs channels, channels/seatalk, channels/telegram and the
  channels data model; channel docs (English and Chinese); ADRs.
