# The knowledge layer is a directory of files, not an index

> 中文版: [knowledge-is-plain-files.zh.md](./knowledge-is-plain-files.zh.md)

**Status**: Accepted — twice revised (see Revision history). The 2026-09-12 revision reinstated document upload, conversion to Markdown with the original under `.raw/`, and ranked semantic retrieval with a sixth tool `coffer__search`. The 2026-09-14 revision removes the ranking again — `coffer__search` stays, as a literal search. Everything else below stands.
**Date**: 2026-09-12 (revised 2026-09-12 and 2026-09-14; see Revision history)
**Deciders**: Yuxing Wu
**Supersedes**: [Retrieval Stack — Markdown Files as Truth, SQLite FTS5 + sqlite-vec](files-as-truth-sqlite-retrieval.md), [Retrieval mode is an internal engine detail](retrieval-mode-is-internal.md)
**Related**: spec [knowledge](../../specs/knowledge/spec.md); [Everything Is a Resource Kind](everything-is-a-resource-kind.md) and [Per-Agent Resource Scope](per-agent-resource-scope.md), both of which survive; [Aggregate Agent Memory](aggregate-agent-memory-never-write-it.md)

## Context

The knowledge layer as built is ~10,800 lines of backend across three layers plus
its surfaces, backed by 11 database tables. It carries two storage lanes, three
kinds of scope, any-format ingestion through MarkItDown, four retrieval modes
over FTS5 and sqlite-vec fused by reciprocal rank, a periodic agentic tidy pass,
and six MCP tools.

An audit of the live installation on 2026-09-12 found how much of that is in use.

**Nothing retrieves it during ordinary work.** Across the entire invocation
history (506 rows, one month), every call to a knowledge tool — 13 `search`,
8 `write`, 8 `list`, 4 `read` — landed on **2026-09-11**, the single day an agent
was building the corpus. Not one call came from daily work before or since.
Meanwhile the same machine's Claude Code native memory holds 75 files for the
Coffer project alone, because that one is loaded into context automatically.

**Most of the machinery has never executed at all:**

| Capability | State on the live installation |
| --- | --- |
| Vector retrieval (sqlite-vec, embeddings, hybrid RRF, `embed_pending` retry) | `embedding_config` is an **empty table**; no scope has ever listed `vector` |
| Periodic tidy (FR-033–FR-035) | **Zero** knowledge audit events; `.history/` **does not exist** anywhere on disk |
| Any-format conversion (MarkItDown, csv converter) | **50 of 50** documents carry `converter: passthrough` and `source_format: md` |
| `.raw/` provenance lane | 50 files, **byte-identical** to their `docs/` counterparts |
| External source tracking (`check-sources`, `update-source`, `auto_update_sources`) | Zero invocations |
| `source_mode: converted \| edited` re-conversion lock | **50 of 50** are `converted`; the lock has never engaged |
| Scope display labels | `knowledge_scope_labels` is an **empty table** |
| Named collections | **Zero** created in three months |
| Per-project scopes | **14** project roots resolved, **1** holds content; 2 of the 4 provisioned scopes are empty shells left behind by a read-only search |

Two structural mistakes explain most of this.

**Properties were built as directories.** The `notes/` ÷ `docs/` lane claims to
separate what someone wrote from what someone uploaded, but the only difference
with any behaviour attached to it is whether a file's truth lives inside Coffer
or outside — and on the live installation nothing's does: all 50 documents are
Markdown an agent wrote, which merely entered through the file door. The
`global` ÷ `project-<ULID>` ÷ collection scope means to say "what is this
knowledge about", which is a property of the content. Both paid the full cost of
physical structure — migrations, empty shells, a split UI, cross-boundary fusion
at query time — to express something a line of frontmatter would carry. That
retrieval has to fuse across scopes by reciprocal rank to be useful at all is the
tell: the isolation was never the point.

**Without embeddings, an index buys only ranking.** The one capability an index
offers that ripgrep cannot is conceptual recall — matching a query for
*鉴权* against a document that says *认证*. That needs embeddings, and
embeddings were never configured. What FTS5 adds over ripgrep once they are gone
is BM25 ordering and chunk granularity, and an agent does both for itself: it
reads the matching lines and decides which file is relevant, then reads the whole
file anyway. Measured on the live corpus (51 files, 1.4 MB), a ripgrep query
returns the same answer set as FTS5 in **27 ms**, and needs no tokenizer to match
CJK. There is no good middle: either the full semantic stack, or no index. FTS5
alone is the worst ratio of cost to capability in that range.

The goal that decides the rest is the user's: **knowledge is managed by the
human and the agent together.** Anything only one of them can see is in the wrong
place.

## Decision

**Knowledge is a directory of Markdown files that an agent greps and reads.
There is no derived index and nothing to reconcile.**

