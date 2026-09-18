# Feature Specification: Resource Framework

**Status**: Accepted
**Scope note**: This spec owns the kind-agnostic half of Coffer's resource model — the kind registry and the `<kind>:<name>` identity, the lifecycle surface every kind is managed through, per-agent reach, the audit log, per-table retention and its background prune, the cross-kind read of the passes in flight, and the rule that every management operation is reachable from both REST and the CLI. What a kind *is* — an MCP server, an agent, a skill, a channel, a knowledge collection, a memory partition, a provider connection — belongs to that kind's own spec.
**Input**: Extracted from spec mcp-gateway, which shipped the framework because it shipped the first kind. Seven kinds later the framework's requirements still sat in one kind's spec, so five routes, two tables, three entities, a user story and four acceptance scenarios were owned by nobody.

## Why this is a spec

An earlier audit rejected a `resource-framework` spec on three pieces of
evidence: `coffer resource` has no create command; with no kind registered
every lifecycle route answers `4xx` or an empty list; and the framework's three
obligations — schema validation, lifecycle audit, per-table retention — would
be stated once in the constitution as the contract each kind inherits.

The first two are true, and this spec does not pretend otherwise (FR-003). The
third is not available. The constitution holds scaffolding-level invariants —
tech stack, workflow, licensing, architectural style — and says so in its own
opening: product behaviour is defined per feature under `specs/`. It holds
rules, not routes, tables, entities or acceptance scenarios. Moving the three
obligations there deleted them as requirements and left the rest of the
framework sitting in a kind's spec with nothing explaining why it was there.

With audit and retention inside it the picture changes, and the five tests in
[`.agents/sdd.md`](../../.agents/sdd.md) now pass:

1. **It owns state.** `audit_log` and `retention_policies` are its tables. Every
   kind writes the first; this spec seeds, reads, configures and prunes both.
2. **Its boundary is provable.** Its route family is `/api/v1/resources*`,
   `/api/v1/audit`, `/api/v1/retention/*` and `/api/v1/upkeep/runs`; its
   packages are `domain/{resource,scope,audit,retention}.py`, the kind-agnostic
   services beside them in `application/`, and their surfaces; importlinter
   contract 6 already fences the core off from every kind; and it has ADRs of
   its own ([Everything Is a Resource Kind](../../docs/decisions/everything-is-a-resource-kind.md),
   [Resource Framework Upfront](../../docs/decisions/resource-framework-upfront.md),
   [Resource Identifier Format](../../docs/decisions/resource-identifier-format.md),
   [Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md)).
3. **The name is accurate** — it is the framework, and nothing here is a kind.
4. **One behaviour**: what happens to a managed thing between the moment a kind
   creates it and the moment it is deleted, recorded while it happens.
5. **Independently operable**: `coffer resource`, `coffer scope`, `coffer audit`
   and `coffer retention` against a running daemon, with the Activity page and
   the Data settings section over the same records.

## User Scenarios & Testing

### User Story 1 — One surface for every kind of thing Coffer manages (Priority: P1)

A user has registered MCP servers, agents, skills, channels and knowledge
collections. They want one place that lists everything Coffer holds, one way to
turn a thing on or off, one way to say which agents it reaches *where that
question applies to the kind at all*, and one way to delete it — instead of
learning a near-identical surface per kind and discovering that one of them
forgot to audit the change or to release the secret the deleted thing
referenced.

**Why this priority**: Every other spec is a kind. Without this one, each of
them re-implements identity, validation, enable/disable, reach, deletion and
auditing slightly differently, and the differences are only found in
production.

**Independent Test**: With one reach-supporting kind registered, list resources
through the kind-agnostic surface, read one back by `<kind>:<name>`, disable it,
set its reach to a single agent, clear the reach, delete it, and see every one
of those steps in the audit log.

**Covering scenarios** (full Given/When/Then under `## Acceptance Scenarios` below):

- the kind-agnostic surface serves every kind
- reject an invalid registration and persist nothing
- set a resource's reach from the kind-agnostic surface

---

### User Story 2 — Same operations from the command line (Priority: P2)

The developer scripts setup and bulk operations from a terminal — adding
resources from a dotfile, automating CI-friendly enable/disable.

