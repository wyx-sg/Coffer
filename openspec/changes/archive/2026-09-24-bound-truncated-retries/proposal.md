## Why

A curation pass cut off by the recursion limit leaves its item owed, so the next
sweep tries it again. An item that is always cut off would then cost a model pass
on every sweep, forever, and hold its place at the head of the inbox.

## What Changes

- An item cut off three times in a row is settled on the third pass — material
  promoted as it stands, an edited document stamped — and the pass reports
  `gave_up`.
- A cut-off item waits behind the collection's other pending items on the next
  sweep.
- `CurationOut` gains `gave_up`.

## Capabilities

### New Capabilities

### Modified Capabilities

- `knowledge`

## Impact

Knowledge curation, its contract and the regenerated client, and the web
message for a pass that gave up.
