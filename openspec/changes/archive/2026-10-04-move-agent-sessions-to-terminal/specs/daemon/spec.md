## MODIFIED Requirements

### Requirement: Report what Coffer stores and clear the rebuildable cache
The daemon MUST report, for Settings › Data, what Coffer keeps on this machine in the four kinds
of [Storage Is Five Classes by Nature](../../../docs/decisions/storage-is-five-classes-by-nature.md)
the user acts on, through `GET /api/v1/storage`: the **vault** (the vault repository
`~/.coffer/vault/`, a git repository whether or not it syncs — its path, its size with its
history and how many versions it holds; no version count before the repository has been created), the
**local content** (channel media under `~/.coffer/content/`, which never sync:
their locations, the one folder to open, and their size), the **history** (the database file
holding the records, `~/.coffer/runs.db` unless `COFFER_DB_URL` names another, with its WAL, and
its size together with the log directory's, `~/.coffer/logs/` unless `COFFER_LOG_DIR` names
another, and with the skills' working files in `~/.coffer/skill-data/` and the config backups in `~/.coffer/config-backups/`) and the **rebuildable cache** (the memory tree under
`~/.coffer/derived/`, and its size). Every path MUST come from the same place its owner
resolves it, so an override the owner honours is honoured here.

`POST /api/v1/storage/cache/clear` MUST delete the files of the memory tree, and nothing else: no vault, local content, history or other file
under `derived/`, and no partition row, so the next memory update rebuilds each partition from the
agents' own memory. It MUST be refused (`UPKEEP_ALREADY_RUNNING`) while a memory pass is running,
because that pass is writing into the tree, and MUST record the clear in the audit log with the
bytes freed.

#### Scenario: the storage summary reports the four kinds
- **GIVEN** a vault repository of three commits, channel media, a database with its WAL and a memory tree
- **WHEN** `GET /api/v1/storage` is called
- **THEN** it reports the vault as `~/.coffer/vault` with 3 versions, the local content with the channel media location under `~/.coffer/content` and its size, the history as `runs.db` with its WAL plus the log directory, `skill-data` and `config-backups`, and the cache as the size of the memory tree
- **AND** before the vault repository has been created it reports the vault with no version count

#### Scenario: clearing the cache leaves everything else
- **GIVEN** a memory tree, a knowledge document in the vault, channel media, a sync round's hand-merge copy and the database
- **WHEN** `POST /api/v1/storage/cache/clear` is called
- **THEN** the memory tree is empty, everything else is untouched, the answer carries the bytes freed and the audit log records the clear
- **AND** while a memory pass is running the clear is refused and nothing is deleted

## ADDED Requirements

### Requirement: Open an agent session in a terminal
The daemon MUST expose `POST /api/v1/fs/terminal`, which starts an agent's session
in a terminal window on the host — an existing session resumed, or a new session
begun with a prompt. The body is `{terminal, agent, cwd, resume | prompt}`: `terminal` is a
launcher value from `GET /api/v1/fs/terminals`, a custom command template, or null for the
system terminal; `agent` is `claude_code` or `codex`; `cwd` is an absolute directory; and
exactly one of `resume` (a session id) or `prompt` (the first message of a new session) is
given. The daemon builds the command itself and the client never sends a command line: a
resume runs `cd '<cwd>' && claude --resume <id>` or `codex resume <id>`; a new session runs
`claude "$(cat '<file>'; rm -f '<file>')"` (`codex` alike), where the prompt was written to a
private temporary file (mode `0600`, under `~/.coffer/tmp/handoff/`) that the command reads and
removes, so the prompt's text never appears on a command line or in shell history. A session id MUST be
checked against `[A-Za-z0-9-]` before it reaches a command. A `cwd` that is absent, or that no longer
exists as a directory, runs in Coffer's default workspace `~/.coffer/content/workspace` (created
on first use) instead of failing.

