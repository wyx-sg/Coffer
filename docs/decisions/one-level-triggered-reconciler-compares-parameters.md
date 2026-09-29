# One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database, Comparing Parameters

**Status**: Proposed
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [Coffer's Agent Hooks Are Marker-Scoped, Explicit, Audited and Repaired When Stale](agent-hook-installation.md), [Skills Reach an Agent as a Directory Link to One Master Folder](cross-platform-skill-delivery.md), [LLM Connections Are Projected Into Each Agent's Own Config File](provider-connections-projected-into-agent-config.md), [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md), [A Kind Plugs In as One Frozen Record of Optional Hooks](kind-plugin-contract.md), [Audit Every Change With Its Actor](audit-and-retention.md), [Channels Are Thin Transport Adapters Over One Shared Core](channel-adapter-framework.md), [Agent Mechanisms Are Optional Facets on the Descriptor](agent-mechanisms-are-optional-facets-on-the-descriptor.md), [Platform Differences Live Behind One Platform Port](platform-differences-live-behind-one-platform-port.md), spec memory "Repair stale delivery hooks", spec skill-manager "Reconcile deliveries per agent on every trigger", spec skill-manager "Heal safely repairable drift at daemon boot", spec provider-switching "Clear an active flag the agent's config contradicts at boot", spec agent-registry "Install Coffer's MCP server into an agent in one action", spec vault-sync "Re-run post-import hooks after applying", PR #413

## Context

Most of what Coffer promises is a state of files it does not own: a
`coffer` entry in `~/.claude.json` and Codex's `config.toml`, a
`SessionStart` / `UserPromptSubmit` hook, a directory link per delivered
skill, a provider's keys in `settings.json`, a running channel adapter. Those
files are rewritten by their own CLIs, by other tools, by backups and by the
user, often while the daemon is not running. The database row says what should
be true; only the file says what is.

Today each kind answers "is it still true?" with its own code, its own
trigger and its own idea of equality:

| What Coffer keeps true | Code | When it checks | What it compares |
| --- | --- | --- | --- |
| Memory delivery hook | `application/memory/delivery.py` `heal_drift`, called from `delivery_switch.py` | boot, `memory` feature switch | the **whole command**, against `command_for(uid)` |
| Skill links | `application/skill/verify_ops.py` (`verify_drift` / `repair_drift`), `application/skill/boot_reconcile.py` | the eight edge events of spec skill-manager "Reconcile deliveries per agent on every trigger", plus boot | link exists and points at the master folder |
| Provider projection | `application/provider/boot_reconcile.py` (boot), `application/provider/sync_reconcile.py` (after a sync import) | boot; post-import | at boot, **presence** of Coffer's keys only (`_projection_present`), never their values |
| Coffer's MCP entry | `application/agent/mcp_service.py` `status`; one-off `application/agent/mcp_home_migration.py` | on request only | **presence** of the `coffer` key (`domain/agent/mcp_install.is_installed`); the shim path is read for display, never compared |
| Agent side effects after import | `application/agent/sync_reconcile.py` | post-import | delegates to skill delivery |
| Channel adapters | `application/channel/runtime.py` `reconcile_once`, desired set from `application/channel/wanted.py` | **every 2 s** (`_DEFAULT_INTERVAL_SECONDS`) | a hash of the binding, so a parameter change restarts the adapter |

Two facts in that table decide this ADR.

- **Presence is not correctness.** PR #413 is the incident: when
  `coffer memory context` moved from `--agent` to `--agent-uid`, every hook on
  disk kept the old option, the agent printed a usage error at the start of
  every session, and the status page said `installed: True` — for months —
  because detection matched the marker and never read the arguments. The fix
  (`heal_drift`) compares the full command. The MCP entry has the same shape
  today: `is_installed` checks the key, so a moved shim binary or a stale
  `--agent-uid` reads as installed. The provider boot heal likewise cannot
  see a projection whose base URL or model no longer match the connection.
