## Why

The drift audit found three places where the code fell short of a requirement
that had no scenario pinning the missing half: re-pairing a channel from another
account left the previous owner's authority in place, a curation pass cut off by
its recursion limit reported success and settled its item, and a curation pass
ran over an unresolved sync conflict. The code is fixed in the same PR; this
change adds the scenarios that pin each fix.

## What Changes

- channels "Pair exactly one owner with a single-use code" gains the scenario
  that pairing from another account replaces the owner everywhere.
- knowledge "Bound a pass to eight writes" gains the scenario for the recursion
  bound: the pass reports `truncated` and leaves its item owed.
- vault-sync "Never overlap a tidy pass and a round" gains the scenario that a
  curation pass is skipped while a round is unresolved.

## Capabilities

### New Capabilities

### Modified Capabilities

- `channels`
- `knowledge`
- `vault-sync`

## Impact

Three new acceptance scenarios, each carried by the test that drove its fix. The
knowledge contract's curate status vocabulary gains `truncated`.
