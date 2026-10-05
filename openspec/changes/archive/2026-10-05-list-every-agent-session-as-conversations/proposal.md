## Why

The Conversations page lists only the conversations IM channels opened. Since the
web chat was removed, that makes it a by-product of Channels — its subtitle reads
"The conversations your channels started" — while most of a person's agent work
happens in sessions they start themselves in a terminal, which the page never
shows. Those sessions are already readable: each agent lists its own native
sessions for its Sessions tab, and a channel conversation is one of them once a
turn has run. The page should be the one place to find every session of every
agent, wherever it was started, and to start a new one.

## What Changes

- **Conversations lists every agent's sessions.** A new cross-agent listing,
  `GET /api/v1/agent-sessions`, merges each managed agent's native session
  listing by latest activity and pages by one cursor. A row a channel
  conversation points at keeps its channel badge, Running / Needs you and Stop.
  Filters: **Source** (This Mac, or one or more channels), **Agent**, and a
  search. The list gains a header row naming its columns. When one agent cannot be read, the others are still listed and a line
  above the list names the agent with Retry.
- **New conversation.** The Conversations page header and an agent's Sessions tab
  carry **New conversation**, a split button that opens a small dialog — agent
  (remembered) and working directory (Coffer's workspace by default, with a
  folder picker) — whose confirm reads **Open in &lt;terminal&gt;**, with the other
  terminals in its ▾. Confirming starts a fresh session of that agent in the
  terminal; it appears in the list once the agent records it.
- **The terminal route starts a blank session.** `POST /api/v1/fs/terminal` accepts
  a body with neither `resume` nor `prompt`, which runs the agent with no argument
  in the directory.
- **Channels stays configuration.** A channel's Overview drops its latest-conversations
  block for one link, **Conversations from this channel →**, to
  `/conversations?source=<uid>`.
- **The channel-only listing goes.** `GET /api/v1/chat/conversations` (the list) is
  removed; the single-conversation read, rename, delete and interrupt routes stay.
- The sidebar keeps Conversations and Channels as two entries; their descriptions
  and the Run group's intent are reworded.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-registry` — adds the cross-agent session listing; the Sessions tab gains
  New conversation.
- `chat` — the Conversations page lists every agent's sessions and starts new
  ones; the channel-only listing requirement is removed.
- `daemon` — the terminal route starts a blank session.
- `web-ui` — sidebar wording for Conversations, Channels and the Run group.
- `channels` — a channel's Overview links to its conversations instead of listing them.

## Impact

- Backend: new route and an application service over `NativeSessionService`;
  `terminal_command.py` gains the blank-session command; the conversation list
  route, its `Narrowing` paging and count are deleted.
- Contracts: `agent-registry` and `chat` OpenAPI regenerated; `daemon`'s
  `FsTerminalRequest` loosens to "at most one of".
- Frontend: Conversations page and filters rewritten over the new listing,
  `NewConversationDialog`, Sessions tab header, channel Overview.
- Docs: `docs-site/guides/chat.md`, `guides/channels.md`, `guides/web-ui.md`,
  `architecture/chat.md` (en + zh); design canvases for Conversations, the
  channel Overview, the agent Sessions tab and the new dialog.
