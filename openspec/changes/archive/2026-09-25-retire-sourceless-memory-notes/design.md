## Context

A `global` note built from a `feedback` entry that now belongs to a project partition keeps being delivered after aggregation moves the entry. Two fixes were on the table:

- **(a)** distil retires a note whose raw entries are all gone, and says why;
- **(b)** a `coffer memory rebuild` command (and REST route) that deletes the derived tree and re-runs aggregation and distil.

## Decision

**(a).** It is the one the spec already implies and the only one that stays consistent with it:

- "Keep the memory tree derived and local" says a partition is derived from what its sources hold. A note whose every provenance entry is gone is derived from nothing; (a) makes every pass enforce that, for this migration and for every later case — an agent deleting a fact, placement rules changing again — without the user having to know a command exists.
- "Record retirements so they stick" says a note never just disappears; it leaves a `RETIRED.md` record saying why. (a) uses exactly that mechanism. (b) would delete `RETIRED.md` along with the tree, and with it every retirement a model pass judged — so the next distil would re-open subjects that had been deliberately retired from unchanged raw entries, the failure that requirement exists to prevent.
- "Cover memory management on REST and the CLI" would have to grow a new destructive operation for (b), on a layer whose spec already guarantees deleting the tree by hand and re-syncing rebuilds it.

## Details

- The sweep runs at the top of `distil_partition`, before `undistilled` is computed, on both the model path and the mechanical one: it is a set comparison, not a judgement about meaning, so "Distil mechanically with no internal connection" still holds structurally.
- A record for it has `sources_gone: true` and empty `entry_ids`. Excluding entries that no longer exist would be meaningless, and if they come back (a hand-deleted `.raw/` re-aggregated, a placement moved back) they must be distilled, not suppressed. For the same reason routing is not handed its title as a retired subject.
- A note with at least one surviving origin is left alone — a partial loss is a merge's business, not a retirement. A note with no origins at all is left alone too: there is no provenance to judge it by.
- Aggregation prunes a raw entry only after reading its source successfully, and never for an agent it skipped, so a reader breaking or an agent being disabled does not retire anything.
