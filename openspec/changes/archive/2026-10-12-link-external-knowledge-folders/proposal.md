## Why

People keep notes outside Coffer, with tools they chose: an Obsidian vault, a
Logseq graph, a folder of Markdown in a repository. They want those notes to
reach their agents the way a Coffer collection does, through the
`coffer-guide` skill, without moving them and without Coffer reorganising
them. When this was discussed the person set the scope: maintaining such a
folder stays with the folder and its own tools, and Coffer only shares it with
agents. The options (import a copy, a synced reference, a symlink, full
collection treatment) are argued in ADR
`linked-knowledge-folders-are-read-only-and-machine-local`.

## What Changes

- **Link an external folder.** `POST /api/v1/knowledge/collections/link`
  (`coffer knowledge link`) takes a folder's absolute path and an optional
  name (the folder's own by default) and records one `knowledge` resource with
  config `{"folder": "<abs path>"}`. Nothing is copied into Coffer. A missing
  folder, a relative path, and Coffer's own home or any folder holding it (the
  home folder too) answer `400 KNOWLEDGE_FOLDER_REFUSED`; a taken name or a
  folder already linked answers `409 KNOWLEDGE_COLLECTION_EXISTS`.
- **Machine-local row.** The kind's `storage_row` hook files a linked folder's
  row under `~/.coffer/local/resources/knowledge/`, so it is never committed
  or synced. A collection Coffer keeps stays in the vault.
- **Read, never written.** The collection list, tree and file routes read a
  linked folder in place through `infrastructure/knowledge/linked.py`, with
  its own path guard; walks skip hidden entries and `node_modules`, stop at
  5000 Markdown files, and do not read a file over 2 MB into the page. Upload,
  file delete, description edit, check, tidy start and finish answer
  `409 KNOWLEDGE_COLLECTION_LINKED`. The sweep, the tidy-all hand-off and the
  changes feed leave it out. Rename changes only the label; deleting the
  resource (Disconnect) leaves the files alone.
- **Collection read.** `CollectionOut` gains `linked`, `note_count` and
  `rules_file` (the first of `AGENTS.md`, `CLAUDE.md`, `README.md` at the
  folder's root).
- **Guide.** The catalogue gives a linked folder its own section: its path
  (home as `~`), its rules file to follow before writing, a statement that
  Coffer's `pages/`, `sources/`, inbox and tidy do not apply, and its notes by
  title. The manual says what a linked folder is.
- **Web UI.** The Add menu gains **Link an external folder…** with the line
  "Files stay where they are and are only shared with agents. Nothing is
  copied into Coffer, synced or tidied."; a link dialog repeats it in a note.
  A linked folder has a tree icon and a page of its own: an **External** tag,
  Location with Reveal in Finder, Notes, Rules file and Managed by, and a ⋯
  menu with Reveal in Finder, Open in Obsidian (when installed), Copy path,
  Rename… and Disconnect…. Its files have no History and no Delete, and the
  upload dialog never offers it. The Sync page's areas line ends "linked
  knowledge folders not synced".

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `knowledge`: two new requirements, "Link a folder the person keeps
  themselves" and "Leave a linked folder to its own tools"; the Purpose and the
  requirements on storage, creating collections, presenting files, deleting,
  the resource file, serving every agent, naming and renaming, the routes and
  commands, the guide's catalogue, the collection page and the Add menu say
  where a linked folder differs.
- `vault-sync`: "Keep machine-local state out of the repository" lists the
  rows of linked knowledge folders among what `local/` holds.

## Impact

- Backend: `domain/knowledge/` (`config.py`, `entry.py`, `errors.py`),
  `application/knowledge/` (`kind.py`, `linking.py`, `service.py`,
  `guide_render.py`, `tidy_service.py`, `collection_writes.py`, the
  `coffer-guide` skill asset), `infrastructure/knowledge/linked.py`, the
  knowledge HTTP routes, schemas and error statuses, `coffer knowledge link`.
- Wire contract: `contracts/api.openapi.yaml` regenerated; `CollectionOut`
  gains three fields and one route is added (additive).
- Frontend: the Add menu, the link and disconnect dialogs, the linked folder's
  page, the tree node, the reader's actions, the upload dialog, the Sync page's
  areas line, i18n (en, zh).
- Docs: new ADR `linked-knowledge-folders-are-read-only-and-machine-local`;
  pointers in `knowledge-is-plain-files` and
  `storage-is-five-classes-by-nature`; docs-site guides (knowledge, vault sync,
  web UI), architecture (knowledge), error codes and CLI reference, en and zh;
  `data-model.md`.
