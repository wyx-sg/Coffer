## Why

On a transport that can read thread history (SeaTalk), every turn that lands in
a thread reads the whole thread — every page — downloads every image and file it
carries, and folds all of it into the turn text. The agent's own session already
holds what earlier turns were given, so a ten-turn thread repeats the thread ten
times: the prompt grows with every turn, the same pictures are downloaded again
and again, and a long thread pushes the person's actual question to the bottom
of a wall of context.

Other bridges settle this with a bounded seed plus a read tool (OpenClaw seeds a
new Slack thread session with about twenty messages and pages older ones on
demand). Coffer takes the same hybrid.

## What Changes

- **Bounded seed.** A conversation's first turn in a thread folds only the
  thread's 20 most recent messages (the triggering message excluded), with their
  media, in today's format.
- **Only what is new afterwards.** Each later turn of the same conversation in
  that thread folds only the messages posted since that conversation's previous
  turn there, leaving out the bot's own replies and the triggering message, and
  folds nothing when there is nothing new. A per-conversation cursor in
  `runs.db` (`channel_thread_cursors`) keeps the place across a daemon restart.
- **Older messages on demand.** When the fold leaves messages out, it ends with
  a one-line note saying how many and how to read them. The SeaTalk 7-day-window
  note stays.
- **New built-in tool `coffer__channel_read_thread`.** It reads a thread's
  messages page by page, newest page first (`before` cursor, `limit` 1–100,
  default 20), returning sender, time and text per message and the local paths
  of the images and files it carries. It reads only threads of chats the channel
  has paired, never a chat's main history, and on a platform with no history API
  (Telegram) says so. Like `coffer__ask` it is turn-scoped: offered only to an
  agent inside a turn Coffer runs.
- **The agent is told.** The origin block names the channel (`channel: <name>`),
  which the tool takes, and the channel note tells a channel-driven agent on a
  platform that can read threads to use the tool for earlier messages.
- **Media only for what is folded.** A thread read is text only; the images and
  files of just the folded messages (or a tool page's messages) are downloaded.
- The quoted message is still folded inline, unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `channels`: "Reply in place inside threads", "Download the media a thread's
  messages carry", "Ground a DM thread's turn in the thread", "Say what a thread
  read cannot show", "Open every turn with its message origin" and "Tell a
  channel-driven agent it is on a chat channel" change; "Ground a thread turn in
  a bounded slice of the thread" and "Read a thread's earlier messages on
  demand" are added. `data-model.md` gains `channel_thread_cursors`.
- `channels/seatalk`: "Read every page of a thread" and "Download the files a
  fetched thread carries" change: the read is text only, and media is fetched
  per kept message.
- `mcp-gateway`: "Forward tools, resources and prompts" names the turn-scoped
  built-ins (`coffer__ask`, `coffer__channel_read_thread`) beside
  `coffer__search_tools`.

## Impact

- Backend: `application/channel/turn_context.py` (bounded fold, cursor),
  `thread_tool.py` (new), `conversation_ops.py` (`predict_conversation`),
  `inbound.py`, `turn_driver.py` (claiming a pending cursor), `store_ports.py`,
  `ports.py` (`ContextFetchPort` returns a `ThreadRead`; per-message media),
  `domain/channel/thread_messages.py` (new), `rich_content.py` (channel line),
  `application/builtin_tools.py` (turn-scoped tools), the gateway's built-in
  view, `infrastructure/channel/seatalk_history.py`, `seatalk.py`,
  `telegram.py`, `cursor_persistence.py` (new), migration `0152`, the channel
  note (`domain/chat/channel_note.py`, `prompt_note.py`, `adapter_support.py`),
  and `surfaces/http/channel_wiring.py` / `app.py`.
- No REST route, no wire contract and no web UI change. The new table is
  history in `runs.db`, deleted with its channel.
- Docs: channels and SeaTalk guides, the chat architecture page, the MCP tools
  reference and the surfaces roster, in English and Chinese.