- **Storage.** `~/.coffer/knowledge/<collection>/…` holds Markdown files with
  human-readable names. A file's YAML frontmatter carries `title`,
  `description`, `actor` (`agent` | `user`) and timestamps — metadata travels
  with the file, so the human sees it by opening the file and the agent finds it
  by grepping. There is no `id` field: the path is the identity.
- **Retrieval is a catalogue plus ripgrep.** `list` walks the tree one level at
  a time — with no argument it names every collection the caller may see, with a
  path it lists that level's subdirectories and files, each with the `title` and
  `description` from its frontmatter. `grep` matches literally or by regex,
  recursively; `read` returns a file. An agent descends the catalogue to choose
  *which file*, and greps to find *which line*. No modes, no ranking, no
  chunking, no `top_k`.
- **The catalogue is generated, never materialized.** It is produced by walking
  the directory and reading frontmatter at call time, so it cannot drift from
  what is on disk — there is no second copy to keep in sync. A materialized
  index file would reintroduce exactly the derived-artifact problem this
  decision removes; the previous design's `knowledge/INDEX.md` was deleted on
  2026-09-11 for being a by-product rather than content, and nothing here needs
  it back.
- **A collection describes itself in its `README.md`.** The catalogue's
  one-line description of a collection is the first paragraph of a `README.md`
  in that directory. It is a convention every human and every agent already
  reads, it keeps the description visible to the person browsing in Finder
  rather than buried in a database row, and it does not drift: a README says
  what the collection is for, never what files it contains.
- **A collection is the only boundary, and it exists to be authorized.** A
  top-level subdirectory is one `knowledge` Resource: the human creates it
  deliberately, and the Resource framework's per-agent scope decides which
  agents may see it. Nesting inside a collection is the human's own filing and
  carries no meaning for the system — ripgrep already recurses.
- **No boundary is derived.** Coffer does not resolve a scope from the agent's
  cwd, does not provision anything on read, and does not mint `project-<ULID>`
  names. An agent's reads span every collection it is authorized for; there is
  no rule that leaves a collection invisible by default.
- **Five tools, down from six.** `list`, `grep`, `read`, `write`, `delete`.
  `search` is gone: with no ranked index behind it, it would be a second name for
  `grep`, and the "is this search or grep?" question is the same guess the
  2026-09-10 merge removed one level up. `write` creates or replaces a file;
  `delete` removes one. A human adds knowledge by dropping a Markdown file into the
  directory — the filesystem is the upload surface, and the next grep sees it.
- **A delivered skill is how an agent learns the layer exists.** Coffer renders
  one skill describing the knowledge layer and delivers it through the skill
  channel it already runs (spec [skill-manager](../../specs/skill-manager/spec.md),
  [Cross-Platform Skill Delivery](cross-platform-skill-delivery.md)). The agent
  discovers it natively — its name and description sit in context, its body
  teaches the catalogue-then-grep motion — with no hook, no session injection
  and no write into any agent's memory files. This channel is known to work on
  the live installation: fifteen `coffer-*` skills are delivered and natively
  discovered today, while the tools' own descriptions have failed to trigger a
  single retrieval in a month. It is a hypothesis with evidence behind it, not a
  proven fix, and it is cheap to verify: the invocation log already records
  every knowledge call, so a week of ordinary work answers it.
- **Tidy survives, with its automation off by default.** A bounded agentic
  pass over a collection — driven by Coffer's internal model connection — merges
  duplicate notes and rewrites them into coherent documents, copying every prior
  revision into `.history/` first. Its tool surface is the same five tools, and
  with no index there is nothing to reconcile afterwards. It is always available
  by hand (a button, and `coffer knowledge organize`); the background worker that
  runs it on an interval is governed by one installation-wide setting, **off by
  default**, because an unattended rewriter of a jointly managed corpus should be
  something the human switches on rather than something they discover running.
  `.history/` is dot-prefixed, so ripgrep skips it and an archived revision never
  returns as a second hit.
- **The UI stays read-only.** It renders content and opens the file in the
  human's own editor ([Daemon Proxies File Actions](daemon-proxies-os-file-actions.md)).
  With no index, an external edit takes effect immediately with no reconciliation.

**Removed:** any-format conversion and the converter registry; the `.raw/`
lane; external source tracking (`check-sources`, `update-source`,
`auto_update_sources`, `source_path`, `source_sha256`); `source_mode` and the
re-conversion lock; the `notes/` ÷ `docs/` lane split and `documents.lane`;
cwd-derived scopes, auto-provisioning and `project-<ULID>` naming; FTS5,
sqlite-vec, hybrid RRF, `embed_pending` degradation retry, chunking, chunk
parameters, lazy reindex-on-read and explicit reindex; per-scope
retrieval/chunk/limit configuration; scope display labels.
Eleven tables go with them: `documents`, `chunks`, the six `documents_fts*`
tables, `embedding_config`, `knowledge_scope_labels`,
`knowledge_scope_project_roots`.

