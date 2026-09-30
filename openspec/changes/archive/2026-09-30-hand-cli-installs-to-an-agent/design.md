# Design — hand CLI installs to an agent

## Decisions

### 1. One hand-off builder, fed facts by each feature

`domain/handoff.py` holds a `Handoff(task, facts, steps)` and
`render_handoff()`, which writes the task sentence, the facts as `-` lines and
the steps one per line, then appends the rules every hand-off carries: check
with the person before anything that needs `sudo` or changes system settings,
and leave any login to the person without handling credentials. A feature
supplies only what it knows; the rules and the shape are the same wherever a
prompt comes from. It is pure domain code, so any kind can use it.

The CLI facts come from `application/skill/cli_handoff.py`:

| Status | Task | Facts | Steps |
| --- | --- | --- | --- |
| `missing` | install `<command>` (title) | skills with minimums; machine | choose the install method for this machine; run `<command> --version` |
| `outdated` | update `<command>` | installed version and path against the minimum; skills; machine | update it the way it was installed, or choose the right method; run `<command> --version` |
| `logged_out` | help me log in to `<command>` | installed path and the login check that failed; the declared login command; skills; machine | tell me what to run, I run it and enter what it asks; run the login check to confirm |
| `ready` | — | — | — |

The machine is `infrastructure/platform/host.machine_label()` — `macOS 15.6,
arm64`, a Linux distribution's `PRETTY_NAME`, or `Windows <release>` — read
once per daemon, since `check_platform_calls.py` keeps OS questions inside the
platform package.

*Rejected:* building the prompt in the web UI. The command line would then
hand over different words, and a second feature would copy the template.

### 2. On the existing responses, not a new route

`CliOut` gains `handoff: HandoffOut | null` (`HandoffOut = {prompt}`), null for
a ready command, on every route that returns a command — the list, one
command and both checks — so the page and the Requires tab read it with the
data they already fetch. `HandoffOut` is one shared schema any later response
can carry. The command line prints it with `coffer cli prompt <command>`
(`--json` for scripts), plain text so it pipes into a clipboard; `coffer cli
show` names that command when a prompt exists. *Rejected:* a
`GET /clis/{command}/prompt` route, which would be a second read of state the
detail response already carries.

The surfaces requirement is replaced rather than modified — "Cover required
commands on REST, the command line and the web" becomes "Serve required
commands on REST, the command line and the web" — because a MODIFIED block
cannot drop its install scenario; the code comments citing it follow.

### 3. Remove the installer outright

`HomebrewInstaller`, `InstallJob`, `InstallerPort`, both install routes, the
install schemas, `coffer cli install`, the audit events
`cli_install_started`/`cli_install_finished` and the codes
`CLI_FORMULA_MISMATCH`, `CLI_INSTALL_NOT_FOUND`, `CLI_INSTALL_RUNNING`,
`CLI_NOT_INSTALLABLE` and `HOMEBREW_NOT_FOUND` go, with no compatibility
path: the installer shipped only on the integration branch. The `brew:` key of
a `requires:` entry is no longer read; a skill that still has one gets the
ordinary "unknown field ignored" warning and keeps its entry.
`scripts/check_removed_commands.py` lists `coffer cli install` with
`coffer cli prompt` as its replacement.

### 4. The web block: Copy prompt and Ask an agent

`components/handoff/AgentHandoff.tsx` takes the prompt text and offers
**Copy prompt** and **Ask an agent**. Ask an agent reuses the New conversation
dialog and its agent picker, then opens the draft `/conversations/new` with
the prompt in the composer. The prompt travels in the router's location state,
never the URL; `useChatController` reads it once on the draft route and
replaces the history entry, so a reload does not apply it again. Nothing is
sent until the person presses Send: a Coffer-managed agent runs with full
permissions, and the person should read what it is asked to do. With no
managed agent available only Copy prompt is shown.

The CLI detail page puts the block in its problem banner; the CLIs list offers
Copy prompt as the row action; a skill's Requires tab offers the block on each
command that needs the person. The Overview attention item is unchanged and
still opens the command's page.
