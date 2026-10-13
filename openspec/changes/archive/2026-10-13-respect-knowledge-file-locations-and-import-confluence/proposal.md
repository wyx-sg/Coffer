## Why

In a collection a person and an agent had built by hand, the sweep filed
navigation files (`index.md`, `log.md`) into `pages/` and broke every relative
link to them, and the checker read only `[[slug]]`, so nothing reported it.
Pages backed by a ticket or a person could only clear "unsourced" with a fake
source, `verified` was set to dates nobody checked, and one review interval
had to fit every page. Separately, a Confluence page export went in as text:
macros stayed as markers that hid the content, attachments and diagrams were
lost, the export's YAML landed as a second block in the body, nothing said
what was lost, a second import duplicated the page, and links in its tables
could not be clicked. The options are argued in ADRs
`knowledge-files-stay-where-their-writer-put-them` and
`confluence-pages-import-as-readable-sources`.

## What Changes

- **Files stay put.** The sweep no longer files anything; it adds frontmatter
  and records. A file at a collection's root beside the README is the
  collection's own: listed as a plain file, never asked for sources, and
  restored byte for byte by Undo.
- **Every link is checked.** `[[slug]]` and relative Markdown links are both
  resolved against the file that holds them; a dead one is `dead_link`, one
  that climbs out of the knowledge root `outside_link` (new finding kind).
- **Evidence and intervals.** A page names `evidence:` (URLs, tickets, people)
  beside `sources:`; the README's `types_without_sources` (default
  `[overview]`) names the types that need neither. `verified: null` stays
  unchecked. A page's `verify_after_days` overrides the collection's. Any page
  type is accepted.
- **Confluence import.** A page export (JSON) is claimed by content and becomes
  a readable source: macros expanded for what they show, HTML kept and
  sanitised where Markdown falls short, the storage kept as `storage.xml`,
  attachments and diagram sources under `assets/confluence-<id>-v<ver>/`, the
  export's metadata as `origin` in the one frontmatter block, and
  `import_report` with body, attachments and macros reported separately.
- **Re-import is explicit.** A page already imported is refused with
  `KNOWLEDGE_SOURCE_EXISTS` (409); `preview` returns the result without
  writing, `replace` writes the new version beside the old and marks the old
  `superseded_by`. The CLI gains `--preview`, `--replace` and `--attachments`.
- **Older imports read converted.** `FileOut` gains `readable_body`, `origin`
  and `import_report`; a source with export markers reads converted with a
  note, and its file is not rewritten.
- **Links open.** The reader renders sanitised HTML; relative links navigate
  inside the knowledge base, dead and outside ones are marked; web links open
  in the default browser through the new `POST /api/v1/fs/open-url` in the
  desktop app, and in a new tab in a browser.
- **Upload dialog.** A partial import lists what is missing; a refused
  re-import offers Replace.

## Impact

- Specs: knowledge (edited directly), knowledge data model, daemon.
- ADRs: two new; addendum to `daemon-proxies-os-file-actions`.
- Backend: knowledge sweep, wiki checks, ingest, converters, HTTP and CLI
  surfaces, fs open service. Frontend: knowledge reader, upload dialog,
  Markdown renderer (`rehype-raw`, `rehype-sanitize`).
- Existing sources in a person's vault are not rewritten; re-importing with
  replace gives them the new layout.
