## RENAMED Requirements

- FROM: `### Requirement: Read Claude Code transcripts from the projects directory`
- TO: `### Requirement: List Claude Code sessions through the Agent SDK`

## MODIFIED Requirements

### Requirement: List Claude Code sessions through the Agent SDK
The native sessions of [agent-registry](../spec.md) "List an agent's native sessions through the agent" for this type
MUST be asked of the Claude Agent SDK — `list_sessions`, `rename_session` and `delete_session` — and not parsed from files.
The SDK finds sessions through `CLAUDE_CONFIG_DIR`: when the agent's config directory is not `~/.claude`, the adapter MUST set that variable
to it for the call, under a module lock, and restore it after; the calls run in a worker thread, off the request path.
The listing is fetched whole (the SDK reads only the head and tail of each session file), then filtered by the search and paged in memory,
the cursor carrying the last row's activity time and session id so a session written between two reads neither repeats nor skips a row.
The sessions live under `<config_dir>/projects/`, which is also the parent of this type's memory stores,
which is why the store read of [agent-registry](../spec.md) "Read one native memory store's files read-only" MUST accept only a
directory the layout of "Scan Claude Code's per-project memory stores" would have listed and reject a sibling path under
`projects/` that merely looks like one.

#### Scenario: list sessions from projects and refuse a sibling as a memory store
- **GIVEN** a registered `claude_code` agent with a session and a `memory/` store under `<config_dir>/projects/<slug>/`
- **WHEN** the user lists the agent's sessions and then opens `<config_dir>/projects/<slug>` as a memory store
- **THEN** the session is listed
- **AND** the store read is rejected as `not_found` (404)

#### Scenario: list sessions of a custom config directory
- **GIVEN** a `claude_code` agent registered with a `config_dir` other than `~/.claude`
- **WHEN** its sessions are listed
- **THEN** the SDK is asked with `CLAUDE_CONFIG_DIR` set to that directory, and the variable is restored afterwards

#### Scenario: a new Claude Code session does not shift the next page
- **GIVEN** an agent's sessions read with `limit=2`
- **WHEN** a new session is written and the next page is read with the first answer's `next_cursor`
- **THEN** the second page holds the sessions that followed the first page's last one, none of the first page's sessions and not the new one

#### Scenario: rename and delete go through the SDK
- **GIVEN** a registered `claude_code` agent with a session
- **WHEN** the session is renamed and then deleted
- **THEN** `rename_session` and `delete_session` are called with the session id, and no session file is edited by Coffer
