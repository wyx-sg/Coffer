## MODIFIED Requirements

### Requirement: Bound a pass to eight writes
A pass MUST be bounded to at most **eight** writes — a retire counts as one — and to a recursion limit, and MUST report reaching either. A single item MUST NOT be able to trigger a corpus-wide rewrite.

#### Scenario: a pass is bounded to a handful of writes
- **GIVEN** a collection holding twenty documents and one new item of material
- **WHEN** a curation pass runs and its agent attempts eleven writes
- **THEN** the pass stops at the eighth and reports the bound, and the writes that did land are complete files rather than truncated ones

#### Scenario: a pass cut off by the recursion limit reports it and leaves its item owed
- **GIVEN** a collection whose inbox holds one item of material and an internal connection configured
- **WHEN** a curation pass over it reaches the recursion limit before the loop completes
- **THEN** the pass reports status `truncated` with the same counters as `ok` (`written`, `retired`, `refused`, `model`, `item`), the documents it wrote stay in the tree, and the item is still in the inbox for a later sweep to finish
- **AND** the sweep goes on to the collection's next pending item rather than stopping
