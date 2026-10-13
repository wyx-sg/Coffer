# Confluence Pages Import as Readable Sources With Their Attachments

**Status**: Accepted
**Date**: 2026-10-13
**Deciders**: Yuxing Wu
**Related**: [Knowledge Sources Keep Their Images; Originals Stay on This Mac](knowledge-sources-keep-their-images-and-originals-stay-on-this-mac.md); [Knowledge Is a Wiki of Pages Compiled From Kept Sources](knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md); [Knowledge Files Stay Where Their Writer Put Them, and Every Link Is Checked](knowledge-files-stay-where-their-writer-put-them.md); [The Loopback Daemon Performs OS File Actions for the UI](daemon-proxies-os-file-actions.md); spec knowledge "Import a Confluence page as a readable source with its attachments", spec daemon "Open web links in the default browser"; OpenSpec changes `respect-knowledge-file-locations-and-import-confluence`, `keep-confluence-export-as-original`

## Context

Much of what an agent needs to know at work lives in Confluence. Pages reach a
collection as a page export: the page's storage format (Confluence's XHTML
with `ac:` and `ri:` elements), its title, id, version and URL, and,
optionally, its attachments. Until now such an export went in as text. The
result was a source an agent and a person could barely read:

- **Macros were left as markup.** A page wrapped whole in a
  `numberedheadings` or `section` macro came out as one block of comment-like
  markers with the real content inside, invisible in the Knowledge page and
  noise to an agent.
- **Attachments were lost.** Pictures and draw.io or PlantUML diagrams were
  referenced by Confluence file name and never kept, so "see the flow below"
  pointed at nothing.
- **Two YAML blocks.** The export's own frontmatter landed inside the body,
  under Coffer's, so the page's URL and version were in a block nothing read.
- **No word of what was lost.** A failed attachment or an unknown macro looked
  the same as a clean import.
- **A second import duplicated the page.** There was no way to say "this is a
  newer version of a page already here".
- **Links in tables could not be clicked.** Confluence tables with merged cells
  stay HTML; the reader showed them as text, and in the desktop app a web link
  had nowhere to open.

## How comparable products handle it

- **Notion's Confluence importer** converts pages to Notion blocks, keeps
  images and attachments as files on the page, and turns macros it does not
  know into plain text or drops them; a re-import makes a new page rather than
  updating one.
- **confluence-markdown-exporter** (open source) writes Markdown per page,
  downloads attachments into a folder beside it, links them relatively, and
  expands common macros (`info`, `code`, `expand`, `toc`); unknown macros are
  dropped. It keeps page metadata in frontmatter.
- **Markdown Exporter for Confluence** (Atlassian Marketplace) converts the
  page body including panels and code macros, exports attachments, and keeps
  tables with merged cells as HTML because Markdown tables cannot express them.
- **Pandoc** reads HTML and writes Markdown, falling back to raw HTML for what
  Markdown cannot express; it knows nothing of Confluence macros.
- **draw.io** stores a diagram as a `.drawio` file and its rendering as a
  `.png`; the macro's picture is only the rendering, and the source is what
  can be edited. **PlantUML** macros carry their source in the page.

The common pattern: **Markdown for the body, HTML where Markdown falls short,
attachments as files beside it, macros expanded for what they show**. Where
they fall short is the same everywhere: none keep the original storage, and
none report what was lost.

## Options Considered

### Option A — Keep the storage XHTML only

- Pro: nothing is lost; one file.
- Con: unreadable for a person and costly for an agent; macros, attachments
  and links stay Confluence's.
- Why it lost: a source nobody reads is not knowledge.

### Option B — Convert to Markdown and keep markers for what did not convert (the former behaviour)

- Pro: the Markdown is the only file; the markers hold what conversion could
  not place.
- Con: markers show up in the reader and in an agent's context as noise, and
  content inside a wrapping macro is hidden in them.
- Why it lost: it is the failure this change fixes.

### Option C — Readable Markdown with its attachments, the export kept as the original, and a report (chosen)

- The page becomes one source in `sources/`, Markdown first, with HTML kept
  where Markdown cannot express it (merged cells) and rendered safely: comments
  dropped, scripts and frames removed, everything sanitised.
- Every macro is read for what a reader sees. A macro that only arranges its
  body (`numberedheadings`, `section`, `column`, `expand`, tabs) gives the body
  back; `info`/`note`/`tip`/`warning` become a labelled quote; `code` keeps its
  language; a diagram shows as the page had it (amended 2026-10-13); generated
  content (`toc`, `children`) is dropped and said so; an unknown macro keeps
  its body or is reported unsupported.
- Attachments go to `assets/confluence-<page id>-v<version>/`, linked
  relatively. The
  export itself is the upload's original: kept on the Mac it was imported on,
  never in the vault, like a PDF's or a deck's (amended 2026-10-13, below).
