# A Sync Round That Would Lose Too Much Is Held, in Both Directions, Counting Losses Not Moves

**Status**: Accepted
**Date**: 2026-09-22
**Deciders**: Yuxing Wu
**Related**: [Vault Sync](vault-sync.md), [Sync Machine Identity](sync-machine-identity.md), [Resource Identity Is an Immutable uid](resource-identity-is-an-immutable-uid.md), spec vault-sync, PRs #381, #404, #409, #416

## Context

A [converge round](vault-sync.md) applies a diff to the vault and publishes a
diff to the remote with nobody reading either. The diff-against-the-pointer
design makes a *correct* round unable to invent a deletion; the breaker exists
for the rounds that are not correct:

- **A defect in the apply, here or on the pushing machine.** Any bug that turns
  "absent" into "deleted" is the 2026-07-10 mutual deletion again.
- **A damaged vault on this machine.** A reinstall that took `~/.coffer`, a
  failed restore or a stray `rm -rf` leaves a vault that is honestly missing
  its files. Relative to a valid pointer that *is* a deletion, and publishing it
  takes every other machine down with it. The same shape arises when a
  returning machine with an empty vault recovers its base
  ([Sync Machine Identity](sync-machine-identity.md)); Coffer cannot tell a
  wiped disk from a deliberate purge.

