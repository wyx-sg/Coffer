## MODIFIED Requirements

### Requirement: Submit every entrance's input as material
Every entrance Coffer serves — `coffer__write`, the CLI's `write` and its route `POST /api/v1/knowledge/material`, an upload, and a channel's `/kb` — MUST **submit material** into the named collection's `.inbox/` rather than write a document. What becomes of material is curation's to decide (see "Curate through a fenced four-tool pass"): which document it belongs in, what in it is new, and what it corrects. The one exception is "Promote material directly when no model is configured", where no model is configured to decide and the material becomes a document as it stands.

#### Scenario: the CLI and the material route leave material in the inbox
- **GIVEN** a `shopee` collection and an internal model connection configured
- **WHEN** material is submitted once with `coffer knowledge write` and once with `POST /api/v1/knowledge/material`
- **THEN** each answer reports `pending` with no path, and two items wait in `shopee/.inbox/`
- **AND** no document has been added to the collection's visible tree

### Requirement: Ingest documents sent to a channel
A document sent to a Coffer channel MUST be ingestible into a collection through the same path, so the phone and the Knowledge page are two ends of one entrance ([channels](../channels/spec.md)). The channel MUST confirm the collection with the owner before storing, and MUST NOT store anything from a non-owner.

#### Scenario: a document forwarded to a channel lands in a collection
- **GIVEN** a paired channel whose owner has just sent `note.txt` as an attachment, and one existing collection named `research`
- **WHEN** the owner follows it with the plain text `/kb research`
- **THEN** the ingest service is called exactly once — that collection, that file name, those bytes, `actor` `user` and the channel's own default agent — and the channel replies with a confirmation naming both the file and the collection
