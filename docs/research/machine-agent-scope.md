# Machine × Agent Resource Scope — Design

> 中文版: [machine-agent-scope.zh.md](./machine-agent-scope.zh.md)

Design note for generalizing machine identity (spec 010 / ADR-043) into a
resource-framework-level **scope** facility, plus a top-level **Machines**
fleet view. Validated in a brainstorming session on 2026-07-10; this note is
the input to the ADR + spec amendments that will carry the product contract.

## Problem

Multi-machine sync converges every resource onto every machine, but some
resources are only *usable* on one machine or by one agent: an MCP server
whose binary exists only on the MacBook, a skill written for Claude Code
only. Today the vault has no way to say so —

- Channels are the only kind with machine affinity (`runs_on`, ADR-043).
- Skills have per-agent delivery policy (consumer-side follow flag +
  exclusions) but no machine dimension.
- MCP servers have neither: the gateway exposes every server's tools to every
  agent on every machine, and out-of-place servers fail or add noise.
- Agents not installed on a machine are handled implicitly by the import
  gate — permanent quarantine noise, retried every run.

ADR-043 explicitly reserved "per-resource runtime affinity" as a follow-up
hanging off machine identity. This design is that follow-up, widened to an
agent axis.

## Decisions (validated with the user)

1. **Sync-but-inactive.** A scoped resource still syncs to and is visible on
   every machine; out of scope it is simply not activated (not spawned, not
   exposed, not delivered). The registry stays the single source of truth and
   scope is editable from any machine. (Consistent with channel `runs_on`.)
2. **Full matrix.** Scope is a per-machine × per-agent matrix, not two
   independent axes — "on the MacBook for Claude Code, on the desktop for
   Codex" is expressible.
3. **Agents get a machine axis too.** An agent declares which machines it
   exists on; the import gate demotes to a safety net and its quarantine
   noise disappears when scope is set correctly.
4. **Framework-level facility.** One `scope` shape owned by the resource
   framework; each kind declares which axes apply and owns its enforcement
   point. Channel `runs_on` migrates into it.
5. **Knowledge and memory never scope.** `knowledge_base` and `memory`
   declare no axes — always shared across all machines and all agents. Chat
   history, audit logs, runtime state, and machine-local settings stay
   machine-local (unchanged, restated as a boundary).
6. **Top-level Machines fleet view.** A new top-level tab lists every machine
   with a per-machine drill-down (the matrix sliced by machine). Sync
   configuration (remote, auto-sync, master key) stays in Settings → Sync.

## Data model

Optional framework-owned `scope` field on a resource:

```yaml
scope: null                       # default: active on all machines, all agents
scope:
  "01HXX…MACBOOK": ["claude-code"]        # MacBook: Claude Code only
  "01HYY…DESKTOP": ["codex", "opencode"]  # desktop: these two
scope:
  "*": ["claude-code"]            # every machine, Claude Code only
scope:
  "01HXX…MACBOOK": "*"            # MacBook only, every agent there
scope: {}                         # dormant everywhere
```

- Keys are machine ULIDs or `"*"`; values are agent-name lists or `"*"`.
- Evaluation: `active(M, G)` ⇔ scope is `null`, or the entry for `M` (exact
  ULID key wins over `"*"`) contains `G` or is `"*"`.
- Kind axis declaration: `mcp_server` machine × agent; `skill` machine ×
  agent; `agent` machine-only; `channel` machine-only; `knowledge_base` /
  `memory` none. Machine-only kinds accept only `"*"` as the agent value
  (schema-enforced).
- Entries referencing unknown machine IDs or agent names are kept but never
  match (the other machine may not have synced yet; the agent may be
  registered later).
- Agents referenced by a matrix are additionally intersected with the agent's
  own machine axis.

## Enforcement points (per kind)

| Kind         | Axes            | Out-of-scope behavior                                                                                                                                                                 |
| ------------ | --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `mcp_server` | machine × agent | Machine axis: upstream not spawned, tools not listed on that machine. Agent axis: the gateway filters the server's tools per session identity.                                          |
| `skill`      | machine × agent | Delivery filters by the matrix **intersected** with the existing per-agent follow policy (follow = agent-side intent, scope = resource-side grant); out-of-scope delivered copies are reconciled away. |
| `agent`      | machine         | No projection / reconcile / shim install on out-of-scope machines; import gate stays as the fallback for in-scope machines missing `config_dir`.                                        |
| `channel`    | machine         | Existing `runs_on` migrates (`runs_on: <id>` → `{"<id>": "*"}`; `runs_on: null` → `{}`); the API field remains as a compatibility alias.                                              |