**Kept:** Markdown files as the sole truth; the `knowledge` Resource kind, now
one Resource per collection, for the sake of per-agent authorization; the tidy
pass and its `.history/` safety net; the read-only viewer and its open-in-editor
affordance.

## Consequences

### Positive

- An entire class of defect disappears. Index-versus-disk drift, content-hash
  reconciliation, and the three-way disagreement between `search`, `read` and
  `grep` about which scope they span (the cause of PR #358) cannot occur when
  there is no index.
- Human and agent genuinely share one artifact. The human's edit in their own
  editor is visible to the agent on the next grep with nothing in between, and
  every piece of metadata the agent writes is legible to the human in the file.
- The layer drops from ~10,800 lines to an estimated 1,500–2,500, and from
  eleven knowledge-specific tables to none: a collection is a row in the
  kind-agnostic `resources` table like every other Resource, and nothing else
  about knowledge lives in the database.
- Adding knowledge by hand costs one file copy, which is cheaper than any upload
  surface could be.
- Authorization becomes meaningful rather than incidental: a collection exists
  because someone drew that boundary, instead of because an agent happened to
  start in a git repository.

### Negative

- **Semantic matching moves from embeddings to the model, and inherits the
  model's limits — and a ceiling.** Nothing is embedded, so `grep` matches only
  literal text; what replaces conceptual recall is the agent reading the
  catalogue and judging which file is relevant, which it does better than a
  vector distance because it understands the intent behind the question. That
  works as long as the catalogue fits in context: at roughly 40 tokens an entry,
  fifty files are nothing and five hundred are comfortable, but five thousand are
  not. The layered catalogue defers the ceiling by letting an agent read one
  level at a time; past it, the answer is a real semantic stack, built for that
  need rather than re-enabling a component that was never switched on. The live
  corpus is 51 files.
- **Tidy rewrites a jointly managed artifact with no review step.** Nothing
  diffs the pass's output before it lands, so `.history/` is the entire safety
  net. Shipping it off by default keeps the human in the loop until they decide
  otherwise, but once the worker is on, an agent is editing the human's files
  unattended. This is the one place where joint management is asymmetric, and it
  is a deliberate trade for a corpus that would otherwise drift.
- **Ranking is the agent's problem.** A broad grep over a large corpus returns
  many matches and the agent must narrow it. The catalogue is what keeps this
  tractable, which puts real weight on file names and `description` lines.
- **Migration is destructive and one-way.** Titles live only in the database
  today, so every one must be written into a file name and into frontmatter
  *before* the tables are dropped; there is no second chance and no compatibility
  shim. The existing corpus lands as two collections — the 48 documents about
  Shopee's internal systems in `shopee`, which is also the set whose authorization
  actually matters, and the Coffer project's own four files in `coffer` — and the
  human re-files from there.

### Neutral

- **Per-agent authorization is a convention, not a security boundary.** An agent
  holding shell or file-read tools can read any file under `~/.coffer/knowledge/`
  directly. The scope prevents mistaken retrieval, not deliberate access. This
  was equally true of the scopes it replaces; real isolation would need a
  separate vault or filesystem permissions, and is out of scope here.
- **Delivery still happens at the agent's initiative.** Knowledge reaches a
  session only when the agent reaches for it
  ([Aggregate Agent Memory](aggregate-agent-memory-never-write-it.md)); the delivered
  skill changes what prompts that reach, not who initiates it. Nothing is pushed
  into a session and no agent's own memory is disabled or written to. Whether the
  skill is enough — the audit above shows tool descriptions were not — is the one
  open question this decision leaves, and the invocation log answers it without
  any new instrumentation.

## Revision history

- **2026-09-12** — Initial decision, as the body above records it: knowledge is a
  directory of Markdown files an agent greps and reads; no derived index, no
  conversion, no lanes, no derived scope, five tools.
- **2026-09-12, the same day** — **Three of the removals are reversed: document
  upload; conversion to Markdown with the original kept under `.raw/`; and ranked
  semantic retrieval, and with it a sixth MCP tool, `coffer__search`.** This is
  not a reversal of the reduction. Everything the reduction's argument actually
  turned on stays the live answer, and stays unqualified: **the path is the
  identity**, **frontmatter is the metadata**, **the files are the sole truth**,
  file names are readable slugs, there are **no lanes**, **no cwd-derived scope**
  and **no auto-provisioning**, and the eleven dropped tables stay dropped. What
  returns is an entrance and a ranking, for reasons the removal did not weigh.
  - **Ingestion returns because the filesystem is not reachable from where the
    user is.** "Put a Markdown file in the directory" is an entrance that exists
    only while the user is sitting at the machine — it remains a complete one,
    with no import and no registration. But their live entrance is a phone, and a
    channel already accepts a document and already extracts it for a turn (spec
    [channels](../../specs/channels/spec.md) FR-030); letting that document land
    in a collection instead of evaporating with the turn is the path this layer
    lacked. The Web upload is the same entrance's other end, which is why it is
    worth having back.
  - **Ranked retrieval returns because it is now a dependency, not a
    convenience.** The removal was right that an agent reading the catalogue buys
    most of what ranking would — for an agent that can afford to read the
    catalogue. Spec `memory` cannot: it must answer "what do I know that bears
    on *this* task" against material the caller has no exact words for, under a
    token budget that forbids handing over the catalogue at all. That is retrieval, and grep cannot be it. This ADR said as much
    itself — the first Negative consequence above names the ceiling and answers
    it with *a real semantic stack, built for that need rather than re-enabling a
    component that was never switched on*. The need arrived before the ceiling
    did; the answer is the one that bullet already gave.
  - **Two constraints keep the audited failure from recurring, and they are the
    heart of this revision.** The audit's root cause was not that an index is
    wrong but that this one was unconfigurable in practice, and that it was a
    second truth to reconcile. So: **(a)** embeddings ride the already-configured
    `internal_default` internal connection and get **no settings surface of their
    own** — no provider, model, endpoint or key belonging to this layer, and no
    page for them. `embedding_config` was an empty table because it asked the user
    to stand up a second provider, and asking a second time would earn the same
    empty table. **(b)** The index is a **disposable sidecar**: outside the vault
    and outside `coffer.db`, at one path the user may delete at any moment,
    excluded from every export and backup, with a literal-search fallback that
    must answer correctly while it is missing, empty or mid-rebuild. Nothing about
    it is a truth, so nothing about it can drift.
  - **Nothing is added to the dependency set for it.** No vector store and no
    embedding model — no `sqlite-vec`, no `fastembed`. Vectors come from the
    internal connection over the HTTP client the installation already has, and
    similarity is computed in-process, because the corpus this serves is hundreds
    of files and a native index for that is precisely the over-build the reduction
    was right about.
  - Spec [knowledge](../../specs/knowledge/spec.md) carries the detail: FR-025–
    FR-029 (ranked retrieval), FR-032–FR-037 (writing and ingestion), FR-080–
    FR-082 (constraints).
- **2026-09-14** — **Ranked retrieval is removed again, and with it every use of
  embeddings anywhere in Coffer.** `coffer__search` and `coffer__recall` keep
  their names and keep answering; what each returns is the tier that used to be
  their fallback, now the whole of them — ripgrep over the collections a caller
  may see for `search`, a case-insensitive substring scan over facts already in
  hand for `recall`. This is a deliberate reduction of a capability that was
  built and did work, not the cleanup of something unused, and it is recorded as
  such rather than folded back into the 2026-09-12 argument.
  - **What goes:** the kind-agnostic ranked-retrieval engine both tools shared,
    the disposable sidecar and the `~/.coffer/index` directory it lived in, the
    OpenAI-compatible `/embeddings` client, the section splitter and cosine
    ranker, the `GET /api/v1/knowledge/index` and `POST .../index/rebuild`
    routes with their `coffer knowledge index` / `reindex` CLI commands, and the
    `score` / `heading` / `mode` / `reason` fields every answer used to carry.
    The never-wired cosine alternative inside `coffer__search_tools` goes with
    them; that tool ranks by BM25, as it always did in practice.
  - **What the 2026-09-12 revision got right, and what it did not.** Its two
    constraints held: embeddings never got a settings surface, and the sidecar
    never became a truth — nothing drifted, and deleting it never lost anything.
    What did not hold is the premise underneath them. Ranking only ever ran for
    an installation that had designated an internal connection, so for most of
    this layer's life the literal path *was* the answer, and it was good enough
    that the difference did not argue for the machinery standing behind it.
  - **What this costs, stated plainly.** A query in the caller's own words no
    longer works: matching is literal, so a question finds nothing where a
    distinctive phrase finds the file. `coffer__recall` can no longer answer
    "what do I know that bears on *this*" for a caller with no exact words —
    the dependency spec `memory` had on ranking is not met any more, and
    FR-052 now asks for the scan rather than the loop. Embeddings may return;
    when they do it should be because that gap was felt, not because the
    component is available.
  - **No migration drops a table**, because none was left to drop: the
    `embedding_config` table went with revision 0066 and the index was never in
    `coffer.db`. Revision 0077 purges the `embedding_config_updated` audit rows
    whose event type no longer exists.
