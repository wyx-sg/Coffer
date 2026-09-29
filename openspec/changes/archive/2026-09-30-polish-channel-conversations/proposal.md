## Why

A long channel turn looked frozen: the live surface showed the first sentence
the agent wrote and stopped there while it ran twenty tools. Nothing buzzed when
a four-minute SeaTalk turn finished, because its answer lives in a message
created when the turn began. Telegram's completion reaction never landed (✅ is
not on the Bot API's reaction list), long answers were cut inside code blocks,
text either side of a tool call ran together, and group scaffolding rang every
member's phone. The agent was not told which platform it was on or what renders
there, so it wrote headings SeaTalk cannot show and tables that arrive as pipes,
and a question that needed the owner's yes ended the turn as ordinary text.

## What Changes

- **One status line** at the top of the live surface: `⏳ Working · 2m 14s · 7
  steps`, the agent's latest narration, the newest three steps, then the answer
  so far. It ticks on the surfaces' keep-alive cadence. Narration between tool
  calls goes to the status line; the final reply keeps it with paragraph breaks.
  A per-channel **show steps** setting (default on) hides the step lines.
- **Reactions** on Telegram follow the turn: 👀 received → 👨‍💻 working → 👌 done /
  😢 failed / 🤷 stopped — each on the Bot API's allowed list.
- **Completion ping** for a turn longer than a per-channel threshold (default
  90 s, 0 = off): where the answer lives in a message created at the start
  (SeaTalk), one short new message `✅ Done · 4m 12s — <first line>` (failed,
  stopped and waiting variants), @mentioning the asker in a group, in the same
  thread. A clean long turn now sends that one line.
- **Telegram group mention**: every group answer opens with a real mention of
  the asker.
- **Channel-turn instructions**: the agent is told the platform and chat kind,
  the Markdown that renders there, and the answer shape — outcome first, no step
  narration, long content under `## Details`, diagrams as PNG files, and a final
  `NEEDS YOU:` line when it needs a yes or a choice.
- **Rendering**: Telegram collapses `## Details` into an expandable block;
  SeaTalk turns tables into bullet rows plus an attached CSV and long logs into
  attached files; continuation messages are numbered `(2/3)`.
- **Buttons for `NEEDS YOU:`**: Yes/No (or up to four options) on both
  platforms; a tap is sent into the conversation as the owner's own reply;
  anyone else's tap is refused.
- **Telegram rich draft**: a direct chat's draft shows the status header in the
  platform's thinking block.
- **SeaTalk summary card**: an answer with details sends a card with the
  outcome and Details / As file buttons; Details posts them as a thread reply.
- Bug fixes: fence-aware chunking, paragraph breaks across tool calls, silent
  Telegram scaffolding and continuation chunks, allowed reactions only.

## Capabilities

### New Capabilities

### Modified Capabilities
- `channels`: status line, reactions, completion ping, show-steps and ping
  settings, `NEEDS YOU:` buttons, reply shaping, details card, the channel note.
- `channels/telegram`: status-message and draft contents, rich draft, mention,
  details block, silent continuations.
- `channels/seatalk`: status in the stream, completion ping, tables and logs as
  files, numbered continuations, summary card.
- `chat`: the channel note in the composed prompt appends names platform, chat
  kind and render facts.

## Impact

- Backend: `application/channel/turn_*` (renderer split into status, surface,
  finish, shape, prompt facts), adapters' capabilities and send paths, channel
  config (`show_steps`, `notify_after_seconds`), CLI `channel add|edit
  --show-steps/--hide-steps --notify-after`, `infrastructure/chat/adapter_support`.
- Frontend: Edit channel dialog, en/zh strings.
- Docs: channels guides, CLI reference, chat architecture page, data model.
- No migration: both settings live in the channel's config document with
  defaults.
