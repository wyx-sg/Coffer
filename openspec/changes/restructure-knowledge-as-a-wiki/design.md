## Context

The decision and its alternatives are in the ADR
[Knowledge Is a Wiki of Pages Compiled From Kept Sources](../../../docs/decisions/knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md).
This file records the mechanics.

## Layout

```text
<collection>/
├── README.md                 schema; first paragraph is the description
├── sources/
│   ├── release-notes.md      converted Markdown + frontmatter (the source)
│   └── release-notes.pdf     the original, when it is not the same text
├── pages/
│   └── session-ownership.md  a page
└── .inbox/                   drop zone; adopted into sources/
```

- A **page** is a Markdown file under `pages/` (any depth). A **source** is a
  Markdown file under `sources/` (any depth). Every other file under the
  collection is a plain file: listed, never catalogued or checked.
- `paths.py` gains `PAGES_DIR_NAME`, `SOURCES_DIR_NAME` and `kind_of(relpath)`
  returning `page`, `source` or `file`.
- An upload's original is kept as `sources/<slug>.<ext>` beside
  `sources/<slug>.md` unless the converter was passthrough (the Markdown *is*
  the original). The source's frontmatter names it in `original:`. A collision
  suffixes both names alike (`-2`).

## Frontmatter

- **Page:** `title`, `type`, `description`, `sources` (list of source slugs),
  `aliases` (list), `actor`, `created_at`, `updated_at`. Coffer writes no page
  itself; the guide tells agents to write these.
- **Source:** `title`, `description`, `actor`, `created_at`, `updated_at`,
  `original` (when kept), and optionally `ingest: skipped`, the one key the
  guide lets an agent add to a source.
- Default page types in the guide: `concept`, `entity`, `how-to`, `decision`,
  `overview`. A README that defines its own types wins; Coffer accepts any
  non-empty string.

## Identity and links

- A page's **slug** is its file stem; a source's slug is its file stem.
  Matching is case-insensitive after NFKC, the same normalisation file names
  get.
- A link is `[[target]]` or `[[target|text]]` anywhere in a page's body
  outside code spans and fenced blocks. `target` resolves against page slugs,
  every page's `aliases`, and source slugs. None → **dead**; more than one
  distinct file → **ambiguous**.
- A page's `sources:` entries resolve against source slugs only. An entry that
  matches none → **missing source**.

## The check

`infrastructure/knowledge/wiki.py` walks one collection once and builds an
in-memory `WikiGraph`: pages with their parsed frontmatter and outbound links,
sources with whether they are skipped, and the resolution maps. Nothing is
stored; every read rebuilds it (the corpus is hundreds of files, measured walks
are milliseconds). From it:

| Finding | Rule |
| --- | --- |
| `dead_link` | a link that resolves to nothing |
| `ambiguous_link` | a link that resolves to more than one file |
| `duplicate_slug` | two pages share a slug, or an alias names two pages |
| `orphan_page` | a page no other page links to, when the collection has two or more pages; `overview` pages are exempt |
| `incomplete_page` | a page missing `title`, `type` or `description` |
| `unsourced_page` | a page with no `sources:` |
| `missing_source` | a `sources:` entry that names no source |
| `waiting_source` | a source no page cites and not `ingest: skipped` |

`GET /api/v1/knowledge/collections/{uid}/check` returns the findings and the
check hand-off. `CollectionOut` carries the counts (`page_count`,
`source_count`, `waiting_source_count`, `finding_count`) and both hand-offs;
the list route computes them per collection, one walk each.

## Reads

- `FileOut` adds `kind`, and for a page `page_type`, `aliases`, `sources`
  (each `{slug, path, title}`, `path` null when missing) and `links` (each
  `{target, path}`, `path` null when dead); for a source `original_path`,
  `cited_by` (`{path, title}`) and `waiting`.
- `FileSummaryOut` adds `kind` and `waiting`, so the tree can mark a waiting
  source without a second call.

## Hand-offs

- **Tidy** (per collection and all): facts gain the waiting-source count; the
  steps say to integrate waiting sources first, by the guide's "Integrating
  sources" section, then tidy pages by "Tidying a collection".
- **Check** (per collection): facts carry the mechanical findings grouped by
  kind with their paths (capped at 40 lines); the task says to follow the
  guide's "Checking a collection", report contradictions, stale statements,
  duplicated subjects and subjects that deserve a page, and change nothing.

## The guide

- Knowledge sections are rewritten: the layout; **Writing a page** (find its
  home in `pages/`, lose nothing, organise by subject, newer wins unless shown
  wrong, link by `[[slug]]` and never by path, when renaming a page update the
  links to it or add the old slug to `aliases`, frontmatter fields, never edit a
  source); **Integrating sources** (read a waiting source, fold what it says
  into the pages that own its subjects, create pages for subjects with none,
  add the source's slug to each page's `sources:`, mark `ingest: skipped` when
  nothing is worth keeping); **Tidying a collection**; **Checking a
  collection** (report only).
- The catalogue lists, per collection, the README path, pages grouped by
  `type` (path, title, description) and waiting sources (path, title). Past
  60,000 characters the whole catalogue drops descriptions, and past it again
  lists only each collection's counts and paths to grep, saying so.

## The sweep

A fourth duty, before the commit of disk edits: **file loose documents**. A
Markdown file in a collection outside `pages/`, `sources/` and hidden entries,
other than the root `README.md`, untouched for 60 seconds, is moved to
`pages/<same relative path>` (suffixed on a collision) as one commit by the
daemon writer with the `layout` operation. Existing collections converge on the
first sweep after upgrade; an agent that writes to the wrong place is corrected
within a minute. Content is never rewritten.

## Web UI

- **Tree**: a collection's root shows `pages` and `sources` as the two folders
  first, labelled Pages and Sources; a waiting source carries a dot and the
  label Waiting.
- **Document pane bar**: crumbs, then on the right **History** (clock icon
  button), Preview / Source, Open in editor, ⋯. History opens a right drawer
  (`?history=1` in the URL) holding the existing version card; the document
  stays beside it. The `/history` path segment redirects to the drawer.
- **Reader**: a page shows a line under the title naming its type and its
  sources (each a link to the source, a missing one struck through); `[[links]]`
  render as links to the page they resolve to, a dead one in the danger tone
  with a tooltip. A source shows "Cited by N pages" or the Waiting chip, and
  its original's name when one is kept.
- **Collection page**: properties Pages, Sources (n waiting), Folder; a
  **Check** section listing the findings grouped by kind, each path opening
  the file, with **Check with agent** beside **Tidy**; a **Change log** section
  reading the changes feed for the collection, one row per change (writer,
  time, what it did, the files it touched, each opening that file with its
  history drawer).

## Risks

- **Moving loose documents changes paths.** Paths are not identity for links
  any more (slugs are), and the catalogue is regenerated, so nothing refers to
  the old path except a person's memory. The move is one commit, reversible.
- **Upload size doubles on disk** for converted formats. The 20 MiB ceiling
  stays.
- **Concurrent edit.** The 60-second quiet rule avoids moving a file an agent
  is still writing.
