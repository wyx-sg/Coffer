## Why

A collection page offered two hand-offs that overlapped: **Tidy**, which edits,
and **Check with agent**, which reports and changes nothing. Tidy's steps
already covered nearly everything a check looked for (duplicates,
contradictions, dead links), yet only the check prompt carried Coffer's
mechanical findings. And a tidy did not read as one thing afterwards: the agent
edits files with its own tools, the sweep commits what it finds as edits on
disk a minute at a time, so a long tidy became a run of `disk` commits with no
boundary, no report and no way to put it back except file by file. The person
asked to merge the two hand-offs, to see a tidy as one entry they can undo, and
to redesign the collection page around what is in it and what needs doing; they
also asked for multi-file upload, one Add menu that says what each entry keeps
in Coffer, and for collections to open in Obsidian. The discussion and the
options are recorded in ADR `tidying-knowledge-is-the-agents-job` (rewritten).

## What Changes

- **Tidy is the only hand-off.** `check_handoff`, **Check with agent** and the
  guide's "Checking a collection" section are removed. The tidy prompt carries
  the collection's mechanical findings (at most 40 lines) and orders the work:
  integrate waiting sources, fix the findings, merge / split / correct, leave
  anything uncertain alone and list it in the report. Tidy all's prompt carries
  per-collection finding counts and names `coffer knowledge check`.
- **A tidy is one change.** The agent runs `coffer knowledge tidy-start`
  (`POST .../collections/{uid}/tidy/start`) before editing and
  `coffer knowledge tidy-finish --set summary=...` (`POST .../tidy/finish`) at
  the end. While open, the vault writer pauses the collection's path prefix, so
  no settle commits its edits; finishing commits them as one `agent` commit,
  operation `tidy`, the report as summary, `Coffer-Status: reported`. The sweep
  closes a tidy left unchanged for 30 minutes (`expired`). The registry is in
  daemon memory; a collection read carries `tidy_running`.
- **Undo a tidy.** `POST /api/v1/knowledge/changes/{version}/undo` (`coffer
  knowledge undo`) puts every file the change touched back as one `user`
  `restore` commit carrying `undoes`; `409 KNOWLEDGE_UNDO_CONFLICT` names files
  edited since unless `force`; `400 KNOWLEDGE_NOT_A_CHANGE`.
- **Contents.** `GET /api/v1/knowledge/collections/{uid}/files` (`coffer
  knowledge files`) lists every page and source with title, kind, type and
  waiting mark.
- **`verified: YYYY-MM-DD`**, an optional page key, returned on a page's read;
  the guide says provenance goes in `sources` / `verified`, never in the body.
- **Collection page redesign.** One summary line replaces the Pages / Sources /
  Folder rows; a "managed by Coffer" line; a tidy-running notice; **To do**
  (renamed from Check: by severity, page titles, minor kinds folded);
  **Contents** by page type; **Change log** with a tidy as one entry, its
  report and **Undo this tidy…**, and runs of disk edits grouped. The tree
  marks each page with its type's icon.
- **Add menu and multi-file upload.** One primary **Add** button (Upload
  documents…, New collection…, each with a line saying what it keeps in Coffer)
  replaces the Upload button; upload takes several files, each with its own
  state, sent one per call.
- **Obsidian.** Obsidian is a detected editor; **Open in Obsidian** appears in
  a collection's and a file's ⋯ menu only when it is installed.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `knowledge`: the tidy hand-off, the guide, tidy as one change, undo, the
  contents route, `verified`, the collection page, the Add menu, multi-file
  upload, Open in Obsidian; "Hand a check to the agent" is removed.
- `vault-storage`: a paused path prefix is left out of every settle until its
  owner commits it.

## Impact

- Backend: `application/knowledge/` (`tidy_service.py`, `tidy_handoff.py`,
  `change_service.py`, `collection_writes.py`, `service.py`, the guide),
  `infrastructure/knowledge/` (`tidy_runs.py`, `history.py`, `wiki.py`,
  `collection_files.py`), `infrastructure/vault/writer.py`, the knowledge HTTP
  routes and schemas, `coffer knowledge` commands, `application/fs/editor_service.py`.
- Wire contract: `contracts/api.openapi.yaml` regenerated; `check_handoff`
  removed from `CollectionOut` (a breaking field removal for the web UI only).
- Frontend: the Knowledge page, collection page, tree, upload dialog, reader.
- Docs: ADRs `tidying-knowledge-is-the-agents-job` and
  `knowledge-is-a-wiki-of-pages-compiled-from-kept-sources`; docs-site guides
  and architecture pages for knowledge, error codes, CLI reference (en, zh);
  `data-model.md`.
