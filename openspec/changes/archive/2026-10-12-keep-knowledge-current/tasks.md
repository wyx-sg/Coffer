## 1. Decision and specs

- [x] 1.1 ADR `knowledge-stays-current-through-flags-coffer-computes`; pointers and in-place rewrites in `knowledge-is-a-wiki-of-pages-compiled-from-kept-sources` and `tidying-knowledge-is-the-agents-job`; README index
- [x] 1.2 Spec deltas for `knowledge`; the knowledge spec's Purpose and `data-model.md`

## 2. Backend

- [x] 2.1 `wiki.py`: `superseded_by` and `summary` on a source, replacement chains, `superseded_source` and `stale_page`, `missing_source` for a replacement that names nothing; a superseded source does not wait
- [x] 2.2 `verify_after_days` read from the README frontmatter, default 90, `0` off, invalid values 90
- [x] 2.3 `wiki_reads.describe`: a page's `stale`, a source's `superseded_by` and `summary`
- [x] 2.4 `FileEntry` and the files listing: `stale`, `superseded_by`, `summary`, `cited_count`, `skipped`
- [x] 2.5 `collection_files.default_readme`; the description read and edited before the first `##` section
- [x] 2.6 Guide: catalogue marks and summaries; write-back, summaries, `superseded_by`, rechecks and Gaps in the manual; the tidy hand-off's steps
- [x] 2.7 `make contracts`
- [x] 2.8 Backend acceptance tests for the superseded, stale, catalogue and README scenarios

## 3. Web UI

- [x] 3.1 To do: Pages citing an outdated source and Pages to recheck, with their details
- [x] 3.2 File line: Needs rechecking and never checked on a page; Superseded by on a source
- [x] 3.3 Contents: each source's state and summary, superseded ones last and struck through
- [x] 3.4 i18n en and zh
- [x] 3.5 Frontend tests for every web scenario added

## 4. Docs

- [x] 4.1 docs-site `guides/knowledge.md`, `architecture/knowledge.md`, `architecture/decisions.md` (en and zh)
