# Resource Framework

## Purpose

The resource framework is the kind-agnostic half of Coffer's resource model: the kind
registry and the immutable `uid` identity, the lifecycle surface every kind is managed
through, per-agent reach, the audit log, per-table retention and its background prune,
the cross-kind read of the passes in flight, and the test that the CLI holds only the
commands that need it, each recorded with its reason, while everything else is managed in
the web UI over REST. A user relies on it for one place
that lists everything Coffer holds, one way to turn a thing on or off, one way to say
which agents it reaches where that question applies to the kind at all, one way to
delete it, and one record of what happened — instead of a near-identical surface per
kind in which one of them forgot to audit the change or to release the secret the
deleted thing referenced. Every other spec that registers a kind relies on it for the
contract that kind inherits: schema validation, lifecycle audit and per-table retention.
A further kind is added by writing a `Kind` descriptor and its own surfaces, with no
change to the lifecycle service, the audit service, the retention machinery or the
kind-agnostic routes.

What a kind *is* — an MCP server, an agent, a skill, a channel, a knowledge collection,
a memory partition, a provider connection — belongs to that kind's own spec: transport,
discovery, delivery, projection and conversation are absorbed here in no part. The seven
kinds that exist are contributed by mcp-gateway (`mcp_server`), agent-registry
(`agent`), skill-manager (`skill`), knowledge (`knowledge`), channels (`channel`),
memory (`memory`) and provider-switching (`provider`); `chat` and `sync` are code
packages, not registered kinds. With no kind registered every lifecycle route is a
refusal or an empty list and the audit log is empty, which is what a framework with
nothing to manage should do. *Enforcing* reach is each kind's own seam at its own choke
point, where the asking identity is known (mcp-gateway at the per-session capability
listing, skill-manager at delivery); a second central gate would be unreachable. The
invocation log is mcp-gateway's; it registers here as a prunable table and nothing more.
Whether the passes this spec reports run on a timer is internal-engine's, and what each
pass does is memory's. `GET /api/v1/upkeep/runs`, the read of the passes
in flight, is a live, read-only status the web UI polls so the Memory page's
run-now button shows a pass the timer or another page started as already running; a terminal
reads the same list in `coffer daemon status`. The passes' switches and timers are
changed on the Settings page, not by command.

It is a spec, not a rule in the principles, because it owns state and operable surfaces.
Resource files (`vault/resources/<kind>/<name>.json`, agents under `local/`),
reach (`local/reach.json`), the `audit_log` table in `runs.db` and the retention
policies (`local/retention.json`) are its state: every kind writes the audit
log, and this spec seeds, reads, configures and prunes it. Its route family is
`/api/v1/resources*`, `/api/v1/audit`, `/api/v1/retention/*`, `/api/v1/upkeep/runs`
and the daemon-wide change feed `/api/v1/events`;
its packages are `domain/{resource,scope,audit,retention}.py`, the kind-agnostic
services beside them in `application/`, and their surfaces; an import-linter contract
fences the core off from every kind; and it has ADRs of its own
([The Sidebar Is Grouped by What the Person Comes to Do: Agents, Run, Capabilities, Context, System](../../../docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md),
[Resource Framework Upfront](../../../docs/decisions/resource-framework-upfront.md),
[A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](../../../docs/decisions/identity-is-the-uid-inside-the-file.md),
[Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)). It is one
behaviour — what happens to a managed thing between the moment a kind creates it and the
moment it is deleted, recorded while it happens — and it is independently operable:
the kind-agnostic `/api/v1/resources*`, `/api/v1/audit` and `/api/v1/retention/*` routes
against a running daemon, `coffer log audit` for a terminal, and the Activity page's audit
tab and the Data settings section's retention table (web-ui's pages) over the same records. An earlier audit rejected it
when it owned only a dispatch seam; that the kind-agnostic surface has no create verb and
that an empty registry answers every lifecycle route with a refusal are still true (see
"Keep creation a per-kind seam"). The daemon it is mounted in — port, discovery file,
token, loopback posture, `Host` guard — is daemon's; the encrypted store behind a
resource's secret refs is secrets', and this spec only probes refs before a
write and releases orphaned ones after a delete, never holding a key. Coffer is a
single-user personal tool with no multi-tenant or remote-access requirement beyond the
token gate.

## Requirements

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

A kind MAY declare that its resources cannot be disabled — `knowledge`, `memory` and `agent` do.
Every resource of such a kind MUST read as enabled, whatever its stored reach holds (a resource disabled before its kind became non-toggleable reads enabled from then on), and enabling or disabling one through the
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

