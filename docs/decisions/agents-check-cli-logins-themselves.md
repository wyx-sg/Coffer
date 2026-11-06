# Agents Check CLI Versions and Logins Themselves; Coffer Only Looks Commands Up

**Status**: Accepted
**Date**: 2026-11-06
**Deciders**: Yuxing Wu
**Related**: spec skill-manager "Check every required command where the agent runs", "Declare the commands a skill requires", "Hand a required command to an agent with a prompt"; spec mcp-gateway (a server's launcher); [Principles](../../docs-site/architecture/principles.md)

## Context

A skill can declare the command-line tools it runs (`requires:`). Until this
decision Coffer did three things per command:

1. looked it up on the agent's `PATH`;
2. ran `<command> --version`, parsed a version out of the output and compared it
   with the highest `min_version` any skill asked for (`outdated` when below);
3. ran a per-command **login check**: a skill or a hand-added tool could name a
   subcommand such as `gh auth status`, Coffer ran it under a 10-second timeout
   with its output discarded, and a non-zero exit made the command `logged_out`.

Steps 2 and 3 each raised an Overview attention item and a hand-off prompt
(update the tool, or help the person log in).

The 2026-11-06 review of command-line tool management found:

- **D1.** A login check that timed out or could not start was recorded as
  `logged_out`. A network-bound check (`aws sts get-caller-identity`) on a slow
  network told the person to log in again when they had not been logged out.
- **D2.** Probe results live in memory. After a daemon restart the login state
  was unknown until someone pressed Check, and unknown read as ready, so the
  Overview item vanished on every restart.
- **D3.** Not every tool prints a version Coffer can parse from `--version`
  (`go version`, `kubectl version --client`, tools that print a banner or
  nothing). For those the minimum could never be compared, and the review's
  first fix was a `version_unverifiable` flag plus a "can't compare" note — more
  surface to say the check does not work for that tool. The next proposal was a
  per-tool `version_command`, more surface again.

The owner's standing principle, set in the same review: Coffer should be as lean
as possible, and anything an agent can do itself Coffer does not do. Asked why
Coffer reads versions at all, the owner chose to remove the version check too.

How comparable products handle it:

- **OpenClaw**, the closest product to Coffer's skill requirements, declares
  `bins` / `anyBins` / `env` and hides a skill whose binary is missing. It checks
  presence only: no version and no login.
- **Claude Code and Codex** have no declaration of required commands at all. An
  agent that runs `gh` and gets "not logged in" or "unknown flag" back reads that
  error and runs `gh auth status` or `gh --version` itself.
- **Homebrew's `brew bundle check`** checks that each Brewfile entry is
  installed; it does not compare versions unless the entry pins one.
- **mise / asdf** do manage versions, but they are version managers that also
  install the tool. Coffer installs nothing, so it has none of the machinery that
  makes a version requirement actionable.

## Options Considered

### Option A — Keep version and login checks as they were

- ✅ The CLIs page and Overview can say "too old" or "not logged in" before an
  agent hits it.
- ❌ D1, D2 and D3 stay: false "log in again" prompts on slow networks, an item
  that disappears on every restart, and minimums that silently cannot be checked.
- ❌ Coffer runs programs per command with the person's credentials in reach, and
  has to police that the login check is the same command and that its output is
  never read.
- ❌ The agent learns the same things for free the moment it runs the command.

### Option B — Keep both and fix the defects

Add an "unconfirmed" login state and persist results; keep `version_unverifiable`
and add a per-tool `version_command` for tools whose `--version` does not parse.

- ✅ Fixes the defects while keeping the early warnings.
- ❌ More states on the wire, in the UI and in the hand-off; a machine-local
  results file; a new field every skill author has to learn.
- ❌ Still point-in-time: a login expires a minute after the check, and a tool
  can be updated or downgraded behind Coffer's back, so the agent has to handle
  the error anyway.

### Option C — Remove login checks, keep the version check

- ✅ D1 and D2 go; Coffer runs only `--version`.
- ❌ D3 stays and needs the unverifiable flag or a version command.
- ❌ It keeps the half of the feature the agent can do just as well, against the
  lean principle.

### Option D — Coffer only looks commands up; agents check versions and logins (chosen)

Drop `login_check`, `login`, `logged_out`, `min_version` (and `version`,
`gh>=2.40`), `outdated`, `version_unverifiable` and the `--version` probe,
including the version an MCP server's launcher reported. Coffer looks each
command up on the agent's `PATH` and reports `missing` or `ready`, and runs none
of them. A skill written for an older Coffer that still declares any of these
fields is accepted without a warning and the fields are never read
(`gh>=2.40` reads as `gh`), so no skill breaks. The `coffer-guide` skill tells
agents to check install, version and login themselves, and the hand-off prompt
for a missing command still says any login is left to the person.

- ✅ D1, D2 and D3 disappear with the feature instead of needing fixes.
- ✅ Coffer runs nothing it checks, which removes a whole class of argument from
  the security model.
- ✅ Matches OpenClaw and Brewfile, and the owner's lean principle.
- ⚠️ The CLIs page no longer warns about a tool that is too old or logged out
  before an agent uses it. The agent finds out when it runs the command, which
  is when it matters, and reports it in its own words.

## Decision

Option D. Coffer checks whether each required command is on the agent's `PATH`;
whether it is new enough or logged in is the agent's to find out when it uses it.
Coffer's own `git` requirement (the vault's minimum git version, checked at
startup) is a separate check of a tool Coffer itself runs and is not affected.

## Consequences

- `CliOut.status` is `missing` or `ready`; `CliOut.version`, `min_version`,
  `version_unverifiable` and `login`, `CliNeededByOut.min_version`,
  `SkillRequirementOut.min_version`, `CliPreviewOut.version` and the MCP
  `requires` launcher's `version` are gone, and so are the `cli_outdated` and
  `cli_logged_out` attention reasons. `CliAddIn` / `CliEditIn` no longer take
  `min_version` or `login_check`; an old client that sends them is ignored.
- A `min_version` or `login_check` stored in the vault's `cli-tools` document by
  an older build is ignored on read and dropped the next time that entry is
  written.
- Skills keep working unchanged; their version and login keys are inert.