- The export's metadata becomes the source's frontmatter under `origin`
  (system, URL, page id, space, version, fetched time), so there is one YAML
  block. `import_report` records the body (converted or partial) and what was
  kept, missing or unsupported, separately for attachments and macros.
- A page already imported (matched by page id) is refused with
  `KNOWLEDGE_SOURCE_EXISTS`. The person can preview a re-import (nothing
  written) and then replace: the new source is written beside the old one,
  which is marked `superseded_by` the new one, and the old files stay, so Undo
  brings the old state back.
- Web links open in the default browser through a daemon route
  (`POST /fs/open-url`, http/https/mailto only); relative links navigate
  inside the knowledge base.

- Pro: a person and an agent read the page as the page; nothing Confluence
  wrote is lost, because the export is kept as the original.
- Pro: what was lost is said, per item, in the upload dialog and on the file.
- Pro: re-import is explicit, previewable and recoverable.
- Con: the vault keeps the attachments of every version imported; a page with
  many versions grows the vault by each one.
- Con: the converter knows a fixed list of macros; a new one shows up as
  unsupported until it is added.

## Decision

**Option C.** A Confluence page export becomes a readable source with its
attachments kept beside it under `assets/`, the export itself kept as its
original on this Mac, its metadata in its
one frontmatter block, and a report of what was kept, missing and unsupported.
A re-import is explicit, previewable, and leaves the older version in place,
marked superseded.

Rules a future change must respect:

- **No markup in the reader.** Nothing Confluence wrote for itself (macros,
  markers, comments) reaches the rendered page; what cannot be shown is
  reported instead.
- **The export is kept.** A future converter can always re-read the page from
  the original on the Mac it was imported on, without asking Confluence again.
- **Never overwrite an import.** A re-import is a new version folder and a new
  source; the older one is superseded, not replaced in place.
- **A diagram shows as the page had it, never rendered by an outside
  service.** Coffer sends no page content to a diagram renderer and downloads
  nothing the export did not carry.
- **Web links leave through the daemon only for http, https and mailto.**

## Consequences

- A page imported before this change keeps its file. The reader shows it
  converted (a note says so) and the duplicate check reads its inner
  frontmatter, but its file is not rewritten; re-importing with replace gives
  it the new layout.
- An attachment on another page, an embed from another service (Google Drive,
  Jira charts) and an attachment the export did not download are reported
  missing, not fetched.
- A diagram is its picture, its link or its PlantUML source; Coffer does not
  render a diagram that has no picture.
- The daemon's OS-action surface gains one route, `POST /fs/open-url`, with the
  same guard as the others.

## Amendment (2026-10-13): the export is the original, and a diagram shows as the page had it

As first shipped, the page's storage was also written into the vault as
`storage.xml` beside the attachments. That made an imported page the one upload
whose raw form was synced to every Mac, unlike a PDF's or a deck's, which
[Knowledge Sources Keep Their Images; Originals Stay on This Mac](knowledge-sources-keep-their-images-and-originals-stay-on-this-mac.md)
keeps on the uploading Mac only. Now:

- **The export is the upload's original.** It gets `original` and
  `original_sha256` like any other upload and is kept in
  `~/.coffer/local/knowledge-originals/`, never synced; no `storage.xml` is
  written and `origin` has no `raw` key. A Markdown upload whose storage
  markers were expanded keeps its file the same way, because the source is no
  longer what was uploaded.
- **No `raw/` folder.** Karpathy's LLM-wiki keeps raw material in a `raw/`
  folder, and Obsidian vaults often keep an attachments folder of originals.
  Here `sources/` already is the raw layer agents read, and an original beside
  it would be synced bytes no agent reads. The user chose to keep this layout
  (decision card, 2026-10-13).
- **A diagram shows as the page had it, and Coffer keeps no file of its own
  for it** (the user's words: "是图片我们直接展示了图片，是链接就展示链接。不要自己再去下载之类的").
  As first shipped, a diagram held in the page was decoded into a `.drawio`
  file and the page's viewer link pointed at that file, and a PlantUML macro
  became a `.puml` file; a reader could no longer click through to the
  diagram. Now an attached draw.io diagram shows its picture; a viewer link
  stays the link it was; a diagram drawn inline gets a viewer link
  (`https://viewer.diagrams.net/?lightbox=1&nav=1#R…`) carrying the diagram in
  its fragment, the way draw.io's own "link" export does; a PlantUML macro
  shows its source as a code block. A browser never sends a fragment to the
  server, so the diagram is drawn in the reader's browser, as it was in
  Confluence. Comparable tools do the same: confluence-markdown-exporter and
  Notion's importer keep the picture and drop the macro, and none keeps a
  diagram file the page did not have.
- **PlantUML is not rendered.** Rendering it needs Java and PlantUML on the Mac
  (the VS Code and Obsidian PlantUML extensions) or a rendering server
  (GitLab); a public server would see internal diagrams. The user chose to
  show the source only (decision card, 2026-10-13).

Old imports keep their `storage.xml` and diagram files; nothing is deleted
from the vault.
