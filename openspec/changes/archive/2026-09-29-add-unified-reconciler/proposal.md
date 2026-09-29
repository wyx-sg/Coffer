## Why

Most of what Coffer promises is a state of files it does not own: its MCP
entry in each agent's config, a delivered skill link, a provider's keys in an
agent's settings, the memory delivery hook. Each kind checked its own part with
its own code, on its own triggers, with its own idea of equality — and two of
them judged by presence alone. PR #413 is the incident: a hook whose command
kept an option the CLI had dropped read as installed for months. Coffer's own
MCP entry had the same shape (a moved shim or a stale `--agent-uid` read as
installed, and nothing ever checked it), and the provider boot check could not
see a projection whose values no longer matched its connection. The ADR
[One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database, Comparing Parameters](../../../docs/decisions/one-level-triggered-reconciler-compares-parameters.md)
decides to replace them with one reconciler.

## What Changes

- One level-triggered reconciler owns every target the agents' projection
  registry lists — the MCP entry, skill links, the provider projection, the
  delivery hook. Each target states what it wants with every parameter, reads
  what is there in the same shape, and repairs a difference only where its
  direction policy allows; the rest is reported. A pass runs at boot, every
  60 seconds, early on an in-process `Changed(kind, uid, rev)` hint after any
  resource write, and on demand after a user's own write, a sync import and a
  feature switch. A target that raises is reported and skipped.
- Resources carry a monotonic `rev`, bumped by every write.
- A dry-run computes the same plan and writes nothing: no file, row, audit
  event or hint.
- A repair's audit event is recorded in the same call as its write; if it
  cannot be, the file is restored from what its backup holds and the item is
  reported failed.
- New read models: `GET /api/v1/reconcile/plan` (the drift and change preview,
  per target and per resource), `POST /api/v1/reconcile/apply` (apply chosen
  items as the caller), `GET /api/v1/attention` (the Overview's cross-kind
  "needs you" list, one action per item), and `coffer drift list|repair`,
  `coffer attention`.
- Coffer's MCP entry is now judged by its shim path and `--agent-uid`; a stale
  one is repaired and an entry an older build left in another agent's file is
  moved on every pass rather than once at start.
- The skill-delivery triggers, the skill boot heal, the provider boot heal and
  post-import reconcile, the agent post-import side effects, the memory
  delivery boot heal and the one-off MCP home migration are removed: each is a
  target now, and a sync import runs one pass with the import's warrant.
- The provider projection is compared by value: a projection whose base URL,
  model, key helper or model catalogue no longer match is re-projected; the
  "flag contradicted" correction runs on every pass.

## Capabilities

### New Capabilities

### Modified Capabilities

- `resource-framework`: the reconciler, its dry-run and audit rule, the drift
  and attention read models, the resource revision.
- `skill-manager`: delivery and drift healing are state on every pass rather
  than a trigger list and a boot heal.
- `provider-switching`: the contradicted-flag correction is state-based, and a
  projection is compared by value.
- `agent-registry`: the MCP install's status gains parameter drift and repair;
  the Claude Code home-file move happens on every pass.
- `memory`: stale delivery hooks are repaired on every pass.
- `vault-sync`: an import runs one reconcile pass with the import's warrant.

## Impact

Backend: `domain/reconcile.py`, `application/reconcile/`, one target per kind
(`application/agent/mcp_reconcile.py`, `application/skill/link_reconcile.py`,
`application/provider/projection_reconcile.py`,
`application/memory/delivery_reconcile.py`), `application/attention.py` and
one attention source per kind, migration 0107, the composition root. The
removed modules are listed in the tasks. Docs: a docs-site architecture page on
the reconciler; `.agents/stack.md`.
