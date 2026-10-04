## Context

The product decisions are fixed by the owner (see proposal). This file records
how they are built and the choices the owner left open.

## Decisions

### Specs move with the code, phase by phase

The change is one OpenSpec change, but the code lands in phases on one
integration branch, and `audit_acceptance` fails any scenario in
`openspec/specs/` that no test covers. So each phase deletes from
`openspec/specs/` the requirements this change REMOVES once their tests are
gone; the ADDED and MODIFIED requirements stay in the change folder (markers
naming their scenarios are accepted while it is in flight). At the end the main
specs are restored to their state before the change and the change is archived
normally, which applies every delta at once. `openspec validate` accepts a
REMOVED requirement that is already missing from the main spec, so the
in-between state validates.

The validator refuses a MODIFIED block that drops or renames a scenario, so a
requirement that loses one is REMOVED and ADDED again under a new title.

### Conversation index stays; text goes

`chat_conversations` keeps `id`, `agent_key`, `title`, `created_at`,
`updated_at`, `channel_uid`, `peer_chat_id` and `agent_config` (cwd, the native
session id, model). Migration `0149` drops `chat_reply_files`, `chat_messages`
and `chat_conversations.archived_at`, deletes conversation rows that no channel
owns (the web's own conversations: their native sessions remain in Agent ›
Sessions), and deletes the retention policy rows of the two conversation
entries. The downgrade recreates the empty tables and the column; the data is
not restored.

A turn no longer receives Coffer's message history: every adapter resumes the
agent's own session, which holds the conversation. A fresh session (first turn,
or the one retry after a forgotten resume id) starts without history.

The conversation's title is still taken from the first message the person
wrote (it lives on the index row).

### Questions and the "needs you" mark stay in memory

The pending-question registry was already in memory; what goes is its copy in
the reply's content blocks. The list's `needs_you` and `running` flags read the
in-memory turn state. A question is answered from the channel (IM card or
reply); the web route that answered one is removed.

### Native sessions behind one port

`agent-registry` owns reading and changing an agent's native sessions
(`NativeSessionService`, application layer) through a per-type adapter
(infrastructure):

- Claude Code: `claude_agent_sdk.list_sessions` / `rename_session` /
  `delete_session`. The SDK locates sessions through `CLAUDE_CONFIG_DIR`; when
  the registered agent's config directory is not `~/.claude`, the adapter sets
  that variable around the call under a module lock. Calls run in a worker
  thread.
- Codex: a short-lived `codex app-server` (the same transport the turns use)
  answering `thread/list` (all source kinds, so sessions Coffer's channels ran
  are listed too, paged with the server's own cursor and `searchTerm`),
  `thread/name/set` and `thread/delete`.

Chat may not import the agent kind (import-linter fence), so the chat routes
reach rename/delete through a port published at the composition root, the way
the model catalogue already is.

`GET /api/v1/agents/{uid}/sessions?q=&limit=&cursor=` replaces
`/transcripts` and `/transcripts/session`. A row carries `session_id`, `title`,
`cwd`, `created_at`, `last_activity_at`, and — when the session is a channel
conversation's — `conversation_id`, `running`, `needs_you` and the channel
binding, so the same busy dialog works from both lists. Search matches title
and cwd. Claude's listing is fetched whole (head/tail reads, no parse) and
filtered and paged in memory by offset cursor; Codex pages with its own cursor.
`PATCH .../sessions/{id}` renames, `DELETE .../sessions/{id}` deletes; a
session that a conversation points at takes its index row with it.

`PATCH /api/v1/chat/conversations/{id}` (title) and `DELETE
/api/v1/chat/conversations/{id}` now act on the conversation's native session
(rename/delete through the port) and then on the index row. A conversation
that has no native session yet (no turn ran) is renamed / deleted in the index
only.

### Opening a terminal

`POST /api/v1/fs/terminal` takes `{terminal, agent, cwd, resume | prompt}`.
The daemon builds the command itself from these fields; the client never sends
a command line. `terminal` is a launcher value from `GET /api/v1/fs/terminals`
or a custom template; null means the system terminal.

- Command: `cd '<cwd>' && claude --resume <id>`, `codex resume <id>`; a new
  session is `claude "$(cat '<file>'; rm -f '<file>')"` (Codex alike). The
  prompt file is written `0600` under `~/.coffer/tmp/handoff/`, so the
  prompt's text never appears on a command line or in shell history (the
  rule the old hand-off kept by never putting the prompt in a URL). Session ids
  are validated (`[A-Za-z0-9-]`) before they reach a command.
