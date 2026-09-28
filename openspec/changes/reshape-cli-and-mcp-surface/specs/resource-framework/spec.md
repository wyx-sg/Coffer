## ADDED Requirements

### Requirement: Carry an optional editable title on every resource
Every resource MUST carry an optional **`title`**: free text of at most 80 characters that a
person chooses for display, separate from the resource's `name`. The title MUST be editable on
every kind, including a kind whose name is fixed, through the kind-agnostic update
(`PATCH /api/v1/resources/{uid}`) and through `coffer <kind> edit <name> --title <text>`. An
empty title MUST clear it. A title longer than 80 characters MUST be refused as a validation
error with nothing changed. A title change MUST be audited like any other update. The web UI and
the CLI MUST show the title in place of the name wherever a resource is listed or shown when a
title is set, and the name when it is not. The title MUST travel with the resource to the
user's other machines through vault-sync, and a resource that arrives without one MUST keep
its title empty.

#### Scenario: a title is shown in place of the name
- **GIVEN** a resource with no title
- **WHEN** the user runs `coffer <kind> edit <name> --title "Team search"` and then lists that kind
- **THEN** the list and `coffer <kind> show` print "Team search" where the name was shown, and `--json` carries both `name` and `title`
- **AND** the change is audited as an update, and the resource's name, uid, reach and enabled state are unchanged

#### Scenario: an over-long title is refused
- **GIVEN** a resource with a title set
- **WHEN** the user submits a title of 81 characters through the update route, and then an empty title
- **THEN** the first is refused as a validation error and the stored title is unchanged
- **AND** the second clears the title, and surfaces show the name again

### Requirement: Read the audit log from the command line
The system MUST let a terminal read the audit log with `coffer log audit`, over the same route
the web UI reads (`GET /api/v1/audit`). It MUST take the filters that route affords,
`--kind`, `--name`, `--event-type`, `--since` and `--limit`, and MUST print the entries newest
first. Each entry MUST show its time, actor, event type, and the label the resource carried at
that moment. With `--json` it MUST print the route's entries as one parseable document with no
human-readable framing.

#### Scenario: the command line reads the audit log
- **GIVEN** the user has disabled a resource and then changed another resource's title
- **WHEN** they run `coffer log audit --limit 2`, and then `coffer log audit --kind <kind> --json`
- **THEN** the first prints both changes newest first, each with its time, actor, event type and label
- **AND** the second prints a parseable JSON document holding only that kind's entries

### Requirement: Change every setting through one key–value command
The system MUST expose Coffer's own settings on the command line through one command,
`coffer config`, over a single registry of keys; a setting that belongs to one resource is
changed with that kind's `edit` instead. Each key MUST name its type, its default if it has one,
and a one-line help. A key MUST be stored where its owning spec already stores the setting:
through the REST route that owns it, or, for a setting that must be readable before the daemon
binds, in the pre-bind settings file, which `coffer config` reads and writes with no daemon
running. Keys MUST be namespaced by the setting's owner (for example `retention.<table>`), and
the spec that owns a setting names its keys.

- `coffer config list [<prefix>]` MUST print every key, or every key under the prefix, with its
  current value, its default, its type and its help.
- `coffer config get <key>` MUST print the current value.
- `coffer config set <key> <value>` MUST validate the value against the key's type before
  anything is written, and MUST refuse a value that fails with a message naming the expected
  type.
- `coffer config unset <key>` MUST return the key to its default. A key that has no default
  MUST refuse `unset` with a message naming how to change that key instead, with nothing
  changed.
- An unknown key MUST be refused with a non-zero exit that names the key, with nothing changed.
- `list` and `get` MUST support `--json`.

#### Scenario: a setting is read, changed and returned to its default
- **GIVEN** a registered key that has a default, and whose value is that default
- **WHEN** the user runs `coffer config set <key> <valid value>`, then `coffer config get <key>`, then `coffer config unset <key>`
- **THEN** `get` prints the new value, and the place that owns the setting reports the same value
- **AND** after `unset` the key reads its default again, and `coffer config list` shows its value, default, type and help

#### Scenario: an invalid setting is refused before any write
- **GIVEN** a key whose type is a whole number of days or `forever`, and a key that has no default
- **WHEN** the user runs `coffer config set <key> soon`, then `coffer config set no.such.key 1`, then `coffer config unset` on the key with no default
- **THEN** all three exit non-zero: the first naming the expected type, the second naming the unknown key, and the third naming how to change that key instead
- **AND** no setting changed

