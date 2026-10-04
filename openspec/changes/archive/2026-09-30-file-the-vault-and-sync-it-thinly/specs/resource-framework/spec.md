## MODIFIED Requirements

### Requirement: Validate every registration and persist nothing on failure
The system MUST validate every registration against its kind's schema and the kind's own
pre-write validators, MUST reject a duplicate name within a kind, and MUST persist
nothing on a validation failure — not a resource file with a rejected config, not a
half-written reach, not an audit entry for a change that did not happen, and no kind-owned side
effect: a registration that fails validation leaves the vault, this machine's reach record and the
audit log exactly as they were before the attempt. This is the contract every kind inherits, which is why it is stated
once here rather than once per kind.

#### Scenario: reject an invalid registration and persist nothing
- **GIVEN** a registered kind with a config schema,
- **WHEN** a registration arrives whose config fails that schema, or whose name is already taken within the same kind,
- **THEN** it is refused with a message naming the cause — a validation error for the schema failure, a conflict for the duplicate,
- **AND** no resource file, no reach record, no audit entry and no kind-owned side effect is left behind.

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

#### Scenario: reach is kept on this machine, not in the resource's file
- **GIVEN** a registered resource
- **WHEN** it is disabled, and later this machine's reach record is deleted and the resource is read again
- **THEN** the disable made no vault commit and the reach record holds the resource's uid with `enabled` false, while the resource's file carries neither `enabled` nor a scope
- **AND** with the record gone the resource reads as enabled with its kind's default reach

### Requirement: Treat a resource's name as a mutable label
A resource's `name` is a **label**, unique within its kind and nothing more. For every kind
except those that declare their name fixed, renaming MUST be an ordinary field of the
kind-agnostic update — at the same level as editing a description, and reached on the command
line as `coffer <kind> edit <name> --name <new>` — and MUST NOT require any other record to be
rewritten, because nothing else holds the name: the resource keeps its identity, its config,
its reach, its enabled state and its audit trail, with the entries written before the change
still saying what it was called then. The same name rules MUST apply to a rename as to a
registration, a collision within the kind MUST be refused before anything moves, and renaming
to the name it already has MUST change nothing and record nothing. The resource's own file,
which is named after the resource, MUST move to the new name in the same vault commit that
records the rename ([vault-storage](../vault-storage/spec.md) "Identify a resource by the uid inside its file"). A kind that keeps an on-disk
artifact named after the resource MUST be given the chance to move it, with a failure aborting
the rename rather than leaving the two disagreeing.

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
  into one that was never its own.

#### Scenario: a fixed name refuses a rename
- **GIVEN** a registered MCP server and a registered skill
- **WHEN** the user submits a different name for each through the kind-agnostic update, and through `coffer <kind> edit <name> --name <new>`
- **THEN** every attempt is refused as a conflict with the code `NAME_IMMUTABLE`, and the command line exits non-zero with a message saying to delete and register the resource again and naming what that resets
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
MUST be readable through both surfaces, filterable by kind, resource, event type and
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
- **WHEN** they open the audit view (CLI or UI),
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

