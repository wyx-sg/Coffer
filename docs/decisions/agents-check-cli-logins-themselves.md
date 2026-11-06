# Agents Check CLI Logins Themselves; Coffer Reads Only Presence and Version

**Status**: Accepted
**Date**: 2026-11-06
**Deciders**: Yuxing Wu
**Related**: spec skill-manager "Check every required command where the agent runs", "Declare the commands a skill requires", "Hand a required command to an agent with a prompt"; [Principles](../../docs-site/architecture/principles.md)

## Context

A skill can declare the command-line tools it runs (`requires:`). Coffer looks
each one up on the agent's `PATH`, reads its version, and until this decision
also ran a per-command **login check**: a skill or a hand-added tool could name a
subcommand such as `gh auth status`, Coffer ran it under a 10-second timeout
with its output discarded, and a non-zero exit made the command `logged_out`.
That raised an Overview attention item and a hand-off prompt asking the agent to
help the person log in.

The 2026-11-06 review of command-line tool management found two defects in it:

- **D1.** A check that timed out or could not start returned `None`, which was
  recorded as `logged_out`. A network-bound check (`aws sts get-caller-identity`)
  on a slow network told the person to log in again when they had not been
  logged out.
- **D2.** Probe results live in memory. After a daemon restart the login state
  was unknown until someone pressed Check, and unknown read as ready, so the
  Overview item vanished on every restart.

The owner's standing principle, set in the same review: Coffer should be as lean
as possible, and anything an agent can do itself Coffer does not do.

How comparable products handle it: OpenClaw, the closest product to Coffer's
skill requirements, declares `bins` / `anyBins` / `env` and hides a skill whose
binary is missing, but has no login check. Claude Code and Codex have no
declaration of required commands at all; an agent that runs `gh` and gets "not
logged in" back reads that error and runs `gh auth status` itself. Homebrew's
`brew bundle check` and `mise doctor` check presence and version, never a login.

## Options Considered

### Option A — Keep login checks as they were

- ✅ The CLIs page and Overview can say "not logged in" before an agent hits it.
- ❌ D1 and D2 stay: false "log in again" prompts on slow networks, and an
  attention item that disappears on every restart.
- ❌ Coffer runs a second program per command with the person's credentials in
  reach, and has to police that it is the same command (the `login_check_command`
  refusal) and that its output is never read.
- ❌ The agent learns the same thing for free the moment it runs the command, so
  the check duplicates work the agent already does.

### Option B — Keep login checks and fix D1 and D2

Add an "unconfirmed" state for a check that did not finish, and persist the last
results locally so a restart does not forget them.

- ✅ Fixes both defects while keeping the early warning.
- ❌ More surface for the same duplicated job: a fourth state on the wire, in the
  UI and in the hand-off, and a machine-local results file to keep in step.
- ❌ Still a point-in-time answer: a login can expire a minute after the check,
  so the agent has to handle "not logged in" anyway.

### Option C — Remove login checks; agents check logins themselves (chosen)

Drop `login_check`, `login` and the `logged_out` status. Coffer reads only
whether a command is found and its version. A skill written for an older Coffer
that still declares `login_check` / `login` is accepted without a warning and the
fields are never read, so no skill breaks. The `coffer-guide` skill tells agents
to check install and login themselves (`command -v`, the tool's own status
command), and the hand-off prompt still says any login is left to the person.

- ✅ D1 and D2 disappear with the feature instead of needing fixes.
- ✅ Coffer runs exactly one thing per command (`--version`), which shrinks what
  the security model has to argue for.
- ✅ Matches every comparable product and the owner's lean principle.
- ⚠️ The CLIs page no longer warns about a logged-out tool before an agent uses
  it. The agent finds out when it runs the command, which is when it matters.

## Decision

Option C. Coffer checks whether each required command is found and how new it
is; whether it is logged in is the agent's to find out when it uses it.

## Consequences

- `CliOut.status` is `missing`, `outdated` or `ready`; `CliOut.login` and the
  `cli_logged_out` attention reason are gone, and `CliAddIn` / `CliEditIn` no
  longer take `login_check`.
- A `login_check` stored in the vault's `cli-tools` document by an older build
  is ignored on read and dropped the next time that entry is written.
- Skills keep working unchanged; their `login_check` / `login` keys are inert.
