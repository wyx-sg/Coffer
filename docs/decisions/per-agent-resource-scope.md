# Per-Agent Resource Scope

> 中文版: [per-agent-resource-scope.zh.md](./per-agent-resource-scope.zh.md)

- **Status:** Accepted
- **Spec:** [vault-export-import](../../specs/vault-export-import/spec.md) (also amends
  [mcp-gateway](../../specs/mcp-gateway/spec.md) and
  [skill-manager](../../specs/skill-manager/spec.md))
- **Amends:** [Everything Is a Resource Kind](./everything-is-a-resource-kind.md) (resources
  now carry a scope), [Tool Retrieval](./tool-retrieval-for-overload.md) /
  [Built-in Agent Is Internal](./builtin-agent-is-internal-capability.md)
  (`coffer__search_tools` ranking is scope-aware), and — since the 2026-09-13
  revision — [Provider Switching](./provider-switching.md) (a connection's
  `compatible_agents` field is replaced by this scope) and spec
  [channels](../../specs/channels/spec.md) (a channel's scope names the agents it
  may drive). See [Revision history](#revision-history).

## Context

Some resources are only *usable* by one agent: an MCP server whose tools only
make sense to a coding CLI, a skill written against Claude Code's frontmatter.
The vault had no general way to say so — the gateway exposed every server's
tools to every agent, and out-of-place servers failed or added noise.

Skills already had a per-agent delivery policy of their own (a consumer-side
follow flag plus exclusions). Per-agent MCP scoping had been tried once before as a
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
   - A kind that declares no scope rejects a non-null value at validation (422).
     Today `agent` is the only such kind, and every other kind declares scope —
     so that rule is now the exception rather than the common case.
   - A kind may also **pre-validate a proposed scope** (`Kind.validate_scope_for`),
     the scope path's counterpart to the config path's `on_update_config`: it is
     handed the resource as it stands plus the scope being proposed, and raising
     rejects the write before anything is persisted (same 422 envelope). It
     exists because a kind that reads scope with a consequence beyond filtering
     can have an invariant *between* its config and its scope, and enforcing
     that on the config path alone lets the other path store the state the
     invariant forbids. It sits beside `on_scope_changed` and deliberately fires
     at the opposite end of the operation: this one may refuse, so it must see
     the row unchanged; that one reconciles, so it must read the row already
     written. Only `channel` supplies one (item 7).

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
   | `skill` | agent | Delivery filters by the skill's own `enabled` flag intersected with scope; out-of-scope or disabled delivered copies are reconciled away. |
   | `knowledge` | agent | The built-in knowledge tools filter the collections a session may list, grep, read and write by the session's identity. |
   | `memory` | agent | Recall filters the partitions a session may read by that session's identity, so an aggregated partition reaches only the agents it is scoped to (spec memory FR-014). |
   | `channel` | agent — **inverted** | A channel is consumed by no agent, so its scope names the agents the channel may **drive**. `/agent` lists, offers and accepts only those; the channel's `default_agent` is held inside the scope on every write path — config and scope alike; a channel that may drive nothing does not start. |
   | `provider` | agent | The projection seam: the switch, the per-agent key lookup, the post-import reconcile and the boot self-heal all read scope (∩ `enabled`) to decide which agents a connection is written into. |
   | `agent` | none | It IS the agent, so there is nothing for a per-agent scope to narrow. A non-null scope is rejected at validation. |

4. **Shim self-reported `--agent` identity.** The shim install writes
   `coffer-mcp-shim --agent <name>` into the agent's config; the shim reports
   the name at handshake alongside the existing cwd `_meta` injection. Sessions
   without an identity (hand-configured shims) see only unscoped servers.
   **Trust boundary:** identity is self-reported by the shim process, not
   cryptographically verified — acceptable in the single-user, loopback-only
   posture. The spec states this boundary explicitly rather than implying
   stronger isolation than exists.

5. **Skill delivery is `enabled` ∩ scope, and nothing else.** This decision
   originally kept the agent-side follow policy and intersected it with scope,
   so delivery was follow ∩ scope minus per-agent exclusions, on top of a
   per-binding enable flag. That was three mechanisms answering one question,
   while `mcp_server` answered it with one. The follow flag and its exclusion
   list are gone; a binding row is now bookkeeping that records a delivered
   copy, not a switch. A skill reaches an agent iff the skill is `enabled` and
   the agent is in its scope, and a change to either is reconciled immediately —
   disabling a skill, or dropping an agent from its scope, reclaims the
   delivered copy even when it was placed by hand.

   What that costs: there is no longer a single agent-side "this agent gets
   nothing" switch. Excluding one agent means removing it from each skill's
   scope — which is exactly what excluding an agent from an MCP server has
   always meant. Per-skill exclusion keeps its full power; it is expressed on
   the skill rather than on the agent.

6. **A knowledge collection scopes — revised 2026-09-12.** This ADR originally
   said the `knowledge` kind declares no scope, because a collection was then
   one of three storage scopes over *content* (`global` / `project-<ULID>` /
   named collection) rather than a boundary anyone drew. With the layer reduced
   to plain files, a collection is the **only** boundary it has, and
   authorization is the reason it is a Resource at all: the kind declares
   `supports_scope`, and an agent lists, greps, reads and writes only the
   collections activated for it ([Knowledge Is Plain Files](knowledge-is-plain-files.md),
   spec knowledge FR-010…FR-012). Enforcement sits at the MCP tool surface
   only, so it prevents mistaken retrieval, not deliberate filesystem access by
   an agent that also holds shell tools (FR-014).
   Chat history, audit logs, runtime state and machine-local settings stay
   machine-local (restated as a boundary, not a new decision).

7. **A channel scopes, and its scope is inverted — added 2026-09-13.** This ADR
   originally said `channel` declares no scope, reasoning that scope names the
   agents a resource is active FOR and a channel is not consumed by an agent.
   The premise was right and the conclusion was wrong: a channel is the one
   inbound surface in the vault, and the natural reading of its scope is the
   mirror image — **the agents this channel may drive**. That is a real
   authorization question (a SeaTalk bot in a work group should not be able to
   drive every agent on the machine), and it had no answer at all.

   Two enforcement seams, because one without the other leaves a hole:
   `/agent` narrows its listing, its selection card and its validation to the
   scope (one narrowed set, so a card can never offer what the next check
   rejects), and the channel's `default_agent` is held inside the scope.

   That second seam is an invariant between two fields — the config's
   `default_agent` and the row's `scope` — and two endpoints can break it, so it
   is enforced on **both** write paths: the config path rejects a
   `default_agent` outside a non-empty scope (`on_update_config`), and the scope
   path rejects a non-empty scope that excludes the current `default_agent`
   (`validate_scope_for`, the framework hook item 1 grows for this). Enforcing
   it on the config path alone was not a narrower rule but a broken one: a
   narrowing accepted by the scope endpoint left a row the runtime then refuses
   to start, and the owner's bot went dead with one log line to say why. A
   thread's sticky `/agent` choice falls back to the channel default once the
   scope stops admitting it.

   `scope = []` is dormant, and for a channel that means the runtime does not
   start its adapter — the loud, early failure, rather than a live bot that
   accepts a message and then refuses it. It is therefore the one scope both
   write paths always accept: dormant is the owner saying "off", and off must not
   also mean frozen, so a dormant channel's config stays editable and a wrong
   token can be corrected without reactivating the channel first. The scope rides
   the live binding, so an edit takes effect within one reconcile tick.

8. **`provider` scopes, and its own "which agents" field is withdrawn — added
   2026-09-13.** The `provider` kind already had this axis: `compatible_agents`
   inside its config, deciding which agents a connection projects into. It was
   the last kind still answering the framework's question its own way — exactly
   the divergence Decision item 3 was written to end — so the field is removed
   and the kind declares `supports_scope`.

   The migration is the interesting part, and the reason this could not be a
   rename. The two axes disagree on what UNSET means: `compatible_agents = null`
   meant *the wire's default* (nothing at all for a keyless ollama connection),
   while `scope = null` means *every agent*. A rename would therefore have
   widened every connection that had never been narrowed. So migration 0071
   **materialises** every existing row — it computes the effective set and
   writes it out concretely, then strips the dead key — and the framework grows
   one small hook, `Kind.default_scope`, so a newly created connection is
   pre-filled from its wire instead of starting out reaching everything. The hook
   is a function of the config alone; `memory`, whose starting scope is the set
   of agents a partition was aggregated FROM, cannot be expressed that way and
   keeps setting its own scope right after registering.

   Two flags survive side by side here, and they are not redundant: `enabled` is
   the user's switch on the resource (a disabled connection projects nowhere and
   resolves no key), while `is_active` records that this is the connection
   currently *written into* the agents it reaches. The second is a claim about a
   file on disk, which is why a boot self-check exists to catch it disagreeing
   with reality.

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
- Scope is now the vault's ONE answer to "which agents does this reach", for
  every kind but `agent` itself. A user who learns the control once can apply it
  to servers, skills, collections, memory partitions, channels and connections,
  and a kind that grows the question later declares the field rather than
  inventing a field of its own.
