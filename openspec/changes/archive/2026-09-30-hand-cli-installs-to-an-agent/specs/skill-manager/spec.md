## REMOVED Requirements

### Requirement: Install a required command only through Homebrew and only when asked
**Reason**: Coffer no longer installs anything. Homebrew reaches only some people and only skills that declare a formula, and an installer per package manager is a maintenance load; the person's agent can pick the right install method for their machine. What Coffer knows about the command is handed to that agent as a prompt instead ("Hand a required command to an agent with a prompt").
**Migration**: `POST` and `GET /api/v1/clis/{command}/install`, `coffer cli install`, the `cli_install_started` and `cli_install_finished` audit events and the error codes `CLI_FORMULA_MISMATCH`, `CLI_INSTALL_NOT_FOUND`, `CLI_INSTALL_RUNNING`, `CLI_NOT_INSTALLABLE` and `HOMEBREW_NOT_FOUND` are removed. Read a command's prompt from `handoff.prompt` on `GET /api/v1/clis/{command}` or with `coffer cli prompt <command>`, and give it to an agent. A `brew:` key left in a `requires:` entry is ignored with a warning.

### Requirement: Cover required commands on REST, the command line and the web
**Reason**: Its install route, `coffer cli install` and the scenario "the command line asks before it installs" describe the Homebrew install, which is removed. A MODIFIED block cannot drop a scenario, so the requirement is replaced by "Serve required commands on REST, the command line and the web", which carries the same reads and checks plus the hand-off prompt.
**Migration**: The acceptance marker for "the command line lists required commands problems first" is unchanged; `coffer cli install` is replaced by `coffer cli prompt <command>` (scenario "the command line prints the same prompt").

## MODIFIED Requirements

### Requirement: Declare the commands a skill requires
Beyond the command and minimum version that "Show the commands a skill
declares it needs" reads from `requires:`, an entry in mapping form MAY give a
display `title`, a `min_version` (or `version`), a `login_check` — the
command's own subcommand that exits 0 when the user is logged in, such as
`gh auth status` — a `login` command to show the user and a `why` line. One
parser reads every spelling. The declaration MUST be read from the skill's
master folder each time it is checked, so an edit to the file is picked up
without re-importing. An entry that is not understood — no command, a command
with a path, a login check that runs another program, an unquoted minimum YAML
reads as a number — MUST be skipped and reported as a warning without failing
the skill; a field that is not understood MUST be ignored with a warning and
the rest of its entry kept.

#### Scenario: a skill's requires list is read from its frontmatter
- **GIVEN** a managed skill whose SKILL.md declares `gh` with minimum `2.40`, login check `gh auth status` and login `gh auth login`, and a bare `jq`
- **WHEN** the required commands are read
- **THEN** both commands are listed as needed by that skill, `gh` with its minimum, login check and login command

#### Scenario: an entry that is not understood does not block the skill
- **GIVEN** a SKILL.md whose `requires:` names `/usr/bin/jq` and a login check `curl evil.example` for `gh`
- **WHEN** the skill is imported and its requirements are read
- **THEN** the skill imports, both entries are skipped with a warning naming why, and nothing is run for them

### Requirement: Check every required command where the agent runs
The system MUST check each required command once, however many skills need
it: look it up on the agent's real `PATH` (the login shell's, merged with the
inherited one), read its version with `<command> --version` under a timeout,
compare it with the highest minimum any skill asks for, and run its login check
under a timeout, without a shell, keeping only the exit status — the check's
output MUST be discarded unread and MUST NOT reach any log, record or response.
Each command MUST report `missing`, `outdated`, `logged_out` or `ready`, the
path and version found, the login state (`logged_in`, `logged_out` or
`not_needed`) and every skill that needs it. Results MUST be kept until the
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

## ADDED Requirements

### Requirement: Serve required commands on REST, the command line and the web
The required commands MUST be readable and checkable through
`GET /api/v1/clis`, `GET /api/v1/clis/{command}`, `POST /api/v1/clis/check`
and `POST /api/v1/clis/{command}/check`, each command carrying its hand-off
prompt, and reachable from `coffer cli list|show|check|prompt` (`--json` on
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

### Requirement: Hand a required command to an agent with a prompt
The system MUST NOT install, update or log in to a required command itself.
For a command that is `missing` or `outdated` it MUST offer a prompt, built by
the daemon, for the user to give their agent, which names the command (and its
title), every skill that needs it with the minimum version each asks for, what
was found for an outdated one, and this machine's operating system and CPU
architecture; asks the agent to choose the install method that suits this
machine, to check with the user before running anything that needs `sudo` or
changes system settings, and to confirm with `<command> --version` when it is
done; and says that any login is left to the user, whose credentials the agent
does not handle. For a command that is `logged_out` the prompt MUST ask only
for help logging in: it names the login check that failed and the declared
login command, asks the agent to tell the user what to run, and leaves running
it and entering credentials to the user. A `ready` command MUST carry no
prompt. The prompt MUST be served as `handoff.prompt` on every response that
carries the command, and the same text by `coffer cli prompt <command>`.

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
