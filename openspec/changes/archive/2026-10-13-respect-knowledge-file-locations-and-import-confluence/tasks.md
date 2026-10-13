## 1. Decision and specs

- [x] 1.1 ADRs `knowledge-files-stay-where-their-writer-put-them` and `confluence-pages-import-as-readable-sources`; addendum to `daemon-proxies-os-file-actions`; README index
- [x] 1.2 Edit `openspec/specs/knowledge/spec.md` and `openspec/specs/daemon/spec.md` directly (`skip_specs: true`)
- [x] 1.3 `data-model.md`: layout, README keys, frontmatter keys, links, findings, `KnowledgeFile`, `Conversion`, `IngestedDocument`

## 2. Backend

- [x] 2.1 Remove filing from the sweep; root files listed as plain files; restore writes non-Markdown files as bytes
- [x] 2.2 Relative links resolved and checked; `outside_link`
- [x] 2.3 `evidence`, `types_without_sources`, per-page `verify_after_days`, null `verified`
- [x] 2.4 Confluence converter: storage, macros, diagrams, assets, metadata, report
- [x] 2.5 Passthrough converter: one frontmatter block; expands export markers
- [x] 2.6 Ingest: duplicate check by page id, preview, replace and supersede
- [x] 2.7 HTTP and CLI surfaces; `readable_body`, `origin`, `import_report`; `make contracts`
- [x] 2.8 `POST /api/v1/fs/open-url`
- [x] 2.9 Guide and default README rules
- [x] 2.10 Backend acceptance tests

## 3. Web UI

- [x] 3.1 Sanitised HTML in the reader; relative, web, dead and outside links
- [x] 3.2 Readable-body note, origin line, Partial import pill
- [x] 3.3 Upload dialog: partial list, Replace on a refused re-import
- [x] 3.4 i18n en/zh; frontend tests

## 4. Docs

- [x] 4.1 docs-site guides, architecture and reference, en and zh