### Requirement: Locate file-backed state with coffer path
The system MUST print the absolute path of every piece of state that its owning spec declares
directly readable or editable as plain files, with `coffer path`, so that a person or an agent
reads and edits those files with their own tools. The targets MUST be `knowledge
[<collection>]`, `memory [<partition>]`, `skill <name>`, `agent <name> config|memory|transcripts`,
`logs` and `vault`. With no target it MUST print every root it knows. With `--json` it MUST print
the paths as one JSON object keyed by what each path is. The paths MUST be composed from reads
the daemon already serves. The command MUST create nothing and change nothing, and a name that
resolves to no resource MUST exit non-zero with a not-found message.

#### Scenario: the command line names the files behind a resource
- **GIVEN** a knowledge collection and a skill are registered
- **WHEN** the user runs `coffer path knowledge <collection>`, `coffer path skill <name> --json`, and `coffer path skill no-such-skill`
- **THEN** the first prints the absolute path of the collection's directory and the second prints a JSON object holding the skill's master folder path, both of which exist on disk
- **AND** the third exits non-zero with a not-found message, and nothing on disk was created or changed

### Requirement: Scan, adopt and discard what Coffer does not manage
The system MUST list, in one command, everything an agent holds that Coffer could manage but does
not: `coffer scan [--agent <name>] [--json]` prints one table with a `kind` column, and each row
carries the agent it was found in and a `ref` that names it. Which kinds a scan reports, and what
adopting or discarding each one does, belong to the spec that owns that kind.

`coffer adopt <kind> <ref>` MUST bring the one row the ref names under management, and
`coffer discard <kind> <ref>` MUST remove it from the agent, each acting through the owning
kind's REST route. The `ref` MUST be the value the scan printed for that row. A ref that names
no row in a fresh scan MUST be refused with nothing changed. A kind that offers no discard MUST
refuse `discard` with a message saying so, with nothing changed. Adopting or discarding MUST be
audited by the owning kind.

#### Scenario: a scan row is adopted by its ref
- **GIVEN** an agent holds an item of a kind Coffer can adopt, and Coffer does not manage it
- **WHEN** the user runs `coffer scan --json`, then `coffer adopt <kind> <ref>` with the ref that row printed, then `coffer scan` again
- **THEN** the first scan lists the row with its kind, agent and ref, and the adopt exits successfully and is audited
- **AND** the second scan no longer lists that row

