# One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database, Comparing Parameters

**Status**: Accepted
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [Coffer's Agent Hooks Are Marker-Scoped, Explicit, Audited and Repaired When Stale](agent-hook-installation.md), [Skills Reach an Agent as a Directory Link to One Master Folder](cross-platform-skill-delivery.md), [LLM Connections Are Projected Into Each Agent's Own Config File](provider-connections-projected-into-agent-config.md), [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md), [A Kind Plugs In as One Frozen Record of Optional Hooks](kind-plugin-contract.md), [Audit Every Change With Its Actor](audit-and-retention.md), [Channels Are Thin Transport Adapters Over One Shared Core](channel-adapter-framework.md), [Agent Mechanisms Are Optional Facets on the Descriptor](agent-mechanisms-are-optional-facets-on-the-descriptor.md), [Platform Differences Live Behind One Platform Port](platform-differences-live-behind-one-platform-port.md), spec memory "Repair stale delivery hooks", spec skill-manager "Reconcile deliveries from state on every pass", spec skill-manager "Heal safely repairable drift on every pass", spec provider-switching "Clear an agent's connection its config contradicts", spec agent-registry "Install Coffer's MCP server into an agent in one action", spec vault-sync "Re-run post-import hooks after applying", PR #413

## Context

Most of what Coffer promises is a state of files it does not own: a
`coffer` entry in `~/.claude.json` and Codex's `config.toml`, a
`SessionStart` / `UserPromptSubmit` hook, a directory link per delivered
skill, a provider's keys in `settings.json`, a running channel adapter. Those
files are rewritten by their own CLIs, by other tools, by backups and by the
user, often while the daemon is not running. The database row says what should
be true; only the file says what is.

Before this decision each kind answered "is it still true?" with its own
code, its own trigger and its own idea of equality:

| What Coffer keeps true | When it checked | What it compared |
| --- | --- | --- |
| Memory delivery hook | boot, the `memory` feature switch | the **whole command**, against what the running build writes |
| Skill links | a list of edge events (a delivery, a switch, a sync) plus boot | link exists and points at the master folder |
| Provider projection | boot, and after a sync import | at boot, **presence** of Coffer's keys only, never their values |
| Coffer's MCP entry | on request only, plus a one-off migration | **presence** of the `coffer` key; the shim path was read for display, never compared |
| Agent side effects after import | post-import | delegated to skill delivery |
| Channel adapters | **every 2 s** (`reconcile_once` in `application/channel/runtime.py`) | a hash of the binding, so a parameter change restarts the adapter |

Two facts in that table decide this ADR.

- **Presence is not correctness.** PR #413 is the incident: when
  `coffer memory context` moved from `--agent` to `--agent-uid`, every hook on
  disk kept the old option, the agent printed a usage error at the start of
  every session, and the status page said `installed: True` — for months —
  because detection matched the marker and never read the arguments. The fix
  compared the full command. The MCP entry had the same shape: presence of
  the key meant a moved shim binary or a stale `--agent-uid` read as
  installed. The provider boot heal likewise could not see a projection whose
  base URL or model no longer matched the connection.
- **Edge triggers miss what happens between edges.** Skill drift that
  accumulated while the daemon was down stayed broken until a boot heal was
  added; its docstring recorded zero `skill_drift_remediated` events in the
  audit log's whole history before then, because the only other path was a
  button nobody pressed. The one kind that never had this problem is the one
  that ticks: the channel runtime recomputes its desired set every two
  seconds and so heals any drift in its own domain without a trigger.

The audit side also needs a stated rule. A reconcile write lands in a file
outside the database; its audit row lands in the database (`audit_log`). The
writers write the file and then record the audit event in the same call, with
no shared transaction, because there is none to share.

## Options Considered

### Option A — One level-triggered reconciler with per-target actuators (chosen)

A single reconciler (`application/reconcile/reconciler.py`) owns a loop and a
registry of **targets** (the contract is `application/reconcile/ports.py`). A
target is supplied by a kind or an agent facet and has these parts:

