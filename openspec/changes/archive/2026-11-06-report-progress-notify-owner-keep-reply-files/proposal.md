## Why

The chat and channel gap review (2026-11-06) found four small gaps the owner
asked to fix directly rather than park in `docs/TODO.md`:

- On SeaTalk a long turn shows only typing, and `/status` said only "Running".
- An agent in a terminal, or in its own scheduled task, had no way to tell the
  owner on their phone that it was done; only REST `notify` existed.
- A reply too long for a chat was not sent, and its `MEDIA:` files were lost
  with it: the short version usually did not repeat them.
- A send whose connection never opened failed at once, so a network blip lost
  the finished reply without a word in the chat (seen on SeaTalk 2026-11-05).

## What Changes

- `/status` on a running turn adds the status header, the agent's latest words
  and the step in hand.
- New built-in tool `coffer__channel_notify`, offered in every MCP session:
  text and optional files to the owner's direct chat, never a group.
- A long reply's `MEDIA:` lines are carried to its short version and sent once.
- Telegram and SeaTalk resend a call whose connection never opened (1 s, then
  3 s); a failure after the request went out is not resent.

## Impact

- `status_card`, `turn_status`, `turn_render`, `turn_driver`, `rewrite_turn`,
  `reply_rewrite`, new `notify_tool`, `channel_wiring`, `telegram_transport`,
  `seatalk_transport`.
- Channels spec: "Render replies by the adapter's declared capabilities",
  "Report the chat's state as a status card", "Ask for the short version of a
  reply too long for a chat", new "Let an agent message the owner's direct chat".
- Docs: channels guide, channel commands and MCP tools reference (en, zh);
  `docs/TODO.md` loses the two entries this ships.
