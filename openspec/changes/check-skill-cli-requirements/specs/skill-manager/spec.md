## ADDED Requirements

### Requirement: Declare the commands a skill requires
A skill MAY declare in its SKILL.md frontmatter, under `requires:`, the
command-line tools it drives. Each entry MUST name a `command` (a bare name,
no path) and MAY give a display `title`, a `min_version`, a `login_check` — the
command's own subcommand that exits 0 when the user is logged in, such as
`gh auth status` — a `login` command to show the user, a Homebrew formula
(`brew`) and a `why` line; a bare string is a command with no conditions. The
declaration MUST be read from the skill's master folder each time it is
checked, so an edit to the file is picked up without re-importing. An entry
that is not understood — no command, a command with a path, a login check that
runs another program — MUST be skipped and reported as a warning without
failing the skill.

#### Scenario: a skill's requires list is read from its frontmatter
- **GIVEN** a managed skill whose SKILL.md declares `gh` with minimum `2.40`, login check `gh auth status`, login `gh auth login` and formula `gh`, and a bare `jq`
- **WHEN** the required commands are read
- **THEN** both commands are listed as needed by that skill, `gh` with its minimum, login check, login command and formula

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
user asks to check again, an install finishes, or the daemon restarts.

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

### Requirement: Install a required command only through Homebrew and only when asked
For a command that is `missing` or `outdated` and declares a Homebrew formula,
the system MUST offer one install: `brew install <formula>` (or `brew upgrade
<formula>` for an outdated one), run as the user, never with `sudo`, without a
shell, only when the request names that exact formula, and only while Homebrew
is on the agent's `PATH`. Its output MUST be streamed to the caller while it
runs, the start and the end MUST be audited with the command run, the exit
code and the last lines of output, and the command MUST be checked again when
the install ends. The system MUST NOT install through anything but Homebrew,
and MUST NOT run a login command.

#### Scenario: installing runs the confirmed Homebrew command and keeps its output
- **GIVEN** a missing command `jq` with formula `jq` and a Homebrew on the agent's path
- **WHEN** an install is requested naming formula `jq`
- **THEN** the daemon runs `brew install jq` with no `sudo`, its output is served while it runs, and the audit log records the start and the end with the exit code
- **AND** `jq` is checked again when the install ends

#### Scenario: an install naming another formula is refused
- **GIVEN** a missing command `jq` with formula `jq`
- **WHEN** an install is requested naming formula `wget`, or for a command with no formula, or while Homebrew is not found
- **THEN** the request is refused and nothing runs

### Requirement: Cover required commands on REST, the command line and the web
The required commands MUST be readable and checkable through
`GET /api/v1/clis`, `GET /api/v1/clis/{command}`, `POST /api/v1/clis/check`
and `POST /api/v1/clis/{command}/check`, installable through `POST` and
followable through `GET /api/v1/clis/{command}/install`, and reachable from
`coffer cli list|show|check|install` (`--json` on every read; `install` prints
the Homebrew command and asks before running it unless given `--yes`). Lists
MUST put problems first: missing, then outdated, then not logged in, then
ready. The web UI's CLIs page shows them (spec web-ui "Show every CLI a skill
requires on the CLIs page") and a skill's detail page carries a **Requires**
tab listing what the skill declares, each linked to its command's page.

#### Scenario: the command line lists required commands problems first
- **GIVEN** skills requiring a missing `jq`, an outdated `gh` and a ready `uv`
- **WHEN** the user runs `coffer cli list --json`
- **THEN** the commands come back in the order `jq`, `gh`, `uv`, each with its status and the skills that need it

#### Scenario: the command line asks before it installs
- **GIVEN** a missing command with a Homebrew formula
- **WHEN** the user runs `coffer cli install <command>` and declines the prompt that names `brew install <formula>`
- **THEN** nothing runs, and with `--yes` the install runs and its output is printed
