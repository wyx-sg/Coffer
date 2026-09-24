# An Unattended Rewriter of Synced Content Runs on One Named Owner Machine

**Status**: Accepted
**Date**: 2026-09-22
**Deciders**: Yuxing Wu
**Related**: [Vault Sync](vault-sync.md), [Sync Machine Identity](sync-machine-identity.md), [Knowledge Curation](knowledge-curation.md), [Internal Engine Settings](internal-engine-settings.md), [Sync Withholds Derived Output](sync-withholds-derived-output.md), spec vault-sync, spec knowledge, spec channels, PRs #401, #409

## Context

The knowledge **curation** pass ([Knowledge Curation](knowledge-curation.md))
runs on a timer, with no human approving its diff, and rewrites synced vault
content: it merges the material waiting in a collection's inbox into that
collection's documents and deletes what it merged. On one machine that is
safe. Once a vault [converges across machines](vault-sync.md) it is not:

- Run over the same corpus on two machines, each pass merges the same inbox
  material — but into *different* documents, because a model's choices are not
  deterministic. git merges the result perfectly cleanly: both sides agree the
  material is gone from the inbox, and the two rewritten documents are
  additions or edits at different paths. The vault ends up holding the same
  knowledge twice, and nothing reports a conflict because nothing conflicted.
- Even where both passes touch the same document, two machine-written rewrites
  of one note produce a real conflict every time the timers line up, which
  stops convergence on both machines for a human to resolve a disagreement no
  human had.

This is a property of *who writes*, which git cannot see. It needs a rule
about where the pass runs.

Which other unattended passes this touches, checked against the code: memory
aggregation and distillation rewrite only the derived memory tree, which never
leaves the machine (`memory` declares `converges=False`); the `coffer-guide`
skill Coffer re-renders is derived output that sync withholds
([Sync Withholds Derived Output](sync-withholds-derived-output.md)); retention
prunes the audit log, MCP invocation records and conversations, none of which
sync. Curation is the one unattended rewriter of synced content today.

## Options Considered

### Option A — One owner machine, named in synced state (chosen)

The owner is one field, `curate_owner_machine_id`, on the singleton
`internal_engine_config` row beside the pass's switch `auto_curate_enabled`.
It travels in the internal-engine state document
(`application/engine_settings_sync.py`), so every machine agrees who the owner
is. The timer asks `GlobalInternalEngineConfig.curate_runs_on(machine_id)`
(`domain/internal_engine_config.py`) on every sweep: on, and either no owner
named or the owner is this machine. On every other machine the pass is a clean
no-op (spec vault-sync "Run an unattended rewriter on one owner machine";
spec knowledge "Curate on one owner machine only").

The owner is reportable and changeable
(spec vault-sync "Report and change the rewriter's owner"): `CurationOwner`
derives four states from the field and the registry — `unowned`, `self`,
`other`, and `unknown` (a machine the registry does not hold). Only `unknown` is
a fault, because the pass then runs on no machine at all; an **empty** registry
never yields it, since "we cannot say" is not "no machine claims this". The
user takes the pass over or clears the owner from
`coffer engine curate-owner show|set|clear` or
`PUT /api/v1/internal-engine-config/curation-owner`. The four states are the
same rule, statement for statement, as a channel's machine binding
(frontend `lib/machineBinding.ts`), because the two facts have the same shape:
one machine named in a document every machine holds.

Two further rules keep the pass from colliding with convergence
(`curation_may_run` in `surfaces/http/curation_wiring.py`): the pass takes the
converge round's own lock, and it is skipped while a round is held for
confirmation or stopped on a conflict
(spec vault-sync "Never overlap a curation pass and a round"). When the owner's
deletion does meet an edit made elsewhere, the edit wins
(spec vault-sync "Let an edit beat a curation deletion").

With the `vault_sync` feature switched off, curation treats the vault as
single-machine and reads only its own switch: no round runs, so there is no
other machine to duplicate the work, and an owner or a hold the user cannot
reach while sync is closed must not stall curation silently.

Pros: removes the duplicate at its source; costs one field on a row that was
already installation-wide and already synced; no coordination protocol.

Cons: if the owner is off, no pass happens until it returns — material waits in
the inbox. An owner naming a machine that is **gone** (retired, reinstalled
under a fallback id, never converged) stops curation everywhere; that case is
why the `unknown` state exists and is surfaced.

It wins because a missed pass costs latency on a background nicety, while a
duplicate costs knowledge the user must find and clean by hand, and no merge
can detect it.

### Option B — Every machine runs the pass

Let each machine curate on its own timer and rely on git to merge.

Pros: no configuration; curation never waits for a machine to wake.

Cons: exactly the silent duplication above, plus a stream of machine-made
conflicts on the documents both passes touched.

Lost: its failure is invisible to git and therefore to every guard Coffer has.

### Option C — Leader election through a lock on the remote

Before a pass, a machine pushes a lease (a lock file or ref) to the remote;
whoever holds an unexpired lease curates.

Pros: automatic failover when the owner is off.

Cons: git is not a lock service — pushes race, a lease needs clocks that agree
across machines, and a machine that goes to sleep holding a lease blocks
everyone until it expires. It makes the remote a coordination point on the
critical path of a local operation, pushing it toward a system of record the
principles forbid. And convergence is hourly by default, so a lease can only
be as fresh as the last round.

Lost: a distributed-systems problem bought to save a user from naming a machine
once.

### Option D — Merge the two machines' rewrites

Let both machines curate and reconcile the results — a CRDT over the
documents, or a model pass that merges duplicates after the fact.

Pros: no owner to configure; eventually one set of documents.

Cons: the duplicates are semantic, not textual — two different paraphrases of
the same material at two paths — so no CRDT sees them as the same thing. A
second model pass to find and fold duplicates is itself another unattended
rewriter with the same problem one level up.

Lost: it treats the symptom with a second instance of the cause.

### Option E — Each machine curates only the material it received

Tag each inbox item with the machine that wrote it, and let a machine curate
only its own.

Pros: work spreads across machines; nothing waits for one owner.

Cons: provenance would have to travel with every inbox file; curation also
carries a person's edit through *other* documents in the collection, so two
machines curating different material can still rewrite the same document; and a
machine that never comes back leaves its material stranded.

Lost: it narrows the collision but does not remove it.

## Decision

An unattended pass that rewrites synced vault content runs on **one owner
machine**, named by a field in synced state, and is a no-op everywhere else. No
owner named means "here", because a vault that never named one is a
single-machine vault. An owner the registry does not hold is a reported fault
with a one-action repair, never a state the product keeps quiet about. The pass
shares the converge lock and does not run while a round waits on the user.

A future unattended rewriter of synced content must adopt the same rule; one
that writes only machine-local or derived state need not.

## Consequences

- On a multi-machine vault, curation happens only while the owner machine is
  running; a user who retires that machine must take the pass over, and the
  surfaces tell them so.
- Clearing the owner is an explicit act, never an automatic repair: it is
  right for a vault down to one machine and wrong for one that still spans
  several.
- An unbound channel runs **nowhere** while an unowned pass runs **here**. The
  difference is deliberate: a bot answering twice cannot be walked back, a
  duplicated note can.
