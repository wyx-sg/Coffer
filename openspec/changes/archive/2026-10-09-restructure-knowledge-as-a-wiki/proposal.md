## Why

A collection was a pile of free-form documents. Each upload stood alone until
someone pressed Tidy, nothing recorded which uploads had already been folded
into the rest, the material as uploaded was not kept apart from what was
written from it, so a statement could not be traced back to where it came
from, and documents were forbidden to name each other, so subjects had no relations an agent could
follow. Knowledge did not compound. The user asked for a structure for the
knowledge base, compared against Karpathy's LLM Wiki, RAG and the alternatives,
and for a less awkward Document / History switch on a document's page. The
decision is recorded in the ADR
[Knowledge Is a Wiki of Pages Compiled From Kept Sources](../../../docs/decisions/knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md);
the research behind it is [knowledge structures](../../../docs/research/knowledge-structures.md).

## What Changes

- **Each collection is a wiki**: its `README.md` is the schema, `sources/` holds
  kept material, `pages/` holds the pages people and agents edit.
- **An upload becomes a source**: its converted Markdown in `sources/`. Only the
  Markdown is kept, not the uploaded file. A Markdown file dropped into `.inbox/` becomes a
  source too.
- **Pages carry** `title`, `type`, `description`, `sources`, `aliases`, `actor`
  and timestamps. A page's identity is its slug; `aliases` give it more names.
- **Pages link by slug**, `[[slug]]` or `[[slug|text]]`. Coffer resolves every
  link on read and reports a dead or ambiguous one.
- **Which sources wait is derived**: a source waits while no page cites it in
  `sources:` and it is not marked `ingest: skipped`.
- **Coffer checks a collection mechanically on every read**: dead and ambiguous
  links, duplicate slugs, orphan pages, incomplete pages, pages without
  sources, pages citing a missing source, and waiting sources. A new route
  `GET /api/v1/knowledge/collections/{uid}/check` and command
  `coffer knowledge check` serve them.
- **Tidy** now compiles waiting sources into pages and then tidies the pages;
  a new **Check** hand-off asks the agent for a report on contradictions, stale
  statements, duplicates and missing pages, changing nothing.
- **The guide skill** teaches the new layout, the page fields, linking by slug,
  integrating sources and checking a collection; its catalogue groups pages by
  type, names waiting sources and shortens itself to titles past a budget.
- **The sweep** also files a Markdown document left outside `pages/` and
  `sources/` into `pages/`, so existing collections take the new layout.
- **The web UI** shows a collection's pages and sources apart, marks a waiting
  source, resolves links in a page (a dead one marked), lists a page's sources
  and a source's citing pages, shows the collection's change log and its check
  findings with **Tidy** and **Check**, and opens a document's history in a
  drawer from the pane bar instead of a History tab that replaced the document.

## Impact

- `knowledge`: most requirements are modified (layout, identity, frontmatter,
  uploads, the inbox, the sweep, the guide, the hand-offs, the web UI, the
  routes and commands); new requirements for sources, links, waiting sources,
  the mechanical check and the check hand-off.
- `web-ui`: "Show a vault file's history on a History tab" is modified so a
  knowledge document shows the same history in a drawer.
- API: `CollectionOut` gains `page_count`, `source_count`,
  `waiting_source_count`, `finding_count` and `check_handoff` in place of
  `document_count`; `FileOut` and `FileSummaryOut` gain the file's kind and its
  page or source fields; a new check route. Contract regenerated.
- Docs: the ADR above (and an amendment note on
  [Knowledge Is Plain Files](../../../docs/decisions/knowledge-is-plain-files.md)),
  the research note, `docs-site` architecture and guide pages for knowledge in
  English and Chinese, the CLI reference.
- Canvas 5 (Context): the Knowledge boards.
