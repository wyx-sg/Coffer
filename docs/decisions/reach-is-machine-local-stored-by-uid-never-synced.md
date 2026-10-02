# Reach Is Machine-Local: Stored by uid in `local/reach.json`, Never Synced

**Status**: Accepted
**Date**: 2026-09-14
**Deciders**: Yuxing Wu
**Related**: [Per-Agent Resource Scope Is One Framework Allow-List, Enforced by Each Kind](per-agent-resource-scope.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](identity-is-the-uid-inside-the-file.md), [Sync Withholds Derived Output; Each Machine Renders Its Own](sync-withholds-derived-output.md), [A Channel Answers Only Its Paired Owner, and Fails Closed in Groups](channel-owner-gate.md), [A Kind Plugs In as One Frozen Record of Optional Hooks: Validators Before the Write, Reactions After](kind-plugin-contract.md), [Agent Mechanisms Are Optional Facets on the Descriptor, and Projection Is One Registry](agent-mechanisms-are-optional-facets-on-the-descriptor.md), spec resource-framework "Carry a per-agent reach on every resource", spec vault-sync "Keep reach machine-local", spec vault-sync "Scope names agents only", spec vault-sync "Remove the machine axis without widening reach", spec vault-sync "Say where reach is set that it is machine-local", spec channels "Limit the agents a channel may drive to its scope", spec channels "Bind each channel to the one machine that runs it", spec mcp-gateway "Gate server exposure by scope per session", spec mcp-gateway "Take the agent identity from the handshake", research note [multi-machine sync](../research/multi-machine-sync.md), PRs #296, #381, #382

## Context

Vault sync converges resource definitions between the user's machines through
a git remote they own: every machine ends up holding every resource, keyed by
uid. Each resource also carries its **reach** — the `enabled` flag and the
per-agent `scope`
([Per-Agent Resource Scope](per-agent-resource-scope.md)). The UI sets them
with one control, and together they answer one question: *is this resource live
here, and for which agents?*

Machines genuinely differ in that answer. A server that needs a VPN only
reachable from the work laptop, a stdio server whose launcher is installed on
one machine only, a skill the user wants on the desktop's Codex and not the
laptop's: a converged vault holds all of these everywhere, so "not here" is
something a resource must be able to say. The decision is *where* it is said,
and, once resources became files a person can read and a git remote carries,
*where it is stored* so that "never travels" is a fact about a place rather
than a rule someone remembers.

## Options Considered

### Option A — Reach is machine-local, one record per resource uid in `local/reach.json`; it never travels (chosen)