**Why this priority**: Coffer's audience is developers. A full CLI is table
stakes for scripted workflows and remote machines. That every management
operation is reachable from both REST and the CLI is policy over every spec
rather than any one spec's private promise — it is stated in
[`.agents/sdd.md`](../../.agents/sdd.md) beside the End-to-End Deliverable Rule
— and FR-009 below is where that policy is made testable, because the assertion
runs over the whole command tree and so has no narrower home.

**Independent Test**: From a fresh install, register two resources, toggle
several capabilities, and view audit/invocation logs entirely from the terminal
— no GUI needed.

**Covering scenarios**:

- command line covers every visual operation
- command line surfaces same errors

---

### User Story 3 — Auditing & activity logs with retention controls (Priority: P3)

The developer wants to see what happened — when a server was added, when a tool
was disabled, what tools were called when — without those logs growing
unbounded.

**Why this priority**: Necessary for trust and debugging, but not blocking the
framework's basic operation. Retention defaults are sensible enough that most
users never touch them.

**Independent Test**: Make several changes, view audit; run several tool calls,
view invocations; change a retention period to a short value, wait for the next
cleanup, confirm older entries are gone and newer ones remain.

**Covering scenarios**:

- audit lifecycle changes
- configure retention per log
- the daemon names the passes in flight

---

### Edge Cases

- **A kind that is not registered.** Every lifecycle route refuses the request
  rather than inventing a kind on first use. A kind exists because the
  composition root wired it, never because a request named it.
- **A validation failure mid-write.** Nothing is persisted — not a row with a
  rejected config, not a half-written reach, not an audit entry for a change
  that did not happen.
- **A deletion whose kind hook fails.** The hook runs while the resource can
  still be resolved and a hook that raises aborts the deletion, so a resource is
  never left registered with its on-disk half already gone.
- **A deletion the kind refuses outright.** Some resources are not the owner's to
  delete — one Coffer generates and rewrites at every boot. The kind says so
  through a pre-write guard that runs before anything is torn down, so the
  refusal costs the caller nothing and leaves no trace but the refusal itself.
- **A retention policy for a table nobody registered.** Policies are upserted at
  startup from the prunable-table registry and never deleted, so a table that
  stops existing leaves a policy that prunes nothing rather than a prune aimed
  at an unknown table.
- **A daemon restart during a long pass.** The in-flight registry is
  per-process: the list comes back empty, which is the truth rather than a lost
  record.

## Acceptance Scenarios

Per [`.agents/sdd.md`](../../.agents/sdd.md) and `.agents/testing.md`, every
scenario in this section is referenced by at least one test marked
`@pytest.mark.acceptance(spec="resource-framework", scenario="…")` (Python) or
`acceptance("resource-framework", "…", …)` (TypeScript). Coverage is audited by
`make verify-acceptance`.

### Scenario: the kind-agnostic surface serves every kind

- **Given** resources of more than one registered kind exist,
- **When** the user lists resources without naming a kind, reads one back by its `<kind>:<name>` reference, then disables and re-enables it,
- **Then** every kind's resources appear in the one list, each carrying its ref, kind, name, config, reach and enabled flag,
- **And** the enable/disable round trip is served by the same route for every kind, and each step is audited.

### Scenario: reject an invalid registration and persist nothing

- **Given** a registered kind with a config schema,
- **When** a registration arrives whose config fails that schema, or whose name is already taken within the same kind,
- **Then** it is refused with a message naming the cause — a validation error for the schema failure, a conflict for the duplicate,
- **And** no resource row, no audit entry and no kind-owned side effect is left behind.

### Scenario: set a resource's reach from the kind-agnostic surface

- **Given** a resource of a kind that supports reach,
- **When** the user sets its scope to one agent, then clears it back to unscoped,
- **Then** each write is persisted, audited as a scope update, and followed by the kind's own post-write reaction,
- **And** a kind that supports no reach rejects a non-null scope, as does a payload carrying a property the scope schema does not define.

### Scenario: a resource is given a different name

