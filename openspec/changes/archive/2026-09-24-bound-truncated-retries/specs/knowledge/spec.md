## MODIFIED Requirements

### Requirement: Bound a pass to eight writes
A pass MUST be bounded to at most **eight** writes — a retire counts as one — and to a recursion limit, and MUST report reaching either. A single item MUST NOT be able to trigger a corpus-wide rewrite. An item the recursion limit cuts off **three times in a row** MUST NOT be offered again: that third pass settles it — material promoted as it stands, an edited document stamped — and reports `gave_up`, so an item too large for the limit costs a bounded number of passes rather than one every sweep.

#### Scenario: a pass is bounded to a handful of writes
- **GIVEN** a collection holding twenty documents and one new item of material
- **WHEN** a curation pass runs and its agent attempts eleven writes
- **THEN** the pass stops at the eighth and reports the bound, and the writes that did land are complete files rather than truncated ones

#### Scenario: a pass cut off by the recursion limit reports it and leaves its item owed
- **GIVEN** a collection whose inbox holds one item of material and an internal connection configured
- **WHEN** a curation pass over it reaches the recursion limit before the loop completes
- **THEN** the pass reports status `truncated` with the same counters as `ok` (`written`, `retired`, `refused`, `model`, `item`), the documents it wrote stay in the tree, and the item is still in the inbox for a later sweep to finish
- **AND** the sweep goes on to the collection's next pending item rather than stopping, and the next sweep offers the item only after the collection's other pending items
- **AND** when a pass over the same item is cut off for the third time in a row, it reports `truncated` with `gave_up` true and the item promoted to a document as it stands (named in `promoted`), and the item is not offered again

### Requirement: Settle an item only after its pass completes
An item MUST be settled only after its pass completes: merged material is deleted from the inbox, and an edited document is stamped with `coffer_curated_at` and nothing else about it changes. Every document curation itself writes MUST be stamped as it is written, so the sweep does not hand the pass its own output back as an edit. A stamp MUST set the file's modification time to the stamp, so the stamping itself does not count as an edit. A pass that does not complete MUST leave the item as it was, so it is curated later rather than lost — the one exception being an item cut off three times in a row, which "Bound a pass to eight writes" settles without losing it.

#### Scenario: curation merges material into the documents and empties the inbox
- **GIVEN** a collection whose inbox holds two items and an internal connection configured
- **WHEN** a curation pass runs over one of them and writes a document
- **THEN** the document is in the collection's tree, stamped with `coffer_curated_at`, and the item the pass absorbed is gone from the inbox while the item it was not handed still waits
- **AND** the pass's own write is not handed back by the next sweep as an edit
