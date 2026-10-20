## Why

Replies in a chat channel still read like an agent's work log. A Codex reply in
SeaTalk carried the model's own working rules ("must not claim…", "report
BLOCKED") and a long unordered list, then a half-filled template. Two causes:
Codex's mid-turn commentary reached the reply (Coffer ignored its `phase` and
did not treat MCP and other tools as tool calls), and the default reply style
asked only for "outcome first, about 15 lines". The owner wants the
conversation to read like two people talking: no intermediate thinking, only
results, short and clearly structured, and a detailed report only as a file the
reader is asked about first.

## What Changes

- Codex: every tool item (MCP, dynamic, sub-agent, web search, image) is a tool
  call; each agent message ends with `MessageEnd`, marked `commentary` for
  Codex's `commentary` phase. The channel renderer leaves commentary out of the
  reply and shows it as the `💬` line. Applies to every channel; Claude Code
  already reported every tool.
- The default reply style is rewritten: write like a person texting, the answer
  first in one or two sentences, no process or caveat lists, about 8 lines, a
  full report only as a file offered first.
- A reply that finished cleanly but is too long for a chat (over 20 lines or
  1,500 characters) is not sent: a follow-up turn asks the same conversation
  for the short version, whose reply carries a **📄 Full report** button; the
  tap asks the agent for the file.

ADR: [long-channel-reply-is-rewritten-short](../../../docs/decisions/long-channel-reply-is-rewritten-short.md);
[channel-prompt-fixed-note-and-editable-style](../../../docs/decisions/channel-prompt-fixed-note-and-editable-style.md) updated.

## Impact

- Specs: channels, chat.
- Backend: `domain/chat/events.py` (`MessageEnd`), `infrastructure/chat/codex_mapping.py`,
  `application/channel/turn_status.py`, `turn_render.py`, `turn_driver.py`,
  `reply_rewrite.py` (new), `rewrite_turn.py` (new), `reply_tracking.py`,
  `inbound_events.py`, `inbound.py`, `domain/chat/channel_prompt.py`.
- Docs: guides/channels, architecture/chat (en + zh).
- An owner who rewrote a channel's reply style keeps it; the Channels page says
  Coffer's default changed since.
