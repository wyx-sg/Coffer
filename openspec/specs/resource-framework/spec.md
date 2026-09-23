# Resource Framework

## Purpose

The resource framework is the kind-agnostic half of Coffer's resource model: the kind
registry and the immutable `uid` identity, the lifecycle surface every kind is managed
through, per-agent reach, the audit log, per-table retention and its background prune,
the cross-kind read of the passes in flight, and the test that every management
operation is reachable from both REST and the CLI. A user relies on it for one place
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
pass does is memory's and knowledge's.

It is a spec, not a rule in the principles, because it owns state and operable surfaces.
`audit_log` and `retention_policies` are its tables: every kind writes the first, and
this spec seeds, reads, configures and prunes both. Its route family is
`/api/v1/resources*`, `/api/v1/audit`, `/api/v1/retention/*` and `/api/v1/upkeep/runs`;
its packages are `domain/{resource,scope,audit,retention}.py`, the kind-agnostic
services beside them in `application/`, and their surfaces; an import-linter contract
fences the core off from every kind; and it has ADRs of its own
([Everything Is a Resource Kind](../../../docs/decisions/everything-is-a-resource-kind.md),
[Resource Framework Upfront](../../../docs/decisions/resource-framework-upfront.md),
[Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md),
[Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)). It is one
behaviour — what happens to a managed thing between the moment a kind creates it and the
moment it is deleted, recorded while it happens — and it is independently operable:
`coffer resource`, `coffer scope`, `coffer audit` and `coffer retention` against a
running daemon, with the Activity page's audit tab and the Data settings section's
retention table (web-ui's pages) over the same records. An earlier audit rejected it
when it owned only a dispatch seam; that `coffer resource` has no create command and
that an empty registry answers every lifecycle route with a refusal are still true (see
"Keep creation a per-kind seam"). The daemon it is mounted in — port, discovery file,
token, loopback posture, `Host` guard — is daemon's; the encrypted store behind a
resource's credential refs is credentials', and this spec only probes refs before a
write and releases orphaned ones after a delete, never holding a key. Coffer is a
single-user personal tool with no multi-tenant or remote-access requirement beyond the
token gate.

## Requirements

### Requirement: Address every resource by an immutable uid through one kind-agnostic surface
The system MUST model every managed thing as a *resource* identified by an immutable,
opaque **`uid`** ([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)),
and MUST expose one kind-agnostic surface — `/api/v1/resources*` and `coffer resource` —
to list, read, update, enable, disable and delete any of them without the caller knowing
the kind. Every route and every stored reference from one resource to another MUST
address the uid. A uid MUST be minted once and never reused, and MUST be the same value
on every machine that holds the resource, so that two machines can tell "the same thing"
from "a different thing with the same name" without asking each other.

A kind exists only because the composition root registered it; a request naming an
unregistered kind MUST be refused rather than bringing one into being.

#### Scenario: the kind-agnostic surface serves every kind
- **GIVEN** resources of more than one registered kind exist,
- **WHEN** the user lists resources without naming a kind, reads one back by its uid, then disables and re-enables it,
- **THEN** every kind's resources appear in the one list, each carrying its uid, kind, name, config, reach and enabled flag,
- **AND** the enable/disable round trip is served by the same route for every kind, and each step is audited.

### Requirement: Validate every registration and persist nothing on failure
The system MUST validate every registration against its kind's schema and the kind's own
pre-write validators, MUST reject a duplicate name within a kind, and MUST persist
nothing on a validation failure — not a row with a rejected config, not a half-written
reach, not an audit entry for a change that did not happen, and no kind-owned side
effect: a registration that fails validation leaves the database exactly as it was
before the attempt. This is the contract every kind inherits, which is why it is stated
once here rather than once per kind.

#### Scenario: reject an invalid registration and persist nothing
- **GIVEN** a registered kind with a config schema,
- **WHEN** a registration arrives whose config fails that schema, or whose name is already taken within the same kind,
- **THEN** it is refused with a message naming the cause — a validation error for the schema failure, a conflict for the duplicate,
- **AND** no resource row, no audit entry and no kind-owned side effect is left behind.

### Requirement: Keep creation a per-kind seam
Creation is a per-kind seam and MUST stay one. The kind-agnostic create route MUST
accept only kinds that declare themselves creatable through it, and MUST refuse a kind
that owns a creation invariant beyond config validation — a skill's master folder, an
agent's on-disk detection — so that such a kind is registered through its own surface,
which can hold that invariant. There is deliberately no `coffer resource create`: a
generic create would have to guess a config shape it cannot know. What this spec owns is
everything that happens to a resource once a kind has made one.

#### Scenario: refuse a generic create for a kind that owns its creation
- **GIVEN** a registered kind that declares it is not creatable through the kind-agnostic surface,
- **WHEN** a registration for that kind arrives on the kind-agnostic create route,
- **THEN** it is refused as a conflict with the code `GENERIC_CREATE_NOT_ALLOWED`, and no resource row and no audit entry is written,
- **AND** `coffer resource` offers no `create` command.

### Requirement: Carry a per-agent reach on every resource
The system MUST carry a framework-level per-agent reach on every resource — one
allow-list of agents, `null` meaning every agent, `[]` meaning none
([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)) — and MUST
serve it for every kind through one kind-agnostic pair of routes rather than per kind,
reporting whether the kind supports reach at all so a client can render the right
control without knowing the kinds itself. A reach is machine-local (see vault-sync).

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

### Requirement: Run the kind's cleanup before a deletion completes
Deleting a resource MUST run the kind's own cleanup hook while the resource can still be
resolved, and a hook that fails MUST abort the deletion rather than leave a half-deleted
thing — a resource is never left registered with its on-disk half already gone. Rows a
kind owns MUST cascade; history MUST NOT — the audit log and the invocation log outlive
the resource they describe. Credentials that no remaining resource cites MUST be
released, and a failure to release MUST NOT turn an already-completed deletion into a
caller-facing error; the store behind those refs is the credentials
spec's.

#### Scenario: deleting a resource runs its kind's cleanup and keeps its history
- **GIVEN** a resource with audit history, whose kind supplies a cleanup hook, and whose config cites a credential that nothing else cites and whose release fails,
- **WHEN** the user deletes it,
- **THEN** the hook runs while the resource can still be read back, the resource is gone, and the deletion returns without an error,
- **AND** the audit entries written before the deletion are still readable for that resource,
- **AND** when the kind's cleanup hook raises instead, the deletion is refused with that error, the resource is still registered, and no deletion audit entry is written.

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
A resource's `name` is a mutable **label**, unique within its kind and nothing more.
Renaming MUST be an ordinary field of the kind-agnostic update — available for every
kind, at the same level as editing a description — and MUST NOT require any other record
to be rewritten, because nothing else holds the name: the resource keeps its identity,
its config, its reach, its enabled state and its audit trail, with the entries written
before the change still saying what it was called then. The same name rules MUST apply
to a rename as to a registration, a collision within the kind MUST be refused before
anything moves, and renaming to the name it already has MUST change nothing and record
nothing. A kind that keeps an on-disk artifact named after the resource MUST be given
the chance to move it, with a failure aborting the rename rather than leaving the two
disagreeing. While the name WAS the identity, renaming needed its own route and only one
kind ever had one.

#### Scenario: renaming a resource is an ordinary edit
- **GIVEN** a resource of any kind, with a reach set, a credential cited by its
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
- **GIVEN** a resource of a kind that keeps an on-disk artifact named after it —
  a skill's master folder, a knowledge collection's directory, a memory
  partition's directory,
- **WHEN** the user renames it,
- **THEN** the artifact is at the new name with its contents intact and is
  served from there,
- **AND** a rename the kind cannot carry out — something already occupies the
  destination — is refused with the row and the artifact both untouched, rather
  than leaving a resource pointing at a directory that is not there or merging
  into one that was never its own.

### Requirement: Audit every lifecycle change
The system MUST record an audit entry for every lifecycle change to any resource or
capability, including the actor (CLI / API / UI / system); every lifecycle change made
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
MAY be pruned, and only through its registered timestamp column. Policies are upserted at
startup from the prunable-table registry and never deleted, so a table that stops
existing leaves a policy that prunes nothing rather than a prune aimed at an unknown
table. Changing a policy MUST itself be audited. This is the retention contract every
log-writing kind inherits.

#### Scenario: configure retention per log
- **GIVEN** the audit and invocation logs grow over time,
- **WHEN** the user sets a retention period for a log (in days, or "keep forever"),
- **THEN** entries older than that period are removed by the next periodic cleanup, and the change itself is audited.

### Requirement: Report the passes in flight in one cross-kind read
The system MUST answer, in one cross-kind read, which long model-driven passes this
daemon is running right now — each named by its kind, its target and when it started —
so that a surface can tell whether a pass is under way without every kind growing a
near-identical endpoint of its own. The read MUST start nothing, and the registry MUST
NOT outlive the process: a restart ends any pass it was running and the list comes back
empty, which is the truth rather than a lost record. Whether a pass runs on a timer at
all is internal-engine's; what a pass *does* is its own kind's.

#### Scenario: the daemon names the passes in flight
- **GIVEN** a long, model-driven pass over one kind's target is running,
- **WHEN** any surface reads the in-flight list,
- **THEN** that pass is named with its kind, its target and when it started,
- **AND** a target absent from the list has no pass running, and the read starts nothing.

### Requirement: Reach every management operation from both REST and the CLI
Users MUST be able to perform every management operation through both (a) a REST API and
(b) a `coffer` command-line interface, sharing the same underlying daemon and a
consistent error model; the reviewed CLI command tree and the management API MUST stay in
step in both directions, so neither can gain an operation the other lacks without the
parity test failing. The rule is policy over every spec and is stated as such in
[`.agents/openspec.md`](../../../.agents/openspec.md); this requirement is where it becomes
testable, because the assertion runs over the entire command tree across every spec and
so has no narrower home. A spec that cannot honour it records the gap in its own
`## Purpose` rather than leaving the omission to be discovered.

#### Scenario: command line covers every visual operation
- **GIVEN** the daemon is running,
- **WHEN** the CLI's live command tree is read,
- **THEN** it is **exactly** the reviewed table of every group the composition root registers and every subcommand under each — `daemon`, `open`, `resource`, `scope`, `audit`, `retention`, `mcp`, `credentials`, `agent`, `channel`, `skill`, `knowledge`, `memory`, `provider`, `sync`, with their nested groups — asserted in both directions, so a UI operation cannot ship a CLI counterpart without a reviewer seeing it here and a CLI command cannot appear without someone deciding it belongs,
- **AND** the groups whose surface is options rather than subcommands are claimed by those options instead, since an empty subcommand set would assert nothing about them,
- **AND** every group's `--help` renders, so an import-time error in one command module cannot wait for a user to reach for it,
- **AND** machine-readable JSON output is available for scripting.

#### Scenario: command line surfaces same errors
- **GIVEN** any failure surfaced by the management API,
- **WHEN** triggered through the command line,
- **THEN** the user sees an actionable message and a non-zero exit code; `--verbose` shows a full trace.