On the command line each table's period MUST be the setting `retention.<table>`, read and
changed with `coffer config get|set|unset retention.<table>` (see "Change every setting through
one key-value command"), taking a whole number of days or `forever`, with `unset` returning the
table to its registered default. The on-demand prune MUST be `coffer log prune [--table
<table>]`, which prunes every registered table, or only the one named, and prints how many
entries each lost.

Before a shorter period is saved, the web UI MUST be able to ask how many entries it would delete:
`GET /api/v1/retention/policies/{table}/preview?days=<n>` answers the entries the table holds now
and how many of them are older than `n` days, counts them against the same timestamp column the
prune uses, and deletes and changes nothing. It is a read that serves a confirmation, so it has no
command of its own: `coffer config set retention.<table>` saves a period directly.

#### Scenario: configure retention per log
- **GIVEN** the audit and invocation logs grow over time,
- **WHEN** the user sets a retention period for a log (in days, or "keep forever"),
- **THEN** entries older than that period are removed by the next periodic cleanup, and the change itself is audited.

#### Scenario: the command line sets a retention period and prunes now
- **GIVEN** the invocation log holds entries older and newer than 7 days
- **WHEN** the user runs `coffer config set retention.mcp_invocations 7` and then `coffer log prune --table mcp_invocations`
- **THEN** `coffer config get retention.mcp_invocations` prints 7, the policy change is audited, and the prune reports how many entries it removed
- **AND** only entries older than 7 days are gone

#### Scenario: a shorter period is previewed before it is saved
- **GIVEN** the audit log holds 4 entries, 2 of them older than 7 days
- **WHEN** the web UI asks `GET /api/v1/retention/policies/audit_log/preview?days=7`
- **THEN** the answer carries 4 entries now and 2 to delete
- **AND** asking again answers 4 entries now: nothing was deleted

### Requirement: Carry an optional editable title on the kinds that have one
A resource of a kind that carries a title MUST carry an optional **`title`**: free text of at
most 80 characters that a person chooses for display, separate from the resource's `name`. The
kinds with a title are those whose name is a label a person chose — `provider`, `channel`
and `memory`. A knowledge collection carries none: it is named by its folder, with an editable
description ([knowledge](../knowledge/spec.md) "Name a collection by its folder and edit its description in place"). `agent`, `mcp_server`, `skill` and `knowledge` carry none: each is shown by its fixed
name, and a non-empty title for one MUST be refused as a validation error (422) on registration
and on update, with nothing changed. On a kind that carries one, the title MUST be editable
through the kind-agnostic update (`PATCH /api/v1/resources/{uid}`) and through
`coffer <kind> edit <name> --title <text>`. An empty title MUST clear it. A title longer than 80
characters MUST be refused as a validation error with nothing changed. A title change MUST be
audited like any other update. The web UI and the CLI MUST show the title in place of the name
wherever a resource is listed or shown when a title is set, and the name when it is not. The
title MUST be a key of the resource's own file, left out while it is empty, so it travels with
the resource to the user's other machines through vault-sync, and a
resource that arrives without one MUST keep its title empty.

#### Scenario: a title is shown in place of the name
- **GIVEN** a resource of a kind that carries a title, with no title
- **WHEN** the user runs `coffer <kind> edit <name> --title "Team search"` and then lists that kind
- **THEN** the list and `coffer <kind> show` print "Team search" where the name was shown, and `--json` carries both `name` and `title`
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
- **AND** `coffer mcp edit` and `coffer mcp add` offer no `--title`, and `coffer skill` offers no `edit`

### Requirement: Converge what Coffer writes outside its database with one reconciler
Everything Coffer keeps true outside its own files — its MCP entry in each
agent's config, the skill links it delivers, a provider connection's projection
into an agent's settings, the memory delivery hook — MUST be converged by one
level-triggered reconciler ([ADR](../../../docs/decisions/one-level-triggered-reconciler-compares-parameters.md)).
Each target MUST state the items it wants with their full parameters, computed
from Coffer's own state, and read what is there into the same shape; a pass
MUST pair the two and treat an item whose parameters differ as drift exactly as
it treats a missing one — presence is how an entry is found, never how it is
judged current. Each target MUST decide every difference by its own direction
policy: repair it, report it, or report that it cannot be repaired right now
(blocked); a difference the policy does not repair MUST be reported, never
written. A pass MUST run at daemon start before the daemon reports ready, every
60 seconds, early for the targets that follow a kind when a resource of that
kind is written, and on demand after a user's own write, a sync round that applied
changes and a feature switch; a lost early start costs at most one period and never
correctness. A target that raises MUST be reported and skipped while the pass
goes on, and a write that raises MUST fail only its own item. Passes MUST NOT
overlap, and a multi-step change a service makes (a provider switch, a sync
round's apply) MUST be able to keep passes out until it is done.

#### Scenario: a changed parameter is drift and is repaired
- **GIVEN** an agent whose Coffer entry is present but carries a parameter this build no longer writes — a hook command with `--agent` instead of `--agent-uid`, or an MCP entry with a shim path an upgrade moved
- **WHEN** a reconcile pass runs
- **THEN** the item is reported as a modification naming the changed parameter and rewritten to the current parameters, every entry that is not Coffer's is left as it was, and the next pass finds nothing

#### Scenario: a target that fails is reported and the pass goes on
- **GIVEN** two targets, one of which cannot read its state
- **WHEN** a pass runs
- **THEN** the failing target is reported with its error and the other target's drift is repaired

#### Scenario: a write brings the next pass forward
- **GIVEN** a target that follows the `agent` kind and one that does not
- **WHEN** an agent resource is written
- **THEN** a pass runs for the first target within moments rather than at the next period, and the second target is not visited by it

### Requirement: Carry a monotonic revision on every resource
Every resource MUST carry an integer revision that is 1 when the resource is
first seen on this machine and grows by one with every change to its file or to
its reach here — config, enabled flag, scope, name, title — whoever made it: a
surface, a hand edit Coffer committed, or a sync checkout. Every change MUST
emit an in-process hint naming the kind, the uid and the new revision, which
only brings the next reconcile pass forward. The revision is derived, never a
key of the file — two machines stamping it would conflict on every edit — and
is kept under `~/.coffer/derived/`; after that directory is deleted every
resource starts again at 1, which costs nothing, because only the in-process
dedupe of hints reads it.

#### Scenario: every write to a resource bumps its revision
- **GIVEN** a newly registered resource at revision 1
- **WHEN** its config, its enabled flag and its title are changed in turn
- **THEN** it reads revision 4, and each write emitted one hint carrying the revision it produced
