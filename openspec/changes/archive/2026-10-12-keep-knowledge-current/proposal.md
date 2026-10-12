## Why

A collection is a wiki compiled from sources, and three things wear it down:
a source goes out of date when a newer version replaces it, a page drifts from
the code or system it describes while its sources stay the same, and what an
agent works out at work stays in that conversation. The person asked for each
to be handled, and for a tidy to say what the wiki is missing and where to look
for it. Two smaller gaps came up on the way: a new collection's README said
nothing about the page types and rules it is the schema for, and a source said
what it holds only through its title. The options are argued in ADR
`knowledge-stays-current-through-flags-coffer-computes`.

## What Changes

- **Superseded sources.** A source may carry `superseded_by: <slug>`. Every
  page that cites it and no later source in its chain of replacements is a
  `superseded_source` finding (`others` = the newest replacement). The old
  source no longer waits, a `superseded_by` naming no source is a
  `missing_source` finding on the source, and a source's read carries its
  replacement as a `SourceRef`.
- **Pages due a recheck.** A page whose `verified` is missing, unreadable or
  older than the collection's interval is a `stale_page` finding (target = the
  date as written, null when missing). The interval is the README
  frontmatter's `verify_after_days`: 90 by default, `0` turns it off, an
  invalid value keeps 90.
- **A new collection's README** is written with `verify_after_days: 90`, its
  heading and description, and "## Page types" (`overview`, `concept`,
  `entity`, `how-to`, `decision`) and "## Rules" sections. The description is
  the first paragraph before the first `##` section; editing it keeps the
  sections.
- **Source summaries.** A source may carry `summary`, one or two sentences an
  agent writes as it integrates or tidies.
- **Guide.** The catalogue at full detail lists every source, marked
  "(waiting)" or "(superseded by `sources/x.md`)", with its summary; shortened,
  it lists only the waiting sources. The writing section tells agents to write
  answers they work out from sources, code or systems back into the owning
  page (never a guess), add `sources`, set `verified` and tell the developer.
  Integrating gives each source a summary and marks a replaced one
  `superseded_by`. A tidy rechecks stale pages, sets `verified` to today,
  summarises every source without a summary, and ends its report with
  **Gaps**; the tidy hand-off prompt says so.
- **Web UI.** To do gains **Pages citing an outdated source** ("cites x,
  replaced by Y") and **Pages to recheck** ("last checked <date>" or "never
  checked"). An open page due a recheck shows **Needs rechecking** (and "never
  checked" without a date); an open superseded source shows **Superseded by**
  its replacement as a link. Contents lists each source with its state
  (waiting, used by N pages, skipped, superseded) and its summary, superseded
  ones last and struck through.
- **Wire.** `FindingKind` gains `superseded_source` and `stale_page`;
  `FileSummaryOut` gains `stale`, `superseded_by`, `summary`, `cited_count` and
  `skipped`; `FileOut` gains `stale`, `superseded_by` (`SourceRefOut` or null)
  and `summary`. All additive.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `knowledge`: three new requirements, "Mark a source superseded by the one
  that replaces it", "Ask for a recheck of a page after the collection's
  interval" and "Start a collection's README with its rules written out"; the
  requirements on frontmatter, the README, creating collections, the
  description, waiting sources, the mechanical check, the guide's teaching and
  catalogue, the tidy hand-off, the collection page and Contents say what
  changed. The Purpose's list of mechanical findings and `data-model.md` follow.

## Impact

- Backend: `infrastructure/knowledge/wiki.py` (both findings, the interval,
  replacement chains), `wiki_reads.py` (a file's read, split out of
  `wiki.py`), `catalogue.py`, `collection_files.py` (the default README),
  `domain/knowledge/entry.py`, `application/knowledge/` (`service.py`,
  `guide_render.py`, `tidy_handoff.py`, the `coffer-guide` skill asset), the
  knowledge HTTP schemas.
- Wire contract: `contracts/api.openapi.yaml` regenerated (additive).
- Frontend: To do, Contents, the file line, i18n (en, zh).
- Docs: ADR `knowledge-stays-current-through-flags-coffer-computes`; pointers
  and in-place rewrites in `knowledge-is-a-wiki-of-pages-compiled-from-kept-sources`
  and `tidying-knowledge-is-the-agents-job`; docs-site guides (knowledge) and
  architecture (knowledge, decisions), en and zh; `data-model.md`.
