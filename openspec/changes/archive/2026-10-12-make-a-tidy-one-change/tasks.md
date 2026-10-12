## 1. Decision and specs

- [x] 1.1 Rewrite ADR `tidying-knowledge-is-the-agents-job` (one Tidy; a tidy as one change; undo); update `knowledge-is-a-wiki-of-pages-compiled-from-kept-sources` (Check hand-off, Obsidian, `verified`); README index
- [x] 1.2 Spec deltas for `knowledge` and `vault-storage`; the knowledge spec's Purpose and `data-model.md`

## 2. Backend

- [x] 2.1 Remove `check_handoff` and `collection_check_prompt`; the tidy prompt carries the findings (40 lines) and the tidy-start / tidy-finish steps; Tidy all carries finding counts
- [x] 2.2 Guide: fold "Checking a collection" into "Tidying a collection"; `verified` key and provenance rule
- [x] 2.3 `VaultWriter.set_paused`; `KnowledgeHistory.pause_tidies`, `settle_as`, `pending_in`; `tidy_runs.TIDY_RUNS`
- [x] 2.4 `TidyService` start / finish / expire; sweep calls `expire`; `tidy_running` on the collection read
- [x] 2.5 Routes `POST .../tidy/start`, `POST .../tidy/finish`, `POST /knowledge/changes/{version}/undo`, `GET .../files`; errors `KNOWLEDGE_UNDO_CONFLICT`, `KNOWLEDGE_NOT_A_CHANGE`
- [x] 2.6 Commands `coffer knowledge tidy-start`, `tidy-finish`, `undo`, `files`
- [x] 2.7 `verified` on the page read; Obsidian among detected editors
- [x] 2.8 `make contracts`
- [x] 2.9 Backend acceptance tests for the tidy, undo, contents and hand-off scenarios

## 3. Web UI

- [x] 3.1 Header: Tidy all and one primary Add menu (Upload documents…, New collection…, each with its line)
- [x] 3.2 Upload: several files, per-file state, refusals before sending, one per call, retry, one summary toast
- [x] 3.3 Collection page: summary line, managed line, tidy-running notice, To do, Contents, Change log with tidy entries, grouped disk edits and Undo this tidy…; no Check with agent
- [x] 3.4 ⋯ menus: Open in Obsidian when installed (collection and file)
- [x] 3.5 Tree: page-type icons; reader: `verified` date, lighter inline code, paths wrap at `/`
- [x] 3.6 i18n en and zh
- [x] 3.7 Frontend tests for every web scenario added or renamed

## 4. Docs and canvas

- [x] 4.1 docs-site `guides/knowledge.md`, `architecture/knowledge.md`, `reference/error-codes.md` (en and zh); the other pages naming Check with agent
- [x] 4.2 `make docs-reference` and `scripts/cli_coverage.py --write`
- [x] 4.3 Rerun `scripts/cli_coverage.py --write` once the frontend's typed client is final
- [ ] 4.4 Redraw the Context canvas's Knowledge boards (header Add menu, collection page, upload dialog, tree icons)
- [ ] 4.5 Regenerate docs screenshots that show the collection page
