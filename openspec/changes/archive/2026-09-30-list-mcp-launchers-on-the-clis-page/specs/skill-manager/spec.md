## MODIFIED Requirements

### Requirement: Check every required command where the agent runs
Beside the commands skills declare, the launcher every enabled stdio MCP
server starts with MUST be required too, by that server, under the command that
provides it — `uv` for `uvx`, `node` for `npx`, `bun` for `bunx`, the launcher
itself otherwise — with no minimum and no login check; a launcher given as a
path is a file, not a command on `PATH`, and is not listed. A server that is
off or reached over HTTP requires nothing.
The system MUST check each required command once, however many skills and
servers need it: look it up on the agent's real `PATH` (the login shell's, merged with the
inherited one), read its version with `<command> --version` under a timeout,
compare it with the highest minimum any skill asks for, and run its login check
under a timeout, without a shell, keeping only the exit status — the check's
output MUST be discarded unread and MUST NOT reach any log, record or response.
Each command MUST report `missing`, `outdated`, `logged_out` or `ready`, the
path and version found, the login state (`logged_in`, `logged_out` or
`not_needed`), every skill that needs it and every MCP server started with
it. Results MUST be kept until the
user asks to check again or the daemon restarts.

#### Scenario: a required command is found with its version on the agent's path
- **GIVEN** a skill requiring `uv` with minimum `0.4`, and `uv 0.4.18` on the login shell's `PATH` but not on the daemon's
- **WHEN** the required commands are checked
- **THEN** `uv` is `ready` with its path and version `0.4.18`

#### Scenario: a command older than the highest minimum is outdated
- **GIVEN** two skills requiring `gh`, one with minimum `2.20` and one with `2.40`, and `gh 2.30` installed
- **WHEN** the required commands are checked
- **THEN** `gh` is `outdated` against `2.40` and names both skills

#### Scenario: a failed login check reports not logged in without keeping its output
- **GIVEN** a command whose login check exits 1 after printing an account name
- **WHEN** the required commands are checked
- **THEN** the command is `logged_out`, and the printed text appears in no response, log line or audit record

#### Scenario: checking again probes afresh
- **GIVEN** a command reported `logged_out`
- **WHEN** the user logs in and asks to check it again
- **THEN** the command is probed again and reported `ready`

#### Scenario: a stdio MCP server's launcher is listed under the command that provides it
- **GIVEN** an enabled stdio MCP server `duckdb` started with `uvx`, one `files` started with `npx`, one started with `./run.sh`, and a skill requiring `uv` with minimum `0.4`
- **WHEN** the required commands are checked
- **THEN** `uv` is listed as needed by the skill and by `duckdb` (launcher `uvx`), and `node` as needed by `files` alone
- **AND** nothing is listed for `./run.sh`

### Requirement: Serve required commands on REST, the command line and the web
The required commands MUST be readable and checkable through
`GET /api/v1/clis`, `GET /api/v1/clis/{command}`, `POST /api/v1/clis/check`
and `POST /api/v1/clis/{command}/check`, each command carrying its hand-off
prompt and the MCP servers started with it (`needed_by_servers`: each server's
uid, name and launcher) beside the skills that need it (`needed_by`), and
reachable from `coffer cli list|show|check|prompt` (`--json` on
every read). Lists MUST put problems first: missing, then outdated, then not
logged in, then ready. The web UI's CLIs page shows them (spec web-ui "Show
every CLI a skill requires on the CLIs page") and a skill's detail page
carries a **Requires** tab listing what the skill declares, each linked to its
command's page and offering the hand-off for a command that needs the user.

#### Scenario: the command line lists required commands problems first
- **GIVEN** skills requiring a missing `jq`, an outdated `gh` and a ready `uv`
- **WHEN** the user runs `coffer cli list --json`
- **THEN** the commands come back in the order `jq`, `gh`, `uv`, each with its status and the skills that need it

#### Scenario: the command line prints the same prompt
- **GIVEN** a missing required command `jq` and a ready `uv`
- **WHEN** the user runs `coffer cli prompt jq`
- **THEN** it prints exactly the `handoff.prompt` that `GET /api/v1/clis/jq` returns
- **AND** `coffer cli prompt uv` exits non-zero saying there is nothing to hand off

#### Scenario: a CLI page lists the MCP servers started with the command
- **GIVEN** an enabled stdio MCP server `duckdb` started with `uvx`, a skill `data-profiling` requiring `uv`, and no `uv` on the agent's `PATH`
- **WHEN** the user reads `GET /api/v1/clis/uv`
- **THEN** it is `missing`, `needed_by` names `data-profiling`, `needed_by_servers` names `duckdb` with launcher `uvx`, and its hand-off prompt names both

### Requirement: Hand a required command to an agent with a prompt
The system MUST NOT install, update or log in to a required command itself.
For a command that is `missing` or `outdated` it MUST offer a prompt, built by
the daemon, for the user to give their agent, which names the command (and its
title), every skill that needs it with the minimum version each asks for, every
MCP server started with it and the launcher it is started with, what was found
for an outdated one, and this machine's operating system and CPU
architecture; asks the agent to choose the install method that suits this
machine, to check with the user before running anything that needs `sudo` or
changes system settings, and to confirm with `<command> --version` when it is
done; and says that any login is left to the user, whose credentials the agent
does not handle. For a command that is `logged_out` the prompt MUST ask only
for help logging in: it names the login check that failed and the declared
login command, asks the agent to tell the user what to run, and leaves running
it and entering credentials to the user. A prompt MUST NOT name an install
command. A `ready` command MUST carry no prompt. The prompt MUST be served as
`handoff.prompt` on every response that carries the command, and the same text by `coffer cli prompt <command>`.

#### Scenario: a missing command carries an install prompt for an agent
- **GIVEN** skills `issues` (minimum `2.40`) and `triage` requiring `gh` (titled GitHub CLI), and no `gh` on the agent's `PATH`
- **WHEN** the user reads `GET /api/v1/clis/gh`
- **THEN** its `handoff.prompt` asks to install `gh` (GitHub CLI), names `issues (version 2.40 or newer)` and `triage`, names the machine's OS and architecture, asks the agent to choose the install method, to check before anything that needs `sudo` or changes system settings, and to run `gh --version`, and leaves any login to the user
- **AND** the list carries the same prompt, and there is no route that installs

#### Scenario: a command that is not logged in carries a prompt that asks only for help logging in
- **GIVEN** `gh` installed with login check `gh auth status` failing and login command `gh auth login`
- **WHEN** the user reads its prompt
- **THEN** the prompt asks for help logging in, names the failing check and `gh auth login`, says the user runs the login and enters anything it asks for, and asks for no install

#### Scenario: a ready command carries no prompt
- **GIVEN** a required command that is present, current and needs no login
- **WHEN** the user reads it
- **THEN** its `handoff` is null
