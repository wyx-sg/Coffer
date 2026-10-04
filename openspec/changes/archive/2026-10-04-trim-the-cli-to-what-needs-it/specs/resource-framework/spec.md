## RENAMED Requirements

- FROM: `### Requirement: Reach every management operation from both REST and the CLI`
- TO: `### Requirement: Keep the command line to what needs it`

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

The lifecycle controls of the web UI are exactly these routes: list, read, update — the
description, `title` on a kind that carries one ("Carry an optional editable title on the kinds that
have one"), and the kind's own fields — enable, disable and delete, plus the reach pair ("Carry a
per-agent reach on every resource"). Creating is not one of them: a kind registers through its own
seam (see "Keep creation a per-kind seam"). A request a kind does not support MUST be refused rather
than ignored (see "Keep creation a per-kind seam" and "Carry a per-agent reach on every resource").

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
- **GIVEN** one registered kind that can be disabled, supports reach and carries a title, and one that does none of these
- **WHEN** each resource is read with `GET /api/v1/resources/{uid}`, given a new description with `PATCH /api/v1/resources/{uid}`, and sent a non-null scope with `PUT /api/v1/resources/{uid}/scope`, a title and `POST /api/v1/resources/{uid}/disable`
- **THEN** both kinds answer the read and the description update through the same routes, and the kind that supports no reach, carries no title or cannot be disabled refuses that request and changes nothing
- **AND** the first kind's disable changes it through the kind-agnostic route and is audited

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
which can hold that invariant. A kind that is created only by the system, such as a memory partition, MUST offer no creation
at all. A generic create would have to guess a config shape it cannot know, which is why creation stays the kind's own. What this spec owns is everything that
happens to a resource once a kind has made one.

#### Scenario: refuse a generic create for a kind that owns its creation
- **GIVEN** a registered kind that declares it is not creatable through the kind-agnostic surface,
- **WHEN** a registration for that kind arrives on the kind-agnostic create route,
- **THEN** it is refused as a conflict with the code `GENERIC_CREATE_NOT_ALLOWED`, and no resource file and no audit entry is written,
- **AND** that kind is created only through a surface of its own that holds its invariant.

### Requirement: Carry a per-agent reach on every resource
The system MUST carry a framework-level per-agent reach on every resource — one
allow-list of agents, `null` meaning every agent, `[]` meaning none
([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)) — and MUST
serve it for every kind through one kind-agnostic pair of routes rather than per kind,
reporting whether the kind supports reach at all so a client can render the right
control without knowing the kinds itself. A reach is machine-local: it is kept, with the
resource's `enabled` flag, in this machine's reach record `~/.coffer/local/reach.json`, keyed
by the resource's uid, and never in the resource's own file, so a reach write makes no vault
commit; a resource with no record there takes its kind's default
([vault-sync](../vault-sync/spec.md) "Keep reach machine-local").

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
- **WHEN** a client sends `PUT /api/v1/resources/{uid}/scope` naming that one agent, then reads `GET /api/v1/resources/{uid}/scope`, then sends `PUT` again naming every agent
- **THEN** the read returns the one agent, and after the second `PUT` the reach is every agent again
- **AND** each write is audited as a scope update, and a kind that supports no reach refuses a non-null scope

#### Scenario: reach is kept on this machine, not in the resource's file
- **GIVEN** a registered resource
- **WHEN** it is disabled, and later this machine's reach record is deleted and the resource is read again
- **THEN** the disable made no vault commit and the reach record holds the resource's uid with `enabled` false, while the resource's file carries neither `enabled` nor a scope
- **AND** with the record gone the resource reads as enabled with its kind's default reach

### Requirement: Treat a resource's name as a mutable label
A resource's `name` is a **label**, unique within its kind and nothing more. For every kind
except those that declare their name fixed, renaming MUST be an ordinary field of the
kind-agnostic update — at the same level as editing a description — and MUST NOT require any other record to be
rewritten, because nothing else holds the name: the resource keeps its identity, its config,
its reach, its enabled state and its audit trail, with the entries written before the change
still saying what it was called then. The same name rules MUST apply to a rename as to a
registration, a collision within the kind MUST be refused before anything moves, and renaming
to the name it already has MUST change nothing and record nothing. The resource's own file,
which is named after the resource, MUST move to the new name in the same vault commit that
records the rename ([vault-storage](../vault-storage/spec.md) "Identify a resource by the uid inside its file"). A kind that keeps an on-disk
artifact named after the resource MUST be given the chance to move it, with a failure aborting
the rename rather than leaving the two disagreeing: a file that cannot be written is refused
before the hook runs, and a write that fails after it asks the kind to move the artifact back.

A kind whose name is visible outside Coffer MUST declare its name fixed, because agents and the
files they read quote that name. Today these are `mcp_server`, whose name prefixes every tool
name an agent sees, and `skill`, whose name is the folder an agent loads it from. A kind MAY
also derive the name from the resource's config, which fixes it too: `agent`, whose name is its
type's ([agent-registry](../agent-registry/spec.md) "Keep one agent per type, named by it"), and
registration MUST refuse any other name for such a kind as a validation error. For a fixed-name
kind, an update whose `name` differs from the current one MUST be refused as a conflict with the
code `NAME_IMMUTABLE`, whichever surface it came through, with nothing moved and nothing
audited. The refusal message MUST say that the resource has to be deleted and registered again
under the new name, and MUST name what a re-registration resets — or, for a derived name, that
the name is the resource's type. None of these kinds carries a title ("Carry an optional
editable title on the kinds that have one"): the fixed name is what every surface shows.

#### Scenario: renaming a resource is an ordinary edit
- **GIVEN** a resource of a kind whose name is not fixed, with a reach set, a secret cited by its
  config, and rows in a table its kind owns,
- **WHEN** the user changes its name through the kind-agnostic update,
- **THEN** the resource is the same resource — its identity, its reach, its
  secret and its kind-owned rows are untouched — and its audit trail comes
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
  destination — is refused with the resource and the artifact both untouched, rather
  than leaving a resource pointing at a directory that is not there or merging
  into one that was never its own,
- **AND** a resource file that cannot be written (an unsettled edit on disk) is refused before
  the artifact moves, and a write that fails after the artifact moved puts it back.

#### Scenario: a fixed name refuses a rename
- **GIVEN** a registered MCP server and a registered skill
- **WHEN** the user submits a different name for each through the kind-agnostic update
- **THEN** every attempt is refused as a conflict with the code `NAME_IMMUTABLE`, with a message saying to delete and register the resource again and naming what that resets
- **AND** each resource keeps its name, its on-disk artifact and its audit trail, and no audit entry is written

#### Scenario: a rename moves the resource's file in one commit
- **GIVEN** a resource of a renamable kind, filed as `resources/<kind>/old.json`
- **WHEN** the user renames it to `new`
- **THEN** one vault commit removes `resources/<kind>/old.json` and adds `resources/<kind>/new.json`, and the resource keeps its uid

### Requirement: Audit every lifecycle change
The system MUST record an audit entry for every lifecycle change to any resource or
capability, including the actor — the originating surface (CLI / API / UI), `system` for the
daemon's own work, `sync` for a change applied from the sync remote, `human` for an edit a person or an agent made to
a vault file on disk that Coffer found and committed, a named background worker
such as `system:memory-aggregate-worker`, or a domain actor a kind names itself, such as `user`,
`channel`, an agent's name, or `agent` for a knowledge write whose session reported no agent. Every lifecycle change made
through any surface — REST, CLI, or a kind's own command — MUST appear in the audit log
with the originating actor, and no surface can mutate a resource without one. Entries
MUST be readable through the REST route, the Activity page and `coffer log audit`, filterable by kind, resource, event type and
time, and MUST carry both the resource's stable identity and the label it carried at
that moment, so a trail survives a rename while each row keeps saying what the resource
was called then. Filtering one resource's history MUST key on that identity and not on
the label: a label cannot tell a renamed resource from a deleted one whose name was
later taken, and rendering two objects' histories as one is a worse answer than a short
one. The event-type vocabulary is shared: this spec defines the resource and retention
events and every kind contributes its own, so one record answers "what happened" for the
whole vault rather than each kind growing a private log.

#### Scenario: audit lifecycle changes
- **GIVEN** the user performs any add / enable / disable / update / delete on a server or capability,
- **WHEN** they open the Activity page's audit tab or run `coffer log audit`,
- **THEN** they see one row per change with actor, timestamp, and a payload describing what changed.

### Requirement: Prune each registered log table on its own retention period
The system MUST provide per-table retention configuration (in days, or "keep forever")
over a registry of prunable tables, seeded with each table's default when the daemon
starts, plus a periodic background pass that prunes entries older than their table's
period and an on-demand prune for the impatient. Entries newer than the period MUST be
retained, and the cleanup MUST NOT block concurrent API calls. Only a registered table
MAY be pruned, and only through its registered timestamp column. Policies are settings of this
machine, kept in `~/.coffer/local/retention.json` rather than in the history they prune, and
are upserted at startup from the prunable-table registry and never deleted, so a table that stops
existing leaves a policy that prunes nothing rather than a prune aimed at an unknown
table. Changing a policy MUST itself be audited. This is the retention contract every
log-writing kind inherits.

On the Data settings section each table's period MUST be a control over
`PATCH /api/v1/retention/policies/{table}`, taking a whole number of days or `forever` and returning the
table to its registered default when cleared. The prune-now action MUST be
`POST /api/v1/retention/prune`, which prunes every registered table, or only the one named, and
answers how many entries each lost.

Before a shorter period is saved, the web UI MUST be able to ask how many entries it would delete:
`GET /api/v1/retention/policies/{table}/preview?days=<n>` answers the entries the table holds now
and how many of them are older than `n` days, counts them against the same timestamp column the
prune uses, and deletes and changes nothing. It is a read that serves a confirmation and changes nothing.

#### Scenario: configure retention per log
- **GIVEN** the audit and invocation logs grow over time,
- **WHEN** the user sets a retention period for a log (in days, or "keep forever"),
- **THEN** entries older than that period are removed by the next periodic cleanup, and the change itself is audited.

#### Scenario: the command line sets a retention period and prunes now
- **GIVEN** the invocation log holds entries older and newer than 7 days
- **WHEN** a client sends `PATCH /api/v1/retention/policies/mcp_invocations` setting 7 days and then `POST /api/v1/retention/prune` naming that table
- **THEN** `GET /api/v1/retention/policies` reports 7 days for it, the policy change is audited, and the prune answers how many entries it removed
- **AND** only entries older than 7 days are gone

#### Scenario: a shorter period is previewed before it is saved
- **GIVEN** the audit log holds 4 entries, 2 of them older than 7 days
- **WHEN** the web UI asks `GET /api/v1/retention/policies/audit_log/preview?days=7`
- **THEN** the answer carries 4 entries now and 2 to delete
- **AND** asking again answers 4 entries now: nothing was deleted

### Requirement: Keep the command line to what needs it
A `coffer` command MUST exist only for one of four reasons, and the web UI is where everything
else is managed:

- **program** — a program Coffer installs or writes runs it (the memory hook entry point, an agent's
  key helper);
- **offline** — it must work when the daemon is down or cannot start (the daemon's start, stop,
  restart and status, the one-time migration, locating the log files, the daemon's own pre-bind
  settings);
- **hand-off** — a prompt Coffer gives an agent tells it to run the command, because what it reads or
  writes is not a file (running a command with secrets in its environment, naming and storing a
  secret, reading the audit, MCP and daemon logs, testing an MCP server after installing it);
- **no-ui** — the web UI cannot do it (listing the hand edits the vault refused).

Each command MUST be recorded with its reason in one place in the CLI package. A test MUST walk the
live command tree and assert that it equals the recorded list in both directions, that every entry
names one of the four reasons, and that every group's `--help` renders. A web UI operation owes no
command line counterpart: the REST routes that serve only the web UI are its interface, and a
mutation or a read of state that is not a file needs no command to be shippable. The rule is policy
over every spec and is stated as such in [`.agents/openspec.md`](../../../.agents/openspec.md); this
requirement is where it becomes testable, because the assertion runs over the entire command tree
across every spec and so has no narrower home.

#### Scenario: command line covers every visual operation
- **GIVEN** the CLI's live command tree
- **WHEN** it is read
- **THEN** every command it holds is one a web UI page does not replace: the recorded list names the memory hook, the proxy key helper, the daemon lifecycle verbs, the migration, `path logs`, `config`, `run`, `secret list` and `secret set`, the three `log` commands, `mcp test` and `vault problems`, and no group exists for a kind the web UI manages
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

#### Scenario: file-backed reads are answered by coffer path
- **GIVEN** a plain file that its owning spec declares directly readable or editable
- **WHEN** a person or an agent needs it
- **THEN** it is read and edited with their own tools at the path the web UI, the spec or the hand-off prompt names, and no command is added for it
- **AND** `coffer path logs` is the one exception, because the log files are what is left to read when the daemon will not start

#### Scenario: command line surfaces same errors
- **GIVEN** any failure surfaced by the management API,
- **WHEN** it reaches a kept command that calls the daemon,
- **THEN** the user sees an actionable message and a non-zero exit code; `--verbose` shows a full trace.

### Requirement: Carry an optional editable title on the kinds that have one
A resource of a kind that carries a title MUST carry an optional **`title`**: free text of at
most 80 characters that a person chooses for display, separate from the resource's `name`. The
kinds with a title are those whose name is a label a person chose — `provider`, `channel`
and `memory`. `agent`, `mcp_server`, `skill` and `knowledge` carry none: each is shown by its fixed
name — a knowledge collection by its folder, with an editable description instead
([knowledge](../knowledge/spec.md) "Name a collection by its folder and edit its description in place")
— and a non-empty title for one MUST be refused as a validation error (422) on registration
and on update, with nothing changed. On a kind that carries one, the title MUST be editable
through the kind-agnostic update (`PATCH /api/v1/resources/{uid}`). An empty title MUST clear it. A title longer than 80
characters MUST be refused as a validation error with nothing changed. A title change MUST be
audited like any other update. The web UI MUST show the title in place of the name
wherever a resource is listed or shown when a title is set, and the name when it is not. The
title MUST be a key of the resource's own file, left out while it is empty, so it travels with
the resource to the user's other machines through vault-sync, and a
resource that arrives without one MUST keep its title empty.

#### Scenario: a title is shown in place of the name
- **GIVEN** a resource of a kind that carries a title, with no title
- **WHEN** a client sends `PATCH /api/v1/resources/{uid}` with the title "Team search" and then lists that kind
- **THEN** the list and the resource read carry "Team search" as the `title` beside the unchanged `name`, and the web UI shows the title where the name was shown
- **AND** the change is audited as an update, and the resource's name, uid, reach and enabled state are unchanged

#### Scenario: an over-long title is refused
- **GIVEN** a resource with a title set
- **WHEN** the user submits a title of 81 characters through the update route, and then an empty title
- **THEN** the first is refused as a validation error and the stored title is unchanged
- **AND** the second clears the title, and surfaces show the name again

#### Scenario: a kind without a title refuses one
- **GIVEN** a registered MCP server, a registered skill and a registered agent
- **WHEN** the user submits a title for each through the kind-agnostic update, and registers an MCP server with a title
- **THEN** each is refused as a validation error (422) and nothing is stored
- **AND** each of those resources is still shown by its fixed name

### Requirement: Change every setting through one key-value command
The system MUST expose the settings the daemon reads before it binds on the command line through one
command, `coffer config`, over a single registry of keys, so a setting that decides whether the
daemon can start is changeable when it cannot. Today that is `daemon.port`. Every other setting MUST
be changed on the Settings page, through the REST route that stores it, and MUST NOT be a key. Each
key MUST name its type, its default if it has one, and a one-line help. A key MUST be stored in the
pre-bind settings file, which `coffer config` reads and writes with no daemon running. Keys MUST be
namespaced by the setting's owner, and the spec that owns a setting names its keys.

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
- **THEN** `get` prints the new value, and the pre-bind settings file holds the same value
- **AND** after `unset` the key reads its default again, and `coffer config list` shows its value, default, type and help

#### Scenario: an invalid setting is refused before any write
- **GIVEN** the `daemon.port` key, whose type is a port number
- **WHEN** the user runs `coffer config set daemon.port soon`, then `coffer config set no.such.key 1`, then `coffer config set` with the name of a setting that is a control on the Settings page
- **THEN** all three exit non-zero: the first naming the expected type and the other two naming the unknown key
- **AND** no setting changed

### Requirement: Locate file-backed state with coffer path
The system MUST print the absolute path of the daemon's log directory and of the `daemon.log` in it
with `coffer path logs`, so that a person or an agent can read the log files when the daemon will not
start. `logs` MUST be the only target: every other file Coffer keeps as a plain file is named by the
web UI, by its owning spec or by a hand-off prompt, and is read and edited with the reader's own
tools. With `--json` the command MUST print the paths as one JSON object keyed by what each path is.
The command MUST need no daemon, MUST create nothing and change nothing, and a target other than
`logs` MUST exit non-zero as an unknown target.

#### Scenario: the command line names the files behind a resource
- **GIVEN** a Coffer home with its log directory
- **WHEN** the user runs `coffer path logs`, `coffer path logs --json`, and `coffer path skill <name>`
- **THEN** the first prints the absolute path of the log directory and of `daemon.log`, and the second prints a JSON object holding both
- **AND** the third exits non-zero as an unknown target, and nothing on disk was created or changed

### Requirement: Serve the drift plan and apply chosen items on REST and the CLI
`GET /api/v1/reconcile/plan` MUST return a dry-run plan — optionally for one
target (`target`), or only the items about one kind or one resource (`kind`,
`uid`), and for the periodic policy or for what a person's request would do
(`trigger=period|manual`) — listing per item its id, target, operation (`add`,
`modify`, `remove`), disposition (`repair`, `report`, `blocked`), a reason code
and one sentence, the resource it concerns, the file, the changed parameter
names, the text before and after, and when a pass first saw it, together with
each target's error and a summary of the last pass. The text MUST be the
target's safe rendering and MUST NOT carry a secret value. `POST
/api/v1/reconcile/apply` MUST apply the named items as the caller asking for
them: an item the policy still will not repair comes back unwritten with its
reason, and one that names no current difference is absent. The web UI's drift views are these two routes' interface, and no command reaches
them: the reconciler repairs what its policy allows on its own every minute.

#### Scenario: list drift with its file and before and after text
- **GIVEN** a registered agent whose Coffer MCP entry names a shim path this build no longer installs
- **WHEN** the user reads the plan (`GET /api/v1/reconcile/plan`)
- **THEN** the MCP entry item reads `modify`, `repair`, the agent's config file, `command` among the changed parameters and the entry before and after, and nothing is written

#### Scenario: apply one drift item as the caller
- **GIVEN** the same drift
- **WHEN** the user applies its id (`POST /api/v1/reconcile/apply`)
- **THEN** the entry is rewritten, the item comes back `applied`, and the audit log records the install with the user as actor

### Requirement: Report what needs a person across every kind
`GET /api/v1/attention` MUST list what needs a person
now, from every source whose experimental feature is on: the reconciler's
drift that a pass could not fix, MCP servers whose last test failed (a server
whose key the upstream refused reads `mcp_key_rejected` and offers
`replace_key`, which opens the server's page where the key is replaced),
whose launcher is missing or whose cited secret is absent, agents whose program is
missing, whose connection is partial or who are not connected, whose Coffer memory hook the agent has not approved or has never run, a sync stopped on
a conflict or holding deletions, channels reconnecting, disconnected or not
running, and commands a skill requires that are missing, older than a skill's
minimum or not logged in (kind `cli`, the command as the uid). Each item MUST carry its kind, the resource's uid and title, a stable
reason code with one sentence, a severity (`error`, `warning`, `info`), when
the condition was first seen where that is known, and exactly one action: a
verb and the REST route and body the kind's own page uses — the list has no
write of its own. Every item MUST also carry `handoff` (Principle IV,
AI-Native): the same prompt the kind's own page offers when its fix is a chore
for an agent — and its reason sentence MUST then name no command to run —
otherwise a prompt the daemon writes from the item's title, reason and action,
carrying no secret. Any item MAY be ignored on this machine by its stable key
([web-ui](../web-ui/spec.md) "Let the user ignore any item on Overview").
The route MUST serve each item's prompt as `handoff.prompt`, the text the web UI copies. A source that fails MUST be reported beside the others'
items, and the answer MUST count the items per kind.

#### Scenario: each item carries one action from its kind's own page
- **GIVEN** an MCP server whose last test failed and a partially connected agent
- **WHEN** the user reads the attention list
- **THEN** the server's item offers `test` through `POST /api/v1/resources/mcp_server/{uid}/test`, the agent's offers `connect` through `POST /api/v1/agents/{uid}/coffer-connection`, errors sort before warnings, and the counts name one item for each kind

#### Scenario: a rejected key is its own attention item
- **GIVEN** an enabled HTTP server whose last test failed with `auth_rejected`
- **WHEN** the user reads the attention list
- **THEN** the server's item reads `mcp_key_rejected` with the reason "Every call is rejected with 401 Unauthorized. The API key looks revoked.", offers `replace_key`, and still carries the diagnosis `handoff`

#### Scenario: every item carries a hand-off prompt
- **GIVEN** an attention item whose kind writes its own hand-off, and another whose source gives none
- **WHEN** the attention list is read
- **THEN** the first carries its kind's `handoff.prompt` and the second a prompt written from its title, reason and action, and the web UI copies exactly each text

#### Scenario: a failing source does not hide the others
- **GIVEN** one source that raises and one that has an item
- **WHEN** the attention list is read
- **THEN** the item is listed and the failing source is reported with its error

#### Scenario: a switched-off feature's signals are left out
- **GIVEN** an attention source tagged with a registered experimental feature that is switched off, holding an item it would report
- **WHEN** the attention list is read
- **THEN** that source's item is not listed and the source is not reported as failing

#### Scenario: a required command that needs attention is listed
- **GIVEN** a skill requiring `gh` with minimum `2.40` and `gh 2.30` installed
- **WHEN** the attention list is read
- **THEN** it carries one `cli` item for `gh` with reason `cli_outdated` whose action is `check` through `POST /api/v1/clis/gh/check`
- **AND** once `gh` is current, present and logged in, no `cli` item is listed

## REMOVED Requirements

### Requirement: Scan, adopt and discard what Coffer does not manage
**Reason**: the requirement defined only the `coffer scan`, `coffer adopt` and `coffer discard` commands; the web UI lists and adopts what an agent holds that Coffer does not manage on each kind's own page, through the owning kind's REST routes.
**Migration**: use each kind's page in the web UI (or its REST adopt and discard routes); the owning kind's spec states what adopting or discarding it does.
