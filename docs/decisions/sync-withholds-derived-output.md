# Sync Withholds Derived Output; Each Machine Renders Its Own

**Status**: Accepted
**Date**: 2026-09-18
**Deciders**: Yuxing Wu
**Related**: [Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person](sync-applies-clean-merges-and-stops-on-any-conflict.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [Coffer Ships Its Own Skill](coffer-ships-its-own-skill.md), [Reach Is Machine-Local: Stored by uid in `local/reach.json`, Never Synced](reach-is-machine-local-stored-by-uid-never-synced.md), [Kind Plugin Contract](kind-plugin-contract.md), [Aggregate Agent Memory, Never Write It](aggregate-agent-memory-never-write-it.md), spec vault-sync, spec memory, spec knowledge, PR #405

## Context

Some of what Coffer holds is not authored by anyone; each machine
**renders** it from inputs it already has:

- **Coffer's own `coffer-guide` skill** ([Coffer Ships Its Own Skill](coffer-ships-its-own-skill.md)).
  Its master folder and its `skill` resource row (whose `version_hash` is that
  folder's digest) are regenerated at every boot and after curation, from the
  running build, the knowledge files and **this machine's own inputs**: its own
  knowledge and memory root paths.
- **The memory tree and its `memory` partition rows**, aggregated from the
  agents installed on *this* machine
  ([Aggregate the Agents' Memory; Never Write It](aggregate-agent-memory-never-write-it.md)).
- **Per-machine side effects of converged resources**: agent-native config
  projections, the stdio shim entries, skill deliveries into each agent's
  directory.

[Sync](sync-applies-clean-merges-and-stops-on-any-conflict.md) publishes the
whole vault repository, so anything stored in the vault would be carried. For
`coffer-guide` that is an endless exchange: two machines holding identical
knowledge but different feature switches, or a relocated knowledge root,
render different bytes, each correct where it is. Each round would overwrite
the other machine's folder and row, the overwritten machine re-renders at its
next boot or curation pass and publishes back, and the result is a commit and
an audit event per tick on both machines, forever, over an artifact neither
reads from the other. Version skew between builds does the same on its own,
since the shipped half of the text changes.

## Options Considered

### Option A — Store derived output outside the vault, so there is nothing to withhold (chosen)

State is filed by what it is
([Storage Is Five Classes by Nature](storage-is-five-classes-by-nature.md)):
only `vault/` is a git repository and only `vault/` is ever committed, and
output a machine derives lives in the **derived** class, `derived/`, which is
simply not in the repository (spec vault-sync "Withhold derived output in both halves"):

- **A whole kind** declares its storage class on its `Kind`
  (`storage`, in `domain/resource.py`). `memory` is the only kind filed as
  derived (`application/memory/kind.py`); its rows and the memory tree live
  under `derived/memory/`.
- **One row of a kind that otherwise lives in the vault** is filed through
  `Kind.storage_row`, a function of the row's config: `skill` answers derived
  for a `builtin` source (`application/skill/kind.py`), so every skill a person
  imported is in the vault and travels, while Coffer's own resource file is
  under `derived/resources/skill/`.
- **The matching master folder** is rendered by the built-in seed
  (`application/skill/builtin_seed.py`) under `derived/skills/`, beside the
  vault's `skills/` store, so the folder of a person's skill and the folder of
  Coffer's own are different directories by construction and no path list
  separates them.
- **Side effects** never enter the vault at all. After a round checks out
  changes, each changed resource raises a hint for the reconciler, which
  re-renders them from current local state
  ([One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database](one-level-triggered-reconciler-compares-parameters.md)).

A machine that finds `derived/` empty rebuilds it; deleting the directory is
always safe.

Pros: stops the churn at its cause; each machine's output is correct for that
machine; the rule is a storage fact, not a branch a translator must remember,
so sync carries no list of names, no flag, and nothing to keep in step with a
renderer's spelling; no round can publish, overwrite or delete derived output,
so there is nothing for the deletion breaker to count.

Cons: a kind or row must say where it is filed, and a new generated artifact
has to be put in `derived/` when it is added or it will churn; a row-level
split means one kind's resources sit in two places.

It wins because derived output has, by definition, every input it needs on
every machine; carrying it can only ever add conflict, and not storing it in
the repository is the one way that cannot be forgotten at a call site.

### Option B — Keep it in the vault and withhold it by declaration in the sync layer

The design this replaced: derived output lived beside authored content in the
mirrored trees and the sync code withheld it in both directions. A whole kind
carried a `converges=False` flag, a single row of a converging kind was
withheld through a per-row predicate, the matching folder was a literal path
in a set inside the sync package (pinned to the renderer's spelling by a
contract test, because sync may not import the skill kind), and side effects
were re-rendered by per-kind post-import hooks. Paths an older build had
already published were left inert in the remote, neither applied nor deleted.

Pros: one tree on disk; the rule sits with the kind that knows a row is
derived.

Cons: two mechanisms (kind flag and row predicate) and a literal path in sync
held honest only by a contract test; the sync layer had to be told about every
derived artifact, so forgetting one meant silent churn; stale derived paths
from older builds stayed in the remote as litter.

Lost: the same fact is now carried by where a file is stored, which cannot
disagree with the sync rule because it is the sync rule.

### Option C — Keep it in the vault and exclude it by pattern

Put derived output in the vault and list it in the repository's exclude file.

Pros: no code in sync; a visible list.

Cons: a name list is edited whenever something new is generated and can speak
only in patterns; an excluded file is still beside authored content, so a
checkout, a restore or a person's `git add -f` treats it as vault content, and
the vault validator and the deletion breaker's area counts must learn to
ignore it.

Lost: the exclusion lives in the wrong place; a directory outside the
repository needs no list.

### Option D — Converge it, and make the rendering deterministic

Forbid anything machine-specific in the rendered skill so two machines render
the same bytes. This was the first answer.

Pros: nothing special in sync.

Cons: determinism removes only accidental differences. Some inputs to the
manual are *meant* to differ per machine, its own knowledge and memory root
paths; no byte ordering makes a laptop and a desktop with different roots
agree. Version skew defeats it again on every release.

Lost: the two machines are not supposed to agree. Determinism survives for a
smaller reason: an unchanged catalogue re-rendering to identical bytes lets the
seed skip the write (spec knowledge "Render the guide skill deterministically").

### Option E — Converge the inputs, switches included

Carry the feature switches too, so both machines render the same manual.

Pros: one manual everywhere.

Cons: publishing the switches lets one machine silently re-answer a question
another machine answered for itself; a feature switch is per machine by
design, and a relocated root is a fact about one disk.

Lost: it trades a churn bug for a settings bug.

### Option F — Withhold it by deleting it from the tree

Treat derived paths like any other absence and let the round publish their
deletion, so the remote ends clean.

Pros: no litter in the remote.

Cons: deletion is the one change every machine acts on. A machine still on a
build that has no rule to protect its own live `coffer-guide` folder would take
the deletion as leave to unlink it, and the row's deletion would reach the
skill's own delete guard, be refused, and be re-refused on every round.

Lost: nothing is published about derived output at all, which is cheaper and
safer than publishing its deletion.

### Option G — Accept the churn

Leave it converging and live with the commits.

Pros: no code.

Cons: an audit event and a commit per tick on every machine, a remote history
dominated by noise, and the breaker's area counts disturbed by a document that
never settles.

Lost: it makes the history useless for the restore it exists to serve.

## Decision

Output a machine derives from converged inputs plus its own machine-local
state is stored in `derived/`, outside the vault repository, so it never
converges in either direction. A kind files all of its rows as derived with its
`storage`, or some of them with `storage_row` (Coffer's own skill, whose
resource file and master folder are under `derived/`); side effects are
re-rendered locally after every checkout from reconciler hints.

## Consequences

- Adding a new generated artifact requires filing it under `derived/` at the
  same time; otherwise it lives in the vault and churns.
- `coffer-guide` and the memory tree can differ between machines, and that is
  correct.
- Derived output can be deleted at any time; it is rebuilt.
- The breaker never sees derived paths, so a fleet mid-upgrade is not held over
  them.
