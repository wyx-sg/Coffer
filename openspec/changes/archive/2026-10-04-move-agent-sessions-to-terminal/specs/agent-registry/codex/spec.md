## REMOVED Requirements

### Requirement: Read Codex transcripts from the sessions directory
**Reason**: The sessions are no longer found by walking `<config_dir>/sessions/**/*.jsonl` and parsing them; they are asked of the Codex app-server. The scenario "list Codex sessions from the sessions directory" described the file walk.
**Migration**: See "List Codex sessions through the app-server" ("list Codex sessions through thread/list" replaces "list Codex sessions from the sessions directory").

## ADDED Requirements

### Requirement: List Codex sessions through the app-server
The native sessions of [agent-registry](../spec.md) "List an agent's native sessions through the agent" for this type
MUST be asked of a short-lived `codex app-server` — the transport the turns use — over JSON-RPC: `thread/list` for the listing,
`thread/name/set` for a rename and `thread/delete` for a delete. The listing MUST ask for every source kind, so sessions
Coffer's channels ran are listed beside the ones the person started in the Codex app or the terminal, and pages with the server's
own cursor, passing the search to the server as its `searchTerm`. Like every Codex process Coffer starts for an agent whose config
directory is not `~/.codex`, the app-server MUST carry `CODEX_HOME=<config_dir>`; for the default directory the
environment is left as the daemon's own.

#### Scenario: list Codex sessions through thread/list
- **GIVEN** a registered `codex` agent with sessions started by the Codex app and by a channel
- **WHEN** the user lists the agent's sessions
- **THEN** both are listed, each with its title, working directory and times, the channel's with its conversation

#### Scenario: ask the app-server of the agent's own Codex home
- **GIVEN** a `codex` agent registered with a `config_dir` other than `~/.codex`
- **WHEN** its sessions are listed
- **THEN** the app-server is started with `CODEX_HOME` set to that `config_dir`, and a listing for the default `~/.codex` starts with the environment untouched

#### Scenario: rename and delete go through the app-server
- **GIVEN** a registered `codex` agent with a session
- **WHEN** the session is renamed and then deleted
- **THEN** `thread/name/set` and `thread/delete` are called with the thread id, and no file under `sessions/` is edited by Coffer
