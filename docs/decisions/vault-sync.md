# Vault Sync

**Status**: Accepted
**Date**: 2026-09-13
**Deciders**: Yuxing Wu
**Spec**: [vault-sync](../../specs/vault-sync/spec.md)
**Constitution**: Principle I (0.6.0 — bidirectional convergence with a user-owned sync remote)

## Context

Coffer is local-first: each machine owns its vault and no vendor cloud is a
system of record. A developer who works the same project from a laptop and a
desktop produces vault state on both — knowledge files, skills, MCP
registrations, agent configuration, credentials — and needs the two to be one
vault rather than two.

This decision has been made four times, and the honest version of the history
is the argument for the current answer.

- **0.3.0 — continuous sync.** The first answer was convergence over a
  user-owned git repository, and it was built: machine identity, tombstones
  with a TTL so a deletion could not be resurrected, timestamp arbitration for
  competing edits, quarantine-and-retry for resources that failed to import, a
  git working tree, and a background worker.
- **0.4.0 — removed.** That machinery was the majority of the sync slice and
  it did not hold. On 2026-07-10 two machines on different builds mutually
  deleted skills, memory and resources: the exporter was destructive — it
  cleared the tree and rewrote it from local state — and it ran before the
  machine's first import, so "I never had this" and "I deleted this" looked
  identical in the diff git was handed. A second failure in the same incident
  had a machine re-exporting a months-old orphaned credential blob and winning
  the merge simply by syncing last, because deleting a resource left its
  credential rows behind for every later export to re-seed. The exception was
  withdrawn and the feature reduced to export and import.
- **0.5.0 — one-way backup.** Export and import answer "move my vault to
  another machine", but not "my disk died" or "restore what I deleted last
  week". So Coffer gained one backup remote: a worker exports on a timer into
  a git working tree, commits, and pushes. It never pulls. Nothing arbitrates,
  because nothing is converging.
- **0.6.0 — bidirectional convergence.** One-way backup leaves two machines
  drifting apart with Coffer neither noticing nor reconciling, and export/import
  closes that gap only by hand, which means not often enough. Coffer now
  converges the vault with a remote the user owns, applying what the remote
  brought in as well as pushing what this machine changed.

### Why the machinery 0.4.0 priced as too expensive is now affordable

0.4.0 removed the exception because convergence cost six things: machine
identity, tombstones with a TTL, conflict arbitration, quarantine-and-retry, a
git workspace, and a background worker.

Two of the six are already built and already paid for. 0.5.0's backup remote
needed the git workspace and the timer worker for its own sake, and they are in
the tree today.

The other four were expensive for one reason: the vault's bulk content was a
**database** being projected into files. The tree git saw was a rendering of
SQLite, not the thing the vault actually edited, so the diff git computed was
not the diff the vault made — and every guarantee convergence needs had to be
re-established outside git, in Coffer's own code, against a projection that
could disagree with its source.

Since [the knowledge layer became a directory of files](knowledge-is-plain-files.md)
the bulk content **is** the files, and what remains in SQLite is a few dozen
small, deterministically serialized documents. Each of the four then collapses:

| 0.4.0 cost | 0.6.0 shape |
| --- | --- |
| Tombstones with a TTL | Dissolve into git's own tree — a deletion is a deletion in the commit graph, and a shared base distinguishes it from "never had it" |
| Machine identity for arbitration | Collapses to one local pointer at the last commit this vault provably absorbed; it never travels |
| Conflict arbitration | Collapses into `git merge` |
| Quarantine-and-retry | Collapses into a set of paths the exporter must not delete |

## Decision

Coffer converges the vault with **one** git repository the user owns. A
background worker runs a round: serialize the vault into the working tree and
commit it, merge the remote into that commit, apply the resulting difference
back into the vault, push. The remote is a rendezvous, never a system of
record — every machine's vault stays complete, so the remote can be deleted and
rebuilt from any single machine.

### Git's three-way merge is the arbiter

