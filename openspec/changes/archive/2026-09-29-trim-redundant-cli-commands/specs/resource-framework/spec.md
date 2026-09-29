## MODIFIED Requirements

### Requirement: Address every resource by an immutable uid through one kind-agnostic surface
The system MUST model every managed thing as a *resource* identified by an immutable,
opaque **`uid`** ([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)),
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
on every resource"); a kind that cannot be disabled offers no `enable` or `disable`. `show` MUST resolve either a name or a uid. `edit` MUST take `--title` and
`--description` on every kind, plus the kind's own flags. Every `list` and `show` MUST support
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
- **THEN** each offers `list`, `show`, `edit` and `rm`, offers `enable` and `disable` only where the kind can be disabled, offers `add` only where the kind can be created from that group, and offers `scope` only where the kind supports reach
- **AND** `coffer <kind> disable <name>` and `coffer <kind> disable <uid>` disable the same resource through the kind-agnostic route, and the change is audited

#### Scenario: a non-toggleable kind refuses to be disabled
- **GIVEN** a `knowledge` collection and a `memory` partition
- **WHEN** each is disabled through `/api/v1/resources` and read back
- **THEN** both requests are refused with 409 `RESOURCE_NOT_TOGGLEABLE`
- **AND** both still read back enabled, with `toggleable` false, and neither `coffer knowledge` nor `coffer memory` offers `enable` or `disable`

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
- **THEN** it is refused as a conflict with the code `GENERIC_CREATE_NOT_ALLOWED`, and no resource row and no audit entry is written,
- **AND** that kind's command group offers `add` only if the kind supplies its own, and the memory group offers no `add` at all.

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
- **THEN** it is **exactly** the reviewed table of every group the composition root registers and every subcommand under each — `daemon`, `open`, `config`, `log`, `path`, `scan`, `adopt`, `discard`, `mcp`, `credentials`, `agent`, `channel`, `skill`, `knowledge`, `memory`, `provider`, `sync`, with their nested groups — asserted in both directions, so a UI operation cannot ship a CLI counterpart without a reviewer seeing it here and a CLI command cannot appear without someone deciding it belongs,
- **AND** every `coffer config` key is paired in the table with the settings route that stores it, or with the pre-bind settings file for a key read before the daemon binds, so a settings route with no key fails the test,
- **AND** the groups whose surface is options rather than subcommands are claimed by those options instead, since an empty subcommand set would assert nothing about them,
- **AND** every group's `--help` renders, so an import-time error in one command module cannot wait for a user to reach for it,
- **AND** machine-readable JSON output is available for scripting.

#### Scenario: file-backed reads are answered by coffer path
- **GIVEN** the reviewed parity table
- **WHEN** its list of file-backed REST routes is compared with the management API
- **THEN** it names every route that serves or writes a plain file for the web UI — the knowledge tree, file read, file write and file delete; the memory partition's file tree, file content, notes, one note and retired notes; the skill master folder's file tree, file read and file write; an agent's config-file list and config-file reads; an agent's native-memory list, file tree and file content — each paired with the `coffer path` target that names the same files
- **AND** a file-backed route missing from that list fails the parity test, as does a listed route the API no longer serves

#### Scenario: command line surfaces same errors
- **GIVEN** any failure surfaced by the management API,
- **WHEN** triggered through the command line,
- **THEN** the user sees an actionable message and a non-zero exit code; `--verbose` shows a full trace.

### Requirement: Scan, adopt and discard what Coffer does not manage
The system MUST list, in one command, everything an agent holds that Coffer could manage but does
not: `coffer scan [--agent <name>] [--json]` prints one table with a `kind` column, and each row
carries the agent it was found in and a `ref` that names it. Which kinds a scan reports, and what
adopting or discarding each one does, belong to the spec that owns that kind.

`coffer adopt <kind> <ref>` MUST bring the one row the ref names under management, and
`coffer discard <kind> <ref>` MUST remove it from the agent, each acting through the owning
kind's REST route. The `ref` MUST be the value the scan printed for that row. A ref that names
no row in a fresh scan MUST be refused with nothing changed. `adopt` and `discard` MUST offer a
command only for a kind that supports that act; a kind whose rows are brought under management
by a command of its own offers neither, and its scan row MUST name that command. Adopting or
discarding MUST be audited by the owning kind.

#### Scenario: a scan row is adopted by its ref
- **GIVEN** an agent holds an item of a kind Coffer can adopt, and Coffer does not manage it
- **WHEN** the user runs `coffer scan --json`, then `coffer adopt <kind> <ref>` with the ref that row printed, then `coffer scan` again
- **THEN** the first scan lists the row with its kind, agent and ref, and the adopt exits successfully and is audited
- **AND** the second scan no longer lists that row

#### Scenario: an unknown or undiscardable row is refused
- **GIVEN** a scan that lists a detected agent which is not registered, and names `coffer agent add <type>` on that row
- **WHEN** the user runs `coffer discard agent <ref>` for that row, and `coffer adopt skill no-such-ref`
- **THEN** both exit non-zero, the first because `discard` offers no `agent` command and the second saying the ref names no row
- **AND** nothing on disk or in the vault changed