The breaker's own field history shaped it. Its first version counted
deletions. A knowledge layout change moved every document one directory down;
the diff carried 56 deletions and 56 additions of identical bytes, the breaker
saw 56 of 58 documents vanish from the area, and the vault sat held for a day
over a round that lost nothing. Content-id pairing fixed that (PR #404). Then
the migration that gave every resource an immutable uid renamed each resource
document *and* added a `uid:` line to it; no content id matched, 28 of 28
resources read as lost, and the publish side held the vault for four days with
nothing wrong. git had reported those as renames all along. Twice the breaker
fired in the field, both times on a migration Coffer shipped, never on a loss.

## Options Considered

### Option A — Hold on losses above a fixed share or floor, in both directions, where a move is not a loss (chosen)

`DeletionGuard` (`domain/sync/diff.py`) trips when, in any one **area**
(`knowledge`, `skills`, `resources`, `state`, `credentials`), the round would
lose **more than 20%** of the area's documents **or 20 or more** of them
(`DEFAULT_DELETION_SHARE`, `DEFAULT_DELETION_FLOOR`). The share catches a small
vault losing most of itself; the floor catches a large one losing a lot while
staying under the share. The registry (`machines/`) and `manifest.json` never
count, because they are never applied.

It runs **in both directions** (spec vault-sync "Guard both directions"): over
what the round would apply to the vault — the incoming diff plus the retry set,
since a held path the tree has since dropped is absorbed as a deletion
(spec vault-sync "Guard the retry set with the diff") — and over what this
round's export would publish as a deletion.

It counts **losses** (`losses()` in `domain/sync/diff.py`;
spec vault-sync "Count losses, not deletions"). A deletion is a move, and does
not count, when it has a destination in the same area of the same diff, shown
either way:

- **the same content id reappears** — git's blob id from `git diff --raw`, a
  fact about bytes rather than a resemblance, read with no file IO; the empty
  blob never pairs, since every empty file shares its id;
- **git's own rename detection pairs it** — asked as a *separate*
  `git diff -M --diff-filter=R` (`GitMirror.renames` in
  `infrastructure/sync/git_mirror.py`) at git's default similarity, so the diff
  the vault applies stays rename-blind and still lands one path at a time
  (spec vault-sync "Ask git about renames separately from the applied diff").

A pairing that crosses areas is discarded: same content in the wrong area is
still a botched relocation of the area that lost it. On the uid migration's
real diff this took counted losses from 31 to 1 (PR #409).

A trip records the round as `awaiting_confirmation` with the lost paths and
the direction, and the user confirms, rejects, or — for a damaged machine —
rebuilds from the remote (spec vault-sync "Rebuild a vault from the remote only on request").
A hold is **a question about one diff**, not a state:

- the hold records the remote tip it was raised against, and a confirmation is
  honoured only while the tip is unchanged; if the remote moved, the round is
  re-derived and asked again, because a "yes" that outlived the diff it was
  given for is the shape of an accident;
- every timer round re-derives the diff even while a hold is outstanding, and
  releases the hold when the direction it was raised for no longer breaches
  (spec vault-sync "Release a hold whose diff no longer breaches") — so a vault
  held by a since-fixed defect converges on its own;
- an outstanding hold is one recorded round, one log line and one audit event
  however many ticks re-derive it (spec vault-sync "Record one outstanding confirmation once", PR #416).

Pros: bounds the damage of any defect in either direction; the three losses it
exists for — wiped disk, failed restore, stray `rm -rf` — produce diffs with
**no additions at all**, so neither pairing test can excuse them; layout
migrations no longer stop convergence.

Cons: git's rename pairing is a similarity judgement. A relocation that
rewrites a document past git's threshold still counts as a loss (one of the 28
uid-migration documents, a channel whose every reference changed at once, would
not have paired). That is the conservative half of the trade and is left
standing. A mass deletion the user really meant costs one confirmation.

It wins because a wrongly held round costs a click while a wrongly excused one
loses data, and the pairing tests can only excuse a deletion when a matching
addition sits in the same area of the same diff — which the real losses never
have.

### Option B — No guard; trust the diff

Rely on the pointer and differential export to make wrong deletions
impossible.

Pros: nothing ever waits on the user.

Cons: it protects against the algorithm's mistakes and nothing else. A damaged
vault is not a mistake of the algorithm — its diff is correct — and would be
published as an ordinary deletion.

Lost: the publish-side case alone requires a guard.

### Option C — Confirm every deletion

Hold any round that deletes anything.

Pros: nothing is ever removed unasked.

Cons: deletion is routine — curation merges notes away, users remove resources
— so every machine would ask on every round the other machine deleted anything,
and a prompt that fires constantly is answered without reading.

Lost: it trains the user to click through the one prompt that matters.

### Option D — Count deletions only (the first version)

Treat every deletion as a loss.

Pros: simplest; no judgement.

Cons: a move is a deletion plus an addition, so every re-layout trips it — the
56-of-58 relocation held the vault for a day over zero loss.

Lost on that incident; replaced by content-id pairing.

### Option E — Exact content id only

Excuse a deletion only when identical bytes reappear in the same area.

Pros: a fact, never a guess.

Cons: a layout migration by definition moves documents *and* rewrites them —
the uid migration added a line to each — so it pairs nothing and holds the
vault on every schema change Coffer itself ships (four days, 28 of 28).

Lost: a rule that stops convergence on every migration is a tax, not a guard.
Kept as one of the two tests.

### Option F — Similarity only

Excuse a deletion when git's rename detection pairs it, and nothing else.

Pros: one test, and it covers moved-and-edited documents.

Cons: git skips rename detection past `diff.renameLimit`, and a pure move of
many files is exactly where exact-content pairing is certain and cheap. Using
similarity alone would make the common case depend on the heuristic.

Lost: the two tests are complementary; each covers what the other can miss.

### Option G — Tombstones

Record every deletion explicitly, with a TTL, and apply only tombstoned
deletions.

Pros: a deletion is an assertion somebody made, not an inference.

Cons: the commit graph already records deletions against a shared base, which
is what the pointer uses; tombstones would be a second record of the same fact
with its own expiry bugs. And they do not help the damaged-machine case — a
wiped vault would write tombstones for everything it lost. The first sync design
used them and they did not prevent 2026-07-10.

Lost: redundant with git history and blind to the case the breaker is for.

### Option H — A bypass flag for migrations, or configurable thresholds

Let a relocation or migration skip the guard for one round, or let the user
tune the share.

Pros: the migrations that tripped the breaker would have passed.

Cons: a guard with a way around it is worth what the least careful caller of
that way leaves of it. A tunable threshold is one a frustrated user raises to
100% the first time it holds them.

Lost: the migration was not special, it simply was not a loss, and the breaker
should be able to say so. The thresholds are fixed constants, and nothing may
skip the guard rather than satisfy it (spec vault-sync "Hold a round that would lose too much").

## Decision

A converge round is held when, in any area and in either direction, its
**losses** exceed 20% of the area or reach 20 documents. A deletion whose
content reappears in the same area, or which git's own rename detection pairs
with a document in the same area, is a move and does not count. The thresholds
are fixed; nothing bypasses the guard. A hold is scoped to one diff: it is
re-derived each round, released when it no longer breaches, voided when the
remote moves, and recorded once.

## Consequences

- Layout and identity migrations publish unattended, and the other machine
  absorbs them without a confirmation of its own.
- The applied diff and the guard's reading of it are two separate git
  questions; a change that fed rename pairs into the apply would break
  path-by-path application and is out of bounds.
- A migration that rewrites most of what it moves past recognition will still
  hold. That is accepted.
- Every timer round of a held vault costs a serialization and a merge, the
  same as an unheld round, in exchange for a latch that can be at most one
  interval stale.
