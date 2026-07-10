# ADR-045 — Machine × Agent Resource Scope

> 中文版: [ADR-045-machine-agent-resource-scope.zh.md](./ADR-045-machine-agent-resource-scope.zh.md)

- **Status:** Accepted
- **Spec:** [010-sync](../../specs/010-sync/spec.md) (amended; also amends
  [001-mcp-gateway](../../specs/001-mcp-gateway/spec.md),
  [004-agent-registry](../../specs/004-agent-registry/spec.md),
  [005-skill-manager](../../specs/005-skill-manager/spec.md), and
  [009-channels](../../specs/009-channels/spec.md))
- **Amends:** [ADR-043](./ADR-043-sync-machine-identity-near-real-time.md)
  (widens the "per-resource runtime affinity" follow-up ADR-043 reserved
  alongside machine identity into a framework-level facility, generalized
  with an agent axis)

## Context

Multi-machine sync (ADR-043) converges every resource onto every machine, but
some resources are only *usable* on one machine or by one agent: an MCP
server whose binary exists only on the MacBook, a skill written for Claude
Code only. The vault has no general way to say so:

- Channels are the only kind with machine affinity (`runs_on`, ADR-043).
- Skills have per-agent delivery policy (consumer-side follow flag +
  exclusions) but no machine dimension.
- MCP servers have neither: the gateway exposes every server's tools to
  every agent on every machine, and out-of-place servers fail or add noise.
- Agents not installed on a machine are handled implicitly by the import
  gate — permanent quarantine noise, retried every run.

ADR-043 explicitly reserved "per-resource runtime affinity" as a follow-up
hanging off machine identity. This ADR is that follow-up, widened to an
agent axis, validated in a brainstorming session on 2026-07-10 and recorded
in [`docs/research/machine-agent-scope.md`](../research/machine-agent-scope.md).

## Decision

Add one framework-owned `scope` field — a per-machine × per-agent activation
matrix — to the resource model; each kind declares which axes apply and owns
its own enforcement point.

1. **Framework-level `scope` matrix.** One `scope` shape lives on the
   `Resource` entity, not inside kind config. Semantics (single source of
   truth for the implementation):

   ```
   scope == None            → active on every machine, for every agent
   scope == {}              → active nowhere (dormant)
   scope == {"<ulid>": ["claude-code"], "*": "*"}   # dict[str, list[str] | "*"]
   ```

   - Entry lookup for machine M: exact-ULID key wins over `"*"` key; no key
     → inactive on M.
   - `machine_in_scope(scope, m)` → entry exists and value is `"*"` or a
     non-empty list.
   - `agent_in_scope(scope, m, agent)` → entry value is `"*"`, or `agent`
     (a name string) is in the list. `agent=None` (unidentified session)
     matches ONLY `"*"` values. `scope=None` → always True.
   - Kind axes: `mcp_server` (machine, agent) · `skill` (machine, agent) ·
     `agent` (machine) · `channel` (machine) · `knowledge_base`, `memory` —
     none (non-null scope rejected).
   - Machine-only kinds accept only `"*"` as entry value.
   - Unknown machine ULIDs / agent names in entries are legal and simply
     never match.
   - Matrices referencing an agent are additionally intersected with that
     agent's own machine axis when computing activation slices (the
     Machines view); the gateway itself trusts the local shim's identity
     and does not re-check the agent's machine axis, since a local shim
     can only run where the agent is installed.

2. **Sync-but-inactive.** A scoped resource still syncs to and is visible on
   every machine; out of scope it is simply not activated (not spawned, not
   exposed, not delivered). The registry stays the single source of truth
   and scope is editable from any machine — consistent with channel
   `runs_on` today.

3. **Per-kind axes and enforcement seams.** Each kind consults scope at its
   existing choke point, not a new central gate:

   | Kind                       | Axes             | Enforcement seam                                                                                                                                                        |
   | --------------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
   | `mcp_server`                | machine × agent  | Machine axis: upstream not spawned, tools not listed on that machine (gateway `_enabled_mcp_servers` + supervisor spawn gate). Agent axis: gateway filters the server's tools per session identity. |
   | `skill`                     | machine × agent  | Delivery filters by the matrix intersected with the existing per-agent follow policy; out-of-scope delivered copies are reconciled away.                                |
   | `agent`                     | machine          | No projection / reconcile / shim install on out-of-scope machines; the import gate stays as the fallback for in-scope machines missing `config_dir`.                    |
   | `channel`                   | machine          | `runs_on` migrates into scope; the channel runtime consults scope instead.                                                                                              |
   | `knowledge_base`, `memory`  | none             | A non-null scope is rejected at validation.                                                                                                                              |

