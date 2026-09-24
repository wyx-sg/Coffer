# Sync Withholds Derived Output; Each Machine Renders Its Own

**Status**: Accepted
**Date**: 2026-09-18
**Deciders**: Yuxing Wu
**Related**: [Vault Sync](vault-sync.md), [Coffer Ships Its Own Skill](coffer-ships-its-own-skill.md), [Resource Reach Is Machine-Local](resource-reach-is-machine-local.md), [Kind Plugin Contract](kind-plugin-contract.md), [Aggregate Agent Memory, Never Write It](aggregate-agent-memory-never-write-it.md), spec vault-sync, spec memory, spec knowledge, PR #405

## Context

Some of what sits in the vault is not authored by anyone; each machine
**renders** it from inputs it already has:

- **Coffer's own `coffer-guide` skill** ([Coffer Ships Its Own Skill](coffer-ships-its-own-skill.md)).
  Its master folder under `~/.coffer/skills/` and its `skill` resource row
  (whose `version_hash` is that folder's digest) are regenerated at every boot
  and after curation, from the running build, the knowledge files — and
  **which collections this machine has enabled**, which is reach and
  deliberately machine-local
  ([Resource Reach Is Machine-Local](resource-reach-is-machine-local.md)).
- **The memory tree and its `memory` partition rows**, aggregated from the
  agents installed on *this* machine
  ([Aggregate Agent Memory, Never Write It](aggregate-agent-memory-never-write-it.md)).
- **Per-machine side effects of converged resources** — agent-native config
  projections, the stdio shim entries, skill deliveries into each agent's
  directory.

[Convergence](vault-sync.md) mirrors `skills/` and publishes every resource
row, so by default it would carry the first two. For `coffer-guide` that is an
endless exchange: two machines holding identical knowledge but a different set
of collections enabled render different bytes, each correct where it is. Each
round overwrites the other machine's folder and row, the overwritten machine
re-renders at its next boot or curation pass and publishes back, and the
result is a commit and an audit event per tick on both machines, forever, over
an artifact neither reads from the other. Version skew between builds does the
same on its own, since the shipped half of the text changes.

## Options Considered

### Option A — Withhold derived output in both directions, declared on the kind (chosen)

Derived output is neither exported nor applied
(spec vault-sync "Withhold derived output in both halves"):

- **A whole kind** declares `converges=False` on its `Kind` (`domain/resource.py`).
  `memory` is the only one (`application/memory/kind.py`); the exporter skips
  its rows and the applier ignores an arriving document of that kind, so an
  older build cannot deliver one either (spec vault-sync "Let a kind withhold its own rows").
  `~/.coffer/memory/` itself is outside the mirrored trees.
- **One row of a converging kind** is withheld through `Kind.converges_row`, a
  function of the row's config: `skill` answers False for a `builtin` source
  (`application/skill/kind.py`), so every skill a person imported still travels
  and Coffer's own does not. `application/sync/exporter.py` asks it for every
  row and the resource applier asks it of every arriving document.
- **The matching folder** in the mirrored `skills/` tree is a path set in the
  sync layer, `NON_CONVERGING_TREE_PATHS = {"skills/coffer-guide/"}`
  (`infrastructure/sync/paths.py`), because the sync package may not import the
  skill kind; `tests/contract/test_non_converging_tree_paths.py` pins it to the
  renderer's own spelling of the name.
- **Side effects** never enter the tree at all. After a round applies, each
  kind's `PostImportHook` re-renders them from current local state
  (spec vault-sync "Re-run post-import hooks after applying").

A withheld **row's** paths already in a remote — written by an older build —
are left **inert**: not published, not applied, not deleted, and never counted
by the deletion breaker (spec vault-sync "Leave the paths of withheld derived output inert").
A withheld **kind's** documents, by contrast, are cleared as ordinary
deletions: nothing at the other end stands on them.

Pros: stops the churn at its cause; each machine's output is correct for that
machine; the rule lives with the kind that knows the row is derived, so sync
carries no list of names.

Cons: two mechanisms (kind flag and row hook) and a literal path in the sync
layer held honest only by a contract test; stale derived paths from older
builds stay in the remote as litter.

It wins because derived output has, by definition, every input it needs on
every machine; publishing it can only ever add conflict.

### Option B — Converge it, and make the rendering deterministic

Forbid anything machine-specific in the rendered skill so two machines render
the same bytes. This was the first answer.

Pros: nothing special in sync.

Cons: determinism removes only accidental differences. The largest input to
the manual is which collections are enabled, which is *meant* to differ per
machine; no byte ordering makes a laptop with a collection switched off agree
with a desktop that has it on. Version skew defeats it again on every release.

Lost: the two machines are not supposed to agree. Determinism survives for a
smaller reason — an unchanged catalogue re-rendering to identical bytes lets the
seed skip the write (spec knowledge "Render the guide skill deterministically").

### Option C — Converge the inputs, reach included

Carry `enabled` too, so both machines render the same manual.

Pros: one manual everywhere.

Cons: publishing reach lets one machine silently re-answer a question another
machine answered for itself — the reason reach is machine-local.

Lost: it trades a churn bug for a permissions bug.

### Option D — A list of non-converging kinds or names in the sync layer

Keep a table in the exporter of what not to publish, as the earlier
machine-local kind list did for `channel`.

Pros: one place to look.

Cons: the sync layer must be edited whenever a kind changes its mind, it
cannot import the kinds it names, and it can speak only about whole kinds, not
one row. The earlier list was retired for exactly these reasons.

Lost: the rule belongs on the kind; sync only asks.

### Option E — Withhold it by deleting it from the tree

Treat withheld paths like any other absence and let the export publish their
deletion, so the remote ends clean.

Pros: no litter in the remote.

Cons: deletion is the one change every machine acts on. A machine still on an
older build has no rule to protect its own live `coffer-guide` folder and
would take the deletion as leave to unlink it; the row's deletion would reach
the skill's own delete guard, be refused, and be re-refused on every round.

Lost: inert paths are the cheaper of the two mistakes.

### Option F — Accept the churn

Leave it converging and live with the commits.

Pros: no code.

Cons: an audit event and a commit per tick on every machine, a remote history
dominated by noise, and the breaker's area counts disturbed by a document that
never settles.

Lost: it makes the history useless for the restore it exists to serve.

## Decision

Output a machine derives from converged inputs plus its own machine-local
state does not converge in either direction. A kind withholds all of its rows
with `converges=False` or some of them with `converges_row`; a derived folder
inside a mirrored tree is listed in the sync layer's non-converging paths and
pinned to the kind's spelling by a contract test; side effects are re-rendered
locally after every apply. Paths an older build already published are left
inert rather than deleted.

## Consequences

- Adding a new generated artifact to a converging tree or kind requires
  declaring it withheld at the same time; otherwise it will churn.
- `coffer-guide` and the memory tree can differ between machines, and that is
  correct.
- The remote may keep an old `skills/coffer-guide/` folder and its
  `resources/skill/` document forever; they are ignored.
- The breaker never counts withheld paths, so a fleet mid-upgrade is not held
  over them.
