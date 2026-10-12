# Knowledge Is a Wiki of Pages Compiled From Kept Sources

**Status**: Accepted
**Date**: 2026-10-12
**Deciders**: Yuxing Wu
<<<<<<< HEAD
**Related**: [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md) (amended by this decision); [Tidying Knowledge Is the Agent's Job, One Hand-Off Recorded as One Change](tidying-knowledge-is-the-agents-job.md); [Knowledge Stays Current Through Flags Coffer Computes and an Agent Clears](knowledge-stays-current-through-flags-coffer-computes.md); [Coffer Ships Its Own Manual as a Skill Resource](coffer-ships-its-own-skill.md); [Knowledge Sources Keep Their Images; Originals Stay on This Mac](knowledge-sources-keep-their-images-and-originals-stay-on-this-mac.md); [Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md); research notes [knowledge curation](../research/knowledge-curation.md) and [knowledge structures](../research/knowledge-structures.md); spec knowledge; OpenSpec change `restructure-knowledge-as-a-wiki`
=======
**Related**: [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md) (amended by this decision); [Tidying Knowledge Is the Agent's Job, One Hand-Off Recorded as One Change](tidying-knowledge-is-the-agents-job.md); [Knowledge Stays Current Through Flags Coffer Computes and an Agent Clears](knowledge-stays-current-through-flags-coffer-computes.md); [Coffer Ships Its Own Manual as a Skill Resource](coffer-ships-its-own-skill.md); [Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md); research notes [knowledge curation](../research/knowledge-curation.md) and [knowledge structures](../research/knowledge-structures.md); spec knowledge; OpenSpec change `restructure-knowledge-as-a-wiki`
>>>>>>> origin/claude/project-thread-6qp5yc

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
├── README.md     the schema: what the collection is for, its page types, its rules, verify_after_days
├── sources/      kept material: each upload's converted Markdown
├── assets/       the pictures taken out of uploads, one folder per upload
└── pages/        the wiki: pages people and agents both edit, linked by [[slug]]
```

- **Sources are kept and do not change.** An upload, or a file dropped into
  `.inbox/`, becomes a source: its converted Markdown with frontmatter, plus
  the pictures taken out of it under `assets/`, linked from the source by
  relative path. The uploaded file itself is not put in the collection: it is
  kept on the Mac that uploaded it only, so the sync repository carries no
  large binaries ([Knowledge Sources Keep Their Images; Originals Stay on This Mac](knowledge-sources-keep-their-images-and-originals-stay-on-this-mac.md)). Agents read sources and never edit them.
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
  frontmatter or sources, sources still waiting, pages citing a superseded
  source, pages due a recheck) on every read. Judgement
  (contradictions, stale statements, duplicated subjects, subjects with no page)
  is the agent's, inside the one **Tidy** hand-off, whose prompt carries the
  mechanical findings: the agent fixes what is certain and reports what needs
  the person's decision
  ([Tidying Knowledge Is the Agent's Job, One Hand-Off Recorded as One Change](tidying-knowledge-is-the-agents-job.md)).

- **Pros.** Closes all three gaps with plain files: pages accumulate, every page
  traces back to kept sources, and pages relate through links that are checked.
  Keeps every constraint of the earlier decision: no derived store, no
  retrieval tool, no model run by Coffer, one undivided store, pull not push.
- **Cons.** A bad conversion can be checked against the uploaded file only on
  the Mac that uploaded it, the one place the original is kept. An
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
<<<<<<< HEAD
  Markdown, with its pictures beside it under `assets/`; the uploaded file is
  never stored in the collection, only on the Mac that uploaded it, which the
  source names in `original` ([Knowledge Sources Keep Their Images; Originals Stay on This Mac](knowledge-sources-keep-their-images-and-originals-stay-on-this-mac.md)). No agent instruction may tell an agent to edit a
  source, except to add the few keys that describe it rather than change it:
  `ingest: skipped` when it holds nothing worth a page, `superseded_by` when a
  newer source replaces it, and a `summary` of what it says; `original` and
  `original_sha256` are Coffer's and stay as written
=======
  Markdown only; the uploaded file is not stored. No agent instruction may tell an agent to edit a
  source, except to add the few keys that describe it rather than change it:
  `ingest: skipped` when it holds nothing worth a page, `superseded_by` when a
  newer source replaces it, and a `summary` of what it says
>>>>>>> origin/claude/project-thread-6qp5yc
  ([Knowledge Stays Current Through Flags Coffer Computes and an Agent Clears](knowledge-stays-current-through-flags-coffer-computes.md)).
- **A page's identity is its slug.** File names are slugs; a page's `aliases`
  are extra names a link may use; a link names a slug or an alias, never a path.
  A slug two pages share is a finding, not something Coffer resolves.
- **What waits is derived, never recorded.** A source waits while no page cites
  it and it is marked neither skipped nor superseded. There is no ingest
  manifest.
- **Coffer's checks are mechanical and read-only.** Coffer computes findings on
  read and fixes nothing; fixing them is the agent's, when the person presses
  Tidy.
- **Coffer moves a file only to keep the layout.** The sweep files a Markdown
  document left outside `pages/`, `sources/` and `assets/` into `pages/` at the same
  relative path, so older collections and agents writing to the wrong place
  converge, as one commit. It rewrites no content.
- **Everything else in [Knowledge Is a Directory of Markdown Files](knowledge-is-plain-files.md)
  stands**: no derived store, no knowledge tool, one undivided store served to
  every agent, nothing pushed into a session.

## Opening a Collection in Obsidian, and Recording When a Page Was Checked

The layout above happens to be what Obsidian reads natively: a folder of plain
Markdown, `[[slug]]` links that resolve by file name, and `aliases` frontmatter.
People who already keep notes in Obsidian asked to browse and edit collections
there. Three options were weighed:

- **Make collections Obsidian-compatible and offer Open in Obsidian (chosen).**
  A collection folder, or the knowledge root, opens as an Obsidian vault with
  nothing converted. Coffer already ignores hidden entries, so Obsidian's
  `.obsidian/` folder is neither committed, catalogued nor synced. The web UI
  offers **Open in Obsidian** in a collection's and a file's ⋯ menu only when
  the daemon detects Obsidian on this Mac, so a person who does not use it never
  sees the word. Pros: no new storage, no new code path for edits — an
  Obsidian save is an edit on disk like any editor's — and the person keeps
  Coffer's history, sync, check and Tidy. Cons: a Markdown file Obsidian
  creates outside `pages/`, `sources/` and `assets/` is filed into `pages/` by the sweep
  within a minute, so people should point Obsidian's default location for new
  notes at the collection's `pages/` folder.
- **Replace the knowledge UI with Obsidian.** Pros: a mature editor, graph view
  and plugins for free. Cons: Obsidian knows nothing of sources that wait, the
  mechanical findings, Tidy or a tidy's report and undo, and it is not
  installed for most people; Coffer's own page is still needed. Lost for that
  reason.
- **Link external folders (an existing Obsidian vault) as collections, for
  now.** Pros: a person's notes stay where they are. Cons: an external folder
  is outside the vault, so it has no history, no sync and no undo, and its own
  conventions would need a second, looser rule set for Tidy and the check.
  Deferred: it is a separate decision with its own trade-offs, and opening
  Coffer's collections in Obsidian covers the browsing and editing that was
  asked for.

A page may also carry **`verified: YYYY-MM-DD`**, when it was last checked
against its sources or the code; a page's read returns it and the reader shows
it. The guide tells agents that where a page's facts came from belongs in
`sources` and `verified`, never in a paragraph of the body listing what was
read: provenance in the body is organisation by provenance, which rule 3 of
writing a page forbids, and a date in frontmatter is something a person or a
later check can compare without reading the page. Coffer compares it: a page
whose `verified` is missing or older than the collection's `verify_after_days`
(90 by default) is a `stale_page` finding, which a tidy clears by rechecking
the page
([Knowledge Stays Current Through Flags Coffer Computes and an Agent Clears](knowledge-stays-current-through-flags-coffer-computes.md)).

## Consequences

- The earlier decision's rule "no document may name another knowledge file"
  becomes "a page links by slug, never by path"; its "no directory carries
  meaning" is reversed for `sources/`, `pages/` and `assets/`. Its "no kept
  originals" holds for the vault: a source is the converted Markdown and its
  pictures, and the uploaded file stays on the Mac that uploaded it
  ([Knowledge Sources Keep Their Images; Originals Stay on This Mac](knowledge-sources-keep-their-images-and-originals-stay-on-this-mac.md)).
- Tidy means: compile the waiting sources into pages, fix the mechanical
  findings, recheck the pages due a recheck, then tidy the pages, reporting
  what is left for the person and the gaps it found.
- The web UI shows a collection as pages and sources, flags a waiting source and
  a dead link, lists the collection's change log, and shows a page's history in
  a drawer beside the page rather than on a tab that replaces it.
- A page's author can still be a person in their editor: frontmatter is
  advisory, and a page with no sources is a finding, not an error.
- Enforcement: spec knowledge "Keep sources and pages apart in each collection",
  "Keep every upload as a Markdown source", "Keep the pictures of an upload
  beside its source", "Keep an upload's original on this Mac only", "Link
  pages by slug and check every link", "Check a collection mechanically on every read", "Hand a
  tidy to the agent", "Open a collection in Obsidian when it is installed".
