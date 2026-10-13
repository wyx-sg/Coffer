## Why

A collection's files have to describe themselves without Coffer: a person keeps
an `index.md`, a `log.md` and a `schema.md` at the collection's root, links pages
with ordinary relative Markdown links, and expects every file to stay where they
put it. Three things break that today.

1. **The sweep moves files.** Every Markdown file outside `pages/`, `sources/`
   and `assets/` (other than the README) is moved into `pages/` a minute after it
   was written, suffixed `-2` on a collision. That carries `index.md`, `log.md`
   and `schema.md` away from the root and breaks every relative link to or from
   them.
2. **An imported Confluence page is unreadable.** A Markdown upload that carries
   its own frontmatter gets a second frontmatter block above it: the title is the
   file's slug and the description is the inner block flattened into one line.
   A page exported by a Confluence CLI keeps unsupported macros as
   `skynet-confluence-storage` HTML comments; when a `numberedheadings` macro
   wraps the whole page, the whole body sits inside one comment, and the
   Knowledge page shows raw XML. Pictures and diagrams are not kept locally.
3. **The check only understands `[[slug]]`.** A page reached from the root
   `index.md` by a relative link is reported as an orphan, a relative link to a
   missing file is not reported, a page whose evidence is code or configuration
   rather than a formal source is always `unsourced_page`, and the recheck
   interval cannot be set per page.

## What Changes

- **No background pass moves or renames a file.** The sweep's "file loose
  documents into `pages/`" duty is removed with its quiet-minute retry. A
  collection's root and any folder a person makes keep their files in place; an
  upload creates only the files it names.
- **Root files are collection files.** Markdown at a collection's root other
  than the README (an index, a log, a schema) and files in folders a person made
  are read, listed, kept in history and restored with the collection; they are
  never pages, so the page checks never flag them, but their links count.
- **Standard relative links are checked.** `[text](path)` links in pages and in
  root files resolve relative to the linking file inside the knowledge root, may
  cross into another collection, and are `dead_link` when the target is missing
  and `outside_link` when they leave the knowledge root; URLs are external.
  `[[slug]]` behaves as before.
- **Evidence and recheck rules per collection and page.** A page's `evidence`
  list (code, configuration, observation) counts as evidence like `sources`; the
  README's `sourceless_types` names page types that need neither; a page's own
  `verify_after_days` overrides the collection's. A missing or null `verified`
  stays due a recheck. Any `type` a README defines is accepted.
- **A Markdown upload keeps one frontmatter.** The upload's own frontmatter
  becomes the source's, a nested second block is merged into it, and the title
  and description come from it.
- **Confluence pages import as readable sources.** An export the person fetched
  with their own authorised tool — a page read result in JSON with its
  attachments, or a Storage Format file — converts to readable Markdown: rich-text
  macros unwrapped, code kept with its language, complex tables as sanitised
  HTML, pictures and diagram sources saved under `assets/`, the Storage Format
  kept beside them, and the page's title, URL, id, version, retrieval time,
  representation, redaction and attachment list in the source's frontmatter.
  What could not be kept is listed with its reason.
- **Uploads report what they kept.** The upload answer carries `status`
  (`complete` or `partial`), the files written and the issues found; the CLI and
  the Knowledge page show them.
- **Explicit re-import.** An upload may name the source it `replaces`: the new
  source is written and the old one gains `superseded_by` in the same commit, so
  nothing is lost; `dry_run` previews the result and writes nothing.
- **Safe reading.** The Knowledge page renders HTML inside a document through a
  sanitiser that drops comments, scripts, iframes, styles and event handlers, and
  shows a source still holding Confluence storage markers with the markers
  expanded to readable Markdown, the file itself untouched.

## Capabilities

- `knowledge` — layout, sweep, upload, check, reading.

## Impact

- Backend: knowledge sweep and its wiring, converters (new Confluence converter),
  ingest, wiki check, document reads, upload route and CLI, generated contract.
- Frontend: Markdown rendering in the Knowledge reader, upload report, finding
  labels.
- Docs: knowledge spec and data model, docs-site (English and Chinese), the
  `coffer-guide` skill source, two ADRs.