#### Scenario: an unknown or undiscardable row is refused
- **GIVEN** a scan that lists a detected agent which is not registered
- **WHEN** the user runs `coffer discard agent <ref>` for that row, and `coffer adopt skill no-such-ref`
- **THEN** both exit non-zero, the first saying that kind cannot be discarded and the second saying the ref names no row
- **AND** nothing on disk or in the vault changed

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
kind registry and served by the kind-agnostic routes: `list`, `show`, `add`, `edit`, `rm`,
`enable`, `disable` and `scope`. A verb the kind does not support MUST be absent from its group
rather than refused when run (see "Keep creation a per-kind seam" and "Carry a per-agent reach
on every resource"). `show` MUST resolve either a name or a uid. `edit` MUST take `--title` and
`--description` on every kind, plus the kind's own flags. Every `list` and `show` MUST support
`--json`. A group MAY add commands that are unique to its kind, and MUST NOT add a second
spelling of a lifecycle verb.

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
- **THEN** each offers `list`, `show`, `edit`, `rm`, `enable` and `disable`, offers `add` only where the kind can be created from that group, and offers `scope` only where the kind supports reach
- **AND** `coffer <kind> disable <name>` and `coffer <kind> disable <uid>` disable the same resource through the kind-agnostic route, and the change is audited

### Requirement: Keep creation a per-kind seam
Creation is a per-kind seam and MUST stay one. The kind-agnostic create route MUST
accept only kinds that declare themselves creatable through it, and MUST refuse a kind
that owns a creation invariant beyond config validation — a skill's master folder, an
agent's on-disk detection — so that such a kind is registered through its own surface,
which can hold that invariant. On the command line a kind's group MUST offer `add` only when
the kind is creatable through the kind-agnostic route, or when the kind supplies an `add` of its
own that holds its invariant. A kind that is created only by the system, such as a memory
partition, MUST offer no `add`. There is no kind-agnostic create command, because a generic
create would have to guess a config shape it cannot know. What this spec owns is everything that
happens to a resource once a kind has made one.

#### Scenario: refuse a generic create for a kind that owns its creation
- **GIVEN** a registered kind that declares it is not creatable through the kind-agnostic surface,
- **WHEN** a registration for that kind arrives on the kind-agnostic create route,
- **THEN** it is refused as a conflict with the code `GENERIC_CREATE_NOT_ALLOWED`, and no resource row and no audit entry is written,
- **AND** that kind's command group offers `add` only if the kind supplies its own, and the memory group offers no `add` at all.

### Requirement: Carry a per-agent reach on every resource
The system MUST carry a framework-level per-agent reach on every resource — one
allow-list of agents, `null` meaning every agent, `[]` meaning none
([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)) — and MUST
serve it for every kind through one kind-agnostic pair of routes rather than per kind,
reporting whether the kind supports reach at all so a client can render the right
control without knowing the kinds itself. A reach is machine-local (see vault-sync).

On the command line the reach MUST be read and written with
`coffer <kind> scope <name> [--agents a,b | --all | --none]`, offered only on a kind that
supports reach. With no option it MUST print the current reach. `--agents` MUST set the
allow-list, `--all` MUST set every agent and `--none` MUST set none.

A non-null reach on a kind that declares none, and a payload carrying a property the
schema does not define, MUST both be refused rather than stored or silently widened — a
client still sending a withdrawn axis means "only there", and keeping what is left would
store "every agent". A reach write MUST be audited and MUST fire the kind's post-write
reaction, so delivery and reclaim stay in step with the edit. *Enforcing* reach is each
kind's own seam at its own choke point; this spec owns the value, its validation and its
write path.

#### Scenario: set a resource's reach from the kind-agnostic surface
- **GIVEN** a resource of a kind that supports reach,
- **WHEN** the user sets its scope to one agent, then clears it back to unscoped,
- **THEN** each write is persisted, audited as a scope update, and followed by the kind's own post-write reaction,
- **AND** a kind that supports no reach rejects a non-null scope, as does a payload carrying a property the scope schema does not define.

#### Scenario: the command line sets a resource's reach
- **GIVEN** a resource of a kind that supports reach, and a registered agent
- **WHEN** the user runs `coffer <kind> scope <name> --agents <agent>`, then `coffer <kind> scope <name>`, then `coffer <kind> scope <name> --all`
- **THEN** the second command prints the one agent, and after the third the reach is every agent again
- **AND** each write is audited as a scope update, and a kind that supports no reach offers no `scope` command

### Requirement: Treat a resource's name as a mutable label
A resource's `name` is a **label**, unique within its kind and nothing more. For every kind
except those that declare their name fixed, renaming MUST be an ordinary field of the
kind-agnostic update — at the same level as editing a description, and reached on the command
line as `coffer <kind> edit <name> --name <new>` — and MUST NOT require any other record to be
rewritten, because nothing else holds the name: the resource keeps its identity, its config,
its reach, its enabled state and its audit trail, with the entries written before the change
still saying what it was called then. The same name rules MUST apply to a rename as to a
registration, a collision within the kind MUST be refused before anything moves, and renaming
to the name it already has MUST change nothing and record nothing. A kind that keeps an on-disk
artifact named after the resource MUST be given the chance to move it, with a failure aborting
the rename rather than leaving the two disagreeing.

A kind whose name is visible outside Coffer MUST declare its name fixed, because agents and the
files they read quote that name. Today these are `mcp_server`, whose name prefixes every tool
name an agent sees, and `skill`, whose name is the folder an agent loads it from. For such a
kind, an update whose `name` differs from the current one MUST be refused as a conflict with the
code `NAME_IMMUTABLE`, whichever surface it came through, with nothing moved and nothing
audited. The refusal message MUST say that the resource has to be deleted and registered again
under the new name, and MUST name what a re-registration resets. A resource of such a kind that
wants a different display uses its title (see "Carry an optional editable title on every
resource").

#### Scenario: renaming a resource is an ordinary edit
- **GIVEN** a resource of a kind whose name is not fixed, with a reach set, a credential cited by its
  config, and rows in a table its kind owns,
- **WHEN** the user changes its name through the kind-agnostic update,
- **THEN** the resource is the same resource — its identity, its reach, its
  credential and its kind-owned rows are untouched — and its audit trail comes
  back whole, with the rows written before the change still saying what it was
  called then,
- **AND** a name another resource of that kind already holds is refused with
  nothing moved, as is a name the rules would have refused at registration, and
  submitting the name it already has changes nothing.

#### Scenario: a kind whose name is a directory moves it with the rename
- **GIVEN** a resource of a renamable kind that keeps an on-disk artifact named after it —
  a knowledge collection's directory, a memory partition's directory,
- **WHEN** the user renames it,
- **THEN** the artifact is at the new name with its contents intact and is
  served from there,
- **AND** a rename the kind cannot carry out — something already occupies the
  destination — is refused with the row and the artifact both untouched, rather
  than leaving a resource pointing at a directory that is not there or merging
  into one that was never its own.

#### Scenario: a fixed name refuses a rename
- **GIVEN** a registered MCP server and a registered skill
- **WHEN** the user submits a different name for each through the kind-agnostic update, and through `coffer <kind> edit <name> --name <new>`
- **THEN** every attempt is refused as a conflict with the code `NAME_IMMUTABLE`, and the command line exits non-zero with a message saying to delete and register the resource again and naming what that resets
- **AND** each resource keeps its name, its on-disk artifact and its audit trail, no audit entry is written, and a title change on the same resource still succeeds

### Requirement: Prune each registered log table on its own retention period
The system MUST provide per-table retention configuration (in days, or "keep forever")
over a registry of prunable tables, seeded with each table's default when the daemon
starts, plus a periodic background pass that prunes entries older than their table's
period and an on-demand prune for the impatient. Entries newer than the period MUST be
retained, and the cleanup MUST NOT block concurrent API calls. Only a registered table
MAY be pruned, and only through its registered timestamp column. Policies are upserted at
startup from the prunable-table registry and never deleted, so a table that stops
existing leaves a policy that prunes nothing rather than a prune aimed at an unknown
table. Changing a policy MUST itself be audited. This is the retention contract every
log-writing kind inherits.

On the command line each table's period MUST be the setting `retention.<table>`, read and
changed with `coffer config get|set|unset retention.<table>` (see "Change every setting through
one key–value command"), taking a whole number of days or `forever`, with `unset` returning the
table to its registered default. The on-demand prune MUST be `coffer log prune [--table
<table>]`, which prunes every registered table, or only the one named, and prints how many
entries each lost.

#### Scenario: configure retention per log
- **GIVEN** the audit and invocation logs grow over time,
- **WHEN** the user sets a retention period for a log (in days, or "keep forever"),
- **THEN** entries older than that period are removed by the next periodic cleanup, and the change itself is audited.

#### Scenario: the command line sets a retention period and prunes now
- **GIVEN** the invocation log holds entries older and newer than 7 days
- **WHEN** the user runs `coffer config set retention.mcp_invocations 7` and then `coffer log prune --table mcp_invocations`
- **THEN** `coffer config get retention.mcp_invocations` prints 7, the policy change is audited, and the prune reports how many entries it removed
- **AND** only entries older than 7 days are gone

### Requirement: Report the passes in flight in one cross-kind read
The system MUST answer, in one cross-kind read, which long model-driven passes this
daemon is running right now — each named by its kind, its target and when it started —
so that a surface can tell whether a pass is under way without every kind growing a
near-identical endpoint of its own. The read MUST start nothing, and the registry MUST
NOT outlive the process: a restart ends any pass it was running and the list comes back
empty, which is the truth rather than a lost record. Whether a pass runs on a timer at
all is internal-engine's; what a pass *does* is its own kind's. The read is served over
REST (`GET /api/v1/upkeep/runs`) and on the command line as the "passes in flight" section
of `coffer daemon status`, which prints the same list, says so when nothing is running, and
carries the list under `--json`.

#### Scenario: the daemon names the passes in flight
- **GIVEN** a long, model-driven pass over one kind's target is running,
- **WHEN** any surface reads the in-flight list,
- **THEN** that pass is named with its kind, its target and when it started,
- **AND** a target absent from the list has no pass running, and the read starts nothing.

#### Scenario: the command line reads the passes in flight
- **GIVEN** a pass over a knowledge collection and a pass over a memory partition are running
- **WHEN** the operator runs `coffer daemon status --json`, and again once both have ended
- **THEN** the first lists both passes with their kind, target and start time, oldest first,
- **AND** the second lists none, and the table form of `coffer daemon status` says that no pass is running.

### Requirement: Reach every management operation from both REST and the CLI
Users MUST be able to perform every mutation, and every read of state that is not a plain file,
through both (a) a REST API and (b) a `coffer` command-line interface, sharing the same
underlying daemon and a consistent error model. For a plain file that its owning spec declares
directly readable or editable, the CLI MUST satisfy parity by naming the file with `coffer path`
(see "Locate file-backed state with coffer path"), while the REST route that serves the file to
the web UI stays, because a browser page cannot read the disk. A setting changed through
`coffer config` counts as the CLI counterpart of the route that stores it (see "Change every
setting through one key–value command"). The reviewed CLI command tree
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
- **THEN** it names every route that serves or writes a plain file for the web UI — the knowledge tree, file read and file delete; the memory partition's file tree, file content, notes, one note and retired notes; the skill master folder's file tree, file read and file write; an agent's config-file list and config-file reads; an agent's native-memory list, file tree and file content — each paired with the `coffer path` target that names the same files
- **AND** a file-backed route missing from that list fails the parity test, as does a listed route the API no longer serves

#### Scenario: command line surfaces same errors
- **GIVEN** any failure surfaced by the management API,
- **WHEN** triggered through the command line,
- **THEN** the user sees an actionable message and a non-zero exit code; `--verbose` shows a full trace.