The terminal is started by one small adapter per launcher, each invoked with an argument vector and no
shell of the daemon's: Terminal.app and iTerm through `osascript`; Warp through a launch configuration
file opened with `open warp://launch/<file>`; Orca through its command line; on Linux `gnome-terminal`,
`konsole` or `x-terminal-emulator` running `sh -lc <command>`; null is the system terminal (Terminal.app
on macOS, `x-terminal-emulator` on Linux). A custom template is split into arguments with
shell-word rules, `{cwd}` and `{command}` are substituted inside each argument, and the result is run as an
argument vector, never through a shell; a template without `{command}` is invalid.

An unknown `agent`, a session id that fails the check, a relative `cwd`, both or neither of `resume`
and `prompt`, or an invalid template MUST be refused `FS_TERMINAL_INVALID` (400) before anything is started;
a launcher that cannot be started is `FS_TERMINAL_FAILED` (502) carrying its reason. The route is guarded by the
same loopback + token auth as every daemon route. Its caller is the web UI's hand-off and session
rows ([web-ui](../web-ui/spec.md) "Let the user choose a terminal"; [chat](../chat/spec.md)
"Open a conversation in the terminal").

#### Scenario: a resume opens the agent's resume command in the session's directory
- **GIVEN** an existing directory `/work/api` and no terminal chosen
- **WHEN** `POST /api/v1/fs/terminal` is called with agent `claude_code`, that `cwd` and `resume` `abc-123`
- **THEN** the system terminal's launcher is started with an argument vector carrying `cd '/work/api' && claude --resume abc-123`
- **AND** the same call for `codex` carries `codex resume abc-123`

#### Scenario: a prompt never appears on a command line
- **GIVEN** a prompt whose text is "rotate the key sk-test"
- **WHEN** it is sent with `prompt` for a new Claude Code session
- **THEN** the launcher's argument vector carries `cat` of a temporary file and not the prompt's text
- **AND** that file holds the prompt, is readable by its owner only, and is removed by the command that reads it

#### Scenario: an unsafe session id is refused before anything starts
- **GIVEN** a `resume` of `abc;touch /tmp/x`
- **WHEN** it is sent
- **THEN** the answer is `FS_TERMINAL_INVALID` (400) and no launcher is started
- **AND** so are an unknown agent, a relative `cwd`, and a body with both or neither of `resume` and `prompt`

#### Scenario: a custom template runs as an argument vector
- **GIVEN** a terminal value `mycli --dir {cwd} -- {command}`
- **WHEN** a resume is sent
- **THEN** the launcher is started with the arguments `mycli`, `--dir`, the directory, `--` and the command, with no shell involved
- **AND** a template without `{command}` is refused `FS_TERMINAL_INVALID`

#### Scenario: a missing directory opens in the default workspace
- **GIVEN** a `cwd` that no longer exists
- **WHEN** a resume is sent
- **THEN** the terminal opens in `~/.coffer/content/workspace`, created if need be

#### Scenario: the terminal route needs the token
- **GIVEN** a call with no token
- **WHEN** `POST /api/v1/fs/terminal` is called
- **THEN** it is rejected and nothing is started

### Requirement: List the terminals installed on this host
The daemon MUST expose `GET /api/v1/fs/terminals`, which enumerates common terminal applications
detected as installed on the host (macOS app-bundle names; Linux commands on `PATH`). It returns each
terminal's display label and the launcher `value` that `POST /api/v1/fs/terminal` accepts as `terminal`,
reads nothing but the presence of the application, starts nothing, and is guarded by the same loopback + token
auth. It is the terminal counterpart of `GET /api/v1/fs/editors`
("Open and reveal existing absolute paths"); its consumer is the web UI's preferred-terminal setting
([web-ui](../web-ui/spec.md) "Let the user choose a terminal").

#### Scenario: the daemon lists the terminals installed on this host
- **GIVEN** a host with two supported terminals installed
- **WHEN** `GET /api/v1/fs/terminals` is called with a valid token
- **THEN** it lists those two with their labels and the launcher values `POST /api/v1/fs/terminal` accepts, and nothing is started
- **AND** the same call with no token is rejected
