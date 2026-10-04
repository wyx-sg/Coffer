## ADDED Requirements

### Requirement: Converge what Coffer writes outside its database with one reconciler
Everything Coffer keeps true outside its own database — its MCP entry in each
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
kind is written, and on demand after a user's own write, a sync import and a
feature switch; a lost early start costs at most one period and never
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
reason, and one that names no current difference is absent. `coffer drift list`
and `coffer drift repair <id>... | --all` MUST reach the same routes; `repair`
exits non-zero when any item failed.

#### Scenario: list drift with its file and before and after text
- **GIVEN** a registered agent whose Coffer MCP entry names a shim path this build no longer installs
- **WHEN** the user reads the plan (`GET /api/v1/reconcile/plan`, or `coffer drift list --json`)
- **THEN** the MCP entry item reads `modify`, `repair`, the agent's config file, `command` among the changed parameters and the entry before and after, and nothing is written

#### Scenario: apply one drift item as the caller
- **GIVEN** the same drift
- **WHEN** the user applies its id (`POST /api/v1/reconcile/apply`, or `coffer drift repair <id>`)
- **THEN** the entry is rewritten, the item comes back `applied`, and the audit log records the install with the user as actor

### Requirement: Report what needs a person across every kind
`GET /api/v1/attention` and `coffer attention` MUST list what needs a person
now, from every source whose experimental feature is on: the reconciler's
drift that a pass could not fix, MCP servers whose last test failed, whose
launcher is missing or whose cited secret is absent, agents whose program is
missing, whose connection is partial or who are not connected, a sync stopped on
a conflict or holding deletions, and channels reconnecting, disconnected or not
running. Each item MUST carry its kind, the resource's uid and title, a stable
reason code with one sentence, a severity (`error`, `warning`, `info`), when
the condition was first seen where that is known, and exactly one action: a
verb and the REST route and body the kind's own page uses — the list has no
write of its own. A source that fails MUST be reported beside the others'
items, and the answer MUST count the items per kind.

#### Scenario: each item carries one action from its kind's own page
- **GIVEN** an MCP server whose last test failed and a partially connected agent
- **WHEN** the user reads the attention list
- **THEN** the server's item offers `test` through `POST /api/v1/resources/mcp_server/{uid}/test`, the agent's offers `connect` through `POST /api/v1/agents/{uid}/coffer-connection`, errors sort before warnings, and the counts name one item for each kind

#### Scenario: a failing source does not hide the others
- **GIVEN** one source that raises and one that has an item
- **WHEN** the attention list is read
- **THEN** the item is listed and the failing source is reported with its error

#### Scenario: a switched-off feature's signals are left out
- **GIVEN** a sync stopped on a conflict and the `vault_sync` feature switched off
- **WHEN** the attention list is read
- **THEN** no sync item is listed

### Requirement: Carry a monotonic revision on every resource
Every resource MUST carry an integer revision that is 1 when the row is
created and grows by one with every write to the row — config, enabled flag,
scope, name, title — and every write MUST emit an in-process hint naming the
kind, the uid and the new revision, which only brings the next reconcile pass
forward.

#### Scenario: every write to a resource bumps its revision
- **GIVEN** a newly registered resource at revision 1
- **WHEN** its config, its enabled flag and its title are changed in turn
- **THEN** it reads revision 4, and each write emitted one hint carrying the revision it produced
