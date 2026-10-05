## REMOVED Requirements

### Requirement: Keep the command line to what needs it
**Reason**: The owner decided (2026-10-05) that every management operation a person can do in the web UI or the desktop app has a `coffer` command, so an agent can do it too; the rule that a web UI operation owes no command is withdrawn.
**Migration**: The recorded reasons now cover only commands that stand for no UI operation; every other command is recorded in the CLI's registry with its route, and the coverage test replaces the reasons test.

## ADDED Requirements

### Requirement: Offer every management operation on the command line
Every management operation a person can do on a web UI page or in the desktop
app MUST have a `coffer` command, so an agent can do it as well: creating,
reading, changing and deleting resources, switching them on and off, their
reach, connecting agents, model providers, MCP servers, custom tools, channels,
managed CLIs, skills, knowledge and memory management, secrets and approvals,
activity, sync and settings. A command MUST call the same REST route the page
calls, so the daemon's validation, audit and lifecycle are the same whoever
acts; it MUST NOT reimplement a route or reach the vault's files, `runs.db` or
ciphertext directly. Exempt are only plain file contents a spec declares
directly readable or editable — knowledge documents, memory notes, a skill's
files, an agent's own config and native-memory files — which an agent reads and
edits with its own tools, and acts whose whole meaning is the window a person
sits at (a native folder picker, opening a file in an editor, terminal or
Finder). Registering, binding, reach, delivery and history restore stay
commands even where what they manage is a file. A command that needs a
person's presence (approving, revealing, writing a key backup) MUST hand that
step to the desktop app's own presence check.

Every such command MUST be recorded in one registry in the CLI package with
the UI operation it stands for and the route(s) it calls; the few commands that
stand for no UI operation (a program runs them, they work while the daemon is
down, or a hand-off names them) are recorded with that reason instead. A test
MUST compare the registry with every route the web UI calls and every command
the desktop shell exposes, and fail on a route or shell command with no command
and no recorded exemption; MUST run every declared command against a recording
transport and assert it calls the route it records; and MUST assert every leaf
of the live command tree is either recorded or has a reason, and every group's
`--help` renders. The coverage table — UI operation, route, command, acceptance
test — is generated from the registry into the CLI reference, in English and
Chinese.

Every command MUST share one contract: `--json` prints the daemon's answer on
standard output and a failure as `{"error": {"code", "message", "details"},
"exit_code"}` on standard error; a body is read from `--data '<json>'`,
`--data @file` or `--data -` (standard input), with repeatable `--set
key=value` merged over it; nothing prompts unless standard input is a terminal
and the command asks for a secret; the daemon's error codes pass through
unchanged; and the exit codes are 0 ok, 2 usage, 3 daemon unreachable, 4 not
found, 5 conflict, 6 invalid input, 7 upstream test failed, 8 secret, 9 approval
pending (with the approval ids and the command that approves them), 10 git
needed, 11 presence not confirmed, 12 desktop app unavailable and 13 a wait
ran out. An operation that runs on after its request returns offers a status
command and a way to wait for its result. The rule is policy over every spec
and is stated as such in [`.agents/openspec.md`](../../../.agents/openspec.md);
this requirement is where it becomes testable, because the assertion runs over
the entire command tree across every spec and so has no narrower home.

#### Scenario: the command line covers every web UI and desktop operation
- **GIVEN** the routes the web UI calls through its typed client and the desktop shell's commands
- **WHEN** they are compared with the CLI's registry
- **THEN** every route has a command or a recorded exemption naming a plain file or the window, and every desktop command has a command or a reason
- **AND** an exemption for a route the web UI no longer calls fails the comparison

#### Scenario: a route the web UI calls without a command fails the test
- **GIVEN** a route the web UI starts calling that no command records
- **WHEN** the comparison runs
- **THEN** it fails naming the route

#### Scenario: every command is a UI operation or has a recorded reason
- **GIVEN** the CLI's live command tree
- **WHEN** it is read beside the registry and the recorded reasons
- **THEN** every leaf is either a recorded UI operation or carries `program`, `offline`, `hand-off` or `no-ui` with a one-line why, never both
- **AND** every group's `--help` renders

#### Scenario: each declared command calls the route it records
- **GIVEN** every command declared over one route
- **WHEN** each is run against a transport that records its requests
- **THEN** each sends the method and route it records, with its body from `--data` and `--set`

#### Scenario: a command takes JSON from a file or stdin and fails with a stable code
- **GIVEN** a command that takes a body
- **WHEN** it is run with `--data -` on standard input, with `--data @file`, with JSON that does not parse, and against a daemon answering 404 with `--json`
- **THEN** the first two send the body read, the third exits 6 with the code `CLI_INVALID_INPUT`, and the last exits 4 printing the daemon's error envelope and the exit code as JSON on standard error

#### Scenario: a plain file is read with the reader's own tools
- **GIVEN** a plain file that its owning spec declares directly readable or editable
- **WHEN** a person or an agent needs it
- **THEN** it is read and edited with their own tools at the path the web UI, the spec or the hand-off prompt names, and no command reads or writes its content
- **AND** `coffer path logs` and `coffer path skill-data` still say where the log files and a skill's working files are

#### Scenario: a kept command surfaces the daemon's errors
- **GIVEN** any failure surfaced by the management API,
- **WHEN** it reaches a command that calls the daemon,
- **THEN** the user sees an actionable message and a non-zero exit code; `--verbose` shows a full trace.