**Gateway session identity.** The shim install writes
`coffer-mcp-shim --agent <name>` into the agent's config; the shim reports the
name at handshake alongside the existing cwd `_meta` injection. Sessions
without an identity (hand-configured shims) see only servers whose agent axis
is `"*"` for the local machine. Identity is self-reported — acceptable in the
single-user, loopback-only posture; the spec states this boundary explicitly.

## Sync semantics — zero new machinery

`scope` is part of the resource doc: it rides the existing export → merge →
import pipeline, auto-conflict resolution, tombstones, and quarantine
untouched. Editing scope on any machine propagates like any other resource
edit. The workspace manifest schema version bumps (new field in resource
docs), so older builds fail with the existing `SYNC_WORKSPACE_TOO_NEW` gate
instead of misreading docs.

## Machines fleet view (top-level tab)

- New top-level nav item **Machines** (`/machines`): a sync-status strip
  (state, last sync, manual run trigger, link to Settings → Sync) above one
  card per machine (display name, platform, last sync, "this machine" badge,
  rename).
- Machine detail (`/machines/:id`): the machine's **activation slice** —
  agents present, MCP servers active, skills delivered per agent, channels
  bound. Computed locally from the synced registry + scope, so any machine
  can render any machine's slice. The local machine additionally shows
  **actuals** (quarantines, install state); remote machines show intent only.
- Resource detail pages gain a **Scope card**: a matrix editor (one row per
  registry machine, per-row agent multi-select or "all"), shaped by the
  kind's axis declaration, with a one-click reset to "everywhere".

## Surfaces

- **REST:** `scope` in resource CRUD payloads (framework-level, validated per
  kind axes); `GET /api/v1/machines/{id}/slice` for the activation slice.
- **CLI:** `coffer scope show|set|clear <kind>:<name>`; `coffer machines`
  promoted out of the sync group (`coffer sync machines` stays as an alias).

## Boundaries

- Out-of-scope-here resources are a badge ("not active on this machine") and
  a list filter, not an error state; gateway/delivery skip silently.
- `scope: {}` (dormant everywhere) is legal — the moral equivalent of
  channel's `runs_on: null` today.
- Machine-entry deletion from the registry is out of scope (the registry has
  no delete semantics today).

## Local-first posture and doc impact

This feature does not weaken local-first — multi-device sync over a
user-owned medium is a core local-first ideal (every machine holds the full
vault; the medium is transport + history only; constitution 0.3.0 conditions
hold). What changes is wording: "local = this one machine" matures into
"local = the user's machines, one vault, each machine complete".

| Document                             | Change                                                                                                            |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| `constitution.md`                    | Editorial 0.3.x amendment: Principle I "the user's machine" → "the user's machines". No principle change.          |
| `architecture.md`                    | Machine identity promoted to a framework core concept; `scope` facility documented alongside the kinds table.       |
| `AGENTS.md` / `README.md`            | Positioning line gains "one vault across the user's machines".                                                      |
| New ADR (amends ADR-043)             | Scope matrix semantics, shim identity, follow-policy intersection, `runs_on` migration.                              |
| Specs 010 / 001 / 004 / 005 / 009    | Amendments per the enforcement table above, each with acceptance scenarios, bilingual pairs.                          |

## Testing

- **Unit:** scope evaluation (wildcard precedence, unknown refs, machine-only
  kinds rejecting agent lists).
- **Integration:** gateway per-session filtering; skill matrix ∩ follow
  delivery and reclaim; channel `runs_on` migration; agent axis with the
  import-gate fallback.
- **Contract:** scope payload validation; the slice endpoint.
- **E2E:** two-machine scope round trip — edit scope on A, activation flips
  on B.

## Out of scope

- Tool-level per-agent filtering (tool preferences remain a separate, shared
  mechanism).
- Machine registry entry deletion / retirement.
- Any change to what syncs vs. stays local beyond restating the boundary.
