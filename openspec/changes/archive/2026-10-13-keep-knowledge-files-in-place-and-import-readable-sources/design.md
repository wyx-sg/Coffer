# Design

## 1. Files stay where their writer put them

The sweep keeps four duties: adopt `.inbox/` files, commit edits found on disk,
close idle tidies, re-render the guide. The fifth, filing loose documents into
`pages/`, is deleted with everything that only served it
(`infrastructure/knowledge/layout.py`, `application/knowledge/layout.py`, the
quiet-minute retry in `knowledge_sweep_wiring.py`). No migration command
replaces it: a collection laid out before `pages/` existed is still valid, and
moving files is an agent's job during a tidy, where it can fix links in the same
change. `OP_LAYOUT` stays only so the changes feed can name commits older
versions made.

A collection is any tree of files. What Coffer gives meaning to:

| Path | Kind | Checked as |
| --- | --- | --- |
| `README.md` at the root | the collection's schema | never a document |
| `pages/**/*.md` | `page` | page checks |
| `sources/**/*.md` | `source` | source checks |
| `assets/**` | `file` | target of links only |
| any other file (root `index.md`, `log.md`, `schema.md`, a person's folder) | `file` | never checked; its links count |

Every `file` is listed in the tree, readable through the read route (Markdown
rendered like a page), committed by the sweep as a disk edit, carried by the
collection's delete and its Undo, and exported with the vault. Nothing renames
one.

## 2. Links

A link is either a wiki link `[[target]]` / `[[target|text]]` (unchanged) or a
standard Markdown link or image `[text](target)` / `![alt](target)` outside code.
A standard target is:

- external when it has a URL scheme (`http:`, `https:`, `mailto:`, …) or starts
  with `#` — never checked;
- otherwise a path, percent-decoded, with any `#fragment` or `?query` dropped,
  resolved relative to the directory of the file that holds it.

A resolved path that leaves the knowledge root is an `outside_link` finding
(target as written). Inside the root, a path naming no existing file is a
`dead_link`. A path naming a page in the same collection counts as an inbound
link for the orphan check; a path into another collection is checked for
existence only. Links in `file`-kind Markdown (root index, log, any person's
folder) and in sources count towards inbound links and are checked for dead and
outside targets too, with the finding's `path` the file that holds the link.
A page's read carries its standard links beside its wiki links, each with the
knowledge-root-relative path it resolves to (or none), so the reader can open
it.

## 3. Evidence and rechecks

- `unsourced_page` fires for a page with neither `sources` nor `evidence`.
  `evidence` is a list of free-form strings (`code: <repo>/<path>@<rev>`,
  `config: …`, `observed: …`); Coffer does not interpret them.
- The README frontmatter `sourceless_types: [<type>, …]` names page types exempt
  from `unsourced_page` (for example `overview` or `how-to`). Default: none.
- A page's own `verify_after_days` overrides the README's, read by the same rule
  (whole non-negative days, `0` off, anything else falls back to the
  collection's interval).
- `verified` missing, null or not a date is due a recheck. Coffer never writes
  `verified`.
- `type` is free text; the README lists the types a collection uses.

## 4. One frontmatter per upload

A passthrough (Markdown / text) upload is split with `split_frontmatter`. When
the remaining body itself opens with a fenced YAML block (a Coffer source
re-uploaded with an imported document's own block under it), that block is
split too and its keys win over the outer ones, except `actor`, `created_at` and
`updated_at`, which Coffer writes. A `description` that is just a frontmatter
block flattened to one line (it starts with `---`) is dropped. Then:

- `title`: the frontmatter's `title`, else the first `# ` heading, else the file
  name;
- `description`: the frontmatter's, else the body's opening prose;
- every other key the upload carried is kept on the source.

## 5. Confluence import

Coffer never calls Confluence: the person fetches the page with the tool they
are authorised to use and uploads the result (Local-First, AI-Native; ADR
confluence-pages-import-from-an-export-the-person-fetched). Accepted inputs, by
content, through the ordinary upload route and its 20 MB ceiling:

1. **A page read result in JSON** — either the Confluence REST content shape
   (`id`, `title`, `version.number`, `space.key`, `body.storage.value`,
   `_links.base` + `_links.webui`) or a CLI read result carrying `pageId`/`id`,
   `title`, `version`, `spaceKey`, `link`/`pageUrl`, `bodyFormat: storage`,
   `body` and `attachments[] {name, mimeType, dataBase64}`.
2. **A Storage Format file** named `*.storage.xml` (no attachments, no
   metadata beyond its name).
3. **A Markdown file carrying `skynet-confluence-storage:v1` markers** — each
   marker's Storage XML is converted in place (section 6), the frontmatter rules
   of section 4 apply, and the uploaded Markdown is kept as the original on this
   Mac.

### Storage → Markdown

The Storage XML is parsed as HTML (CDATA kept as text). Then:

| Element | Becomes |
| --- | --- |
| `numberedheadings`, `easy-heading-free`, `section`, `column`, `details`, any unknown macro with a `rich-text-body` | its body, unwrapped; an unknown one is also listed `unsupported_macro` |
| `toc`, `children`, `pagetree`, `anchor` | nothing (generated navigation) |
| `expand` | `**<title>**` followed by its body |
| `info`, `note`, `tip`, `warning`, `panel` | a blockquote opening `**Info:**` (etc., or the panel's title) |
| `code`, `noformat` | a fenced block with the `language` parameter, text verbatim |
| `status` | its `title` in backticks |
| `jira` | the issue `key` |
| `plantuml` | a fenced `plantuml` block, and `diagram-N.puml` kept; `not_rendered` |
| `drawio` / `inc-drawio` | the attachment `<diagramName>.png` shown and `<diagramName>` (`.drawio`) kept when present, else `missing_attachment` |
| `html` holding `data-mxgraph` | its `xml` saved as `diagram-N.drawio`, a line linking it |
| `html` holding a `viewer.diagrams.net` / `app.diagrams.net` iframe or link with `#R<data>` | the data inflated locally into `diagram-N.drawio` |
| the same with `#G…`, `#U…` or anything else | a line naming the hosted diagram's URL; `external_embed` |
| any other `html` macro | a line saying an HTML block was not kept; `unsupported_macro` |
| `ac:image` + `ri:attachment` | `![alt](coffer-asset:<name>)` when the attachment is present, else `missing_attachment` (`on another page` when it names a page) |
| `ac:image` + `ri:url` | the remote image link; `external_image` |
| `ac:link` + `ri:page` / `ri:attachment` / `ri:user` | the link body or the page title / file name / `@user` as text |
| `ac:inline-comment-marker`, `ac:emoticon`, `ac:placeholder` | their text / shortname / nothing |
| `ac:task-list` | `- [ ]` / `- [x]` items |
| a table with merged cells or block content in a cell | a sanitised HTML table (only `table thead tbody tr th td colspan rowspan p br ul ol li a strong em code pre img`) |
| any other table | a Markdown table |
| `diagrams.net` viewer `<a>` links elsewhere in the body | inflated the same way when `#R`, kept as links otherwise |

Nothing is executed and nothing is fetched. A macro's text is never dropped
silently: unknown macros keep their body, and a macro with no body that is not
in the table above is listed as `unsupported_macro`.

### Where things go

- Source: `sources/<slug of title>.md`.
- Assets: `assets/confluence-<pageId>-v<version>/` (a Storage Format file with
  no id uses `<title-slug>-<sha8>`). When the folder exists with different
  bytes, the folder gains `-<sha8>`; when it holds the same bytes, it is reused.
- Kept files: every picture the body shows and every diagram source, by a safe
  name (unsafe characters replaced with `-`), and `page.storage.xml`, the Storage
  Format as it came. Links in the body are written `coffer-asset:<name>` by the
  converter and pointed at `../assets/<folder>/<name>` by the ingest.
- The uploaded file itself is kept on this Mac only (the existing original).

### Frontmatter

```yaml
title: "Service A"   # the page's own title
description: <opening prose>
origin: https://confluence.example.com/pages/viewpage.action?pageId=1234
page_id: "1234"
page_version: 7
space: DOCS
retrieved_at: 2026-10-13T10:00:00+00:00     # when it was imported, not verified
representation: markdown from confluence storage
original_representation: ../assets/confluence-1234-v7/page.storage.xml
redaction: none                              # or what the export said
attachments:
  - {name: architecture.drawio.png, original_name: "architecture.drawio.png",
     path: ../assets/confluence-1234-v7/architecture.drawio.png, status: saved}
  - {name: image.png, status: missing, reason: not in the export}
import_status: complete                      # or partial
import_issues:
  - {kind: external_embed, name: diagram, reason: hosted on Google Drive; not fetched}
actor: user
created_at: …
updated_at: …
original: page.json
original_sha256: …
```

`import_status` is `partial` whenever an issue other than `not_rendered` exists.

## 6. Storage markers in a Markdown file

`expand_storage_markers(markdown)` replaces each
`<!-- skynet-confluence-storage:v1 kind=… \n<xml>\n-->` block (with `--`
unescaped back to `--`) by the Storage → Markdown conversion of its XML, with no
asset folder (an image becomes a `missing_attachment`). The document read route
answers `display_body` — the expanded body — for a document whose body holds a
marker, and nothing otherwise; the file is never rewritten. The Knowledge page's
preview shows `display_body` when present; Raw shows the file.

## 7. Upload report and re-import

`POST /api/v1/knowledge/upload` gains form fields `replaces` (a source's path in
the same collection) and `dry_run` (bool). The answer gains:

- `status`: `complete` | `partial`;
- `files`: knowledge paths written beside the source;
- `issues`: `[{kind, name, reason}]`;
- `replaced`: the replaced source's path, or null;
- `dry_run`: whether anything was written.

With `replaces`, the new source and `superseded_by: <new slug>` on the old one
are one commit. `dry_run` runs the conversion and answers the same shape with
the paths that would be written, writing nothing. `coffer knowledge upload`
gains `--replaces` and `--dry-run` and prints status, files and issues.

## 8. Safe rendering

The Knowledge reader (not chat) renders Markdown with `rehype-raw` followed by
`rehype-sanitize`, schema = the default GitHub schema plus `details`, `summary`,
`colspan`/`rowspan` on cells; comments, `script`, `style`, `iframe`, `object`,
`embed`, `form` and every `on*` attribute are removed. Relative links between
knowledge files open in the reader; relative images go through the asset route
as today.