- **Edge triggers miss what happens between edges.** Skill drift that
  accumulated while the daemon was down stayed broken until
  `boot_reconcile.py` was added; its docstring records zero
  `skill_drift_remediated` events in the audit log's whole history before
  then, because the only other path was a button nobody pressed. The one kind
  that never had this problem is the one that ticks: the channel runtime
  recomputes its desired set every two seconds and so heals any drift in its
  own domain without a trigger.

The audit side also needs a stated rule. A reconcile write lands in a file
outside the database; its audit row lands in the database (`audit_log`). The
current writers (`DeliveryService.install`, `AgentMcpService.install`) write
the file and then record the audit event in the same call, with no shared
transaction, because there is none to share.

## Options Considered

### Option A — One level-triggered reconciler with per-target actuators (chosen)

A single reconciler in `application/` owns a loop and a registry of
**targets**. A target is supplied by a kind or an agent facet and has three
parts:

- `desired()` — computed only from Coffer's own state (rows, reach, the
  running build's `command_for`, the shim path), as a list of items, each
  with a stable key and the **full parameters** it should have;
- `observe(key)` — reads what is actually there and returns the same shape,
  parsed (the provider heal already compares parsed JSON/TOML rather than
  text, because the removers reserialise);
- `apply(item)` / `remove(item)` — the one write each difference needs,
  through the kind's existing marker-scoped, atomic, backed-up writer.

A pass computes `desired − observed` for every target and applies the
differences. It runs at boot, on a fixed period, and whenever a hint arrives.
Hints are in-process `Changed(kind, uid, rev)` messages emitted after a write
through `ResourceService`; they only bring the next pass forward for the named
targets, so a lost hint costs at most one period and never correctness. The
same pass with `dry_run=True` returns the planned differences and writes
nothing — the change preview the UI needs before a switch and the drift view
it needs afterwards.

Each target also declares a **direction policy**, because not every
difference may be repaired by writing. The provider heal's documented rule —
correct Coffer's own flag, never re-route a user's agent on stale evidence —
and skill repair's "never clobber foreign content"
(`verify_ops._REPAIRABLE_KINDS`) stay, as policies of their targets. A
difference the policy will not repair is reported, not written.

- **Pros.** A parameter change is drift by construction, so the PR #413 class
  of failure is closed for every target at once, including the MCP entry that
  has it today. Drift that happens while the daemon is down, or between
  edges, is found on the next pass without anyone designing a trigger for it.
  One dry-run and one drift report cover every kind. The channel runtime
  shows the model already works in this codebase.
- **Cons.** A periodic pass reads files on a timer; its cost must be measured
  and bounded. Every target must make `observe` return parameters, not just
  presence, which is real work for the provider and MCP targets. Direction
  policies become explicit per target and must be reviewed as such.
- **Why it wins.** It is the only option under which "Coffer says it is
  installed" and "it works" cannot quietly diverge, and it generalises two
  mechanisms (`heal_drift`, the channel tick) the code already trusts.

### Option B — Keep a reconcile per kind, and add parameter comparison to each

Leave the table above as it is and bring each heal up to `heal_drift`'s
standard, kind by kind.

- **Pros.** No new framework; each kind keeps full control; the smallest
  diff per step.
- **Cons.** Six mechanisms keep six trigger sets, and whether a target is
  checked at boot, on a switch, after an import or never stays an accident of
  history — the MCP entry is checked never. There is no single place to ask
  "what would change?", so a dry-run is six implementations or none. The next
  targets (rules, commands, permissions, in
  [Agent Mechanisms Are Optional Facets on the Descriptor](agent-mechanisms-are-optional-facets-on-the-descriptor.md))
  would each add another. PR #413 shows how this fails: the rule was learned,
  applied to one target, and the neighbouring target with the same shape was
  left without it.
- **Why it loses.** It fixes today's instances and keeps the structure that
  produced them.

### Option C — Edge-triggered: an event bus, each change fans out to reactions

`ResourceService` publishes `ResourceChanged`; each kind subscribes and
re-applies what the change affects. Correctness rests on delivery.

- **Pros.** Work happens only when something changed; fast and cheap;
  natural for "the user just switched provider".
