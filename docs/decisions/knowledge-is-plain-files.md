# Knowledge Is a Directory of Markdown Files, Not an Index

**Status**: Accepted
**Date**: 2026-09-23
**Deciders**: Yuxing Wu
**Related**: spec knowledge; [Knowledge Curation Merges New Material Into the Documents](knowledge-curation.md); [Coffer Ships Its Own Manual as a Skill Resource](coffer-ships-its-own-skill.md); [Per-Agent Resource Scope](per-agent-resource-scope.md); [Aggregate the Agents' Memory; Never Write It](aggregate-agent-memory-never-write-it.md); [Experimental Features Instead of a Release Branch](experimental-features-instead-of-a-release-branch.md); research note [knowledge curation](../research/knowledge-curation.md); PRs #368, #382, #404, #405, #418

## Context

A developer who runs more than one coding agent over the same work writes the
same durable facts down more than once — "the account service's staging DSN
lives in X", "we squash-merge" — once per agent, in each agent's own memory,
and the copies drift. Coffer's knowledge layer exists to hold those facts once,
for every agent, in a form a person can also read and correct. Three questions
decide its shape: how the facts are stored, how an agent finds them, and
whether each agent gets its own view.

The layer was first built as a retrieval system: eleven tables, an FTS5 keyword
index and a sqlite-vec vector index fused by reciprocal rank, a configurable
embedder, two storage lanes, three kinds of scope and six MCP tools. Before
that it had been a vendored stack — LlamaIndex for documents, mem0 for memory,
chroma as mem0's vector store. Two audits of the maintainer's live vault
decided what replaced both.

The 2026-09-12 audit found almost none of the index had ever executed:
`embedding_config` was an empty table, `.history/` did not exist on disk, 50 of
50 documents were `converter: passthrough`, and every knowledge tool call in a
month fell on the single day an agent built the corpus. The index was removed
(PR #368), a ranked search was restored the same day and removed again with all
embeddings two days later (PR #382).

The 2026-09-17 audit asked whether removing the index had been enough, and
measured something worse than "literal matching misses":

| Measured over 448 Claude Code sessions since the corpus was built | |
| --- | --- |
| Sessions that loaded the delivered knowledge skill | **0** |
| Sessions that called any `coffer__` knowledge tool | **0** |
| Sessions that loaded *any* of the 20 delivered `coffer-*` skills | 1 |
| Broken `*.md` cross-references inside the corpus itself | **343 of 398 (86%)** |

The retrieval question had never come up: nothing reached the tools at all.
The skill's description named the layer ("a fact about THIS user's working
environment") rather than the corpus's subjects, so a model working on a
`session` service had nothing to match. Meanwhile every agent Coffer drives —
Claude Code and Codex — already has `Read` and `Grep`, which need no
remembering. And the corpus's only navigation aid, a hand-written index,
pointed at 33 file names a migration had renamed out from under it: a
hand-maintained map of paths rots.

## Options Considered

### Option A — A tree of Markdown files, read with the agent's own tools, and a generated catalogue (chosen)

`~/.coffer/knowledge/<collection>/` holds Markdown documents with YAML
frontmatter (`title`, `description`, `actor`, timestamps), nested however
whoever filed them chose. The path is the identity; there is no id field and
no id-to-path table. There is no derived store of any kind. An agent reads
documents with its own `Read` and `Grep` at absolute paths; what tells it which
paths exist is a catalogue — every enabled collection's documents with path,
title and description — rendered into Coffer's own `coffer-guide` skill, whose
frontmatter description names the subjects the collections cover (drawn from
each collection's `README.md`). The only knowledge tool is `coffer__write`,
which submits new material.

- **Pros.** Nothing to keep level with the disk: a person's edit in their own
  editor is live on the next read. Retrieval uses the tools the agent uses all
  day, so the one step that failed in the audit — remembering to call a Coffer
  tool — is gone. The catalogue is generated, so it cannot rot the way the
  hand-written index did. The files are what a person backs up, syncs and reads.
- **Cons.** No ranking and no paraphrase matching: a query in the caller's own
  words does not find what a distinctive phrase would. The catalogue has a
  ceiling — roughly 40 tokens an entry, about 5.2K tokens for 58 documents when
  measured — so a corpus of thousands of documents would not fit. Losing the
  read tools loses `mcp_invocations` as a record of use; the agents' own
  transcripts, which Coffer already reads, are the replacement measurement.
- **Why it wins.** It is the only option that answers the measured failure.
  Every retrieval option argues about *how* an agent searches; the audit showed
  agents never searched. The catalogue changes what the agent is shown, not
  which tool it is asked to remember.

### Option B — FTS5 keyword index plus sqlite-vec vectors in SQLite

What was built: files as truth, with a keyword and a vector index as
rebuildable sidecars, fused by reciprocal rank, behind `coffer__search`.

- **Pros.** Ranked results, paraphrase matching through embeddings, chunk-level
  granularity.
- **Cons.** Eleven tables and an embedder to configure, a reindex path, and an
  index that can diverge from the files. FTS5 alone buys BM25 ordering and chunk
  granularity — the two things an agent reading whole files does for itself — at
  the worst ratio of cost to capability.
- **Why it lost.** It never ran: the embedding table was empty and the tools
  were not called. An index over a design that is still moving is exactly what
  the audit found unused (PR #368, PR #382).

### Option C — A vendored engine (LlamaIndex, mem0, chroma)

The original stack.

- **Pros.** Retrieval, chunking and embedding adapters off the shelf.
- **Cons.** Every one of these libraries wants to own a derived store.
  LlamaIndex persists an index and insists on owning it, so the index can
  diverge from the Markdown and then nothing is authoritative to back up or
  rebuild from. mem0 calls an LLM at write time — its default
  `llm_provider="none"` made `add_memory` answer 503 out of the box — and it
  dual-wrote fact text to chroma *and* SQLite, which is the dual-source-of-truth
  bug itself. chroma is a second embedded datastore.
- **Why it lost.** Owning a derived store is structurally incompatible with the
  files being the only copy. The ban is therefore enforced, not remembered: the
  import-linter contract "Dropped engines banned everywhere" in
  `backend/pyproject.toml` forbids `coffer.domain`, `coffer.application`,
  `coffer.infrastructure` and `coffer.surfaces` from importing `llama_index`,
  `mem0`, `chromadb`, `sentence_transformers`, `sqlite_vec` or `fastembed` (its
  name lists only the first four; it bans all six). An import of one is a
  mistake, not a design choice, which is why the contract is repo-wide.

### Option D — Literal search tools (`coffer__list`, `coffer__grep`, `coffer__read`, `coffer__search`)

The step between B and A: no index, but Coffer-hosted tools that grep and read
the tree for the agent.

- **Pros.** An invocation record for every read; one place to add ranking later.
- **Cons.** The agent must remember to call them, and 448 sessions showed it
  does not. They duplicate `Read` and `Grep`, which the agent already has.
- **Why it lost.** A tool an agent does not remember to call is not retrieval.
  The literal matcher survives in exactly one place — curation's candidate
  selection, reachable by nothing outside the process (see
  [Knowledge Curation](knowledge-curation.md)).

### Option E — Lanes inside a collection

Two designs were shipped and withdrawn: `notes/` ÷ `docs/` (agent-written
versus person-written, PR #336), and later `sources/` ÷ `topics/` (people and
uploads write sources; only curation writes topics, which agents read).

- **Pros.** A lane nothing rewrites makes unattended rewriting safe: the
  derived lane can always be regenerated from a pristine source.
- **Cons.** It takes the documents away from the person. A correction had to be
  filed as a new source and wait for a pass, instead of being made where the
  mistake was. An upload landed twice — original and extracted text — and
  stayed as a file forever, so the lane people browsed became a pile of
  carriers rather than knowledge. Callers had to decide which lane a fact
  belonged in.
- **Why it lost.** The user's own statement of the product (2026-09-23,
  PR #418): knowledge is co-created by AI and people; an upload is parsed to
  Markdown and from then on both edit it; each upload appends its new knowledge
  to the knowledge base. One tree with every writer is that sentence; lanes
  contradict it. How curation stays safe without a pristine lane is
  [Knowledge Curation](knowledge-curation.md)'s decision.

### Option F — A store or a view per agent

A silo per agent; or one store with the resource framework's per-agent scope,
so each agent is served a subset; or one store with a separate rendered skill
copy per agent.

- **Pros.** Per-agent non-disclosure; a fact meant for one agent stays there.
- **Cons.** A silo per agent is the drift this layer exists to remove. A
  per-agent view never chose anything in practice: on the live vault no
  collection had ever carried a scope (PR #404), and it could not have
  narrowed anything, because the skill it narrowed hands the agent the absolute
  knowledge root and tells it to read files — any process with shell tools can
  open any file under it. Per-agent skill copies were a second delivery
  mechanism beside the skill kind's own.
- **Why it lost.** A fact about a project is about the project, not the agent.
  One undivided store with one agent-agnostic surface means adding an agent
  adds no knowledge-layer code at all, and an agent never has to classify a fact
  before it can find it. Scope was withdrawn from this kind; the
  framework-wide rule is in [Per-Agent Resource Scope](per-agent-resource-scope.md),
  and the single shared skill in [Coffer Ships Its Own Skill](coffer-ships-its-own-skill.md).

### Option G — Project the store into each agent's native files

Write the facts into `CLAUDE.md`, `AGENTS.md` or each agent's memory directory,
so they load ambiently without the agent reaching for anything.

- **Pros.** Ambient loading, which a catalogue in a skill body is not.
- **Cons.** Writing another tool's files is intrusive and illegible, collapses
  the boundary between agent configuration and knowledge, and owes a
  hand-maintained adapter per agent for a format that moves upstream.
- **Why it lost.** It was built, as native projection, and removed; the
  prohibition is argued in full in
  [Aggregate the Agents' Memory; Never Write It](aggregate-agent-memory-never-write-it.md).
  This layer pushes nothing into a session.

### Option H — Semantic retrieval as a disposable sidecar

Embeddings and ranking over the files, held outside the vault, rebuildable at
any time, with literal matching as the fallback while the index is missing.

- **Pros.** Recovers the one real loss of Option A: a query in the caller's own
  words finding what a distinctive phrase would.
- **Cons.** It is an index, so it needs a settled design to index; the
  knowledge design moved four times in two weeks.
- **Status.** Not rejected — deferred. The 2026-09-14 removal recorded a real
  loss, and it lost to the unsettled design under it, not to the idea. It is
  expected to return once the design settles, under this ADR's constraints:
  the files stay the only truth, and the index is a sidecar that can be deleted
  and rebuilt. It would re-enter through the knowledge spec as a new
  requirement.

## Decision

**A collection is one tree of Markdown documents under
`~/.coffer/knowledge/<collection>/`, and the files are the only copy. There is
no derived index of any kind. An agent reads the documents with its own file
tools, at the paths a generated catalogue in the `coffer-guide` skill gives it.
There is one store, served whole to every agent.**

Rules a future change must respect:

- **No derived store.** No vectors, no FTS5, no sidecar, no chunking, no
  reindex, no cache — every answer is read off disk. No table in `coffer.db`
  beyond the collection's row in the kind-agnostic `resources` table. Engines
  that own a derived store stay banned by the import-linter contract.
- **Path is identity; frontmatter is metadata.** A collection describes itself
  in its own `README.md`, which is not a document and is not curated.
- **One tool.** `coffer__write` is the only built-in knowledge tool; there is no
  `list`, `grep`, `read`, `search` or `delete`. Deleting a document is a
  person's action on the REST, CLI and web surfaces.
- **The catalogue is generated and delivered as a skill.** This layer renders
  the text; the skill kind writes, registers and delivers it.
- **One undivided store.** A collection carries no per-agent reach: every
  enabled collection is named in the one rendered skill, a disabled one in
  none. `enabled` is the collection's only gate; above it, the `knowledge`
  experimental feature (off by default on the stable channel) closes the whole
  layer — its routes, `coffer__write`, the catalogue in the skill and the
  curation sweep.
- **Pull, never push.** Nothing in this layer writes into a session or into an
  agent's own files.

## Consequences

- **The agent stops guessing.** It never has to name a collection, guess a
  phrase or remember a tool: the catalogue is in front of it with absolute
  paths, and the tools it reads with are the ones it uses all day.
- **A person's correction is live immediately.** Direct edits in the tree are a
  complete way to change knowledge; no import or registration step exists.
- **Adding an agent costs this layer nothing.** The surface is one write tool
  and plain files.
- **`enabled` is non-disclosure, not access control.** An agent with shell tools
  can read any file under the knowledge root; a disabled collection is one no
  skill names, not one no process can open. The surfaces say so rather than
  implying a boundary.
- **Keeping the corpus organised becomes someone's job.** Duplication, drift
  and contradictions across documents are not prevented by a lane; they are
  resolved by curation, which rewrites the only copy under the rules in
  [Knowledge Curation](knowledge-curation.md).
- **A ceiling exists.** Hundreds of documents fit the catalogue comfortably.
  Past that the answer is Option H built for the need, not a return to FTS5.
- **Semantic retrieval is a placeholder, not a verdict.** Nothing here is to be
  read as "we decided against semantic search"; the constraint on its return is
  that it is a disposable sidecar over files that remain the truth.
- **Enforcement.** `backend/pyproject.toml` import-linter contracts (the
  dropped-engines ban; `markitdown` confined to the knowledge converters and the
  channel's document extraction); path construction and the traversal guard in
  `backend/coffer/infrastructure/knowledge/paths.py`;
  spec knowledge "Store each collection as one tree of Markdown files",
  spec knowledge "Expose exactly one knowledge tool",
  spec knowledge "Gate collections with enabled alone",
  spec knowledge "Carry no vector or embedding dependency".
