# Data Model — Workflow

The workflow layer keeps two kinds of state. The **shape of the work** is a
Resource, carried in the kind-agnostic `resources` table like every other kind
and travelling with sync. The **execution of the work** is four new tables plus
a directory of files. Authority is [`spec.md`](./spec.md) and
[A Workflow Run's Writes Are Gated at the Gateway](../../../docs/decisions/workflow-gates-tool-calls.md).

## The template is a Resource, not a table

A template has no table of its own ("Register a template as a workflow
resource"). It is one row in `resources` with `kind = 'workflow'`, carrying its
name, `enabled`, its per-agent `scope` — read inverted, as the agents this
template may drive ("Read a template's scope as the agents it may drive") — and
its `config`, which holds the whole definition:

```json
{
  "description": "Requirement to release, one repository",
  "stages": [
    {
      "key": "design",
      "name": "Tech Design",
      "optional": false,
      "nodes": [
        {
          "key": "draft_td",
          "name": "Draft the technical design",
          "type": "ai",
          "skill": "coffer-writing-td",
          "instructions": "Ground every identifier in this repository.",
          "artifacts": [{ "name": "td.md", "required": true }],
          "approval": "never",
          "on_failure": { "action": "retry", "times": 1 },
          "agent": null,
          "attempt_ceiling": 3
        }
      ]
    }
  ]
}
```

Field rules, all enforced at write time ("Refuse an invalid template naming
the offending path") with the refusal naming the JSON path of the offending
field:

| Field | Rule |
|---|---|
| `stages` | at least one; `key` unique within the template, lowercase slug |
| `stages[].nodes` | at least one per stage; `key` unique **within the template**, not merely within the stage, because an event names a node by key alone |
| `nodes[].type` | `ai` \| `manual` — the type decides whether a turn is dispatched at all (`manual` records a human step and never opens a conversation) |
| `nodes[].skill` | `null`, or the name of a registered `skill` resource |
| `nodes[].agent` | `null` (the run's default), or a registered agent inside the template's scope |
| `nodes[].artifacts[].name` | a single path segment; no separators, no dots-only |
| `nodes[].artifacts` | may be omitted or empty in what is STORED; a task read back with none is given `[{"name": "report.md", "required": true}]` ("Give every task at least one deliverable"). The default is supplied on read, so a task later given a deliverable of its own does not end up owing two |
| `nodes[].approval` | `never` \| `always` |
| `nodes[].on_failure.action` | `stop` \| `continue` \| `retry`, with `times` ≥ 1 when `retry` |
| `nodes[].attempt_ceiling` | ≥ 1, default 3; how many attempts THIS task may open across a run ("Bound each task's attempts by its own ceiling") |

The engine reads no meaning from any `key` ("Attach no behaviour to a stage
key"). `design`, `coding`, `张三的阶段` are the same to it.

## Tables

All four are created by one Alembic migration. `id` values are UUIDv4 strings,
timestamps are UTC.

### `workflow_runs`

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | |
| `template_ref` | TEXT | the template's LABEL as it read at creation — provenance only, rendered raw, allowed to go stale; the snapshot is authoritative (migration 0100 stripped the `workflow:` prefix, which spelled a form of identity that no longer resolves) |
| `template_snapshot` | JSON not null | frozen at creation ("Freeze the template when a run is created") |
| `title` | TEXT not null | |
| `description` | TEXT nullable | what the developer says this delivery is; a LABEL like the title, and like it outside the version cycle ("Edit a run's title and description as labels") |
| `workdir` | TEXT not null | absolute path the node conversations run in |
| `machine_id` | TEXT not null | only this machine advances the run ("Advance a run only on the machine that owns it") |
| `status` | TEXT not null | `draft` \| `running` \| `paused` \| `completed` \| `aborted` \| `failed` |
| `current_stage_key` | TEXT nullable | projection |
| `current_node_key` | TEXT nullable | projection |
| `version` | INTEGER not null default 1 | optimistic lock ("Refuse a command carrying a stale version") |
| `tokens_spent` | INTEGER not null default 0 | a readout of what the run has spent; nothing caps it ("Bound each task's attempts by its own ceiling") |
| `inputs` | JSON not null default `[]` | mounted inputs — `knowledge`, `file`, `note`, `link`, `repo` ("List a run's mounted inputs to every node" and "Keep the developer's own notes in a run's context") |
| `created_at` / `updated_at` | TIMESTAMP | |

Indexes: `idx_workflow_runs_status(status)`, `idx_workflow_runs_updated(updated_at)`.

`current_stage_key`, `current_node_key`, `status` and `tokens_spent` are
**projections** — rebuilt from `workflow_events` on daemon start ("Rebuild a
run from its event log"). They exist so a list query is one row read, not a
fold.

A run has **no conversation column**. Every conversation belongs to one node
and hangs off `workflow_node_attempts.conversation_id` ("Give a run no
conversation of its own"). A run-level `main_conversation_id` existed in an earlier draft of this spec and is gone from
the migration itself rather than dropped by a later one: nothing has ever run
0085 outside a throwaway database, so the migration describes the shape the
layer actually has instead of building a column and then removing it.

### `workflow_events`

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | |
| `run_id` | TEXT not null → `workflow_runs.id` | |
| `sequence` | INTEGER not null | monotonic per run |
| `event_type` | TEXT not null | see the list below |
| `actor` | JSON not null | `{actor_kind, actor_id, source_surface}` |
| `stage_key` / `node_key` | TEXT nullable | |
| `payload` | JSON not null default `{}` | |
| `created_at` | TIMESTAMP not null | |

Unique `(run_id, sequence)`; index `idx_workflow_events_run(run_id, sequence)`.
Append-only: no row is ever updated or deleted while its run exists.

Event types — a closed set, and the whole vocabulary:

`run.created`, `run.started`, `run.paused`, `run.resumed`, `run.aborted`,
`run.completed`, `run.failed`,
`node.started`, `node.output_ready`, `node.feedback_submitted`,
`node.completed`, `node.failed`, `node.retried`, `node.skipped`,
`node.restored`, `node.adhoc_added`, `node.briefed`,
`approval.created`, `approval.approved`, `approval.rejected`,
`approval.expired`, `artifact.added`.

There is no `node.waiting_review` event: waiting is the absence of a next event,
not an event. This is the simplification [`spec.md`](./spec.md) takes over the
prior art it is based on.

### `workflow_node_attempts`

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | |
| `run_id` | TEXT not null → `workflow_runs.id` | |
| `stage_key` | TEXT not null | |
| `node_key` | TEXT not null | `adhoc:<slug>` for an unplanned task ("Add an ad-hoc task to any stage") |
| `attempt` | INTEGER not null | from 1 |
| `status` | TEXT not null | `pending` \| `running` \| `waiting_review` \| `waiting_approval` \| `completed` \| `skipped` \| `failed` |
| `conversation_id` | TEXT nullable | `null` for a `manual` node |
| `instructions` | TEXT nullable | an ad-hoc task's own brief |
| `summary` | TEXT nullable | what the node reported |
| `failure_reason` | TEXT nullable | `interrupted`, `agent_error`, `missing_artifact`, `attempt_ceiling` |
| `tokens` | INTEGER not null default 0 | |
| `started_at` / `finished_at` | TIMESTAMP nullable | |

Unique `(run_id, node_key, attempt)`; index `idx_workflow_attempts_run(run_id)`.
An attempt row is never rewritten by a retry — a retry inserts `attempt + 1`
("Keep every attempt when a node is retried"), and the conversation of the
earlier attempt stays readable.

### `workflow_approvals`

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | |
| `run_id` | TEXT not null → `workflow_runs.id` | |
| `attempt_id` | TEXT nullable → `workflow_node_attempts.id` | |
| `kind` | TEXT not null | `tool_call` — the only kind an approval is ever created with |
| `tool_name` | TEXT nullable | prefixed upstream name, for `tool_call` |
| `payload` | JSON not null | the exact arguments that will execute ("Refuse an unapproved write-class tool call made for a run") |
| `status` | TEXT not null | `pending` \| `approved` \| `rejected` \| `expired` \| `superseded` |
| `decided_by` / `decided_surface` | TEXT nullable | |
| `comment` | TEXT nullable | what the developer said when deciding — a rejection's reason is the one thing the held node can act on |
| `expires_at` | TIMESTAMP not null | |
| `created_at` / `decided_at` | TIMESTAMP | |

Index `idx_workflow_approvals_run(run_id, status)`.

A decision on a terminal approval returns that terminal state unchanged
("Make an approval decision idempotent"). Aborting a run moves its `pending`
approvals to `superseded`.

`payload` is the arguments **verbatim**, not a summary — a decision on a summary
is not a decision (ADR). It may therefore contain whatever the agent passed;
credential material never reaches it, because credentials are injected by the
gateway at dispatch and are not part of the call's arguments.

## Write-class judgements live on the server, not in a new table

The judgement "is this upstream tool write-class" is a property of the tool, so
it is stored on the `mcp_server` resource that serves it, as one map in its
`config`:

```json
{ "tool_write_class": { "create_issue": "write", "search_issues": "read" } }
```

A tool absent from the map is treated as write-class ("Treat an unjudged tool
as write-class and remember the answer"); the developer's answer writes an
entry. Because it is resource config it travels with sync, which is correct: whether `create_issue` writes is not a fact about a machine.

## On disk

```text
~/.coffer/workflows/<run_id>/
├── CATALOG.md                      # generated; never hand-edited ("Generate the index of earlier tasks")
├── workspace/                      # the run's working directory — Coffer's own ("Give each run a working directory of its own")
├── inputs/                         # uploaded files, and notes the developer wrote ("Store an uploaded input under the run's directory" and "Keep the developer's own notes in a run's context")
└── artifacts/
    └── <node_key>/
        └── <attempt>/
            └── td.md
```

`workspace/` is what every node's conversation runs in. Coffer creates it with
the run and nobody is asked for it: creating a run takes a template and a title
("Create a run from a template and a title alone"), and a path is not a thing a
person should have to decide before the work has started. `workdir` stays a
COLUMN because what a run ran in is worth recording, but it is derived from the
run id rather than supplied.

`$COFFER_WORKFLOW_ROOT` overrides the root for tests — and the tests **must**
set it, for the reason recorded in
[`docs/architecture.md`](../../../docs/architecture.md): unset, it resolves to the developer's real
vault.

Path construction lives in exactly one module,
`infrastructure/workflow/paths.py`, which owns the segment guard (no empty,
hidden, dots-only or separator-bearing segment reaches a path).

Nothing under this root is indexed, chunked or embedded ("Never index a run's
directory"). `CATALOG.md` is regenerated from the directory after every `artifact.added`; it is a
convenience for reading, never a source of truth — delete it and the next
regeneration reproduces it.

Promotion ("Promote what a run is made of into a knowledge collection") copies
`artifacts/` into a new `knowledge` collection and leaves the run directory
untouched.

## Deletion

Deleting a run cascades its events, attempts and approvals, and removes its
directory. Its node **conversations are not deleted** — they are ordinary
conversations and belong to the chat layer's own retention. Deleting a template
is refused while a run references it only for provenance; since the snapshot is
authoritative, deletion is permitted and `template_ref` is left saying what
the run was started from, the way a deleted source leaves an artifact's
provenance intact. Renaming the template leaves it alone for the same reason:
it is a label frozen at a moment, not an address.