- **Given** a resource of a kind that declares it may be renamed,
- **When** the user gives it a new name,
- **Then** it is reachable under the new name with its config, reach and enabled state intact, the old name resolves to nothing, and the change is audited against the same row id it always had,
- **And** a name already taken within that kind is refused, a kind that declares no rename is refused, and submitting the name it already has changes nothing.

### Scenario: command line covers every visual operation

- **Given** the daemon is running,
- **When** the CLI's live command tree is read,
- **Then** it is **exactly** the reviewed table of every group the composition root registers and every subcommand under each — `daemon`, `open`, `resource`, `scope`, `audit`, `retention`, `mcp`, `credentials`, `agent`, `channel`, `skill`, `knowledge`, `memory`, `provider`, `sync`, with their nested groups — asserted in both directions, so a UI operation cannot ship a CLI counterpart without a reviewer seeing it here and a CLI command cannot appear without someone deciding it belongs,
- **And** the groups whose surface is options rather than subcommands are claimed by those options instead, since an empty subcommand set would assert nothing about them,
- **And** every group's `--help` renders, so an import-time error in one command module cannot wait for a user to reach for it,
- **And** machine-readable JSON output is available for scripting.

### Scenario: command line surfaces same errors

- **Given** any failure surfaced by the management API,
- **When** triggered through the command line,
- **Then** the user sees an actionable message and a non-zero exit code; `--verbose` shows a full trace.

### Scenario: a kind refuses a deletion before anything is torn down

- **Given** a registered kind supplying a pre-write delete guard, and one resource of that kind the guard refuses,
- **When** the delete is attempted through the kind's own route and through the kind-agnostic one,
- **Then** both are refused with the same error the guard raised, carrying the same code and the same status,
- **And** the kind's cleanup hook never ran, the resource and everything it owns are exactly as they were, and no deletion audit entry was written,
- **And** a resource of the same kind the guard does not refuse still deletes normally.

### Scenario: audit lifecycle changes

- **Given** the user performs any add / enable / disable / update / delete on a server or capability,
- **When** they open the audit view (CLI or UI),
- **Then** they see one row per change with actor, timestamp, and a payload describing what changed.

### Scenario: configure retention per log

- **Given** the audit and invocation logs grow over time,
- **When** the user sets a retention period for a log (in days, or "keep forever"),
- **Then** entries older than that period are removed by the next periodic cleanup, and the change itself is audited.

### Scenario: the daemon names the passes in flight

- **Given** a long, model-driven pass over one kind's target is running,
- **When** any surface reads the in-flight list,
- **Then** that pass is named with its kind, its target and when it started,
- **And** a target absent from the list has no pass running, and the read starts nothing.

## Requirements

### Functional Requirements

**Resource lifecycle**