- Adapters (one small function each, argv only, no shell in the daemon):
  Terminal.app / iTerm — `osascript` (`do script`; iTerm `create window with
  default profile` + `write text`); Warp — a launch configuration YAML in
  `~/.warp/launch_configurations/coffer-<id>.yaml` opened with
  `open warp://launch/<file>`; Orca — `orca terminal create --worktree
  path:<cwd> --command <cmd> --focus`; Linux — `gnome-terminal`, `konsole`,
  `x-terminal-emulator` running `sh -lc <cmd>`; custom — the template split
  with `shlex`, `{cwd}` and `{command}` substituted inside each argument,
  executed as an argument vector.
- `GET /api/v1/fs/terminals` lists the installed ones (app bundles on macOS,
  commands on `PATH` elsewhere), reading nothing but presence — like
  `/fs/editors`.
- No cwd (a hand-off) runs in Coffer's default workspace directory, the folder
  hand-off conversations already used.

### One session, one place

- From the web: a row whose turn is running or waiting on a question opens a
  dialog — "answer in <platform>" or "stop this turn and continue in the
  terminal". The second calls the existing interrupt (which cancels the
  question and tells the agent the owner stopped) and then opens the terminal.
- From a channel: before a turn resumes a native session, the turn platform
  asks a `SessionInUsePort` whether any process outside the daemon's own
  process tree has the session id among its arguments (psutil). If one has,
  the turn does not start and the channel replies "This session is open in a
  terminal — continue there, or send /thread to start a new one." Codex's
  `-32600` "already has an active writer" error is mapped to the same refusal.

### Lists are lists

The Conversations page lists only channel conversations (`source` = a channel
uid); there is no Active/Archived toggle and no bulk bar. Its filters keep
Channel and Agent. Each row: title, needs-you / running mark, channel, agent,
directory, time, inline Stop while running, the split button, and ⋯ (Rename,
Delete…). Agent › Sessions uses the same row component without the channel
column.

The lists refresh on window focus and on the change feed's chat events, as
before.

### Settings

`coffer.preferredTerminal` (string; empty = system terminal) and
`coffer.handoffAgent` (`claude_code` | `codex`) in `localStorage`, read at click
time. The hand-off's default agent falls back to the first managed agent when
the stored one is not available.

### Hand-off button

`AgentHandoff` keeps its props (`prompt`, `size`, `help`); `autoSend` becomes
`label` (it only named the button). Main part: "Hand off to <Agent>" →
`POST /fs/terminal` with the prompt; a toast says the terminal opened, or
shows the error with Copy prompt as the way out. Menu: "Hand off to <other
agent>" when the other one is managed, then Copy prompt. No managed agent →
Copy prompt only. A prompt given as a function is called with the agent's
display name, as before.

## Risks

- Terminal adapters cannot run in CI (Linux); they are unit-tested by the
  argv they build. Real behaviour on macOS is listed for local verification.
- Process-argument detection only sees sessions started with the id on the
  command line (`--resume <id>`); a session the person opened by picking it
  inside the agent's own picker is not seen. Codex's writer lock still
  protects Codex; Claude would fork in that case.
- Claude Code deletes old sessions after `cleanupPeriodDays` (about 30 days by
  default). Now that Coffer keeps no copy, a channel conversation older than
  that resumes as a fresh session; the docs say where to change the setting.
