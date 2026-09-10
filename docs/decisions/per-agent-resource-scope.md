# Per-Agent Resource Scope

> 中文版: [per-agent-resource-scope.zh.md](./per-agent-resource-scope.zh.md)

- **Status:** Accepted
- **Spec:** [vault-export-import](../../specs/vault-export-import/spec.md) (also amends
  [mcp-gateway](../../specs/mcp-gateway/spec.md) and
  [skill-manager](../../specs/skill-manager/spec.md))
- **Amends:** [Everything Is a Resource Kind](./everything-is-a-resource-kind.md) (resources
  now carry a scope) and [Tool Retrieval](./tool-retrieval-for-overload.md) /
  [Built-in Agent Is Internal](./builtin-agent-is-internal-capability.md)
  (`coffer__search_tools` ranking is scope-aware)

## Context

Some resources are only *usable* by one agent: an MCP server whose tools only
make sense to a coding CLI, a skill written against Claude Code's frontmatter.
The vault had no general way to say so — the gateway exposed every server's
tools to every agent, and out-of-place servers failed or added noise.

Skills already had a per-agent delivery policy (a consumer-side follow flag
plus exclusions). Per-agent MCP scoping had been tried once before as a
kind-specific feature and reverted in the 2026-06-20 simplification, because
carrying an allowlist and a session identity inside one kind cost more than it
returned there. Two kinds solving the same problem two different ways is the
signal to lift it into the framework instead, where the identity plumbing is
paid for once and every kind that needs it can declare it.

This ADR originally also carried a **machine** axis, added alongside continuous
multi-machine sync. That sync is withdrawn ([Vault Export and Import](./vault-export-import.md)),
and with it the machine registry that gave machine identities meaning, so the
machine axis is removed and only the agent axis remains.

## Decision

Add one framework-owned `scope` field — a list of agent names — to the resource
model; each kind declares whether it supports scope and owns its own
enforcement point.

1. **Framework-level `scope`.** One `scope` shape lives on the `Resource`
   entity, not inside kind config:

   ```
   scope == None                       → active for every agent
   scope == []                         → active for no agent (dormant)
   scope == ["claude-code"]            → active only for the named agents
   ```

   - `agent_in_scope(scope, agent)` → `True` when `scope is None`, else
     `agent` is in the list. An unidentified session (`agent=None`) matches
     only `scope is None`.
   - Unknown agent names in the list are legal and simply never match — an
     agent can be scoped in before it is registered.
   - Kinds that declare no scope reject a non-null value at validation (422).

2. **Exported but inactive.** A scoped resource still exports and imports
   normally, and stays visible in the registry everywhere; out of scope it is
   simply not activated — not exposed, not delivered. The registry remains the
   single source of truth, and scope is an ordinary resource field that travels
   through export and import unmodified.

3. **Per-kind support and enforcement seams.** Each kind consults scope at its
   existing choke point, not at a new central gate:

   | Kind | Scope | Enforcement seam |
   | --- | --- | --- |
   | `mcp_server` | agent | The gateway filters the server's tools by the session's identity. |
   | `skill` | agent | Delivery filters by scope intersected with the existing per-agent follow policy; out-of-scope delivered copies are reconciled away. |
   | `agent`, `channel`, `knowledge` | none | A non-null scope is rejected at validation. |

4. **Shim self-reported `--agent` identity.** The shim install writes
   `coffer-mcp-shim --agent <name>` into the agent's config; the shim reports
   the name at handshake alongside the existing cwd `_meta` injection. Sessions
   without an identity (hand-configured shims) see only unscoped servers.
   **Trust boundary:** identity is self-reported by the shim process, not
   cryptographically verified — acceptable in the single-user, loopback-only
   posture. The spec states this boundary explicitly rather than implying
   stronger isolation than exists.

5. **Skill scope ∩ follow policy.** Follow is agent-side intent ("deliver
   skills to me"); scope is resource-side grant ("this skill may run here").
   Delivery is the intersection — scoped-in *and* followed, minus manual
   exclusions. Scope is a hard grant that overrides manual bindings: an
   out-of-scope skill is reclaimed even if it was previously delivered by hand.

6. **Knowledge never scopes.** The `knowledge` kind declares no scope and
   rejects a non-null value — always shared across every agent. (Its own
   `global` / `project-<ULID>` / named-collection axis is a knowledge-layer
   scope over *content*, unrelated to this framework field, which is about
   *which agent may see a resource*.)
   Chat history, audit logs, runtime state and machine-local settings stay
   machine-local (restated as a boundary, not a new decision).

## Alternatives considered

- **Machine × agent matrix** — what this ADR previously decided. Its machine
  axis was keyed by machine ULIDs from the sync machine registry; without
  continuous sync there is no registry, no second machine to be inactive on,
  and nothing for the axis to mean. Withdrawn with the sync it belonged to.
- **Keep per-agent scoping inside each kind** — no framework field, each kind
  rolls its own allowlist and identity handling. This is the shape that was
  tried and reverted in 2026-06. Rejected: two kinds had already diverged on
  the same problem, and a third would have diverged again.
- **Deny-list instead of allow-list** — "every agent except these". Rejected:
  a new agent would silently gain access to every scoped resource, which is the
  wrong default for a grant.

## Consequences

- `scope` is one nullable list on `Resource`, validated per kind, and rides
  export/import as an ordinary field — no dedicated machinery.
- The gateway's tool listing becomes identity-dependent: the same server can
  present different tool sets to different agents in the same vault.
- A hand-configured shim without `--agent` is not a privilege escalation path
  in the other direction: it sees strictly less (unscoped resources only).
- Scoping a skill out reclaims it from an agent that already has it, so scope
  edits have visible filesystem effects — audited like any other delivery
  change.