- **FR-001**: System MUST model every managed thing as a *resource* identified by `<kind>:<name>` ([Resource Identifier Format](../../docs/decisions/resource-identifier-format.md)), unique within its kind, and MUST expose one kind-agnostic surface — `/api/v1/resources*` and `coffer resource` — to list, read, update, enable, disable and delete any of them without the caller knowing the kind. A kind exists only because the composition root registered it; a request naming an unregistered kind MUST be refused rather than bringing one into being.
- **FR-002**: System MUST validate every registration against its kind's schema and the kind's own pre-write validators, MUST reject a duplicate name within a kind, and MUST persist nothing on a validation failure. This is the contract every kind inherits, which is why it is stated once here rather than once per kind.
- **FR-003**: Creation is a per-kind seam and MUST stay one. The kind-agnostic create route MUST accept only kinds that declare themselves creatable through it, and MUST refuse a kind that owns a creation invariant beyond config validation — a skill's master folder, an agent's on-disk detection — so that such a kind is registered through its own surface, which can hold that invariant. There is deliberately no `coffer resource create`: a generic create would have to guess a config shape it cannot know. What this spec owns is everything that happens to a resource once a kind has made one.
- **FR-004**: System MUST carry a framework-level per-agent reach on every resource — one allow-list of agents, `null` meaning every agent, `[]` meaning none ([Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md)) — and MUST serve it for every kind through one kind-agnostic pair of routes rather than per kind, reporting whether the kind supports reach at all so a client can render the right control without knowing the kinds itself. A non-null reach on a kind that declares none, and a payload carrying a property the schema does not define, MUST both be refused rather than stored or silently widened — a client still sending a withdrawn axis means "only there", and keeping what is left would store "every agent". A reach write MUST be audited and MUST fire the kind's post-write reaction, so delivery and reclaim stay in step with the edit. *Enforcing* reach is each kind's own seam at its own choke point; this spec owns the value, its validation and its write path.
- **FR-005**: Deleting a resource MUST run the kind's own cleanup hook while the resource can still be resolved, and a hook that fails MUST abort the deletion rather than leave a half-deleted thing. Rows a kind owns MUST cascade; history MUST NOT — the audit log and the invocation log outlive the resource they describe. Credentials that no remaining resource cites MUST be released, and a failure to release MUST NOT turn an already-completed deletion into a caller-facing error; the store behind those refs is spec credentials'.
- **FR-010**: A kind MAY supply a **pre-write delete guard**: given the resource a delete names, it refuses the deletion before anything is torn down. The framework MUST run it after resolving the resource and **before** the kind's cleanup hook of FR-005, MUST turn its refusal into the caller's error unchanged, and MUST leave the resource exactly as it was — no link removed, no row touched, no lifecycle audit entry for a deletion that did not happen. The refusal MUST be identical whichever door the delete came through, the kind's own route or the kind-agnostic one, which is the whole reason it belongs here: a guard written into one route is a guard the second route silently lacks, and the kind-agnostic surface exists precisely so a caller need not know the kind. It is a **validator**, alongside the registration validators of FR-002, rather than a rejection raised from inside `on_delete` — that hook is a *reaction to an already-decided delete*, run to tear the kind's own half down, so a kind refusing from in there refuses only after the framework has committed to the operation and the caller has been told it is under way. The guard is the seam for a resource whose existence is not the owner's to decide: the only one today is a builtin skill, whose master folder the next boot writes back (spec [skill-manager](../skill-manager/spec.md) FR-029).
- **FR-011**: A resource's name is a LABEL the person chose, and the system MUST let them change it in place for any kind that can bear the change, keeping the resource's identity, its config, its reach, its enabled state and its audit trail. A kind whose name is written out somewhere the move cannot reach — into another tool's configuration, into a folder on disk — MUST declare that the kind-agnostic surface may not rename it; that attempt MUST be refused rather than half-applied, and the kind's own surface, which repairs what it knows about, MUST be the one that moves it. Renaming to a name already taken within the kind MUST be refused, and renaming to the name it already has MUST change nothing and record nothing.

**Audit**

- **FR-006**: System MUST record an audit entry for every lifecycle change to any resource or capability, including the actor (CLI / API / UI / system). Entries MUST be readable through both surfaces, filterable by kind, name, event type and time, and MUST carry the resource's stable row id so a trail survives a rename while each row keeps saying what the resource was called then. The event-type vocabulary is shared: this spec defines the resource and retention events and every kind contributes its own, so one record answers "what happened" for the whole vault rather than each kind growing a private log.

**Retention**

- **FR-007**: System MUST provide per-table retention configuration (in days, or "keep forever") over a registry of prunable tables, seeded with each table's default when the daemon starts, plus a periodic background pass that prunes entries older than their table's period and an on-demand prune for the impatient. Only a registered table MAY be pruned, and only through its registered timestamp column. Changing a policy MUST itself be audited. This is the retention contract every log-writing kind inherits.

**Passes in flight**

- **FR-008**: System MUST answer, in one cross-kind read, which long model-driven passes this daemon is running right now — each named by its kind, its target and when it started — so that a surface can tell whether a pass is under way without every kind growing a near-identical endpoint of its own. The read MUST start nothing, and the registry MUST NOT outlive the process: a restart ends any pass it was running and the list comes back empty, which is the truth rather than a lost record. Whether a pass runs on a timer at all is spec internal-engine's; what a pass *does* is its own kind's.

**Surface parity**

- **FR-009**: Users MUST be able to perform every management operation through both (a) a REST API and (b) a `coffer` command-line interface, sharing the same underlying daemon and a consistent error model. The rule is policy over every spec and is stated as such in [`.agents/sdd.md`](../../.agents/sdd.md); this requirement is where it becomes testable, because the assertion runs over the entire command tree across every spec and so has no narrower home. A spec that cannot honour it records the gap in its own `## Assumptions` rather than leaving the omission to be discovered.

