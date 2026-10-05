## MODIFIED Requirements

### Requirement: Open an agent session in a terminal
The daemon MUST expose `POST /api/v1/fs/terminal`, which starts an agent's session
in a terminal window on the host — an existing session resumed, a new session
begun with a prompt, or a blank new session. The body is `{terminal, agent, cwd, resume? | prompt?}`: `terminal` is a
launcher value from `GET /api/v1/fs/terminals`, a custom command template, or null for the
system terminal; `agent` is `claude_code` or `codex`; `cwd` is an absolute directory; and
at most one of `resume` (a session id) or `prompt` (the first message of a new session) is
given — neither starts a new session with no first message. The daemon builds the command itself and the client never sends a command line: a
resume runs `cd '<cwd>' && claude --resume <id>` or `codex resume <id>`; a new session runs
`claude "$(cat '<file>'; rm -f '<file>')"` (`codex` alike), where the prompt was written to a
private temporary file (mode `0600`, under `~/.coffer/tmp/handoff/`) that the command reads and
removes, so the prompt's text never appears on a command line or in shell history; a blank
session runs `cd '<cwd>' && claude` (`codex`) with no argument. A session id MUST be
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

An unknown `agent`, a session id that fails the check, a relative `cwd`, both `resume`
and `prompt`, or an invalid template MUST be refused `FS_TERMINAL_INVALID` (400) before anything is started;
a launcher that cannot be started is `FS_TERMINAL_FAILED` (502) carrying its reason. The route is guarded by the
same loopback + token auth as every daemon route. Its caller is the web UI's hand-off, session
rows and New conversation ([web-ui](../web-ui/spec.md) "Let the user choose a terminal"; [chat](../chat/spec.md)
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
- **AND** so are an unknown agent, a relative `cwd`, and a body with both `resume` and `prompt`

#### Scenario: a body with neither resume nor prompt starts a blank session
- **GIVEN** an existing directory `/work/api`
- **WHEN** `POST /api/v1/fs/terminal` is called with agent `codex`, that `cwd` and neither `resume` nor `prompt`
- **THEN** the launcher is started with an argument vector carrying `cd '/work/api' && codex` and nothing after it

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