- **Cons.** The drift this ADR is about is caused by parties Coffer never
  hears from — another CLI, a restore, an upgrade of Coffer itself changing
  `command_for`. No event is ever published for those, so an event-driven
  design needs a periodic full pass anyway, at which point the events are only
  an accelerator. A lost or reordered event is a permanent divergence rather
  than a late one. [A Kind Plugs In as One Frozen Record of Optional Hooks](kind-plugin-contract.md)
  already rejected a bus for lifecycle hooks on the silent-miss argument, and
  it applies here with more force.
- **Why it loses.** It cannot see the changes that cause drift. Its useful
  half — reacting quickly — survives in Option A as the `Changed` hint.

### Option D — Filesystem watching on the target files

Watch every agent config file and skill directory and reconcile on change.

- **Pros.** Near-instant repair of external edits.
- **Cons.** It still misses changes made while the daemon was down and
  changes to Coffer's own desired state (a new build), so it needs the full
  pass too. Watchers differ per OS (FSEvents, inotify, ReadDirectoryChangesW)
  and would pull a platform mechanism into every target, which
  [Platform Differences Live Behind One Platform Port](platform-differences-live-behind-one-platform-port.md)
  keeps out of `application/`. Watching files Coffer itself rewrites also
  needs self-write suppression.
- **Why it loses.** It can be an optional hint source later, behind the
  platform port; never the basis of correctness.

## Decision

Everything Coffer keeps true outside its own database is converged by **one
level-triggered reconciler**. Each target states its desired items with their
full parameters, observes the actual items parsed into the same shape, and
repairs a difference only where its declared direction policy allows;
anything else is reported. A pass runs at boot, on a period, and early on an
in-process `Changed(kind, uid, rev)` hint; no hint is ever required for
correctness. A dry-run pass computes the same plan and writes nothing.

Rules a future change must respect:

- **Equality includes parameters.** A target whose `observe` can only answer
  "present / absent" is incomplete. Marker-scoped detection stays the way an
  entry is *found*, never the way it is *judged current*.
- **Audit follows the write, in the same call.** The reconciler writes the
  file (atomically, with the existing backup), then records the audit event
  with actor `system` before the call returns. If recording fails, it restores
  the prior content from that backup and reports the item as failed, so the
  next pass retries it. There is no cross-store transaction and none is
  claimed: a crash between the write and the audit leaves one unaudited
  write, which the daemon log records.
- **Dry-run is pure.** It may read anything and writes nothing — no file, no
  row, no audit event, no hint.
- **A pass outlives any one target.** A target that raises is reported and
  skipped, as `heal_drift` and `reconcile_once` already do.

## Consequences

- **Extends** the per-kind reconciles listed in Context rather than
  superseding an ADR. `heal_drift`, `SkillDriftBootHeal`,
  `ProviderProjectionBootHeal`, `ProviderProjectionReconcile` and
  `AgentSideEffectsReconcile` become targets; the one-off
  `mcp_home_migration` retires once the MCP target compares the entry's path.
  The sync post-import hooks (`application/sync/convergence_ops.reconcile`)
  become a hint source. The channel runtime keeps its own two-second loop for
  adapter lifecycle; its desired-set computation is the pattern the other
  targets follow.
- **Newly covered:** the MCP entry's shim path and `--agent-uid`; the provider
  projection's values, not just its presence; skill links on a period rather
  than only on edges.
- **Obligations.** Resources gain a monotonic `rev` for the hint (today
  `Resource` in `domain/resource.py` carries only `updated_at`). The period
  and a per-pass time budget are measured and kept under `perf/`. Spec deltas
  are needed where requirements name a trigger list instead of a state
  (skill-manager's per-trigger reconcile, provider-switching's boot-only
  heal), and to add parameter drift to the MCP install requirement.
- **Follow-up work:** the reconciler and its target contract; a test that
  reproduces PR #413 (a changed parameter is reported as drift and repaired);
  a test that a dry-run writes nothing under an isolated `HOME`; one drift /
  preview endpoint that the overview page and the change-preview component
  read.