Coffer writes no arbitration of its own. Two machines editing different parts
of one document is the common case, and git merges it without help; the same
hunk edited twice is a real conflict and is treated as one. Timestamp
arbitration was the 0.3.0 answer and it is exactly what let a months-old blob
win by syncing last: "newest commit" is a fact about when a machine ran, not
about what the user meant.

Two narrow rules sit beside the merge rather than replacing it. Credential
ciphertext never reaches a text merge — a Fernet token carries its encryption
time in cleartext, so two blobs for one ref can be ordered without the key, and
the fresher encryption wins. And where an internal model is configured, a
bounded agent pass may attempt the remaining conflicts **in the working tree
only**, behind a validation gate. With no model, or when the gate fails, the
round stops and the user resolves with their own git tools; the vault is not
touched and the pointer does not move.

### Local state is committed before the merge

The order is the decision. Pulling first and then applying loses local edits:
with the tree at the pointer and nothing committed, a fetch fast-forwards, git
is never given the chance to three-way-merge, and the remote's version of a
path simply overwrites whatever the vault changed there.

Committing local state first gives git its three inputs — base, local, remote.
The vault equals the local commit at that moment, so the diff from local to the
merge result contains exactly what the remote contributed, and applying it
lands the vault on the merge result with local edits intact.

### What is applied is a diff against the pointer, not a wholesale overwrite

The pointer is the commit this vault has provably absorbed. It is stored
locally, never travels, and advances only when a round's changes are actually
applied. Everything the round applies is expressed relative to it.

This is what makes deletion safe. A deletion is applied only when it appears in
the diff as a deletion, and it can only get there because some machine actually
removed that document relative to a shared base. A machine that merely *lacks*
a document has made no change relative to its own base, and git treats
"unchanged" as an assertion about nothing. That is the guarantee 0.3.0 could
not make.

Two rules protect the honesty of that diff and are normative in the spec: the
exporter writes differentially and must never clear and rewrite a directory,
and it must never delete a path in the retry set — a document this vault failed
to absorb is pending, not deleted.

The same guarantee is what lets shared state be deleted at all. Under one-way
import a state area could only ever be upserted; under convergence a deleted
state document is a decision some machine took back, and every area's provider
honours it in its own terms (spec `## Applying a diff`): an override is cleared,
a server's capabilities are re-enabled, the engine settings are reset to their
defaults, and the plugin inventory — which has no local store beyond the
document and no uninstall path — drops nothing. One rule follows for the
exporter: an area publishes a document only while there is a decision to carry,
never for its defaults, or the machine that reset and the machine that never
chose would add and delete the same document at each other forever.

Because the apply runs unattended, two guards bound a defect in it. A pre-apply
snapshot is tagged at the local commit, so rollback is the same machinery run
backwards. And a circuit breaker stops a round whose deletions exceed a fixed
share — 20% of an area, or 20 documents — and asks the user instead — **in
both directions**. It guards
what the round would apply to the vault, and equally what the round's own export
would publish as a deletion. The second direction is the one that matters when
this machine is the damaged one: a vault that lost its files to a reinstall, a
failed restore or a stray `rm -rf` would otherwise publish that loss as an
ordinary deletion and take the other machines down with it.

### The breaker counts losses, and a move is not a loss

The first thing the breaker met in the field was not a loss at all. The
knowledge two-lane rewrite moved every document from `knowledge/<c>/<doc>.md`
to `knowledge/<c>/sources/<doc>.md`; the diff carried 56 deletions *and* 56
additions of identical bytes, and a breaker that counted deletions saw 56 of 58
documents disappear from one area. It held the vault for a day, re-asking every
hour, over a round in which nothing was lost.

The considered alternative was an escape hatch: a flag a relocation or a
migration could set to skip the guard for one round. It was rejected. A guard
with a way around it is worth what the least careful caller of that way leaves
of it, and the thing needing to be waved through here is not special — it is
simply not a deletion, and the breaker should be able to say so.