- `desired()` — computed only from Coffer's own state (rows, reach, the
  command the running build writes, the shim path), as a list of items, each
  with a stable key and the **full parameters** it should have;
- `observe()` — reads what is actually there and returns the same shape,
  parsed (the provider target compares parsed JSON/TOML rather than text,
  because the removers reserialise);
- `decide(differences, trigger)` — the direction policy, below;
- `apply(change)` — the one write each repairable difference needs, through
  the kind's marker-scoped, atomic, backed-up writer.

A pass computes `desired − observed` for every target and applies the
repairable differences. It runs at boot (awaited before the daemon reports
ready), on a fixed period (60 seconds), and whenever a hint arrives. Hints are
in-process `Changed(kind, uid, op)` messages emitted by a repository wrapper
(`application/reconcile/hints.py`) after every write to a resource row; they
only bring the next pass forward for the targets that follow that kind, so a
lost hint costs at most one period and never correctness. A person's own write,
a sync import and a feature switch also request a pass with their own trigger,
which the direction policies read. A dry-run plan returns the planned
differences and writes nothing — the change preview before a switch and the
drift view afterwards (`GET /api/v1/reconcile/plan`; a person applies chosen
differences with `POST /api/v1/reconcile/apply`).

Each target also declares a **direction policy**, because not every
difference may be repaired by writing. The provider target's rule —
correct Coffer's own flag, never re-route a user's agent on stale evidence —
and skill repair's "never clobber foreign content" are policies of their
targets. A
difference the policy will not repair is reported, not written.

- **Pros.** A parameter change is drift by construction, so the PR #413 class
  of failure is closed for every target at once, including the MCP entry that
  had it. Drift that happens while the daemon is down, or between
  edges, is found on the next pass without anyone designing a trigger for it.
  One dry-run and one drift report cover every kind. The channel runtime
  shows the model already works in this codebase.
- **Cons.** A periodic pass reads files on a timer; its cost must be measured
  and bounded (a full pass over two agents, twenty skills, a provider and both
  hooks measured about 27 ms, `backend/tests/integration/perf/test_reconcile_pass_cost.py`). Every target must make `observe` return parameters, not just
  presence, which is real work for the provider and MCP targets. Direction
  policies become explicit per target and must be reviewed as such.
- **Why it wins.** It is the only option under which "Coffer says it is
  installed" and "it works" cannot quietly diverge, and it generalises two
  mechanisms (the whole-command hook comparison, the channel tick) the code already trusts.

### Option B — Keep a reconcile per kind, and add parameter comparison to each

Leave the table above as it was and bring each heal up to the hook heal's
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
in-process `Changed(kind, uid, op)` hint; no hint is ever required for
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
  skipped, as the channel runtime's loop already does.

## Consequences

- The memory delivery hook, skill links, the provider projection and Coffer's
  MCP entry are targets (`application/memory/delivery_reconcile.py`,
  `application/skill/link_reconcile.py`,
  `application/provider/projection_reconcile.py`,
  `application/agent/mcp_reconcile.py`); the per-kind boot heals, the
  post-import reconciles and the one-off MCP home migration the design
  replaced are gone. A sync round runs one reconcile pass with the import's
  trigger after it applies, and `SyncService` holds the reconciler for the
  round, so a pass cannot judge the vault before the round's own import pass
  and undo what another machine switched.
- Newly covered: the MCP entry's shim path and `--agent-uid`; the provider
  projection's values, not just its presence; skill links on a period rather
  than only on edges. The period and a per-pass time budget are kept under
  `backend/tests/integration/perf/`.
- The channel runtime keeps its own two-second loop for adapter lifecycle
  (`reconcile_once`); its desired-set computation is the pattern the targets
  follow, and channels are not a target of the unified reconciler.
- Not built yet: a monotonic `rev` on resources. Hints carry the kind, the uid
  and the operation; a pass compares content, so no revision is needed for
  correctness.
- Not built yet: filesystem watching as a hint source. It could be added
  behind the platform port without touching correctness.