#### Scenario: every kind answers the same lifecycle routes
- **GIVEN** one registered kind that can be disabled, supports reach and carries a title, and one that does none of these
- **WHEN** each resource is read with `GET /api/v1/resources/{uid}`, given a new description with `PATCH /api/v1/resources/{uid}`, and sent a non-null scope with `PUT /api/v1/resources/{uid}/scope`, a title and `POST /api/v1/resources/{uid}/disable`
- **THEN** both kinds answer the read and the description update through the same routes, and the kind that supports no reach, carries no title or cannot be disabled refuses that request and changes nothing
- **AND** the first kind's disable changes it through the kind-agnostic route and is audited

#### Scenario: a non-toggleable kind refuses to be disabled
- **GIVEN** a `knowledge` collection, a `memory` partition and an `agent`
- **WHEN** each is disabled through `/api/v1/resources` and read back
- **THEN** all three requests are refused with 409 `RESOURCE_NOT_TOGGLEABLE`
- **AND** all three still read back enabled, with `toggleable` false
- **AND** an agent whose stored reach says off, left from before the kind was non-toggleable, reads back enabled

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
allow-list of agents, `null` meaning every agent, otherwise a non-empty list of them
([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)) — and MUST
serve it for every kind through one kind-agnostic pair of routes rather than per kind,
reporting whether the kind supports reach at all so a client can render the right
control without knowing the kinds itself. A reach is machine-local: it is kept, with the
resource's `enabled` flag, in this machine's reach record `~/.coffer/local/reach.json`, keyed
by the resource's uid, and never in the resource's own file, so a reach write makes no vault
commit; a resource with no record there is enabled and unscoped
([vault-sync](../vault-sync/spec.md) "Keep reach machine-local").

There is no empty list: a resource reaches nobody only by being switched off (its
`enabled` flag, which every toggleable kind carries, a channel included), and being off
keeps the agents that were chosen. A scope of `{"agents": []}` MUST be refused on every
kind, on the scope route and on every other write that carries a scope, with `422`
`SCOPE_INVALID`. A non-null reach on a kind that declares none, and a payload carrying a property the
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

#### Scenario: a resource's reach is written and read through the scope routes
- **GIVEN** a resource of a kind that supports reach, and a registered agent
- **WHEN** a client sends `PUT /api/v1/resources/{uid}/scope` naming that one agent, then reads `GET /api/v1/resources/{uid}/scope`, then sends `PUT` again naming every agent
- **THEN** the read returns the one agent, and after the second `PUT` the reach is every agent again
- **AND** each write is audited as a scope update, and a kind that supports no reach refuses a non-null scope

#### Scenario: an empty agent list is refused
- **GIVEN** a resource of a kind that supports reach, reaching one agent
- **WHEN** a client sends `PUT /api/v1/resources/{uid}/scope` with `{"agents": []}`
- **THEN** the write is refused with `422` `SCOPE_INVALID` and the reach is unchanged
- **AND** the same list on any other write that carries a scope is refused the same way, and switching the resource off is the way to reach nobody

#### Scenario: a reach record left with no agent is switched off at startup
- **GIVEN** a machine's reach record holding `{"enabled": true, "agents": []}` for one resource and `{"enabled": false, "agents": []}` for another, written before an empty list was refused
- **WHEN** the daemon starts
- **THEN** both records read `enabled` false with no agent restriction (`agents` null), so turning either on gives it to every agent
- **AND** a second start changes nothing

#### Scenario: reach is kept on this machine, not in the resource's file
- **GIVEN** a registered resource
- **WHEN** it is disabled, and later this machine's reach record is deleted and the resource is read again
- **THEN** the disable made no vault commit and the reach record holds the resource's uid with `enabled` false, while the resource's file carries neither `enabled` nor a scope
- **AND** with the record gone the resource reads as enabled and unscoped

### Requirement: Run the kind's cleanup before a deletion completes
Deleting a resource MUST run the kind's own cleanup hook while the resource can still be
resolved, and a hook that fails MUST abort the deletion rather than leave a half-deleted
thing — a resource is never left registered with its on-disk half already gone. To keep that
true when the write itself would be refused, the framework MUST first confirm the resource's
file can be written now (not read-only, no unsettled edit on disk) before it runs the hook. Rows a
kind owns MUST cascade; history MUST NOT — the audit log and the invocation log outlive
the resource they describe. Secrets that no remaining resource cites MUST be
released, and a failure to release MUST NOT turn an already-completed deletion into a
caller-facing error; the store behind those refs is the secrets
spec's.

#### Scenario: deleting a resource runs its kind's cleanup and keeps its history
- **GIVEN** a resource with audit history, whose kind supplies a cleanup hook, and whose config cites a secret that nothing else cites and whose release fails,
- **WHEN** the user deletes it,
- **THEN** the hook runs while the resource can still be read back, the resource is gone, and the deletion returns without an error,
- **AND** the audit entries written before the deletion are still readable for that resource,
- **AND** when the kind's cleanup hook raises instead, the deletion is refused with that error, the resource is still registered, and no deletion audit entry is written.

