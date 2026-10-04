## MODIFIED Requirements

### Requirement: Keep the command line to what needs it
A `coffer` command MUST exist only for one of four reasons, and the web UI is where everything
else is managed:

- **program** — a program Coffer installs or writes runs it (the memory hook entry point, an agent's
  key helper);
- **offline** — it must work when the daemon is down or cannot start (the daemon's start, stop,
  restart and status, locating the log files, the daemon's own pre-bind
  settings);
- **hand-off** — a prompt Coffer gives an agent tells it to run the command, because what it reads or
  writes is not a file (running a command with secrets in its environment, naming and storing a
  secret, reading the audit, MCP and daemon logs, testing an MCP server after installing it,
  listing the command-line tools Coffer manages);
- **no-ui** — the web UI cannot do it (listing the hand edits the vault refused).

Each command MUST be recorded with its reason in one place in the CLI package. A test MUST walk the
live command tree and assert that it equals the recorded list in both directions, that every entry
names one of the four reasons, and that every group's `--help` renders. A web UI operation owes no
command line counterpart: the REST routes that serve only the web UI are its interface, and a
mutation or a read of state that is not a file needs no command to be shippable. The rule is policy
over every spec and is stated as such in [`.agents/openspec.md`](../../../.agents/openspec.md); this
requirement is where it becomes testable, because the assertion runs over the entire command tree
across every spec and so has no narrower home.

#### Scenario: the command tree holds only commands the web UI does not replace
- **GIVEN** the CLI's live command tree
- **WHEN** it is read
- **THEN** every command it holds is one a web UI page does not replace: the recorded list names the memory hook, the proxy key helper, the daemon lifecycle verbs, `path logs`, `config`, `run`, `secret list` and `secret set`, `cli list`, the three `log` commands, `mcp test` and `vault problems`, and no group exists for a kind the web UI manages
- **AND** a web UI operation with no command line counterpart ships without a reviewer being asked for one

#### Scenario: every command has a recorded reason
- **GIVEN** the recorded list of commands
- **WHEN** it is read beside the live command tree
- **THEN** every command carries one of `program`, `offline`, `hand-off` or `no-ui` and a one-line why
- **AND** every group's `--help` renders, so an import-time error in one command module cannot wait for a user to reach for it

#### Scenario: a command missing from the list fails the test
- **GIVEN** a command in the live tree that the recorded list does not name, and a recorded entry whose command is gone
- **WHEN** the test compares the tree with the list
- **THEN** it fails in both directions, naming the unrecorded command and the stale entry

#### Scenario: a plain file is read with the reader's own tools
- **GIVEN** a plain file that its owning spec declares directly readable or editable
- **WHEN** a person or an agent needs it
- **THEN** it is read and edited with their own tools at the path the web UI, the spec or the hand-off prompt names, and no command is added for it
- **AND** `coffer path logs` is the one exception, because the log files are what is left to read when the daemon will not start

#### Scenario: a kept command surfaces the daemon's errors
- **GIVEN** any failure surfaced by the management API,
- **WHEN** it reaches a kept command that calls the daemon,
- **THEN** the user sees an actionable message and a non-zero exit code; `--verbose` shows a full trace.