- Two kinds read scope with a consequence beyond filtering: a dormant channel
  does not run, and a dormant connection projects into no agent. "Dormant" is
  therefore not always merely invisible — for those two it is off. Off is still
  only off: a dormant resource stays visible, exportable and editable.
- Because a kind whose scope has such a consequence can pre-validate the scope
  write (item 1), narrowing a reach can now be REFUSED rather than merely having
  an effect the user did not intend. That is one more way a scope edit can fail,
  and the cost is worth naming: the user occasionally has to make two edits in
  order (change the channel's default agent, then narrow its scope) where one
  used to be accepted. What that buys is that the only way to stop a channel is
  to say so — `scope = []`, or disabling it — never a narrowing that looked like
  it worked.

## Revision history

- **2026-08-xx** — Accepted with a machine × agent matrix, `mcp_server` and
  `skill` scoped, and `agent` / `channel` / `knowledge` declaring none.
- **2026-09-09** — The machine axis is withdrawn with continuous multi-machine
  sync ([Vault Export and Import](./vault-export-import.md)); only the agent
  axis remains.
- **2026-09-12** — `knowledge` reverses to scoping: with the layer reduced to
  plain files, a collection is the only boundary it has (Decision item 6).
- **2026-09-13** — `channel` and `provider` reverse to scoping (Decision items 7
  and 8), and `memory` — which shipped with `supports_scope` but never got a row
  — is entered in the table. `agent` is now the only kind that declares no
  scope, and the ADR no longer justifies the two exclusions it used to.