#### Scenario: a file that cannot be written stops a deletion before the cleanup runs
- **GIVEN** a resource whose file has an edit on disk that is not settled yet, and a kind with a cleanup hook,
- **WHEN** the user deletes it,
- **THEN** the deletion is refused as stale, the hook never ran, and the resource is still registered.

### Requirement: Let a kind refuse a deletion before anything is torn down
A kind MAY supply a **pre-write delete guard**: given the resource a delete names, it
refuses the deletion before anything is torn down. The framework MUST run it after
resolving the resource and **before** the kind's cleanup hook (see "Run the kind's
cleanup before a deletion completes"), MUST turn its refusal into the caller's error
unchanged, and MUST leave the resource exactly as it was — no link removed, no row
touched, no lifecycle audit entry for a deletion that did not happen. The refusal MUST be
identical whichever door the delete came through, the kind's own route or the
kind-agnostic one, which is the whole reason it belongs here: a guard written into one
route is a guard the second route silently lacks, and the kind-agnostic surface exists
precisely so a caller need not know the kind.

It is a **validator**, alongside the registration validators (see "Validate every
registration and persist nothing on failure"), rather than a rejection raised from
inside `on_delete` — that hook is a *reaction to an already-decided delete*, run to tear
the kind's own half down, so a kind refusing from in there refuses only after the
framework has committed to the operation and the caller has been told it is under way.
The guard is the seam for a resource whose existence is not the owner's to decide: the
only one today is a builtin skill, whose master folder the next boot writes back
([skill-manager](../skill-manager/spec.md) "Refuse deleting a builtin skill").

#### Scenario: a kind refuses a deletion before anything is torn down
- **GIVEN** a registered kind supplying a pre-write delete guard, and one resource of that kind the guard refuses,
- **WHEN** the delete is attempted through the kind's own route and through the kind-agnostic one,
- **THEN** both are refused with the same error the guard raised, carrying the same code and the same status,
- **AND** the kind's cleanup hook never ran, the resource and everything it owns are exactly as they were, and no deletion audit entry was written,
- **AND** a resource of the same kind the guard does not refuse still deletes normally.

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

An entry's `details` MUST say what changed, not only that something did: a value that
changed carries its value before and after (a name, a scope, a switch, a retention period,
a provider), an action over several things names them or counts them (the agents, files,
skills or pages it touched), and an action with a cause the caller knows names it. A text
edit to a vault file Coffer writes or commits — a knowledge page, a memory note, a skill
file — carries a unified diff of the edit, cut at 8 KB (UTF-8) with `diff_truncated: true`
and its size before the cut (`diff_bytes`). `details` MUST NOT hold a secret value: a
secret is named by its reference, and a resource's configuration passes its kind's
redactor first. Every audited event is also written to `daemon.log` as one `coffer.<event>`
line carrying the actor, the resource and the entry's `details`, cut at 2 KB with
`details_truncated: true`.

#### Scenario: audit lifecycle changes
- **GIVEN** the user performs any add / enable / disable / update / delete on a server or capability,
- **WHEN** they open the Activity page's audit tab or run `coffer log audit`,
- **THEN** they see one row per change with actor, timestamp, and a payload describing what changed.

#### Scenario: a rename and a knowledge edit say what changed
- **GIVEN** a skill renamed from `notes` to `journal`, and a knowledge page whose one line was edited
- **WHEN** the audit log is read
- **THEN** the rename's details carry `notes` before and `journal` after
- **AND** the edit's details carry a unified diff with the line removed and the line added

#### Scenario: the daemon log line carries the event's details
- **GIVEN** a retention period changed from 30 to 7 days
- **WHEN** `daemon.log` is read
- **THEN** its `coffer.retention_updated` line carries the actor, the table and both periods

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

#### Scenario: set a retention period and prune now over REST
- **GIVEN** the invocation log holds entries older and newer than 7 days
- **WHEN** a client sends `PATCH /api/v1/retention/policies/mcp_invocations` setting 7 days and then `POST /api/v1/retention/prune` naming that table
- **THEN** `GET /api/v1/retention/policies` reports 7 days for it, the policy change is audited, and the prune answers how many entries it removed
- **AND** only entries older than 7 days are gone

#### Scenario: a shorter period is previewed before it is saved
- **GIVEN** the audit log holds 4 entries, 2 of them older than 7 days
- **WHEN** the web UI asks `GET /api/v1/retention/policies/audit_log/preview?days=7`
- **THEN** the answer carries 4 entries now and 2 to delete
- **AND** asking again answers 4 entries now: nothing was deleted

### Requirement: Retain attachments on an adjustable policy
Attachment files MUST NOT accumulate without bound, and how long they are kept MUST be the
user's to choose. One retention policy named `attachments` covers the directory that holds
them — `~/.coffer/content/channel-media` (what a channel downloaded). It is listed by
`GET /api/v1/retention/policies` and set by `PATCH /api/v1/retention/policies/attachments`
like any table policy (a whole number of days, or `forever`; the change is audited), and
its default is 30 days, so a user who never chose keeps today's behaviour. The policy
is seeded at daemon start with the other policies and stored beside them. A file is past the
window when its mtime is older than the window; there is no size cap and no reference
check. On the retention cadence and on a full prune, files past the window are deleted
from that directory and the prune answers how many files it removed under `attachments`;
under `forever` nothing is deleted. A prune naming `attachments` sweeps only attachments.
`GET /api/v1/retention/policies/attachments/preview?days=<n>` counts the files held now and how many are older than `n` days and deletes nothing. A sweep that
fails is logged and skipped, never stopping the table prune.

#### Scenario: attachments are kept for thirty days unless the user chose otherwise
- **GIVEN** a fresh daemon and attachment files in the channel media directory, one of them 31 days old
- **WHEN** a full retention prune runs
- **THEN** `GET /api/v1/retention/policies` lists `attachments` at 30 days
- **AND** the 31-day-old file is deleted, the rest are kept, and the prune answers one file under `attachments`

#### Scenario: a changed attachments window decides what is deleted
- **GIVEN** a channel-downloaded file 10 days old and the `attachments` policy at 30 days
- **WHEN** a client sets the policy to 7 days
- **THEN** the preview for 7 days counts the file as one to delete before and nothing is deleted by the preview
- **AND** a prune naming `attachments` deletes the file

#### Scenario: attachments kept forever are never swept
- **GIVEN** the `attachments` policy set to `forever` and an attachment 400 days old
- **WHEN** a full retention prune runs
- **THEN** the file is kept and the prune answers no files removed under `attachments`

### Requirement: Retain skill working files on an adjustable policy
The logs, operation journals and temporary files a skill's scripts generate MUST have one
shared place and MUST NOT accumulate without bound: `~/.coffer/skill-data/<skill-name>/`,
outside the vault so they never sync, named by `coffer path skill-data`. One retention policy
named `skill_data` covers the whole directory. It is listed by `GET /api/v1/retention/policies`
and set by `PATCH /api/v1/retention/policies/skill_data` like any other policy (a whole number
of days, or `forever`; the change is audited), its default is 30 days, and it is seeded at
daemon start. A file is past the window when its mtime is older than the window, wherever it
sits under the directory, since skills keep subfolders. On the retention cadence and on a full
prune, files past the window are deleted, directories left empty are removed (never
`skill-data` itself), and the prune answers how many files it removed under `skill_data`;
under `forever` nothing is deleted. A prune naming `skill_data` sweeps only it, a symlink is
neither followed nor deleted, and a sweep that fails is logged and skipped. `GET
/api/v1/retention/policies/skill_data/preview?days=<n>` counts the files held now and how many
are older than `n` days, and deletes nothing.

#### Scenario: skill working files are swept recursively and kept thirty days by default
- **GIVEN** a fresh daemon and `skill-data/alpha/logs/run.log` 31 days old, `skill-data/alpha/journal.txt` 2 days old and `skill-data/beta/tmp.bin` 40 days old
- **WHEN** a full retention prune runs
- **THEN** `GET /api/v1/retention/policies` lists `skill_data` at 30 days
- **AND** the two old files are deleted, the recent one is kept, and the prune answers two files under `skill_data`

#### Scenario: a sweep removes emptied folders but never the root or a symlink
- **GIVEN** `skill-data/beta/` holding only a file past the window, `skill-data/gamma` a symlink to a directory outside it, and a file there past the window
- **WHEN** a prune naming `skill_data` runs
- **THEN** `skill-data/beta/` is removed, `skill-data` itself and the symlink remain, and the file behind the symlink is untouched
- **AND** the prune answers only `skill_data`

#### Scenario: skill working files kept forever are never swept
- **GIVEN** the `skill_data` policy set to `forever` and a file 400 days old under `skill-data`
- **WHEN** a full retention prune runs
- **THEN** the file is kept and the prune answers no files removed under `skill_data`

#### Scenario: the skill working files preview counts files and deletes none
- **GIVEN** the `skill_data` policy at 30 days and four files under `skill-data`, two of them older than 7 days
- **WHEN** a client asks for the preview for 7 days
- **THEN** the answer carries 4 now and 2 to delete, and every file is still there

### Requirement: Report the passes in flight in one cross-kind read
The system MUST answer, in one cross-kind read, which long passes this
daemon is running right now — memory's aggregate and distil passes, each named by its kind, its target and when it started, and, for a run that works through several items one pass at a time, how many of them it has done of how many —
so that a surface can tell whether a pass is under way without every kind growing a
near-identical endpoint of its own. The read MUST start nothing, and the registry MUST
NOT outlive the process: a restart ends any pass it was running and the list comes back
empty, which is the truth rather than a lost record. Whether a pass runs on a timer at
all is internal-engine's; what a pass *does* is its own kind's. The read is served over
REST (`GET /api/v1/upkeep/runs`) and on the command line as the "passes in flight" section
of `coffer daemon status`, which prints the same list, says so when nothing is running, and
carries the list under `--json`.

#### Scenario: the daemon names the passes in flight
- **GIVEN** a long pass over one memory partition is running,
- **WHEN** any surface reads the in-flight list,
- **THEN** that pass is named with its kind, its target and when it started,
- **AND** a target absent from the list has no pass running, and the read starts nothing.

#### Scenario: the command line reads the passes in flight
- **GIVEN** passes over two memory partitions are running
- **WHEN** the operator runs `coffer daemon status --json`, and again once both have ended
- **THEN** the first lists both passes with their kind, target and start time, oldest first,
- **AND** the second lists none, and the table form of `coffer daemon status` says that no pass is running.

### Requirement: Carry an optional editable title on the kinds that have one
A resource of a kind that carries a title MUST carry an optional **`title`**: free text of at
most 80 characters that a person chooses for display, separate from the resource's `name`. The
kinds with a title are those whose name is a label a person chose — `provider` and `channel`.
`agent`, `mcp_server`, `skill`, `memory` and `knowledge` carry none: each is shown by its fixed
name — a memory partition by its name, a knowledge collection by its folder, with an editable description instead
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
- **GIVEN** a registered MCP server, a registered skill, a registered agent and a memory partition
- **WHEN** the user submits a title for each through the kind-agnostic update, and registers an MCP server with a title
- **THEN** each is refused as a validation error (422) and nothing is stored
- **AND** each of those resources is still shown by its fixed name

### Requirement: Read the audit log from the command line
The system MUST let a terminal read the audit log with `coffer log audit`, over the same route
the web UI reads (`GET /api/v1/audit`). It MUST take the filters that route affords,
`--kind`, `--name`, `--event-type`, `--since` and `--limit`, and the route's cursor as
`--cursor`, and MUST print the entries newest first. Each entry MUST show its time, actor,
event type, and the label the resource carried at that moment; when more entries follow the
page, the output MUST end with the `--cursor` value that reads the next one. With `--json` it
MUST print the route's answer — its entries and its `next_cursor` — as one parseable document
with no human-readable framing.

#### Scenario: the command line reads the audit log
- **GIVEN** the user has disabled a resource and then changed another resource's title
- **WHEN** they run `coffer log audit --limit 2`, and then `coffer log audit --kind <kind> --json`
- **THEN** the first prints both changes newest first, each with its time, actor, event type and label
- **AND** the second prints a parseable JSON document holding only that kind's entries

#### Scenario: the command line pages the audit log by cursor
- **GIVEN** three audit entries
- **WHEN** the user runs `coffer log audit --limit 2 --json` and then `coffer log audit --limit 2 --cursor <next_cursor> --json` with the cursor the first printed
- **THEN** the first prints the two newest entries and a `next_cursor`, and the second prints the oldest entry and a `null` `next_cursor`

### Requirement: Change the daemon's pre-bind settings through one key-value command
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

### Requirement: Locate the log files with coffer path
The system MUST print the absolute path of the daemon's log directory and of the `daemon.log` in it
with `coffer path logs`, so that a person or an agent can read the log files when the daemon will not
start, and the absolute path of `~/.coffer/skill-data` with `coffer path skill-data`, so that a
skill's script finds where its working files go (see "Retain skill working files on an adjustable
policy"). `logs` and `skill-data` MUST be the only targets: every other file Coffer keeps as a plain
file is named by the web UI, by its owning spec or by a hand-off prompt, and is read and edited with
the reader's own tools. With `--json` the command MUST print the paths as one JSON object keyed by
what each path is. The command MUST need no daemon, MUST create nothing and change nothing, and a
target other than those two MUST exit non-zero as an unknown target.

#### Scenario: path logs names the log files and refuses other targets
- **GIVEN** a Coffer home with its log directory
- **WHEN** the user runs `coffer path logs`, `coffer path logs --json`, and `coffer path` with any other target
- **THEN** the first prints the absolute path of the log directory and of `daemon.log`, and the second prints a JSON object holding both
- **AND** the third exits non-zero as an unknown target, and nothing on disk was created or changed

#### Scenario: path skill-data names the skill working folder
- **GIVEN** a Coffer home with no `skill-data` directory yet
- **WHEN** the user runs `coffer path skill-data` and `coffer path skill-data --json`
- **THEN** the first prints the absolute path of `~/.coffer/skill-data` and the second a JSON object holding it
- **AND** the directory was not created

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

### Requirement: Preview a reconcile pass without writing anything
The reconciler MUST offer a dry-run that computes the same plan a pass would
carry out and writes nothing: no file, no database row, no audit event and no
hint, and it MUST NOT count as the last pass.

#### Scenario: a dry-run pass writes nothing under the home directory
- **GIVEN** an isolated home whose agents carry drift for several targets, and Coffer's database in that home
- **WHEN** the plan is computed
- **THEN** the plan lists the drift, and every file under the home — path, size, content and modification time — and the audit log's row count are identical before and after

### Requirement: Record a reconcile repair's audit in the same call as its write
A repair MUST write through the kind's own marker-scoped, atomic, backed-up
writer and then record its audit event — actor `system` for a pass Coffer ran
itself, `sync` for an import's pass, `system:features` for a switch's pass, and
the caller for items a person applied — before the call returns. If the event
cannot be recorded, the reconciler MUST restore what the write replaced (the
content its backup holds, or no file where there was none) and report the item
as failed, so the next pass retries it. No transaction across the file and the
database is claimed.

#### Scenario: a repair whose audit cannot be recorded is put back
- **GIVEN** a stale entry the pass would repair, and an audit log that refuses writes
- **WHEN** the pass runs
- **THEN** the item is reported failed and the agent's file holds exactly what it held before the pass

### Requirement: Serve the drift plan and apply chosen items over REST
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
running, model provider connections that an agent or Coffer's speech to text
runs on whose endpoint does not answer (`provider_unreachable`, offering
`check` through `POST /api/v1/providers/{uid}/check`, run in place) or refuses
the key (`provider_key_rejected`, offering `replace_key`, which opens the
connection's page) — read from the kept health verdict
([provider-switching](../provider-switching/spec.md) "Know each connection's
health without opening it"), only while `models` is on — and commands a skill
requires that are missing, older than a skill's minimum or not logged in (kind
`cli`, the command as the uid). Each item MUST carry its kind, the resource's uid and title, a stable
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

#### Scenario: a connection an agent runs on that fails is listed
- **GIVEN** Claude Code runs on connection A, whose verdict is `unreachable`, and connection B, which nothing runs on, whose verdict is `key_rejected`
- **WHEN** the attention list is read
- **THEN** it carries one `provider` item for A with reason `provider_unreachable` whose action is `check` through `POST /api/v1/providers/{uid}/check`, and none for B
- **AND** once A's verdict is `key_rejected`, its item reads `provider_key_rejected` and offers `replace_key`

### Requirement: Announce every write to a resource as an in-process hint
Every change to a resource MUST emit an in-process hint naming the kind, the uid and
whether the resource still exists (`upsert` or `delete`) — whoever made the change: a
surface, a hand edit Coffer committed, or a sync checkout. The hint only brings the next
reconcile pass forward for the targets that follow that kind. No revision number is kept:
nothing compares one, and a hint is an accelerator that is cheap to repeat. A resource's
`updated_at` is the modification time of its file on this machine, so reading a resource
writes nothing.

#### Scenario: every write to a resource is hinted
- **GIVEN** a newly registered resource
- **WHEN** its config, its enabled flag, its title, its scope and its name are changed in turn, and it is then deleted
- **THEN** each write emitted one hint for that uid, the last one marked `delete`
- **AND** a read of the resource emitted none

### Requirement: Announce every change on one daemon-wide event stream
`GET /api/v1/events` MUST be one Server-Sent Events stream for the whole
daemon, gated by the token header like every other management call, so a
client reads it with `fetch` rather than `EventSource`. Each `change` event
MUST carry an envelope `{seq, kind, id, op}` and an SSE id that names both
the daemon run and the `seq`, because `seq` starts again at 1 on every run:
`seq` grows by one per event across the daemon run, `kind` is the resource
kind or `attention`, `id` is the resource's uid (none for `attention`), and `op` is
`upsert` or `delete`. Every resource write through the framework MUST produce
one envelope, and so MUST every change in what the attention list reports. An
envelope is an invalidation hint only: it MUST NOT carry the resource's state,
and a client refetches through the typed endpoints. The daemon MUST keep a
bounded buffer of recent envelopes: a client that reconnects with
`Last-Event-ID` MUST receive every envelope after that `seq` still in the
buffer, in order, and then live ones; when the buffer cannot cover the gap —
the `seq` is older than the buffer's oldest, or is not one this daemon run has
issued — the stream MUST send one `resync` event before going live, telling the
client to refetch everything. While nothing changes the stream MUST send a
`heartbeat` event carrying the current head `seq` at a fixed interval.

#### Scenario: a resource write is announced as an invalidation hint
- **GIVEN** a client reading the event stream
- **WHEN** a resource is disabled and then deleted
- **THEN** the client receives two `change` events for that uid, an `upsert` for the disable and then a `delete`, with consecutive `seq` values
- **AND** neither envelope carries any field of the resource beyond its kind and uid

#### Scenario: a reconnecting client resumes after the last event it saw
- **GIVEN** a client that saw `change` events up to `seq` n and disconnected, after which two more resources were written
- **WHEN** it reconnects with the SSE id of event n as `Last-Event-ID`
- **THEN** it receives exactly the two missed envelopes, `seq` n+1 and n+2, before any live event, and no `resync`

#### Scenario: a client the buffer cannot cover is told to resync
- **GIVEN** more writes since a client's last `seq` than the buffer holds, or a `Last-Event-ID` this daemon run never issued — an earlier run's included, even when its `seq` is one this run has reached
- **WHEN** the client reconnects with that `Last-Event-ID`
- **THEN** the first event it receives is `resync`, and live `change` events follow it

#### Scenario: an attention change is announced on the event stream
- **GIVEN** a client reading the event stream and an attention list with no items
- **WHEN** something starts needing a person, so the attention list gains an item
- **THEN** the client receives a `change` event of kind `attention` with no id, and no attention item in it

#### Scenario: an idle event stream carries heartbeats
- **GIVEN** a client reading the event stream while nothing changes
- **WHEN** the heartbeat interval passes
- **THEN** the client receives a `heartbeat` event carrying the current head `seq`

#### Scenario: the event stream requires the token
- **GIVEN** a running daemon
- **WHEN** a client opens `GET /api/v1/events` without the `X-Coffer-Token` header
- **THEN** the request is refused `401 UNAUTHENTICATED` and no stream is opened

### Requirement: Page growing lists by an opaque cursor
A list that can grow while it is being read — the audit log, the MCP
invocation log, an agent's native sessions and the chat conversation
listing — MUST page by an opaque cursor rather than by `offset`. A request
MUST take `limit` and an optional `cursor`; the answer MUST carry
`next_cursor`, which is `null` exactly when no row follows the page. The list
MUST have a stable order with a unique tie-break, and the page read with a
cursor MUST hold the rows that follow the cursor's row in that order, so a row
written at the head between two reads neither repeats an earlier row nor
skips a later one. A cursor MUST be bound to the list and the filters it was
issued for: one that does not decode, or that is sent to another list or with
other filters, MUST be refused `400 CURSOR_INVALID`.

#### Scenario: a page read after new rows arrive neither repeats nor skips
- **GIVEN** an audit log of five entries read with `limit=2`, and a new entry recorded after the first page was read
- **WHEN** the next two pages are read with each answer's `next_cursor`
- **THEN** together the three pages hold the five original entries exactly once each, newest first, and the new entry is not among them

#### Scenario: the last page carries no next cursor
- **GIVEN** an audit log of three entries
- **WHEN** it is read with `limit=3`
- **THEN** the answer holds all three and its `next_cursor` is `null`

#### Scenario: a malformed or foreign cursor is refused
- **GIVEN** a cursor issued for the audit log filtered by one kind
- **WHEN** it is sent with another kind's filter, and a string that is not a cursor is sent as `cursor`
- **THEN** both requests are refused `400 CURSOR_INVALID`

### Requirement: Count a log's matching rows beside each page
The audit log (`GET /api/v1/audit`) and the MCP invocation log (`GET /api/v1/mcp/invocations`,
`GET /api/v1/resources/mcp_server/{uid}/invocations`) answers MUST carry `total`: the number of rows
that match the request's filters across every page. The cursor and `limit` MUST NOT change it, so a
client can say how many entries a filtered view holds without paging through all of them. It is
counted with the same filters as the page (see "Page growing lists by an opaque cursor"), so the two
cannot disagree about which rows are in the view.

#### Scenario: a page carries the count of every matching row
- **GIVEN** an audit log of five entries, three of them about one kind
- **WHEN** it is read filtered to that kind with `limit=2`, and then with the answer's `next_cursor`
- **THEN** both answers carry `total` 3

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

### Requirement: Retain config backups on an adjustable policy
The copies Coffer makes of an agent's own config file before it rewrites or deletes it MUST
live in Coffer's own folder and MUST NOT accumulate without bound: `~/.coffer/config-backups/`,
outside the vault so they never sync. Each config file has one folder there, named
`<file name>-<12 hex digits of the sha-256 of its absolute path>` so that two files with the same
name stay apart, and each backup in it is named by the UTC time it was taken
(`YYYYMMDDTHHMMSSffffffZ`) with the file's own extension. One retention policy named
`config_backups` covers the whole directory. It is listed by `GET /api/v1/retention/policies`
and set by `PATCH /api/v1/retention/policies/config_backups` like any other policy (a whole
number of days, or `forever`; the change is audited), its default is 30 days, and it is seeded
at daemon start. A backup is past the window when its modification time is older than the
window. On the retention cadence and on a full prune, backups past the window are deleted
EXCEPT the newest backup of each config file, which is kept however old it is so that an undo
of the last write is always possible; folders left empty are removed (never `config-backups`
itself), and the prune answers how many files it removed under `config_backups`; under
`forever` nothing is deleted. A prune naming `config_backups` sweeps only it, a symlink is
neither followed nor deleted, and a sweep that fails is logged and skipped. `GET
/api/v1/retention/policies/config_backups/preview?days=<n>` counts the files held now and how
many a window of `n` days would delete (the newest of each file excluded), and deletes nothing.

#### Scenario: old config backups are swept but each file's newest is kept
- **GIVEN** a fresh daemon, three backups of one config file 40, 35 and 2 days old, and two backups of another 90 and 60 days old
- **WHEN** a full retention prune runs
- **THEN** `GET /api/v1/retention/policies` lists `config_backups` at 30 days
- **AND** the 40 and 35 day old backups of the first file and the 90 day old backup of the second are deleted, the 2 day old one and the 60 day old one (the newest of its file) are kept, and the prune answers three files under `config_backups`

#### Scenario: config backups kept forever are never swept
- **GIVEN** the `config_backups` policy set to `forever` and two backups of one file, 400 and 500 days old
- **WHEN** a full retention prune runs
- **THEN** both are kept and the prune answers no files removed under `config_backups`

#### Scenario: the config backups preview counts files and deletes none
- **GIVEN** the `config_backups` policy at 30 days and five backups of one file, aged 1, 3, 10, 20 and 40 days
- **WHEN** a client asks for the preview for 7 days
- **THEN** the answer carries 5 now and 3 to delete, and every file is still there

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
ran out, with 1 for any other failure (a switched-off feature among them). An
operation that runs on after its request returns offers a status command and a
way to wait for its result.

The contract MUST hold on every path, not only the daemon's answer: a name the
command resolves to nothing, a refusal read by an older hand-written reader, and
a daemon that cannot be started each print the same `--json` error envelope. A
file or standard input that cannot be read or is not UTF-8 text exits 6 with
`CLI_INVALID_INPUT` before anything is sent or started. An answer that waits on
approvals exits 9 whether it names them as a list (`pending_approvals`,
`approval_ids`), as `pending_approval_id`, or as an `approval_id` beside a
`pending` state. A test command whose answer reports `ok: false` prints the
whole answer and exits 7. `coffer --verbose` adds the request behind a daemon's
refusal (method, path, status; never a header) to the text or the envelope.
Every management command MUST be reachable from the visible help; only a
command a program runs (`memory hook`, `proxy token`) is hidden. The rule is policy over every spec
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

#### Scenario: every failure path keeps the JSON error contract
- **GIVEN** a command run with `--json`
- **WHEN** a name it resolves matches nothing, an older reader's route refuses, a `--data @file` is not UTF-8, or a test's answer says `ok: false`
- **THEN** the first three print one `{"error", "exit_code"}` object on standard error and exit 4, 6 and 6 with nothing sent for the file, and the last prints the answer and exits 7

#### Scenario: a single pending approval exits 9
- **GIVEN** a change whose answer names one approval as `pending_approval_id`, or as `approval_id` beside a `pending` state
- **WHEN** the command that made it ends
- **THEN** it exits 9 printing `next: coffer approval approve <id>`

#### Scenario: management commands are visible in help
- **GIVEN** the CLI's live command tree
- **WHEN** each registry command is looked up from the root help
- **THEN** no management command sits under a hidden group or is hidden itself, and the only hidden leaves are the program-run `memory hook` and `proxy token`

#### Scenario: a plain file is read with the reader's own tools
- **GIVEN** a plain file that its owning spec declares directly readable or editable
- **WHEN** a person or an agent needs it
- **THEN** it is read and edited with their own tools at the path the web UI, the spec or the hand-off prompt names, and no command reads or writes its content
- **AND** `coffer path logs` and `coffer path skill-data` still say where the log files and a skill's working files are

#### Scenario: a kept command surfaces the daemon's errors
- **GIVEN** any failure surfaced by the management API,
- **WHEN** it reaches a command that calls the daemon,
- **THEN** the user sees an actionable message and a non-zero exit code; `--verbose` adds the request behind it (method, path and status)
