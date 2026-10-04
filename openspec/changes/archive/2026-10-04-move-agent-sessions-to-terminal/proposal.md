## Why

The principles say Coffer is **not a second agent**: what a coding agent already
does for itself, Coffer does not rebuild. The web Conversations page was a
second chat client for Claude Code and Codex — the Claude desktop app and the
Codex app already are that — and it saw almost no use (two conversations ever
started from the web, on one day; every other conversation came from a
channel). Coffer also kept a second copy of every conversation's text in
`chat_messages`, beside the agent's own session record.

What Coffer does that no agent does alone stays: the turn platform that lets an
IM channel reach an agent on this machine. The web keeps the lists — the
channel conversations, and every native session of each agent — and hands an
opened row to the agent's own interface: the person's terminal. The hand-off
button follows the same path (principles, IV. AI-Native, amended in this PR).

## What Changes

- **Two lists, no detail pages.** The Conversations page lists the conversations
  that came from channels; Agent › Sessions lists that agent's own native
  sessions. Both are lists only. Columns: title, agent, working directory, last
  activity and (Conversations) the channel. Search matches title and directory.
  Rows keep the "Needs you" mark and an inline Stop.
- **Opening a row resumes the session in the preferred terminal**:
  `claude --resume <id>` / `codex resume <id>` in the session's directory. The
  row's split button is **Open in terminal ▾ Copy command**. A running turn or
  a pending question asks first: answer in the channel, or stop the turn and
  continue in the terminal.
- **One session runs in one place.** Before a channel resumes a session, the
  daemon looks for a process whose arguments carry that session id; if one is
  found the channel replies that the session is open in a terminal (and Codex's
  "active writer" refusal gets the same reply).
- **Rename and delete use the agent's own operations** (Claude Agent SDK
  `rename_session` / `delete_session`; Codex app-server `thread/name/set` /
  `thread/delete`). Delete is permanent and asks first. Coffer's own rename,
  archive, unarchive, delete, read-only archived view and conversation
  retention are removed.
- **Coffer stores no conversation text.** `chat_messages` and
  `chat_reply_files` are dropped, with `chat_conversations.archived_at`. The
  conversation index (channel thread ↔ conversation ↔ native session id), the
  in-memory event stream of the running turn, the queue, interrupt and the
  channel tables stay. Questions live in memory only, as before.
- **Session listings come from the agents**: Claude's `list_sessions`, Codex's
  `thread/list`. The hand-written transcript parser, its sidecar cache and its
  warm worker, and the windowed transcript read are removed.
- **Settings › General** gains **Preferred terminal** (built like Preferred
  editor: the system terminal by default, the terminals the daemon detects via
  `GET /api/v1/fs/terminals`, or a custom command template with `{cwd}` and
  `{command}`) and **Hand-off agent** (Claude Code or Codex).
- **The daemon opens a terminal**: `POST /api/v1/fs/terminal` starts an agent
  session — resumed, or new with a prompt — through a small adapter per
  terminal (Terminal.app and iTerm via `osascript`, Warp via a launch
  configuration, Orca via its CLI, a custom template as an argument vector).
  A prompt travels in a private temporary file, never on the command line.
- **The hand-off button** reads "Hand off to <Agent>": it starts the default
  agent in the preferred terminal with the prompt sent; its menu holds the
  other installed agent and Copy prompt.
- Removed with the page: the message thread, composer, draft conversation,
  web uploads, answer cards, web-reply mirroring into channels, model dropdown,
  files-changed card and diff drawer, and their routes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `chat`: the turn platform keeps the conversation index, queue, events and
  interrupt; the web chat, the message store and conversation retention go;
  the Conversations page becomes a list that opens rows in a terminal.
- `channels`: refuse to resume a session open elsewhere; drop the
  archived-conversation rule and references to the web thread.
- `agent-registry` (+ `claude-code`, `codex`): native session listing, rename
  and delete through the agents' own interfaces; the transcript reader goes.
- `daemon`: `POST /api/v1/fs/terminal`, `GET /api/v1/fs/terminals`.
- `web-ui`: preferred terminal and hand-off agent settings; the hand-off
  button; the Agent › Sessions list.
- `resource-framework`: the conversation retention entries and chat media go.

## Impact

- **Removing shipped behaviour** (principles, Governance): the web chat, the
  transcript reader and Coffer's copy of conversation text. A reversal would
  have to restore the deleted modules (git history has them), and the migration
  that drops `chat_messages`, `chat_reply_files` and `archived_at` is **not
  reversible for data**: the downgrade recreates empty tables. The agents' own
  session records are untouched, so no conversation is lost to the person —
  each is still in Claude Code / Codex until the agent's own clean-up removes it.
- Backend: `application/chat`, `infrastructure/chat`, `surfaces/http/chat`,
  `application/agent` + `infrastructure/agent` transcript modules,
  `application/fs` (terminal), `application/channel` (open-elsewhere refusal,
  mirror removal), retention registry, one migration.
- Frontend: `components/chat`, `components/agents/sessions`,
  `components/handoff`, `lib/chat`, `lib/conversations`, settings, i18n.
- Docs: principles IV, the Conversations and Sessions guides, hand-off pages,
  persistence and chat architecture pages (en + zh), ADRs.
- Canvas (not editable from this session; listed for the owner): Foundations
  0.7.04 hand-off button, Run canvas Conversations list and detail boards,
  Agents canvas Sessions boards (2.1.52–2.1.54), Shell canvas Settings › General.