So the breaker counts what a round **loses**: a deletion whose content
reappears at another path in the same area of the same diff is a move. The
pairing is on content, because git hands us a blob id per side of every change
— identical bytes have the same id anywhere, different bytes do not — so "this
is the same document" is a fact to read rather than a resemblance to guess at,
and it costs one pass over the change list and no file reads. Name similarity
was never a candidate: a guess that wrongly excuses a deletion loses data,
while a guess that wrongly holds one costs a click. A relocation that also
rewrites its documents is therefore held, and a deletion with nothing receiving
its content — a wiped disk, a failed restore, a stray `rm -rf` — is held
exactly as it was before.

### 2026-09-19 — "a relocation that also rewrites is held" is withdrawn

The clause above survived exactly one more migration. Giving every resource an
[immutable uid](resource-identity-is-an-immutable-uid.md) renamed each document
*and* added a `uid:` line to it, so the content ids differed on the two sides
and nothing paired: 28 of 28 resources read as lost, the publish-side breaker
tripped, and the vault stopped converging for four days with nothing wrong with
it. git had reported that same diff as 28 renames all along.

Twice now the breaker has fired in the field, both times on a migration this
project shipped, and never once on a loss. That is not a guard being cautious,
it is a guard that stops convergence whenever Coffer changes its own
serialization — and "moves documents and rewrites them" is the *definition* of
a layout migration, not an unusual case it happens to catch.

The asymmetry the clause rested on is real: wrongly excusing a deletion loses
data, wrongly holding one costs a click. What is wrong is that it reaches this
mechanism at all. A similarity pairing can only excuse a deletion when a
sufficiently similar **addition exists in the same diff**, and the three losses
the breaker was built for — a wiped disk, a failed restore, a stray `rm -rf` —
produce diffs with no additions whatsoever. There is nothing for git to pair
them with, so they are held exactly as before. The clause was not buying the
protection it was written to buy.

So a deletion now has a destination if **either** test shows one: the same
content id reappearing, or git's own rename detection pairing the two sides.
Three restrictions keep the second test from widening anything else. It is
asked as a separate `git diff` invocation, so the diff the vault *applies*
stays rename-blind and still lands one path at a time. Its pairings are
filtered by area in the domain, because git pairs across the whole tree while
the breaker's unit is the area. And it runs at git's own default similarity
rather than a number of ours, because there is nothing to base a different one
on.

What this does not do is make the breaker exact, and the same incident shows
where the edge is: one of those 28 documents — the channel, whose every
internal reference switched to uid form at once — fell below the similarity
threshold and would not have paired either. Twenty-seven of twenty-eight keeps
an area under its share, so that round would have proceeded; a migration that
rewrites *most* of what it moves past recognition is still held. That is the
conservative half of the trade, and it is left standing.

### A hold is a question about one diff, not a state the vault sits in

The same incident exposed a second defect, in what a *held* vault does next. A
round whose predecessor had been held returned immediately, before computing
anything, and the caller recorded that as a round: ten `awaiting_confirmation`
rows over a day, one an hour, each reporting no changes in either direction
because none had been computed. The short-circuit was there to save the work,
and what it actually saved was the vault from ever noticing that the question
had stopped applying.

A round now re-derives its diff even while a confirmation is outstanding, and
releases the hold when the direction it was raised for no longer breaches —
which is what lets a vault held by a defect since fixed converge again on its
own rather than waiting for someone to notice a button. That costs a
serialization and a merge per tick, which is what every unheld round costs
anyway, and it buys the property that matters: the latch can only ever be as
stale as one interval. A diff that still breaches stays held, keeps the moment
the user was asked, and is written over the round that first reported it, so
one outstanding confirmation is one row in the history, one line in the log and
one audit event however long it stands.

### Joining a remote is two cases, and telling them apart is the decision

A machine with no pointer is joining, and there are two kinds of joiner that
need opposite treatment. The remote's registry either holds this machine's id or
it does not, and that is what decides:

- **A new machine takes the union.** Its id is absent from the registry, so the
  pointer is git's empty tree, the diff is a diff from nothing, and it can only
  contain additions. The machine takes everything the remote holds and keeps
  everything it already had. Deletion is structurally impossible here rather
  than merely avoided.
