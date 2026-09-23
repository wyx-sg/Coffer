## ADDED Requirements

### Requirement: Report every pass outcome as a status
Every curation outcome MUST be reported as a `status`, and the route that runs a pass MUST answer **200** for each of them, because none is a fault of the request: `ok` when a pass ran and settled its item; `no_model` when no internal connection is configured (see "Promote material directly when no model is configured"); `up_to_date` when nothing is pending, in which case no pass runs and nothing is touched; `too_large` when the item is past the size one pass can hold, with `limit` naming the ceiling; `truncated` when the recursion limit cut the pass off (see "Bound a pass to eight writes"); and `failed` when the pass did not complete. The route MUST answer **404** for an unknown or disabled collection and **409** while a pass over the same collection is running (see "Run one pass per collection at a time"). A `too_large` item MUST never be shown to the model and MUST never be left pending — left where it was it would be offered to every sweep and refused by every pass: material is promoted to a document as it stands, exactly as the no-model path promotes it, and reported in `promoted`; an edited document, which has nothing to promote, is stamped curated and reported in `stamped`. Neither changes a word of the item.

#### Scenario: oversized material is promoted as it stands
- **GIVEN** a collection whose inbox holds one item of material longer than the item-size ceiling, and an internal connection configured
- **WHEN** a curation pass runs
- **THEN** it reports `too_large` with `limit` and lists in `promoted` the document the item became, whose body is the material as submitted and which carries a `coffer_curated_at` stamp
- **AND** the model was shown nothing, the inbox is empty and nothing is pending

#### Scenario: an oversized edited document is stamped, not re-offered
- **GIVEN** a document a person edited past the item-size ceiling, owed a pass, and an internal connection configured
- **WHEN** a curation pass runs
- **THEN** it reports `too_large` with `limit` and names the document in `stamped`, and the document's body is exactly what the person wrote under a new `coffer_curated_at` stamp
- **AND** the model was shown nothing and the sweep no longer finds the document pending

#### Scenario: a collection with nothing pending reports up to date
- **GIVEN** a collection holding only documents curation has already seen, and an internal connection configured
- **WHEN** a curation pass is run over it
- **THEN** it reports `up_to_date` with the collection's name and nothing else
- **AND** the model was shown nothing and every document is unchanged, stamp included

## MODIFIED Requirements

### Requirement: Settle an item only after its pass completes
An item MUST be settled only after its pass completes: merged material is deleted from the inbox, and an edited document is stamped with `coffer_curated_at` and nothing else about it changes. Every document curation itself writes MUST be stamped as it is written, so the sweep does not hand the pass its own output back as an edit. A stamp MUST set the file's modification time to the stamp, so the stamping itself does not count as an edit. A pass that does not complete MUST leave the item as it was, so it is curated later rather than lost. The two ways an item leaves the queue without a pass — no model configured ("Promote material directly when no model is configured") and an item too large for any pass ("Report every pass outcome as a status") — keep the item as it stands rather than settle a merge that never happened.

#### Scenario: curation merges material into the documents and empties the inbox
- **GIVEN** a collection whose inbox holds two items and an internal connection configured
- **WHEN** a curation pass runs over one of them and writes a document
- **THEN** the document is in the collection's tree, stamped with `coffer_curated_at`, and the item the pass absorbed is gone from the inbox while the item it was not handed still waits
- **AND** the pass's own write is not handed back by the next sweep as an edit
