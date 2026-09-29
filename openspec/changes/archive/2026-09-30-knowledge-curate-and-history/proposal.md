# Curate a collection until nothing is pending, and keep every document's history

## Why

The manual trigger runs one pass, so a collection with ten waiting items needs ten
clicks, and nothing says how far it got or which item failed. Curation rewrites
documents with no review step, and what a pass replaced is gone: the only way back
is the sync working tree, and only for people who sync. A person who adds a
document from the page has no route that goes through the inbox like every other
entrance, a stale save says only "conflict", and the wording mixes "merge",
"material" and "notes" for things the page calls curation, items and documents.
A few "disabled collection" leftovers survive although a collection has no
switch.

## What Changes

- **Curate now drains.** `POST /api/v1/knowledge/collections/{uid}/curate` and
  `coffer knowledge curate <collection>` run passes one at a time — inbox items
  oldest first, then documents edited out of band — until nothing that was
  pending is left, each pass still bounded to eight writes, stopping at the
  first failed pass. The answer lists every pass's outcome. Progress (*n of m*)
  is on `GET /api/v1/upkeep/runs` and announced on the event stream after each
  pass; the CLI prints it. Given one document, one pass over it. 409 while a
  pass runs, as before.
- **History.** Every accepted write to a collection is a git commit naming its
  writer — the user, the agent that submitted promoted material, Coffer's
  curation (naming the item and, from the `knowledge_written` audit event, the
  agent that wrote it), sync, or an edit made on disk. Until the vault is one
  git repository (a later item), the commits live in a repository of the
  knowledge root's own, `<knowledge root>/.git`, shaped to fold into the vault's.
  New REST routes and CLI commands: a document's versions and each version's
  diff, restore a version (a new commit), recent changes across collections
  with the items still waiting, one change in full, and undo a curation pass as
  a whole — refused, naming the document, when a later change would be
  overwritten.
- **Add a document is an item.** The page's Add a document submits through
  `POST /material` with actor `user`; no route creates a document at a path.
- **A stale save explains itself.** `KNOWLEDGE_FILE_CONFLICT` carries
  `saved: false` and the document's current body and fingerprint, enough for
  Reload, Compare and Copy my text.
- **No disabled collection.** The sweep lists every collection; the remaining
  "disabled" wording in the spec and the code goes.
- **Wording.** CLI help and messages say curate / curation, documents and items.

## Capabilities

### Modified Capabilities

- `knowledge`: the manual trigger drains with progress; history, restore,
  recent changes and whole-pass undo; the stale-save refusal carries the disk
  version; the REST and CLI roster grows by the history surfaces; no disabled
  collection anywhere.
- `resource-framework`: an in-flight run reports how many of its items it has
  done of how many.

## Impact

- Backend: `application/knowledge/` (drain, history service, pass commits),
  `infrastructure/knowledge/history.py` (git), knowledge routes and schemas,
  `upkeep_runs` progress, `coffer knowledge` commands, the sync applier that
  names sync in history.
- Wire contract: `CurationRunOut` replaces `CurationOut` as the curate route's
  answer; new history and change schemas; `UpkeepRunOut` gains `done` / `total`.
  Frontend types regenerated and the one caller adapted; the Knowledge page UI
  is a later change.
- Git becomes a runtime dependency of knowledge history (not of knowledge
  itself: without git every write still works).
- No database migration.