### Key Entities

- **Resource**: A user-managed entity inside Coffer, identified by `(kind, name)`. Carries kind-specific configuration, an enabled flag, a description, a per-agent reach and timestamps. Kind-agnostic by construction, so a new kind adds a row shape rather than a table.
- **Kind**: The descriptor one kind's spec contributes — its config schema, its name rule, its pre-write validators (registration, and the optional delete guard of FR-010), its post-write reactions, whether it is creatable generically and whether it supports reach. Pure data: it names no router and no service, so the domain layer never references a surface.
- **Scope**: A resource's reach — one allow-list of agents, `null` for every agent, `[]` for none. Machine-local (spec vault-sync, `## What does not sync`).
- **AuditEntry**: One lifecycle change — timestamp, event type, the resource's stable row id, the kind and name it carried at the time, the actor, and a JSON payload describing what changed.
- **RetentionPolicy**: One prunable table's period — `null` for keep-forever — plus when it was last pruned and how many rows went.
- **PrunableTable**: The registry entry a log-writing spec contributes: the table, its timestamp column, its default period and its labels.
- **UpkeepRun**: One pass in flight — kind, target, start time. In-process only.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A further kind can be added by writing a `Kind` descriptor and its own surfaces, with no change to the lifecycle service, the audit service, the retention machinery or the kind-agnostic routes.
- **SC-002**: Every lifecycle change made through any surface — REST, CLI, or a kind's own command — appears in the audit log with the originating actor, and no surface can mutate a resource without one.
- **SC-003**: A registration that fails validation leaves the database exactly as it was before the attempt.
- **SC-004**: Entries older than their table's retention period are removed by the periodic cleanup while newer entries are retained, and the cleanup does not block concurrent API calls.
- **SC-005**: The reviewed CLI command tree and the management API stay in step in both directions — neither can gain an operation the other lacks without the parity test failing.
- **SC-006**: Every Acceptance Scenario in this document is covered by at least one test marked with `acceptance(spec="resource-framework", scenario="…")`, and `make verify-acceptance` reports zero uncovered scenarios.

## Assumptions

- The daemon this framework is mounted in — its port, its discovery file, its token, its loopback posture and its `Host` guard — is spec daemon's. This spec contributes routers, Typer groups and a background worker to it.
- The encrypted store behind a resource's credential refs is spec credentials'. This spec probes refs before a write and releases orphaned ones after a delete; it never holds a key.
- At least one kind is registered. With none, every lifecycle route is a refusal or an empty list and the audit log has nothing in it — which is what a framework with nothing to manage should do, not a defect. The seven kinds that exist are contributed by spec mcp-gateway (`mcp_server`), spec agent-registry (`agent`), spec skill-manager (`skill`), spec knowledge (`knowledge`), spec channels (`channel`), spec memory (`memory`) and spec provider-switching (`provider`). `chat` and `sync` are code packages, not registered kinds.
- The web surfaces over these records — the Activity page's audit tab and the Data settings section's retention table — are spec web-ui's pages over this spec's routes.
- Coffer runs as a single-user personal tool on the user's own machine; there is no multi-tenant or remote-access requirement beyond the existing token gate.

## Deliberately out of scope

- **What a kind is.** Transport, discovery, delivery, projection, conversation — every kind's own behaviour is its own spec's. This spec absorbs none of it.
- **Enforcing reach.** Each kind gates at its own choke point, where the asking identity is known: spec mcp-gateway at the per-session capability listing, spec skill-manager at delivery, and so on. A second central gate would be unreachable, because every per-kind path already runs downstream of its own.
- **Scheduling the passes FR-008 reports.** Whether `organise` and `tidy` run on a timer, how often, and against which model is spec internal-engine's; what each pass does is spec memory's and spec knowledge's.
- **The invocation log.** A per-call record of gateway traffic is spec mcp-gateway's; it registers as a prunable table here, which is the whole of the relationship.
- **A generic resource-creation command.** See FR-003.
