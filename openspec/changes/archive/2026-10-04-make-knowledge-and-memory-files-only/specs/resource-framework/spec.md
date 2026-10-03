## MODIFIED Requirements

### Requirement: Address every resource by an immutable uid through one kind-agnostic surface
The system MUST model every managed thing as a *resource* identified by an immutable,
opaque **`uid`** ([A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](../../../docs/decisions/identity-is-the-uid-inside-the-file.md)),
and MUST expose one kind-agnostic REST surface, `/api/v1/resources*`, to list, read, update,
enable, disable and delete any of them without the caller knowing the kind. Every route and
every stored reference from one resource to another MUST address the uid. A uid MUST be minted
once and never reused, and MUST be the same value on every machine that holds the resource, so
that two machines can tell "the same thing" from "a different thing with the same name" without
asking each other.

On the command line, every kind's group MUST offer the same lifecycle verbs, generated from the
kind registry and served by the kind-agnostic routes: `list`, `show`, `edit`, `rm`,
`enable`, `disable` and `scope`. `add` is not one of them: a group offers `add` only when its
kind supplies one of its own (see "Keep creation a per-kind seam"). A verb the kind does not support MUST be absent from its group
rather than refused when run (see "Keep creation a per-kind seam" and "Carry a per-agent reach
on every resource"); a kind that cannot be disabled offers no `enable` or `disable`, and a kind
with nothing on its record a person may edit — `skill`, whose name is fixed and whose description
is its SKILL.md's — offers no `edit`. `show` MUST resolve either a name or a uid. `edit` MUST take
`--description`, and `--title` on a kind that carries one ("Carry an optional editable title on
the kinds that have one"), plus the kind's own flags. Every `list` and `show` MUST support
`--json`. A group MAY add commands that are unique to its kind, and MUST NOT add a second
spelling of a lifecycle verb.

A kind MAY declare that its resources cannot be disabled — `knowledge` and `memory` do.
Every resource of such a kind MUST be enabled, and enabling or disabling one through the
kind-agnostic surface MUST be refused with `RESOURCE_NOT_TOGGLEABLE` (409), changing
nothing. The resource read carries the kind's answer as `toggleable`, so a surface can
leave the switch out rather than offer one that is refused.

A kind exists only because the composition root registered it; a request naming an
unregistered kind MUST be refused rather than bringing one into being.

#### Scenario: the kind-agnostic surface serves every kind
- **GIVEN** resources of more than one registered kind exist,
- **WHEN** the user lists resources without naming a kind, reads one back by its uid, then disables and re-enables it,
- **THEN** every kind's resources appear in the one list, each carrying its uid, kind, name, title, config, reach and enabled flag,
- **AND** the enable/disable round trip is served by the same route for every kind, and each step is audited.

#### Scenario: every kind's group offers the same lifecycle verbs
- **GIVEN** the CLI's command tree
- **WHEN** each registered kind's group is read
- **THEN** each offers `list`, `show` and `rm`, offers `edit` only where the kind has something to edit and `--title` only where it carries a title, offers `enable` and `disable` only where the kind can be disabled, offers `add` only where the kind can be created from that group, and offers `scope` only where the kind supports reach
- **AND** `coffer <kind> disable <name>` and `coffer <kind> disable <uid>` disable the same resource through the kind-agnostic route, and the change is audited

#### Scenario: a non-toggleable kind refuses to be disabled
- **GIVEN** a `knowledge` collection and a `memory` partition
- **WHEN** each is disabled through `/api/v1/resources` and read back
- **THEN** both requests are refused with 409 `RESOURCE_NOT_TOGGLEABLE`
- **AND** both still read back enabled, with `toggleable` false

### Requirement: Keep creation a per-kind seam
Creation is a per-kind seam and MUST stay one. The kind-agnostic create route MUST
accept only kinds that declare themselves creatable through it, and MUST refuse a kind
that owns a creation invariant beyond config validation — a skill's master folder, an
agent's on-disk detection — so that such a kind is registered through its own surface,
which can hold that invariant. On the command line a kind's group MUST offer `add` only when
the kind supplies an `add` of its own that holds its invariant. A kind that is created only by the system, such as a memory
partition, MUST offer no `add`. There is no kind-agnostic create command, because a generic
create would have to guess a config shape it cannot know. What this spec owns is everything that
happens to a resource once a kind has made one.

#### Scenario: refuse a generic create for a kind that owns its creation
- **GIVEN** a registered kind that declares it is not creatable through the kind-agnostic surface,
- **WHEN** a registration for that kind arrives on the kind-agnostic create route,
- **THEN** it is refused as a conflict with the code `GENERIC_CREATE_NOT_ALLOWED`, and no resource file and no audit entry is written,
- **AND** that kind's command group offers `add` only if the kind supplies its own.

### Requirement: Reach every management operation from both REST and the CLI
Users MUST be able to perform every mutation, and every read of state that is not a plain file,
through both (a) a REST API and (b) a `coffer` command-line interface, sharing the same
underlying daemon and a consistent error model. For a plain file that its owning spec declares
directly readable or editable, the CLI MUST satisfy parity by naming the file with `coffer path`
(see "Locate file-backed state with coffer path"), while the REST route that serves the file to
the web UI stays, because a browser page cannot read the disk. A setting changed through
`coffer config` counts as the CLI counterpart of the route that stores it (see "Change every
setting through one key-value command"). The reviewed CLI command tree
and the management API MUST stay in step in both directions, so neither can gain an operation
the other lacks without the parity test failing, and every REST route answered by `coffer path`
MUST be listed by name in the reviewed table, so that a REST read with no CLI command is a
reviewed decision rather than a gap. The rule is policy over every spec and is stated as such in
[`.agents/openspec.md`](../../../.agents/openspec.md); this requirement is where it becomes
testable, because the assertion runs over the entire command tree across every spec and
so has no narrower home. A spec that cannot honour it records the gap in its own
`## Purpose` rather than leaving the omission to be discovered.

#### Scenario: command line covers every visual operation
- **GIVEN** the daemon is running,
- **WHEN** the CLI's live command tree is read,
- **THEN** it is **exactly** the reviewed table of every group the composition root registers and every subcommand under each — `daemon`, `open`, `config`, `log`, `path`, `scan`, `adopt`, `discard`, `mcp`, `secrets`, `agent`, `channel`, `skill`, `provider`, `sync`, with their nested groups — asserted in both directions, so a UI operation cannot ship a CLI counterpart without a reviewer seeing it here and a CLI command cannot appear without someone deciding it belongs,
- **AND** every `coffer config` key is paired in the table with the settings route that stores it, or with the pre-bind settings file for a key read before the daemon binds, so a settings route with no key fails the test,
- **AND** the groups whose surface is options rather than subcommands are claimed by those options instead, since an empty subcommand set would assert nothing about them,
- **AND** every group's `--help` renders, so an import-time error in one command module cannot wait for a user to reach for it,
- **AND** machine-readable JSON output is available for scripting.

#### Scenario: file-backed reads are answered by coffer path
- **GIVEN** the reviewed parity table
- **WHEN** its list of file-backed REST routes is compared with the management API
- **THEN** it names every route that serves or writes a plain file for the web UI — the skill master folder's file tree, file read and file write; an agent's config-file list and config-file reads; an agent's native-memory list, file tree and file content — each paired with the `coffer path` target that names the same files
- **AND** a file-backed route missing from that list fails the parity test, as does a listed route the API no longer serves

#### Scenario: command line surfaces same errors
- **GIVEN** any failure surfaced by the management API,
- **WHEN** triggered through the command line,
- **THEN** the user sees an actionable message and a non-zero exit code; `--verbose` shows a full trace.

### Requirement: Locate file-backed state with coffer path
The system MUST print the absolute path of every piece of state that its owning spec declares
directly readable or editable as plain files, with `coffer path`, so that a person or an agent
reads and edits those files with their own tools. The targets MUST be `skill <name>`, `agent <name> config|memory|transcripts`,
`logs` and `vault`. With no target it MUST print every root it knows. With `--json` it MUST print
the paths as one JSON object keyed by what each path is. The paths MUST be composed from reads
the daemon already serves. The command MUST create nothing and change nothing, and a name that
resolves to no resource MUST exit non-zero with a not-found message.

#### Scenario: the command line names the files behind a resource
- **GIVEN** a skill is registered
- **WHEN** the user runs `coffer path skill <name>`, `coffer path skill <name> --json`, and `coffer path skill no-such-skill`
- **THEN** the first prints the absolute path of the skill's master folder and the second prints a JSON object holding it, both of which exist on disk
- **AND** the third exits non-zero with a not-found message, and nothing on disk was created or changed

### Requirement: Correlate the audit log, the MCP invocation log and the daemon log by one trace id
Every record the daemon writes for a unit of work — an HTTP request, or a chat
or channel turn — MUST carry that unit's correlation id, `trace_id`, so its
audit rows, its MCP invocations and its daemon log lines can be read as one
story rather than lined up by time. An HTTP request's id is its
`X-Coffer-Trace` (the client's, sanitised, or one the daemon mints; spec
[daemon](../daemon/spec.md) "Answer the status probe without a token" is
answered with one like every other route). A turn carries a `conversation_id`
and a fresh `turn_id` of its own, and keeps the trace id of the request that
started it; a turn no request started — a channel message that arrived over a
websocket or a long poll — uses its turn id as its trace id. The ids MUST
follow the work into the tasks it starts, so a turn's renderer and a request's
background write carry them too.

- An audit row MUST store `trace_id`, and `conversation_id` and `turn_id` when a
  turn wrote it; a row written with nothing bound (a boot pass, a periodic
  worker) stores none, and no id is invented for a row written before the
  columns existed.
- An MCP invocation MUST store the `/mcp` request's `trace_id` beside its
  session id, and the audit rows the call causes carry the same `trace_id`.
- Every daemon log line MUST carry `trace_id` (`-` when none is bound), and
  `session_id`, `conversation_id` and `turn_id` when it was written inside an
  MCP call or a turn.

`GET /api/v1/audit`, `GET /api/v1/mcp/invocations` (and one server's
invocations) and `GET /api/v1/daemon/logs` MUST each take a `trace_id` filter,
and `coffer log audit`, `coffer log mcp` and `coffer log daemon` MUST take it
as `--trace`, the audit and MCP tables showing each row's trace id. The
Activity page's record drawer MUST show a change's and a call's trace id when
the record has one.

#### Scenario: a request's audit rows carry its trace id
- **GIVEN** a request sent with `X-Coffer-Trace: req-a1` that creates a resource
- **WHEN** the audit log is read with `trace_id=req-a1`
- **THEN** it returns that request's `resource_created` row, carrying `trace_id: "req-a1"`, and no row another request wrote
- **AND** the daemon log read with `trace_id=req-a1` returns the lines that request wrote

#### Scenario: an MCP call's records carry its session and trace id
- **GIVEN** an MCP session that calls `coffer__search_tools` on a `/mcp` request sent with `X-Coffer-Trace: mcp-call-7`
- **WHEN** the invocation log, the audit log and the daemon log are each read with `trace_id=mcp-call-7`
- **THEN** the invocation carries the session id and `mcp-call-7`, and the log lines carry both the trace id and the session id
- **AND** an audit row a call writes, when it writes one, carries the call's trace id

#### Scenario: a turn's records carry its conversation and turn
- **GIVEN** a chat turn that records an audit event while it runs, with no HTTP request behind it
- **WHEN** the row and the turn's log lines are read back
- **THEN** each carries the conversation's id and the turn's own id, and the trace id is the turn id
- **AND** a second turn of the same conversation carries a different turn id, and a turn a request started keeps that request's trace id

#### Scenario: the command line filters each log by trace id
- **GIVEN** a request sent with trace id `cli-trace-3` that created a resource, and an MCP call made with the same trace id
- **WHEN** the user runs `coffer log audit --trace cli-trace-3`, `coffer log mcp --trace cli-trace-3 --json` and `coffer log daemon --trace cli-trace-3 --json`
- **THEN** each prints only the records carrying `cli-trace-3`, the audit table showing the id on each row

#### Scenario: the Activity drawer shows a record's trace id
- **GIVEN** an audit row and an MCP call that each carry a trace id
- **WHEN** the user opens each in the Activity page's drawer
- **THEN** the drawer shows a "Trace id" fact with that id
- **AND** a record with no trace id shows no such fact
