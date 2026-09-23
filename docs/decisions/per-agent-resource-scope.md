# Per-Agent Resource Scope

**Status**: Accepted
**Date**: 2026-09-09
**Deciders**: Yuxing Wu
**Spec**: [vault-sync](../../openspec/specs/vault-sync/spec.md) (also amends [mcp-gateway](../../openspec/specs/mcp-gateway/spec.md) and [skill-manager](../../openspec/specs/skill-manager/spec.md))
**Amends**: [Everything Is a Resource Kind](./everything-is-a-resource-kind.md) (resources now carry a scope), [Tool Retrieval](./tool-retrieval-for-overload.md) / [Built-in Agent Is Internal](./builtin-agent-is-internal-capability.md) (`coffer__search_tools` ranking is scope-aware), and — since the 2026-09-13 revision — [Provider Switching](./provider-switching.md) (a connection's `compatible_agents` field is replaced by this scope) and spec [channels](../../openspec/specs/channels/spec.md) (a channel's scope names the agents it may drive). See [Revision history](#revision-history).

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

This ADR has twice carried a **machine** axis, and twice lost it. The second
time settled the question. A converged vault holds every machine's resources on
every machine, so "not here" is genuinely something a resource must be able to
say — but there are two places to say it, and only one of them can be checked by
the person saying it. Naming machine ids inside a synced `scope` says it from
wherever you happen to be sitting, about machines you cannot see. Keeping the
answer *on* each machine says it where it takes effect. Coffer now does the
second: a resource's reach is machine-local and never travels, so a machine
expresses "not here" simply by not activating it here, and the axis has nothing
left to add.

## Decision

Add one framework-owned `scope` field — an allow-list of agents — to the
resource model; each kind declares whether it supports scope and owns its own
enforcement point. Scope, together with the resource's `enabled` flag, is the
resource's **reach**, and reach is machine-local.

1. **Framework-level `scope`.** One `scope` shape lives on the `Resource`
   entity, not inside kind config:

   ```
   scope == None                          → active for every agent
   scope == {agents: ["claude-code"]}     → that agent only
   scope == {agents: []}                  → dormant (an empty list matches nothing)
   ```

   [The list holds agent **uids**, not names, since
   [Resource Identity Is an Immutable `uid`](./resource-identity-is-an-immutable-uid.md):
   a scope is a reference to another resource, and a name is a label its owner
   may change. While it held names, renaming an agent silently emptied every
   scope naming it. Migration `0096` rewrote the stored lists. Nothing else in
   this item changes — read `"claude-code"` above as that agent's uid.]

   - `None` is unrestricted; a list restricts to it.
   - `is_active(scope, agent)` → `True` when the scope admits that agent. An
     unidentified session (`agent=None` — a hand-configured shim reporting no
     `--agent`) matches only an unrestricted scope, so it sees strictly less,
     never more.
   - Unknown entries are legal and simply never match — a resource can be scoped
     to an agent before that agent has appeared, or on a machine that does not
     have it.
   - A kind that declares no scope rejects a non-null value at validation (422).
     Four kinds declare scope — `mcp_server`, `skill`, `provider`, `channel` —
     and three declare none: `agent`, `knowledge` and `memory` (item 7). A kind
     is expected to say which, not to inherit either answer.
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
     written. Only `channel` supplies one (item 8).

2. **Reach is machine-local.** `scope` and `enabled` are one thing — the
   resource's *reach*, written by one control — and neither is serialized into
   the sync bundle or written by a converge round (spec
   [vault-sync](../../openspec/specs/vault-sync/spec.md) "Keep reach machine-local"). What
   travels between machines is the resource: what it *is*, and how it is
   configured. What it reaches, here, stays here.

   The alternative — a synced reach carrying machine ids — is the shape this ADR
   shipped on 2026-09-14 and withdrew immediately after. It fails on two counts.
   It cannot be verified from where it is set: the laptop's user picks ids out of
   a registry describing machines they are not sitting at, and a mistyped or
   retired id makes a resource dormant somewhere they cannot look. And it has no
   honest answer to who wins: two machines editing one resource's reach put a
   permission through a text merge, and whichever round ran last quietly decides
   what the other machine exposes. Machine-local reach has neither problem,
   because there is nothing to merge.

   The cost is real and worth naming: a resource arriving on a machine for the
   first time starts at that kind's default reach there, not at the reach it has
   elsewhere. That is a state the user can see on the page and change in one
   click, and it is the direction that asks rather than assumes.

   Surfaces MUST say this where reach is set, not in a document. Someone
   restricting a resource is entitled to know the restriction stops at this
   machine.

   One control means one button, labelled with the answer it already holds —
   *Every agent*, *2 agents*, *Disabled* — that opens a panel where those states
   are the choices: *Disabled*, *Every agent*, *Only selected agents* over the
   scope's tick-list, with the machine-local sentence beneath them. It earned
   that shape by losing the previous one. Three segments side by side
   (*Disabled* / *Everywhere* / *Restricted…*) spent three controls on two
   states, because "everywhere" and "restricted with every agent ticked" are one
   answer written twice — and the reader had to compare all three to learn which
   of them was live. A button that states the reach answers that by being read.
   *Disabled* keeps a choice of its own because it still IS a choice of its own:
   its own endpoint, its own audit events, and a write that deliberately leaves
   `scope` alone, so re-enabling restores the agents the user had picked. The
   panel stages the tick-list and writes exactly once, when it closes — the two
   whole-value choices close it themselves — so a panel that was opened and
   dismissed writes nothing at all. A kind that declares no scope gets the same
   button over a two-choice *Disabled* / *Enabled* panel, and a multi-select,
   which has no current reach to name, gets one reading *Set reach…* that opens
   with nothing chosen.

3. **Registered everywhere, active where it is granted.** A resource still
   converges to every machine and stays visible in every registry; out of reach
   it is simply not activated — not exposed, not delivered. The registry remains
   the single source of truth for what exists; reach is the local answer to what
   runs.

   `channel` converges like every other kind, and answers "which machine runs
   it" with a field of its own — `runs_on`, in its config ([channels](../../openspec/specs/channels/spec.md) "Bind each channel to the one machine that runs it"). It is deliberately not a scope axis: reach is the LOCAL answer to
   what runs here, which is why it never travels, while the machine that runs a
   channel is one answer the machines share. A channel briefly did not converge
   at all, for want of anywhere to say that.

4. **Per-kind support and enforcement seams.** Each kind consults scope at its
   existing choke point, not at a new central gate:

   | Kind | Enforcement seam |
   | --- | --- |
   | `mcp_server` | The gateway filters the server's tools by the session's agent, so a server scoped away from that agent presents no tools to it. |
   | `skill` | Delivery filters by the skill's own `enabled` flag intersected with scope; out-of-scope or disabled delivered copies are reconciled away. |
   | `channel` | **Inverted.** A channel is consumed by no agent, so its scope names the agents the channel may **drive**: `/agent` lists, offers and accepts only those, and a channel that may drive nothing does not start its adapter at all. |
   | `provider` | The projection seam: the switch, the per-agent key lookup, the post-import reconcile and the boot self-heal read scope (∩ `enabled`) to decide which agents a connection is written into. |
   | `agent` | None. It IS the agent, so there is nothing for a scope to narrow. A non-null scope is rejected at validation. |
   | `knowledge`, `memory` | None, as of 2026-09-18. Both serve files an agent is handed the path to, so reach could only have hidden them from a well-behaved retrieval — never withheld them. See item 7. |

5. **Shim self-reported `--agent` identity.** The shim install writes
   `coffer-mcp-shim --agent <name>` into the agent's config; the shim reports
   the name at handshake alongside the existing cwd `_meta` injection. Sessions
   without an identity (hand-configured shims) see only unscoped servers.
   [Since [Resource Identity Is an Immutable `uid`](./resource-identity-is-an-immutable-uid.md)
   the flag is `--agent-uid <uid>` and the handshake key is
   `coffer/agent-uid`, for the reason that makes this item work at all: the
   entry is written once into a file Coffer does not revisit, so a label in it
   would go stale on the first rename. An older shim still sending the
   name-based key is read as *unidentified* — there is deliberately no name
   fallback, so a stale label can never be matched against a scope. Everything
   else in this item, the trust boundary included, is unchanged.]
   **Trust boundary:** identity is self-reported by the shim process, not
   cryptographically verified — acceptable in the single-user, loopback-only
   posture. The spec states this boundary explicitly rather than implying
   stronger isolation than exists.

6. **Skill delivery is `enabled` ∩ scope, and nothing else.** This decision
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

7. **`knowledge` and `memory` declare no reach — withdrawn 2026-09-18.** Both
   kinds have been on both sides of this. `knowledge` declared none originally
   (a collection was then one of three storage scopes over *content* rather
   than a boundary anyone drew), took it up on 2026-09-12 when the layer was
   reduced to plain files and a collection became its only boundary, and gives
   it up again now. `memory` shipped with `supports_scope` from the start. The
   withdrawal rests on one argument and two observations.

   The argument is that for these two kinds reach was **non-disclosure, never
   withholding**. Both serve files on disk to an agent that is handed the path,
   and enforcement sat at the MCP tool surface only — a point the previous
   revision of this item already conceded, describing it as preventing mistaken
   retrieval rather than deliberate filesystem access by an agent that also
   holds shell tools. Knowledge goes further than conceding it: the skill the
   layer delivers *tells* the agent to grep the whole root. A control that the
   system's own instructions route around is not a boundary, and the page was
   presenting it as one.

   The observations come from the vault this was measured against. **Knowledge
   never used it once** — every `kind='knowledge'` row carried
   `scope_json IS NULL`, unrestricted, for the whole life of the field. And
   **memory's use of it was nobody's decision**: every partition carried a
   value, all of them written automatically by the aggregation pass to "the
   agents this partition was aggregated from". That default did real harm.
   `memory/coffer` was scoped to `["claude-code"]`, so a Codex session in the
   Coffer repository was served no project memory at all; the `account*`
   partitions were scoped to `["codex"]`, so Claude Code was served none of
   theirs. A layer that exists so several agents can read what the others
   learned was defaulting to hiding it — invisibly, because nobody set it and
   so nobody thought to look.

   Dropping the column therefore **widens reach deliberately**, which is the
   point of the change rather than a side effect it has to survive: migration
   `0088` NULLs `scope_json` for both kinds and is one-way, because the values
   it clears were an auto-default worth losing. It is safe precisely because
   neither kind's reach was ever a boundary; the four kinds that keep theirs —
   where reach decides what is exposed, delivered, written into a config file
   or allowed to drive an agent — are untouched.

   Both kinds remain Resources: identity, the lifecycle
   surface, the audit trail and the enable switch are all still worth having
   without a scope. [That identity was `<kind>:<name>` when this was written;
   it is now an immutable `uid` —
   [Resource Identity Is an Immutable `uid`](./resource-identity-is-an-immutable-uid.md).] Chat history, audit logs, runtime state and machine-local
   settings stay machine-local (restated as a boundary, not a new decision).

8. **A channel scopes, and its scope is inverted — added 2026-09-13.** This ADR
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

9. **`provider` scopes, and its own "which agents" field is withdrawn — added
   2026-09-13.** The `provider` kind already had this axis: `compatible_agents`
   inside its config, deciding which agents a connection projects into. It was
   the last kind still answering the framework's question its own way — exactly
   the divergence Decision item 4 was written to end — so the field is removed
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
   is a function of the config alone. `memory` was the counter-example that
   justified leaving the hook optional: its starting scope was the set of agents
   a partition had been aggregated FROM, which is not a function of the config,
   so it set its own scope right after registering instead. That auto-default is
   what item 7 withdraws, and `provider` is now the only user of the hook —
   which is the honest reading of it: a *sensible* starting reach is a rare
   thing for a kind to know, and a kind that cannot name one should declare no
   reach rather than invent one.

   Two flags survive side by side here, and they are not redundant: `enabled` is
   the user's switch on the resource (a disabled connection projects nowhere and
   resolves no key), while `is_active` records that this is the connection
   currently *written into* the agents it reaches. The second is a claim about a
   file on disk, which is why a boot self-check exists to catch it disagreeing
   with reality.

## Alternatives considered

- **A machine axis inside the synced scope** — in either shape it was tried:
  the 2026-08 machine × agent matrix, or the two `AND`-ed allow-lists of
  2026-09-14. Both answer "where does this run?" by writing machine ids into a
  document that travels. Rejected for the reasons in Decision item 2: the person
  setting it cannot verify it from where they are, and two machines editing it
  put a permission through a text merge. The machine-local answer needs no ids,
  no registry lookup at edit time, and no merge — and the question it cannot
  express, "a different agent per machine on one resource", is answered by
  setting that resource differently on each machine, which is how it reads to
  the user anyway.
- **Sync reach, but let the newest write win** — keep `enabled` and `scope` in
  the bundle and accept that convergence decides. Rejected: the losing machine
  is never told. A permission that changes because another machine's round ran
  is exactly the class of silent widening this design refuses everywhere else,
  including in its own migration.
- **Keep per-agent scoping inside each kind** — no framework field, each kind
  rolls its own allowlist and identity handling. This is the shape that was
  tried and reverted in 2026-06. Rejected: two kinds had already diverged on
  the same problem, and a third would have diverged again.
- **Deny-list instead of allow-list** — "every agent except these". Rejected:
  a new agent would silently gain access to every scoped resource, which is the
  wrong default for a grant.

## Consequences

- `scope` is one nullable object on `Resource`, validated per kind, with no
  dedicated machinery. It does not travel: a converge round neither reads nor
  writes it.
- Every seam asks the same question of the same function, `is_active(scope,
  agent)`. There is no evaluator object to build, no machine identity to thread
  or forget, and no seam that reads "one axis but not the other" and has to
  explain itself.
- Reach is answered per machine, which means two machines can legitimately
  disagree about one resource and neither is wrong. That is the point, and it is
  also the thing surfaces have to say out loud, because a user who assumes
  otherwise would be assuming the more dangerous half.
- The gateway's tool listing becomes identity-dependent: the same server can
  present different tool sets to different agents in the same vault.
- A hand-configured shim without `--agent` is not a privilege escalation path
  in the other direction: it sees strictly less (unscoped resources only).
- Scoping a skill out reclaims it from an agent that already has it, so scope
  edits have visible filesystem effects — audited like any other delivery
  change.
- Scope is the vault's ONE answer to "which agents does this reach" wherever
  the question is asked at all. A user who learns the control once can apply it
  to servers, skills, channels and connections, and a kind that grows the
  question later declares the field rather than inventing a field of its own.
  What the framework does not do is put the question to every kind: `agent`,
  `knowledge` and `memory` answer it with nothing, and a surface reads
  `supports_scope` rather than assuming a control belongs on every row.
- Two kinds read scope with a consequence beyond filtering: a dormant channel
  does not run, and a dormant connection projects into no agent. "Dormant" is
  therefore not always merely invisible — for those two it is off. Off is still
  only off: a dormant resource stays visible, exportable and editable. Dormant
  is nonetheless not *disabled*, and no surface may print it as such: an empty
  list is a scope narrowed to nothing, while disabled is the switch thrown — so
  the reach control reports it as *No agent selected*.
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
  sync ([Vault Sync](./vault-sync.md)); only the agent axis remains.
- **2026-09-12** — `knowledge` reverses to scoping: with the layer reduced to
  plain files, a collection is the only boundary it has (Decision item 7).
- **2026-09-13** — `channel` and `provider` reverse to scoping (Decision items 8
  and 9), and `memory` — which shipped with `supports_scope` but never got a row
  — is entered in the table. `agent` is now the only kind that declares no
  scope, and the ADR no longer justifies the two exclusions it used to.
- **2026-09-14** — The machine axis returns with bidirectional sync
  ([Vault Sync](./vault-sync.md)), as a second `AND`-ed allow-list rather than
  the matrix it was in 2026-08.
- **2026-09-14, later the same day** — The machine axis is withdrawn again, and
  this time the reason is not that machines stopped existing. A resource's reach
  — `enabled` and `scope` together — is declared **machine-local**: it is set on
  the machine it applies to, never serialized, never converged, and every
  machine sets its own (Decision item 2). With that settled the axis has nothing
  left to express, so `scope` is agents only again and migration `0076` strips
  the key — resolving each row against the machine id the daemon was actually
  using, and taking dormant whenever it cannot tell, so nothing widens. `channel`
  stopped converging at all along with it (item 3), and has since started again
  — on a machine binding of its own rather than on an axis of `scope`. The
  machine **registry** is untouched: it belongs to sync, not to permissions.
- **2026-09-18** — `knowledge` and `memory` withdraw from per-agent reach
  (Decision item 7); both kinds stop declaring `supports_scope` and migration
  `0088` NULLs their `scope_json`. For both, reach was non-disclosure only —
  the corpus is files on disk that an agent is handed the path to, and
  knowledge's own delivered skill tells the agent to grep the whole root — so
  it could prevent a mistaken retrieval but never withhold anything. The vault
  bears that out: **knowledge never used it once** (every row's `scope_json`
  was already `NULL`), while **memory's every row carried an auto-default** the
  aggregation pass wrote to "the agents this partition was aggregated from",
  chosen by nobody and actively working against the layer's purpose —
  `memory/coffer` scoped to `["claude-code"]` served a Codex session in the
  Coffer repository no project memory at all, and the `account*` partitions
  scoped to `["codex"]` served Claude Code none of theirs. Stripping the column
  widens reach on purpose. The decision itself stands unchanged for
  `mcp_server`, `skill`, `provider` and `channel`, where reach decides what is
  exposed, delivered, written into a config file or allowed to drive an agent.
- **2026-09-18, later the same day** — The scope's allow-list stops holding
  agent **names** and holds agent **uids**
  ([Resource Identity Is an Immutable `uid`](./resource-identity-is-an-immutable-uid.md),
  migration `0096`). Nothing about the decision changes: one nullable
  allow-list, `is_active(scope, agent)` the only predicate, machine-local,
  per-kind enforcement seams. What changes is what the list points at, and it
  closes two holes this ADR had lived with — renaming an agent silently emptied
  every scope that named it, and a channel's `default_agent` (item 8) was
  compared against a scope written in the agent's *other* name, which is why
  `application/channel/agent_vocabulary.py` existed. That module is deleted:
  one vocabulary, and it is the one that cannot change underneath a reference.
