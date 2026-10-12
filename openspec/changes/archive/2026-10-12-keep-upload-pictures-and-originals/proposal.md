## Why

An upload became a source of Markdown only: every picture in a PDF, a slide
deck or a Word document was dropped, and the uploaded file was thrown away once
converted. Diagrams, flow charts and screenshots often carry the meaning a
design doc or a deck exists for, and agents and people both need them; and the
person sometimes wants to look at the original layout a conversion flattens.
The person chose to keep the pictures in the collection, where they sync, and
the original on the uploading Mac only, where it costs the sync repository
nothing. The options (pictures in the vault, the original in the vault, the
original on this Mac only, Markdown only) are argued in ADR
`knowledge-sources-keep-their-images-and-originals-stay-on-this-mac`.

## What Changes

- **Pictures are taken out of an upload.** The MarkItDown converter inlines an
  Office or HTML document's pictures (`keep_data_uris`) and takes each out as a
  named file; a PDF's pictures are read with pdfminer and listed after the text
  under `## Images`, one `Page N:` heading per page. Decorations under 48 px on
  a side and pictures over 5 MB are dropped, a repeat is kept once, an upload
  keeps at most 40, and a format a browser cannot show is re-encoded as PNG.
- **Pictures land under `assets/`.** At
  `<collection>/assets/<title-slug>-<first 8 hex of the upload's sha256>/image-N.ext`,
  in the same commit as the source, which links them relatively
  (`../assets/<folder>/image-1.png`). `assets/` is visible so the pictures
  sync and keep history; the sweep never files anything out of it.
- **The original stays on this Mac.** The uploaded file is kept at
  `~/.coffer/local/knowledge-originals/<sha256><.ext>` (mode 0600, once per
  content, never synced). The source's frontmatter gets `original` and
  `original_sha256`, written by Coffer. A Markdown or text upload keeps none.
- **Reads.** `GET /api/v1/knowledge/file` carries `original` and
  `original_path` (null on a Mac without the copy). New
  `GET /api/v1/knowledge/asset?path=` answers a picture's bytes (png, jpg,
  jpeg, gif, webp, svg, up to 10 MB) through the path guard, linked folders
  included, and 404 for anything else.
- **Web UI.** The reader shows a picture a Markdown document links by relative
  path inline; a picture opened from the tree shows the picture; an open
  source's line shows **Original <name>**, a button opening the file with the
  Mac's default app, or on another Mac that the original is on the Mac it was
  uploaded from.
- **Guide.** `coffer-guide` explains `assets/` and tells agents to leave
  `original` and `original_sha256` alone.
- An image-only PDF is still refused.

## Capabilities

### Modified Capabilities

- `knowledge`: "Keep every upload as a Markdown source" now keeps the pictures
  beside the source and the original on this Mac; new requirements "Keep the
  pictures of an upload beside its source" and "Keep an upload's original on
  this Mac only"; the layout, sweep, frontmatter, route-list and web UI
  requirements name `assets/` and the original. Existing requirement and
  scenario text changes across many requirements ("an upload is kept as a
  Markdown source" now names the original), so the main spec is edited
  directly and this change sets `skip_specs: true`.

## Impact

- Backend: `infrastructure/knowledge/converters/images.py`,
  `converters/markitdown_converter.py`, `assets.py`, `originals.py`,
  `paths.py`, `layout.py`, `fs.py`, `inbox.py`; `application/knowledge/ingest.py`
  and `service.py`; `domain/knowledge/converter.py` and `entry.py`; the
  knowledge routes and schemas; the regenerated contract.
- Frontend: the reader's inline pictures, the picture pane, the file line's
  original, the asset API call, i18n en and zh.
- Docs: the new ADR and in-place rewrites of the wiki, plain-files and storage
  ADRs; `openspec/specs/knowledge/spec.md` and `data-model.md`; docs-site
  knowledge guide and architecture pages (en and zh).
