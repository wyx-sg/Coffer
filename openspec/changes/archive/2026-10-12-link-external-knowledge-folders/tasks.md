## 1. Decision and specs

- [x] 1.1 ADR `linked-knowledge-folders-are-read-only-and-machine-local`; pointers in `knowledge-is-plain-files` and `storage-is-five-classes-by-nature`; README index
- [x] 1.2 Spec deltas for `knowledge` and `vault-sync`; the knowledge spec's Purpose and `data-model.md`

## 2. Backend

- [x] 2.1 `KnowledgeConfig.folder` and `linked_folder`; `CollectionEntry.linked`, `note_count`, `rules_file`; errors `KNOWLEDGE_COLLECTION_LINKED` (409) and `KNOWLEDGE_FOLDER_REFUSED` (400)
- [x] 2.2 `infrastructure/knowledge/linked.py`: folder check, path guard, walk, list a level, read a file, rules file, description
- [x] 2.3 The kind's `storage_row` hook files a linked row machine-local; rename and delete leave the folder alone
- [x] 2.4 `KnowledgeService`: `all_rows`, `collection_rows` without linked folders, `linked_rows`, `owned_collection`, `find_collection`; reads served for either sort
- [x] 2.5 Tidy, check, description edit, upload and file delete refused for a linked folder; tidy-all and the changes feed leave it out
- [x] 2.6 `linking.link_folder`; route `POST /knowledge/collections/link`; command `coffer knowledge link`
- [x] 2.7 Guide: a linked folder's catalogue section and the manual's paragraph on linked folders
- [x] 2.8 `make contracts`
- [x] 2.9 Backend acceptance tests for the link, read-only, disconnect and guide scenarios

## 3. Web UI

- [x] 3.1 Add menu item Link an external folder… with its line; the link dialog with its note and a name that follows the folder
- [x] 3.2 The linked folder's page: External tag, facts, ⋯ menu with Disconnect…; the disconnect dialog
- [x] 3.3 Tree icon for a linked folder; no History and no Delete on its files; the upload dialog leaves it out
- [x] 3.4 The Sync page's areas line says linked knowledge folders are not synced
- [x] 3.5 i18n en and zh
- [x] 3.6 Frontend tests for every web scenario added

## 4. Docs

- [x] 4.1 docs-site `guides/knowledge.md`, `architecture/knowledge.md`, `reference/error-codes.md`, `guides/vault-sync.md`, `guides/web-ui.md` (en and zh)
- [x] 4.2 `make docs-reference` and `scripts/cli_coverage.py --write`
