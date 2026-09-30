# Check the command-line tools skills require

## Why

A skill often drives a command-line tool — `gh`, `jq`, `aws` — and fails at
the step that calls it when the tool is missing, too old or not logged in.
Nothing tells the user before an agent trips over it, and one missing tool
breaks every skill that needs it. The web UI's CLIs page (change
`revise-web-ui-ia`, spec web-ui "Show every CLI a skill requires on the CLIs
page") fixes where this is shown; this change adds what the page shows: what a
skill declares, how Coffer checks it, and the one install path it offers.

## What Changes

- **A skill declares what it needs.** SKILL.md frontmatter gains `requires:` —
  a list of commands, each with an optional display title, minimum version,
  login check (a subcommand of the same command, e.g. `gh auth status`), login
  command to show, Homebrew formula and a line on why the skill needs it. A
  bare command name is shorthand for a command with no conditions.
- **Coffer checks each command where the agent runs.** The command is looked
  up on the agent's real `PATH` (the login shell's, merged with the inherited
  one — the same lookup agent detection uses), its version read from
  `<command> --version` under a timeout and compared with the highest minimum
  any skill asks for, and its login check run under a timeout with its output
  discarded. One result per command, however many skills need it.
- **Install through Homebrew only, only when asked.** For a missing or
  outdated command with a declared formula, the daemon runs
  `brew install <formula>` (or `brew upgrade <formula>`) as the user, never
  with `sudo`, only after the person confirmed that exact command; the output
  is streamed to the page and recorded in the audit log. Logging in is never
  done for the user: the login command is shown to copy.
- **Surfaces.** REST `/api/v1/clis…`, CLI `coffer cli list|show|check|install`,
  an attention item per command that is missing, outdated or not logged in, a
  CLIs page with a detail page per command, and a Requires tab on the skill
  page linking each requirement to its command.

Capabilities whose requirements change: `skill-manager` (the declaration, the
check, the install, the surfaces), `resource-framework` (the attention list
names the new source).