4. **Shim self-reported `--agent` identity.** The shim install writes
   `coffer-mcp-shim --agent <name>` into the agent's config; the shim
   reports the name at handshake alongside the existing cwd `_meta`
   injection. Sessions without an identity (hand-configured shims) see only
   servers whose agent axis is `"*"` for the local machine. **Trust
   boundary:** identity is self-reported by the shim process, not
   cryptographically verified — acceptable in the single-user,
   loopback-only posture; the spec amendments state this boundary
   explicitly rather than implying stronger isolation than exists.

5. **Skill scope ∩ follow policy.** Follow is agent-side intent ("deliver
   skills to me"); scope is resource-side grant ("this skill may run
   here"). Delivery is the intersection of both — scoped-in *and*
   followed, minus manual exclusions. Scope is a hard grant that overrides
   manual bindings: an out-of-scope skill is reclaimed even if it was
   previously delivered by hand.

6. **Channel `runs_on` → scope migration.** `runs_on: <id>` becomes
   `{"<id>": "*"}`; `runs_on: null` becomes `{}`. A data migration converts
   existing channel resources on upgrade. The `runs_on` field is **not**
   removed from the schema — old payloads and synced docs from
   not-yet-upgraded machines must still validate — but it becomes inert:
   the channel runtime reads scope only, and `runs_on` is documented as
   deprecated in place.

7. **Knowledge and memory never scope.** `knowledge_base` and `memory`
   declare no axes and reject a non-null `scope` — always shared across all
   machines and all agents. Chat history, audit logs, runtime state, and
   machine-local settings stay machine-local (unchanged; restated here as a
   boundary, not a new decision).

8. **Machines fleet view.** A new top-level `Machines` nav item lists every
   registered machine (a sync-status strip above one card per machine); a
   per-machine detail view renders that machine's activation slice (agents
   present, MCP servers active, skills delivered per agent, channels
   bound), computed locally from the synced registry plus scope so any
   machine can render any machine's slice. Sync configuration (remote,
   auto-sync, master key) stays in Settings → Sync — this view is about
   activation, not transport.

9. **Manifest `SCHEMA_VERSION` → 4.** `scope` rides the resource doc
   through the existing export → merge → import pipeline, auto-conflict
   resolution, tombstones, and quarantine, unmodified — zero new sync
   machinery. Adding the field to resource docs bumps the workspace
   manifest schema version from 3 to 4, so a not-yet-upgraded build fails
   closed with the existing `SyncWorkspaceTooNew` gate instead of silently
   dropping or misreading the field.

## Alternatives considered

- **Per-kind bespoke fields** — let each kind grow its own affinity field
  (channel already has `runs_on`; give MCP servers and skills their own).
  Rejected: three incompatible shapes to validate, document, migrate, and
  render in the UI, for one concept. A framework-level field with per-kind
  axis declarations gets the same expressiveness from one implementation.
- **Consumer-side selection** — let each agent's local config decide which
  resources it uses (an override, not a registry field), mirroring how
  per-machine JSON-Merge-Patch overrides already handle divergent config
  values. Rejected: overrides are local by design and never sync as intent,
  so another machine could never see or edit a resource's activation — the
  registry would stop being the single source of truth for "where is this
  supposed to run."

## Consequences

- Migrations 0046 (adds `resources.scope_json`) and 0047 (channel `runs_on`
  → scope data migration) ship with this ADR's implementation; workspace
  manifest v4 means all machines must upgrade before scope-bearing docs
  sync cleanly — the same fleet-upgrade requirement ADR-043 introduced for
  v2.
- New REST surface (`GET`/`PUT .../scope`, `GET /api/v1/machines/{id}/slice`)
  and CLI surface (`coffer scope show|set|clear`, top-level `coffer
  machines`) for a concept that previously had no direct surface (channel
  `runs_on` was buried in channel config).
- The gateway, skill delivery, agent import/reconcile, and channel runtime
  each gain a scope-aware branch at their existing enforcement seam — no
  new seam is introduced, but four call sites change behavior.
- Self-reported shim identity is a trust boundary, not an isolation
  boundary: any process able to write `_meta` on the loopback MCP
  connection can claim any agent name. Accepted for a single-user tool;
  documented so a later multi-tenant posture doesn't inherit the
  assumption silently.
- Out-of-scope resources are a badge and list filter, never an error state;
  gateway and delivery skip silently — consistent with today's `runs_on`
  behavior, now generalized.
- Tool-level per-agent filtering (tool preferences) and machine-registry
  entry deletion remain out of scope for this ADR; no change to what syncs
  versus what stays machine-local beyond restating the existing boundary.
