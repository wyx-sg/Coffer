# Resource Reach Is Machine-Local and Never Converges

**Status**: Accepted
**Date**: 2026-09-14
**Deciders**: Yuxing Wu
**Related**: [Per-Agent Resource Scope](per-agent-resource-scope.md),
[Vault Sync](vault-sync.md),
[Sync Withholds Derived Output](sync-withholds-derived-output.md),
spec vault-sync "Keep reach machine-local",
spec vault-sync "Scope names agents only",
spec vault-sync "Say where reach is set that it is machine-local",
spec channels "Bind each channel to the one machine that runs it",
research note [multi-machine sync](../research/multi-machine-sync.md),
PRs #296, #381, #382

## Context

Vault sync converges resource definitions between the user's machines through
a git remote they own ([Vault Sync](vault-sync.md)): every machine ends up
holding every resource, keyed by uid. Each resource also carries its
**reach** — the `enabled` flag and the per-agent `scope`
([Per-Agent Resource Scope](per-agent-resource-scope.md)). The UI sets them with
one control, and together they answer one question: *is this resource live
here, and for which agents?*

Machines genuinely differ in that answer. A server that needs a VPN only
reachable from the work laptop, a stdio server whose launcher is installed on
one machine only, a skill the user wants on the desktop's Codex and not the
laptop's: a converged vault holds all of these everywhere, so "not here" is
something a resource must be able to say. The decision is *where* it is said.

## Options Considered

### Option A — reach is machine-local; it never travels (chosen)

The exporter (`application/sync/exporter.py`) serialises a resource's identity,
name, description and config, and leaves `enabled` and `scope` out. The
resource applier (`application/sync/appliers_resource.py`) updates an existing
row's config and description only, so the local reach stays exactly as this
machine set it; a row arriving for the first time is registered through the
normal path and takes the framework's defaults on this machine — `enabled`,
and the kind's `default_scope` (unrestricted for every kind except `provider`,
which pre-fills from its wire). "Not here" is expressed by disabling or
narrowing the resource on the machine it should be dark on.

Pros: reach is set where it takes effect, by someone who can see the agents it
names and test the result; there is nothing to merge, so no machine can
silently re-answer another machine's decision; `scope` needs no machine ids and
no registry lookup at edit time. Cons: a resource does not arrive with the
reach it has elsewhere — a newly arrived MCP server is live here for every
agent until the user narrows it, exactly as if it had been created here; and
"restrict this on every machine" is N edits, one per machine. The UI must say
at the control that reach is local, because a user who assumes it syncs would
be assuming the more dangerous half (spec vault-sync "Say where reach is set
that it is machine-local").

Wins because it is the only option in which the person setting reach can
verify it from where they are sitting, and in which two machines cannot
disagree about it through a merge.

### Option B — sync reach like any other field

`enabled` and `scope` travel in the resource document and converge; newest
write wins. Pros: set once, applies everywhere; the simplest serializer. Cons:
the laptop that deliberately left a server dark finds it live after the
desktop's next round, with nothing in the history that reads like a decision;
the losing machine is never told. A permission changing because some other
machine's round ran is the silent widening the rest of the design refuses. Lost
on that.

### Option C — per-machine overrides inside the synced document (a machine axis)

Tried twice. PR #296 (2026-07) shipped a machine × agent matrix in `scope`; PR
#381 (2026-09-14) shipped two `AND`-ed allow-lists, machines and agents. Pros:
one document states the whole fleet's reach; a user can configure a machine
they are not sitting at. Cons: it cannot be verified from where it is set — the
user picks machine ids out of a registry describing machines they cannot see,
and a mistyped or retired id makes a resource dormant somewhere they cannot
look; and two machines editing one resource's reach put a permission through a
text merge, so whichever round ran last decides what the other machine exposes.
Lost: PR #382 removed the axis the following day. Migration 0076 resolved each
stored row against the machine id the daemon was actually using and took
dormant whenever it could not tell, so the removal narrowed rather than widened
(spec vault-sync "Remove the machine axis without widening reach").

### Option D — templated reach, chezmoi-style

The synced document would carry reach as a template over machine attributes
(`{{ if eq .hostname "work-laptop" }}enabled{{ end }}`), evaluated at apply
time on each machine, the way chezmoi renders dotfiles. Pros: expressive —
"every machine tagged `work`" is one line; one source of truth. Cons: it is
Option C with a language on top: the author still writes conditions about
machines they cannot see, and a wrong condition still fails silently elsewhere.
It also puts a template language inside a UI control whose job is a checkbox
list, and makes the effective reach of a resource something the page has to
compute and explain. Lost: it buys expressiveness for a fleet of a few personal
machines at the cost of the verifiability that motivates the decision.

## Decision

A resource's reach — `enabled` and `scope` — is machine-local. It is never
exported to the sync remote, never written by a converge round, and an import
leaves every existing row's reach untouched. A resource arriving on a machine
for the first time takes that machine's defaults for its kind. `scope` names
agents only; there is no machine axis.

What does travel is the resource itself: identity, name, description and
config. Two things that look like reach are deliberately *not* reach and do
converge:

- **Which machine runs a channel** is a field in the channel's config
  (`runs_on`), because it is one answer every machine must share — an arriving
  channel starts nothing on a machine it does not name (spec channels "Bind
  each channel to the one machine that runs it").
- **Per-capability toggles** on an MCP server (the disabled tool set) converge
  as a shared state area: they describe the server, not this machine.

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
- Enforced in `application/sync/exporter.py` (reach never serialised) and
  `application/sync/appliers_resource.py` (reach never written by an arriving
  document); the scope wire schema refuses a payload that still carries a
  `machines` key with 422 rather than storing what is left, which would read as
  every agent (`ScopeOut` in `surfaces/http/schemas.py`).
