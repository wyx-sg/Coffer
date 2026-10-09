# Knowledge Is a Wiki of Pages Compiled From Kept Sources

**Status**: Accepted
**Date**: 2026-10-09
**Deciders**: Yuxing Wu
**Related**: [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md) (amended by this decision); [Tidying Knowledge Is the Agent's Job](tidying-knowledge-is-the-agents-job.md); [Coffer Ships Its Own Manual as a Skill Resource](coffer-ships-its-own-skill.md); [Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md); research notes [knowledge curation](../research/knowledge-curation.md) and [knowledge structures](../research/knowledge-structures.md); spec knowledge; OpenSpec change `restructure-knowledge-as-a-wiki`

**Amended** (2026-10-09): the owner decided that an upload keeps only its converted Markdown source, `sources/<slug>.md`; the uploaded file itself is no longer stored and a source has no `original` key. The collection stays one tree of Markdown every agent can read, and the sync repository carries no binaries. The text below describes that.

## Context

[Knowledge Is a Directory of Markdown Files](knowledge-is-plain-files.md)
settled how knowledge is **stored and found**: plain Markdown under
`~/.coffer/vault/knowledge/<collection>/`, no derived index, read with the
agent's own `Read` and `Grep` at paths a generated catalogue in the
`coffer-guide` skill hands it. It left open how a collection is **structured**:
every document was free-form, an upload became one more document beside the
others and was rewritten in place by every tidy, and a document was forbidden
to name another file, because hand-written file references had rotted (343 of 398 dead).

Living with that showed three gaps:

- **Knowledge did not compound.** Each upload stood as an isolated document
  until someone pressed Tidy, and nothing recorded which uploads had already
  been folded into the rest. A collection grew as a pile of carriers rather than
  as subjects.
- **Nothing could be checked against its origin.** An upload was rewritten in
  place as it was tidied into the rest, and no document said what it drew on,
  so a wrong summary could not be traced back to the material it came from.
- **Documents could not point at each other.** The ban on naming files removed
  the dead links, and with them every relation between subjects. An agent found
  related material only by grepping for words.

Andrej Karpathy's "LLM Wiki" pattern (April 2026) addresses exactly these:
immutable **raw sources**, an LLM-maintained **wiki** of interlinked pages
compiled from them, and a **schema** document that tells the LLM how to
maintain it, with ingest, query and lint as the operations. Two research rounds
([knowledge curation](../research/knowledge-curation.md), 2026-09, and
[knowledge structures](../research/knowledge-structures.md), 2026-10) compared
it with RAG, knowledge graphs and some fifty products and open-source
implementations.

## Options Considered

### Option A — Keep free-form documents (the status quo)

- **Pros.** Already built; nothing to migrate.
- **Cons.** The three gaps above stay open. A tidy has no way to tell what is
  new, an agent has no relations to follow, and nothing traces a statement to
  its origin.

### Option B — Vector RAG over the documents

Chunk and embed the collections; retrieve the top chunks per question.

- **Pros.** Paraphrase matching; scales to corpora far beyond a catalogue.
- **Cons.** It answers retrieval, which was never the failure: the audit behind
  the earlier decision found agents never called a retrieval tool, and they use
  `Read` and `Grep` all day. The field moved the same way: Claude Code dropped
  vector RAG for agentic search, Obsidian Copilot V4 dropped its own index for
  file tools, and Cursor measured +0.3% overall from its semantic index in live
  traffic (+2.6% on repositories over 1,000 files). Nothing accumulates: every
  question re-derives its answer from chunks. An index is a derived store that
  can disagree with the files.
- **Why it lost.** It does not address any of the three gaps, and the earlier
  decision's constraint stands: semantic retrieval may return later only as a
  disposable sidecar over files that remain the truth.

### Option C — A knowledge graph (GraphRAG, LightRAG, Graphiti, Cognee)

Extract entities and relations into a graph store and query it.

- **Pros.** The strongest relations; good at corpus-wide questions.
- **Cons.** An opaque store a person cannot open in an editor, a model-driven
  extraction pipeline Coffer would have to run unattended, and heavy indexing
  cost. Typed wikilinks in plain Markdown (Basic Memory's approach) give most
  of the relational benefit without a graph database.
- **Why it lost.** It contradicts "knowledge is plain files a person can edit",
  and Coffer runs no model of its own over knowledge.

### Option D — An LLM Wiki adapted to Coffer (chosen)

Each collection holds three things:

```text
<collection>/
├── README.md     the schema: what the collection is for, its page types, its conventions
├── sources/      kept material: each upload's converted Markdown
└── pages/        the wiki: pages people and agents both edit, linked by [[slug]]
```

- **Sources are kept and do not change.** An upload, or a file dropped into
  `.inbox/`, becomes a source: its converted Markdown with frontmatter. Only the Markdown
  is kept, not the uploaded file, so the collection stays one tree of Markdown
  and the sync repository carries no binaries. Agents read sources and never
  edit them.
- **Pages are compiled from sources by the agent**, when the person presses
  **Tidy** (an ingest plus a tidy), or as the agent learns something durable.
  A page names the sources it draws on in its `sources:` frontmatter, so which
  sources are still waiting is derived from the pages themselves, with no
  manifest to keep.
- **Pages link by slug.** A link is `[[slug]]` or `[[slug|text]]`, resolved
  against page file names and each page's `aliases:`. The research found title
  links to be the commonest cause of dead links and duplicate pages in other
  implementations. Coffer checks every link on read, so a rename that breaks one
  shows up at once instead of rotting silently, which is what made the earlier
  ban necessary.
- **The catalogue stays generated.** An LLM-maintained `index.md` was the
  commonest cause of drift in the implementations surveyed; Coffer keeps
  rendering the catalogue into `coffer-guide`, now grouped by page type, and
  shrinks it to titles once it outgrows its budget.
- **The vault's git history is the log.** Every write is already one commit
  naming its writer and operation; a collection's change log is those commits,
  so there is no `log.md` to keep.
- **Checking is in two layers.** Coffer itself computes the mechanical findings
  (dead and ambiguous links, duplicate slugs, orphan pages, pages missing
  frontmatter or sources, sources still waiting) on every read. Judgement
  (contradictions, stale statements, duplicated subjects, subjects with no page)
  is handed to the agent with **Check**, which reports and changes nothing: one
  implementation found that separate unattended maintenance passes undid each
  other.

- **Pros.** Closes all three gaps with plain files: pages accumulate, every page
  traces back to kept sources, and pages relate through links that are checked.
  Keeps every constraint of the earlier decision: no derived store, no
  retrieval tool, no model run by Coffer, one undivided store, pull not push.
- **Cons.** A bad conversion cannot be checked against the uploaded file,
  because Coffer does not keep it; the person keeps that file themselves. An
  ingest costs agent tokens, and a compiled wiki is expensive to build compared
  with retrieving from raw sources (one preregistered study measured about 100×
  the build cost, with better cross-document answers and worse single-fact
  lookup), so the guide keeps grep over `sources/` as the fallback for exact
  facts. Agents can still write a bad page; the history is the recovery path, as
  before.
- **Why it wins.** It is the only option that makes knowledge compound while
  staying files a person can read, edit and back up.

## Decision

**A collection is a wiki: a `README.md` schema, kept `sources/` and edited
`pages/`. Material becomes a source; the person's agent compiles sources into
pages when asked. Pages link by slug, cite their sources in frontmatter, and
are checked mechanically by Coffer on every read. The catalogue stays
generated, the git history stays the log, and judgement stays the agent's.**

Rules a future change must respect:

- **Sources are kept and immutable.** An upload is kept as its converted
  Markdown only; the uploaded file is not stored. No agent instruction may tell an agent to edit a
  source, except to mark one `ingest: skipped` when it holds nothing worth a
  page.
- **A page's identity is its slug.** File names are slugs; a page's `aliases`
  are extra names a link may use; a link names a slug or an alias, never a path.
  A slug two pages share is a finding, not something Coffer resolves.
- **What waits is derived, never recorded.** A source waits while no page cites
  it and it is not marked skipped. There is no ingest manifest.
- **Coffer's checks are mechanical and read-only.** Coffer computes findings on
  read and fixes nothing; the agent's Check reports and edits nothing.
- **Coffer moves a file only to keep the layout.** The sweep files a Markdown
  document left outside `pages/` and `sources/` into `pages/` at the same
  relative path, so older collections and agents writing to the wrong place
  converge, as one commit. It rewrites no content.
- **Everything else in [Knowledge Is a Directory of Markdown Files](knowledge-is-plain-files.md)
  stands**: no derived store, no knowledge tool, one undivided store served to
  every agent, nothing pushed into a session.

## Consequences

- The earlier decision's rule "no document may name another knowledge file"
  becomes "a page links by slug, never by path"; its "no directory carries
  meaning" is reversed for `sources/` and `pages/`. Its "no kept originals"
  stands: a source is the converted Markdown alone.
- Tidy now means: compile the waiting sources into pages, then tidy the pages.
  A second hand-off, Check, asks the agent for a report only.
- The web UI shows a collection as pages and sources, flags a waiting source and
  a dead link, lists the collection's change log, and shows a page's history in
  a drawer beside the page rather than on a tab that replaces it.
- A page's author can still be a person in their editor: frontmatter is
  advisory, and a page with no sources is a finding, not an error.
- Enforcement: spec knowledge "Keep sources and pages apart in each collection",
  "Keep every upload as a Markdown source", "Link pages by slug and
  check every link", "Check a collection mechanically on every read", "Hand a
  check to the agent".
