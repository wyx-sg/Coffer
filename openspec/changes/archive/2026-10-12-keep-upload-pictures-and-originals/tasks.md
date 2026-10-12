## 1. Decision and specs

- [x] 1.1 ADR `knowledge-sources-keep-their-images-and-originals-stay-on-this-mac`; in-place rewrites in `knowledge-is-a-wiki-of-pages-compiled-from-kept-sources`, `knowledge-is-plain-files` and `storage-is-five-classes-by-nature`; README index
- [x] 1.2 Edit `openspec/specs/knowledge/spec.md` directly (`skip_specs: true`): rewrite "Keep every upload as a Markdown source", add "Keep the pictures of an upload beside its source" and "Keep an upload's original on this Mac only", name `assets/` in the layout, sweep, frontmatter and route requirements
- [x] 1.3 `data-model.md`: `assets/`, `original` and `original_sha256`, the machine-local originals store, `KnowledgeFile` / `FileOut` fields

## 2. Backend

- [x] 2.1 `converters/images.py`: take pictures out of inlined data URIs and PDFs, with the bounds (48 px, 5 MB, repeats once, 40 per upload, PNG re-encoding)
- [x] 2.2 MarkItDown converter asks for `keep_data_uris` and returns the pictures on the `Conversion`
- [x] 2.3 `assets.py`: the per-upload folder, relative links, writing pictures in the source's commit, the read guard
- [x] 2.4 `originals.py`: keep the upload under `local/knowledge-originals/`, resolve `original_path`
- [x] 2.5 `ingest.py` / `service.py`: write `original` and `original_sha256`, the pictures in the same commit; no original for a passthrough upload
- [x] 2.6 The sweep leaves `assets/` alone
- [x] 2.7 `GET /api/v1/knowledge/asset`; `original` and `original_path` on `FileOut`; `make contracts`
- [x] 2.8 Guide: `assets/` and leaving `original` / `original_sha256` alone
- [x] 2.9 Backend acceptance tests for the picture and original scenarios

## 3. Web UI

- [x] 3.1 Inline pictures in the reader through the asset route
- [x] 3.2 A picture opened from the tree shows the picture
- [x] 3.3 File line: Original <name> opening the file on this Mac; the note on another Mac
- [x] 3.4 i18n en and zh
- [x] 3.5 Frontend tests for the web scenarios

## 4. Docs

- [x] 4.1 docs-site `guides/knowledge.md` and `architecture/knowledge.md`, `architecture/decisions.md` and the persistence page where they list what is kept (en and zh)
