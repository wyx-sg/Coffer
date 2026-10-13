## Why

An imported Confluence page wrote its storage into the vault as `storage.xml`,
so it was the one upload whose raw form synced to every Mac; a PDF's or a
deck's original stays on the Mac it was uploaded from. And diagrams became
files the page never had: a draw.io diagram held in the page was decoded into
a `.drawio` file and the page's viewer link pointed at it, so a reader could
not click through to see the diagram; a PlantUML macro became a `.puml` file.

## What Changes

- **The export is the upload's original.** It gets `original` and
  `original_sha256` and is kept on this Mac only, like any upload's. No
  `storage.xml` is written, and `origin` has no `raw` key. A Markdown upload
  whose Confluence storage markers were expanded keeps its file the same way.
- **No `raw/` folder** (user decision, 2026-10-13).
- **A diagram shows as the page had it, and no file is made for it.** An
  attached draw.io diagram shows its picture; a viewer link stays as it was; a
  diagram drawn inline gets a viewer link carrying the diagram in its `#R`
  fragment; a PlantUML macro shows its source as a code block (user decision,
  2026-10-13: no rendering). The `source_kept` report status is gone.
- Sources imported before keep their `storage.xml` and diagram files; nothing is deleted.

## Impact

- Capabilities: `knowledge` ("Keep an upload's original on this Mac only",
  "Import a Confluence page as a readable source with its attachments") and its
  data model.
- Code: `ingest.py`, `converters/confluence/{page,storage,macros,diagrams}.py`,
  `passthrough_converter.py`, `source_view.py`, the delivered guide.
- Docs: knowledge guide and architecture (en, zh); ADR
  confluence-pages-import-as-readable-sources (amendment).