Reach is stored in `~/.coffer/local/reach.json`
(`infrastructure/vault/reach_store.py`), one JSON object keyed by the
resource's uid: `{"<uid>": {"enabled": true, "agents": ["<agent uid>", …] |
null, "projects": null}}`. `agents: null` is unrestricted; `projects` is a
reserved key that is always written `null`. The file lives in the `local/`
class, which no sync round commits
([Storage Is Five Classes by Nature](storage-is-five-classes-by-nature.md)),
and it is never in a resource's own vault file, so a reach write makes no vault
commit. A resource with no record reaches as registration would have made it:
enabled, with its kind's default scope (unrestricted for every kind except
`provider`, which pre-fills from its wire). That is what a resource that
arrives from another machine, or a file a person wrote by hand, gets until
someone narrows it here. "Not here" is expressed by disabling or narrowing the
resource on the machine it should be dark on. Custom tools' per-tool reach
follows the same rule in the sibling file `local/tool-reach.json`.

Enforcement is each kind's own seam at its own choke point, where the asking
identity is known: the MCP gateway at the per-session listing, skill delivery
and the provider projection at their reconcile targets, the channel runtime at
routing. The framework stores and validates reach; it does not enforce it.

Pros: reach is set where it takes effect, by someone who can see the agents it
names and test the result; there is nothing to merge, so no machine can
silently re-answer another machine's decision; `scope` needs no machine ids and
no registry lookup at edit time; and because the file is outside the
repository, no ignore rule, no forgotten exporter field and no hand-run
`git add -f` can publish it. Cons: a resource does not arrive with the reach it
has elsewhere — a newly arrived MCP server is live here for every agent until
the user narrows it, exactly as if it had been created here; and "restrict this
on every machine" is N edits, one per machine. The UI must say at the control
that reach is local, because a user who assumes it syncs would be assuming the
more dangerous half (spec vault-sync "Say where reach is set that it is
machine-local").

It wins because it is the only option in which the person setting reach can
verify it from where they are sitting, in which two machines cannot disagree
about it through a merge, and in which "never synced" is structural.

### Option B — Sync reach like any other field

`enabled` and `scope` travel in the resource document and converge; newest
write wins.

- **Pros.** Set once, applies everywhere; the simplest serializer.
- **Cons.** The laptop that deliberately left a server dark finds it live after
  the desktop's next round, with nothing in the history that reads like a
  decision; the losing machine is never told. A permission changing because
  some other machine's round ran is the silent widening the rest of the design
  refuses.
- **Why it loses.** Reach is a permission, and a permission must not be
  re-answerable from elsewhere.

### Option C — Per-machine overrides inside the synced document (a machine axis)

Tried twice. PR #296 (2026-07) shipped a machine × agent matrix in `scope`; PR
#381 (2026-09-14) shipped two `AND`-ed allow-lists, machines and agents.

- **Pros.** One document states the whole fleet's reach; a user can configure a
  machine they are not sitting at.
- **Cons.** It cannot be verified from where it is set — the user picks machine
  ids out of a registry describing machines they cannot see, and a mistyped or
  retired id makes a resource dormant somewhere they cannot look; and two
  machines editing one resource's reach put a permission through a text merge,
  so whichever round ran last decides what the other machine exposes.
- **Why it loses.** PR #382 removed the axis the following day. The removal
  resolved each stored row against the machine id the daemon was actually
  using and took dormant whenever it could not tell, so it narrowed rather than
  widened (spec vault-sync "Remove the machine axis without widening reach"),
  and the scope's wire schema refuses a payload that still carries a
  `machines` key with a 422 rather than storing what is left, which would read
  as every agent.

### Option D — Templated reach, chezmoi-style

The synced document carries reach as a template over machine attributes
(`{{ if eq .hostname "work-laptop" }}enabled{{ end }}`), evaluated at apply time
on each machine, the way chezmoi renders dotfiles.

- **Pros.** Expressive — "every machine tagged `work`" is one line; one source
  of truth.
- **Cons.** It is Option C with a language on top: the author still writes
  conditions about machines they cannot see, and a wrong condition still fails
  silently elsewhere. It also puts a template language inside a UI control
  whose job is a checkbox list, and makes the effective reach of a resource
  something the page has to compute and explain.
- **Why it loses.** It buys expressiveness for a fleet of a few personal
  machines at the cost of the verifiability that motivates the decision.

### Option E — Reach as two columns of the resource's database row, kept out of sync by omission

The design this replaced. Resources lived in a database, and `enabled` and
`scope_json` were columns of the same row as the config. The sync exporter
serialised identity, name, description and config and left the two columns out;
the applier updated an existing row's config and description only.

- **Pros.** One row, one transaction for a resource and its reach; no second
  store.
- **Cons.** Machine-locality was a property of two code paths that each had to
  remember it. A new field, a new applier or a changed exporter could publish
  reach, and nothing structural stopped it.
- **Why it loses.** Once resources are files the file *is* what travels, so the
  safe place for reach is outside it; the rule moves from "the exporter leaves
  two fields out" to "reach is not in a file anything commits".

### Option F — One predicate over an extensible context (not adopted yet)

Replace the one-identity predicate with `is_active(reach, ctx)` over a
`ReachContext(agent_uid, project, …)`:

- `enabled` false → false; each dimension that is `null` → no restriction; each
  restricted dimension → the context's value must be in the list; a restricted
  dimension the context cannot answer (no agent identity, no project) → false,
  which generalises the existing rule that an unidentified session sees
  strictly less; a dimension the build does not know → false and the resource
  is flagged, because a permission read by a build that cannot interpret it
  must narrow, never widen.
- `enabled` folds into the predicate, so enforcement sites stop combining the
  two halves by hand and a new site cannot forget the first half.
- `projects` becomes a real dimension once a project-level landing point for
  delivered assets exists
  ([Agent Mechanisms Are Optional Facets on the Descriptor](agent-mechanisms-are-optional-facets-on-the-descriptor.md)).
- A channel's "agents it may drive" becomes a field of the channel's own
  config, validated with `default_agent` in one file, so the invariant that the
  default agent is inside the allow-list is no longer split between a synced
  document and a machine-local record.

- **Pros.** One predicate and one answer per site; a second dimension is a key,
  not a signature change; the channel's two fields that must agree live in one
  validated file.
- **Cons.** Every enforcement site changes once (the predicate is called from
  over a dozen places in `application/`, several of them in the channel runtime); a
  dimension the context cannot supply narrows to nothing, which a caller that
  forgets to pass one sees as a resource that vanished; channel routing would
  become a synced setting, so narrowing it on one machine narrows it on the
  machine that runs the channel.
- **Why it is not adopted.** No second dimension has a consumer. The record
  already reserves `projects`, so adding the dimension later costs one key and
  a change of call signature, not a migration of stored data. The channel
  invariant is real, and today it is held by two checks (the kind's config
  check and its scope check, on both write paths) plus a runtime guard that
  refuses to start a channel whose scope excludes its own default agent and
  says why. It becomes worth building with the first project-level consumer.

## Decision

A resource's reach — `enabled` and `scope` — is machine-local. It is stored in
`local/reach.json`, one record per resource uid, never in the resource's file,
never committed, never written by a sync round. A resource arriving on a
machine for the first time takes that machine's defaults for its kind. `scope`
names agents only, by uid; there is no machine axis. Each kind enforces reach at
its own choke point.

What does travel is the resource itself: identity, name, description and
config. Two things that look like reach are deliberately *not* reach and do
converge:

- **Which machine runs a channel** is a field in the channel's config
  (`runs_on`), because it is one answer every machine must share — an arriving
  channel starts nothing on a machine it does not name (spec channels "Bind
  each channel to the one machine that runs it").
- **Per-capability toggles** on an MCP server (the disabled tool set) converge
  as a state document in the vault: they describe the server, not this machine.

Rows a kind *derives* on each machine — the whole `memory` kind, and Coffer's
own generated `coffer-guide` skill — are withheld from sync for a different
reason, covered in [Sync Withholds Derived Output](sync-withholds-derived-output.md).

## Consequences

- Two machines can legitimately disagree about one resource's reach, and
  neither is wrong.
- Every reach control states that the setting is for this machine only and is
  not synced, and names an empty agent list as dormant.
- The machine registry belongs to sync alone; nothing about permissions reads
  it.
- A newly converged resource is live here at its kind's default reach; a user
  who wants it dark on this machine turns it off here. That is visible on the
  page and one click to change.
- A channel's scope is still reach: it names the agents the channel may drive,
  stays machine-local, and is checked against the synced `default_agent` at
  write time and again when the adapter would start.
- Not built yet: the context predicate of Option F — there is no `ReachContext`,
  `is_active` takes one agent uid, enforcement sites still combine `enabled`
  and scope themselves, `projects` is stored as `null` and enforced nowhere,
  and a channel's drive list has no `may_drive` config field.