- **A returning machine recovers its base.** Its id is present, so it has
  converged before and its descriptor names the commit it reached. That commit
  becomes the pointer and the round is an ordinary stale-machine round: the
  merge takes the remote's deletions, keeps this machine's edits, and nothing
  resurrects.

Treating a returning machine as new looks like the conservative default — a
union deletes nothing — and it is in fact a data-loss bug. A machine that
reinstalls Coffer keeps its vault files but loses its pointer; rejoined as new,
it republishes everything the other machines deleted while it was away. Every
deletion is undone at once, and no conflict is raised, because a union has no
base to disagree with.

The mirror image is the reason the publish-side breaker exists. A returning
machine whose `~/.coffer` was wiped has a valid recovered base and an empty
vault, which the merge reads as "this machine deleted everything" — the
2026-07-10 shape reached from the other direction. Coffer cannot distinguish a
wiped disk from a deliberate purge, so it does not guess: the round stops and
asks.

The detection is a property of any round that starts with no pointer, not of the
`adopt` command, so configuring a remote on a machine that has forgotten its
pointer cannot route around it. Either way joining is an explicit, reported act:
the surfaces say which case it is and what it would move before anything is
applied.

### Local export and import are deleted

Writing a bundle to a directory and reading one back is a wholesale overwrite
with no base. It is the operation that caused the 2026-07-10 incident, and it
cannot coexist with the diff-based apply: keeping it means keeping a supported
path by which a stale machine silently overwrites a fresh vault, which is
precisely what the pointer exists to prevent.

The needs it served are met without it. A new machine runs `coffer sync adopt`.
An offline medium is a `file://` remote on a USB drive. Handing a copy to
someone else is `git clone ~/.coffer/sync`. Each of those has a base; the
bundle did not.

### Machine identity is derived from the host; the name is a mutable label

`machine_id` is a key: it names the machine's descriptor file, it is what the
tidy owner and a returning machine's recovered pointer are found by, and it must
survive reinstalling Coffer. A machine that comes back under a new identity
becomes a ghost — it rejoins as a stranger, its old descriptor lingers with
nobody to update it, and anything that named it stops meaning this machine, with
no error to explain it. So the id is derived from the host (`IOPlatformUUID` on macOS,
`/etc/machine-id` on Linux, a stored UUID only as a fallback) rather than
generated by Coffer, and what travels is a salted hash of it, never the raw
hardware identifier.

The strongest argument for deriving it is the one above: only an id that
survives reinstalling Coffer can tell a **returning** machine from a **new**
one. A generated id makes a reinstalled machine unrecognisable, every rejoin a
union, and every deletion the fleet made while it was away come back. Derived
identity is not a bookkeeping nicety; it is what makes joining safe.

`machine_name` is the opposite: chosen by the user, changeable at any time at
no cost, and stored inside the machine's own descriptor. Nothing in the vault
references it, so renaming a machine rewrites nothing.

### The machine registry is a derived view, not a synced table

Each machine writes exactly one document — `machines/<machine_id>.yaml` — and
writes no other machine's. Because every machine owns a disjoint path, these
documents cannot conflict, and git merges them trivially. The registry is
simply whatever `machines/*.yaml` currently holds.

A descriptor also publishes that machine's pointer — the commit it last
absorbed. The pointer itself never travels as a shared input to the algorithm;
what is published is a record of where this machine got to, so that this machine
can recover its own base if it forgets it. That is the field a returning joiner
reads.

A synced registry *table* is the opposite: every machine writes every row, so
the one piece of state whose entire job is to describe the fleet becomes the
most contended thing in the tree. 0.4.0 deleted that table; it does not come
back. A heartbeat field is restamped at most once per calendar day, so an idle
machine does not commit a round's worth of noise, and the surfaces say "last
converged day" rather than implying a timestamp they do not have.

### An unattended rewriter of synced content names one owner machine

