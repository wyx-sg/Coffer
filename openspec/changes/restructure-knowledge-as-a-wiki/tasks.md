## 1. Decision and research

- [x] 1.1 ADR `knowledge-is-a-wiki-of-pages-compiled-from-kept-sources`; amendment note on `knowledge-is-plain-files` and `tidying-knowledge-and-memory-is-the-agents-job`
- [x] 1.2 Research note `docs/research/knowledge-structures.md`, indexed

## 2. Backend: layout, sources and the wiki graph

- [ ] 2.1 `paths`: `pages/`, `sources/`, `kind_of`; uploads and inbox adoption write `sources/`, keeping the original beside a converted source
- [ ] 2.2 `wiki.py`: walk a collection into pages (frontmatter, links outside code), sources (skipped, cited), slug and alias resolution
- [ ] 2.3 Findings: dead and ambiguous links, duplicate slugs, orphan, incomplete, unsourced pages, missing and waiting sources
- [ ] 2.4 Reads: `FileOut` kind, page type, aliases, resolved sources and links; source original, cited-by and waiting; `FileSummaryOut` kind and waiting
- [ ] 2.5 `CollectionOut` page, source, waiting and finding counts, `check_handoff`; `GET /knowledge/collections/{uid}/check`; `coffer knowledge check`
- [ ] 2.6 Sweep: file loose Markdown into `pages/` (daemon writer, `layout` operation, one-minute quiet rule)
- [ ] 2.7 Hand-offs: tidy with waiting sources; check prompt with findings
- [ ] 2.8 Guide: layout, Writing a page, Integrating sources, Tidying, Checking; catalogue by type with waiting sources and a budget
- [ ] 2.9 `make contracts`; data-model.md

## 3. Web UI

- [ ] 3.1 Tree: Pages and Sources first, Waiting mark
- [ ] 3.2 Pane bar without tabs; History drawer (`?history=1`), `/history` redirects
- [ ] 3.3 Reader: page line (type, sources), resolved and dead `[[links]]`; source line (cited by / waiting, original)
- [ ] 3.4 Collection page: Pages / Sources / Folder properties, Check section, Check with agent, Change log
- [ ] 3.5 i18n en and zh

## 4. Tests

- [ ] 4.1 Backend acceptance tests for every new and changed scenario
- [ ] 4.2 Frontend tests for the tree, drawer, reader and collection page scenarios

## 5. Docs and design

- [ ] 5.1 `docs-site` architecture/knowledge and guides/knowledge, en and zh; CLI reference regenerated
- [ ] 5.2 Canvas 5 (Context) Knowledge boards redrawn

## 6. Ship

- [ ] 6.1 `make verify`
- [ ] 6.2 Archive the change
