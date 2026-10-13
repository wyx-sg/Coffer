# Confluence Pages Import From an Export the Person Fetched

**Status**: Accepted
**Date**: 2026-10-13
**Deciders**: Yuxing Wu
**Related**: [Knowledge Sources Keep Their Images; Originals Stay on This Mac](knowledge-sources-keep-their-images-and-originals-stay-on-this-mac.md); [Knowledge Is a Wiki of Pages Compiled From Kept Sources](knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md); [Knowledge Files Stay Where Their Writer Put Them](knowledge-files-stay-where-their-writer-put-them.md); principles I (Local-First) and IV (AI-Native); spec knowledge "Keep every upload as a Markdown source"; OpenSpec change `keep-knowledge-files-in-place-and-import-readable-sources`

## Context

Design documents often live in Confluence. People brought them into a
collection by reading a page with a Confluence CLI as Markdown and uploading
the file. The result was unreadable:

- The CLI's Markdown keeps every macro it cannot convert as a hidden
  `<!-- skynet-confluence-storage:v1 … -->` comment holding the macro's Storage
  XML, so the page can be written back. When a `numberedheadings` macro wraps
  the whole page (a common template), the whole body is inside one comment:
  the Markdown has no visible text, and Coffer's reader showed the XML.
- A code macro inside a table cell came out mangled: its CDATA was parsed as
  markup, so text such as `account-<module>-<env>` vanished.
- The upload kept the file's own frontmatter as body text, wrote a second
  frontmatter above it with the slug as title, and took the description from
  the "first paragraph" — the inner frontmatter flattened into one line.
- Pictures stayed remote or were not downloaded; draw.io diagrams appear in
  three different shapes (a PNG attachment with an editor link carrying the
  compressed diagram, an iframe onto a diagram hosted on Google Drive, and the
  diagram's XML inline in an HTML macro).

The forces:

- **Coffer holds no Confluence credential.** Reading Confluence needs the
  person's token or session and their network; the daemon is a local vault, and
  a token stored only to fetch pages would be one more secret for a feature an
  agent already does well.
- **Storage Format is the faithful form.** It is Confluence's own XHTML
  dialect (`ac:` and `ri:` elements). Any readable Markdown is a lossy view of
  it; the Storage Format is what proves what the page said.
- **Nothing in a page may run.** HTML macros carry scripts and iframes;
  rendering them would execute someone else's code in Coffer's UI.
- **Nothing may leave the machine.** Rendering PlantUML or fetching a hosted
  draw.io diagram through a public service would send internal material out.

### How comparable products handle it

- **Notion's Confluence importer** reads a space through Confluence's API with
  the person's credentials, or takes the space's HTML export, and converts
  macros it understands; others are flattened or dropped.
- **Confluence's own export** (HTML or PDF) bundles a page with its
  attachments; it renders macros server-side, so diagrams arrive as pictures and
  the diagram sources do not.
- **Community exporters** (for example the `confluence-markdown-exporter`
  style of tool) call the REST API, convert Storage Format to Markdown and
  download attachments next to the Markdown, leaving unsupported macros as
  notes.

The common pattern: **the fetch happens with the person's own access**, the
converter works on Storage Format, attachments become files beside the
Markdown, and what cannot be converted is named rather than hidden.

## Options Considered

### Option A — Coffer fetches pages from Confluence itself

- Pro: one step for the person.
- Con: Coffer would hold a Confluence token or ride the person's session, talk
  to an internal host the daemon has no business reaching, and own a per-site
  integration (Cloud, Data Center, a company's gateway).
- Con: an agent with the person's authorised CLI already does this, under the
  person's eyes (principle IV).
- Why it lost: it puts credentials and a vendor integration into the vault for
  something the person's own tools already do.

### Option B — Keep accepting the CLI's Markdown as it comes

- Pro: no new code.
- Con: the defects above stay: hidden bodies, mangled code, no pictures.
- Why it lost: the Markdown is a write-back format, not a reading format.

### Option C — Convert an export the person fetched, from Storage Format (chosen)

The person (or their agent) reads the page with their own tool and uploads
the result through the ordinary upload: a page read result in JSON — the
Confluence REST content shape, or a CLI read result that embeds the
attachments' bytes — or a bare `*.storage.xml`. A Markdown file that still
carries storage markers is converted the same way, marker by marker. Coffer
converts the Storage Format to readable Markdown: layout macros unwrapped,
code kept with its language, panels as quotes, complex tables as sanitised
HTML. It saves the pictures and diagram sources it can get locally (an
attachment in the export, a diagram inline in the page, an editor link that
carries the compressed diagram) under `assets/confluence-<id>-v<version>/`,
keeps the Storage Format there as `page.storage.xml`, and lists what it could
not keep — a hosted diagram, an attachment on another page, a macro it does not
know — with its reason. The source's frontmatter records the page's own title,
URL, id, version, retrieval time, representation, redaction and attachments.
PlantUML is kept as source and not rendered.

- Pro: no credential and no network in Coffer; it works with any tool that can
  produce Storage Format.
- Pro: the readable Markdown is for people and agents, and the Storage Format
  beside it is the evidence.
- Pro: the report says exactly what is missing, so a partial import is never
  mistaken for a complete one.
- Con: two steps (fetch, upload), which an agent does in one go.
- Con: Coffer's converter knows a fixed set of macros; others keep their text
  and are listed.

## Decision

**Option C.** Coffer imports a Confluence page from an export the person
fetched, converts it from Storage Format, keeps the Storage Format and every
picture and diagram source it can get locally, and reports the rest. A
re-import is explicit: an upload names the source it replaces, which gains
`superseded_by` in the same commit, and a dry run previews it.

Rules a future change must respect:

- **No credential, no fetch.** Coffer never calls Confluence or an external
  rendering service.
- **Nothing executes.** HTML, iframes and scripts in a page are never rendered
  live; the reader sanitises every HTML element it shows.
- **Never claim completeness.** An import with a missing attachment, a hosted
  embed or an unknown macro is `partial`, with each item named.
- **Never rewrite existing sources silently.** Replacing one is an explicit
  re-import that keeps the old source and marks it superseded.

## Consequences

- Existing sources made from the CLI's Markdown stay as they are. The reader
  shows them with their storage markers expanded, and the person re-imports
  them when they want pictures and clean frontmatter.
- The vault gains the Storage Format of each imported page next to its
  pictures; it is text and small next to the pictures.