A worker that rewrites vault content with no human approving the diff is safe
on one machine and unsafe on several. The knowledge tidy pass is the case that
exists today: run over one corpus on two machines, each merges the same two
notes into a topic document — but into *different* documents. The merge is
perfectly clean (both agree the two notes are deleted; the two topic documents
are additions at different paths) and the vault ends up holding the same
knowledge twice. Git cannot see this, because nothing conflicted.

So such a rewriter names one owner machine and is a no-op everywhere else. Tidy
is already off by default and installation-wide, so this costs a field rather
than a concept, and "the owner is off, so no tidy happens" is the right trade
for a background nicety. A pass and a converge round also take the same lock —
an export taken mid-rewrite is a torn snapshot — and delete-versus-edit
resolves toward the edit, because an edit is something a person or an agent
just decided while the deletion is a housekeeping judgement the next pass will
make again. The retention worker needs none of this: it prunes the audit log,
MCP invocation records and conversations, none of which sync.

## Alternatives considered

- **Leave the file trees to the user's own git and sync only the structured
  state** — rejected. If Coffer runs the pull it is convergence either way and
  needs this same amendment; if the user runs it, Coffer is not syncing at all
  and the drift it was meant to fix stays. It also cuts the seam through
  `skill`, whose files and registry rows are two faces of one thing, leaving
  half of a resource on each side of the boundary.
- **Restore the 0.3.0 machinery as it was** — rejected. It was built to
  converge a database being projected into files, and that database no longer
  holds the bulk content. Rebuilding tombstones, arbitration and quarantine now
  would re-implement outside git four things git already does, and would carry
  forward the projection gap that produced the 2026-07-10 incident.
- **A hosted Coffer sync endpoint** — best UX, but a vendor-controlled system
  of record; rejected, and explicitly outside the 0.6.0 exception. It would
  need a much broader constitutional amendment.
- **Copy `~/.coffer/` wholesale** — simplest, but it carries machine-local
  state (daemon configuration, port allocations, per-machine logs) and a binary
  SQLite file that cannot be merged, inspected, or partially applied; rejected.
  Hence the deterministic text serialization, which is also what lets a round
  with nothing to say produce no commit.

## Consequences

- The `sync/` slice keeps its serializer, path portability and credential
  ciphertext handling, and gains the round: a pointer and retry set stored
  locally, a diff-based applier per document kind, the pre-apply snapshot and
  the circuit breaker. The 0.5.0 git workspace and timer worker are reused
  rather than replaced.
- A resource's **reach** — its `enabled` flag and its `scope` — is machine-local
  and does not converge. What travels is the resource: its identity and its
  configuration. Each machine decides for itself what that resource reaches
  there, so convergence can never re-answer a permission question a machine had
  already answered ([Per-agent resource scope](./per-agent-resource-scope.md)).
- The `channel` kind converges like every other, and each channel names the one
  machine whose daemon runs its adapter. It did NOT converge at first, on the
  grounds that a channel is an inbound surface bound to one machine and so
  travels to be at best inert and at worst a second machine answering the same
  conversation. That objection is answered rather than avoided by a binding
  (spec channels FR-026): the document travels, the adapter does not, and only
  the machine the document names starts one. The reversal is written up in spec
  vault-sync's `## What does not sync` amendment.
- Coffer now writes the vault without a human in the loop. That is the real
  cost of this decision, and it is why the pointer, the snapshot and the
  circuit breaker are normative rather than nice to have.
- A conflict blocks convergence on both machines until a human resolves it.
  That is intended: two machines quietly disagreeing about one document is
  worse than two machines waiting.
- Determinism of the serializer becomes load-bearing in a new way. Under
  backup it made diffs readable; under convergence, a non-deterministic field
  is a spurious conflict on every round.
- The remote needs a push credential, resolved at push time, never written into
  `.git/config` and never passed on a command line. Credential ciphertext
  travels only when the user opts in, and the master key is still bootstrapped
  out-of-band.
- Conversations, the audit log and MCP invocation records stay machine-local.
  They record what happened *on a machine*; merging them is a different feature
  with a different shape.
