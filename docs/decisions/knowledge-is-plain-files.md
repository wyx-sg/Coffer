# The knowledge layer is a directory of files, not an index

**Status**: Accepted
**Date**: 2026-09-12 (revised 2026-09-14, 2026-09-17, 2026-09-18 and 2026-09-23; see Revision history)
**Deciders**: Yuxing Wu
**Supersedes**: [Retrieval Stack — Markdown Files as Truth, SQLite FTS5 + sqlite-vec](files-as-truth-sqlite-retrieval.md)
**Related**: spec [knowledge](../../openspec/specs/knowledge/spec.md); [Everything Is a Resource Kind](everything-is-a-resource-kind.md) and [Per-Agent Resource Scope](per-agent-resource-scope.md), both of which survive; [Aggregate Agent Memory](aggregate-agent-memory-never-write-it.md); [Cross-Platform Skill Delivery](cross-platform-skill-delivery.md)

## Context

This layer was built as a retrieval system: eleven tables, two storage lanes,
three kinds of scope, four retrieval modes over FTS5 and sqlite-vec, and six MCP
tools. A 2026-09-12 audit found almost none of it had ever executed —
`embedding_config` was an empty table, `.history/` did not exist on disk, 50 of
50 documents were `converter: passthrough`, and every knowledge tool call in a
month landed on the single day an agent built the corpus. The index went.

A second audit, on 2026-09-17, asked whether removing the index had been enough.
It had not, and it measured something worse than "literal matching misses".

| Measured over 448 Claude Code sessions since the corpus was built | |
| --- | --- |
| Sessions that loaded the delivered `coffer-knowledge` skill | **0** |
| Sessions that called any `coffer__` knowledge tool | **0** |
| Sessions that loaded *any* of the 20 delivered `coffer-*` skills | 1 |
| Broken `*.md` cross-references inside the corpus itself | **343 of 398 (86%)** |

So the retrieval question had never come up. Nothing reached the tools at all,
and the only navigational aid in the corpus — a hand-written index the user
maintained — pointed at 33 file names that migration 0066 had renamed out from
under it, while still instructing readers to use a `scope` argument deleted two
days later. Three things follow.

**A tool an agent does not remember to call is not retrieval.** The 2026-09-12
decision hoped a delivered skill would prompt the reach that tool descriptions
had not. It did not: the skill's description named the layer ("a fact about THIS
user's working environment") rather than the corpus's subjects, so a model
working on a `session` service had nothing to match against. Meanwhile every
agent Coffer supports already has `Read` and `Grep`, which need no remembering.

**A hand-maintained map of generated paths rots.** Every one of the 343 broken
references was a file name written into prose, invalidated by a rename the
prose never saw. The corpus cannot hold its own map.

**"The files are the sole truth" was blocking the fix.** With every file
authoritative, nothing may rewrite one without risking the only copy — which is
why the tidy pass shipped off by default and ran once. A layer that cannot
reorganise itself accumulates exactly the duplication and drift it was supposed
to survive.

**And splitting the writers apart was the wrong fix for that.** The 2026-09-17
revision answered the previous point with two lanes: `sources/`, which people
wrote and nothing rewrote, and `topics/`, which a model derived from them and
agents read. It made curation safe by making it untouchable — and in doing so
took the documents away from the person. They could no longer correct a
document; a correction had to be filed as a new source and wait for a pass. An
upload landed twice, as its original and its extracted text, and stayed in the
tree as a file forever, so the collection grew by one file per arrival and the
lane people browsed was a pile of carriers rather than knowledge. On 2026-09-23
the user named what was wrong with it: *knowledge is co-created by AI and
people. Source files arrive in different formats; an upload is parsed into
Markdown, and from then on AI and people edit it together. Each upload appends
the new knowledge in the file to the knowledge base.*

## Decision

**A collection is one tree of Markdown documents that a person and Coffer's
internal model write together. New knowledge arrives as material in a hidden
inbox, and a curation pass merges what is new in it into the documents. An
agent reads the documents with its own tools. There is still no derived
index.**

- **One tree, every writer.** `~/.coffer/knowledge/<collection>/` holds
  documents, nested however whoever filed them chose. No directory says who may
  write where: a person edits, adds and deletes documents in their own editor;
  an agent may edit one with its own file tools; the curation pass writes and
  retires them. The 2026-09-12 refusal of lanes stands, and now covers
  `sources/` ÷ `topics/` too — there is no `notes/` ÷ `docs/`, no `global` ÷
  `project-<ULID>`, no cwd-derived scope, no auto-provisioning.
- **New knowledge is material, and material is merged.** Every entrance Coffer
  serves — `coffer__write`, the CLI's `write`, an upload, a channel's `/save`
  — submits into the collection's hidden `.inbox/`. A pass folds each item into
  whichever documents own its subject and deletes it. An upload is parsed to
  Markdown and submitted like any other material; **neither the original nor
  the extracted text is kept** — the document was the carrier of its knowledge,
  and once the knowledge is merged the carrier has nothing left to say. The
  inbox is the one hidden directory Coffer writes, and nothing lists it.
- **A person's edit is the truth, and curation carries it.** The sweep runs
  every minute: first it drains the inbox, then it takes every document whose
  modification time is newer than the `coffer_curated_at` stamp Coffer writes
  into its frontmatter — a document a person or an agent edited out of band.
  That pass carries the edit into the rest of the collection — correcting the
  other documents that said otherwise — and is instructed never to revert or
  reword what the person wrote. Where new material contradicts a document, the
  newer statement wins and the superseded one stays legible as a dated
  correction.
- **No model, no waiting.** With no internal model configured, material
  becomes a document of its own on arrival, as it stands; a pass promotes
  whatever is already in the inbox the same way. Merging is the model's job,
  but knowledge sitting in a hidden directory for a connection nobody set up is
  knowledge no agent can read.
- **Curation is bounded, not fenced.** One pass sees one item in full, at most
  five candidate documents in full, and the collection's whole catalogue of
  titles and descriptions. Its tools — `list_documents`, `read_document`,
  `write_document`, `retire_document` — reach this collection's documents and
  nothing else: not the inbox, not the README, not another collection. It may
  make at most eight writes. It defaults **on**, because it is how submitted
  material becomes part of what an agent reads.
- **A document may not name another file.** Enforced at the write, not asked
  for in a prompt, because this is what produced 343 broken links. A document
  names its subject; the catalogue resolves subjects to paths, and the
  catalogue is generated.
- **One tool: `coffer__write`.** `list`, `grep`, `read`, `search` and `delete`
  are removed. Retrieval is the agent's own `Read` and `Grep` against an
  absolute path. `write` survives because submitting is where an agent
  genuinely needs Coffer — the collection, the frontmatter, the inbox and the
  audit entry are Coffer's to decide — and because it is the one place an
  invocation record still gets written. Deleting a document is a person's
  action on the human surfaces, for any document.
- **The skill is generated, and it carries the catalogue.** The catalogue is
  one section of Coffer's own `coffer-guide` skill, an ordinary `skill`
  Resource with one master folder, generated at every boot and re-rendered
  whenever the catalogue changes; this layer renders the text and nothing else
  (see [Coffer Ships Its Own Skill](coffer-ships-its-own-skill.md)). Its
  frontmatter description names the subjects of the enabled collections, drawn
  from their READMEs — the only part of this layer always in a model's context,
  so it must carry matchable specifics. Its body carries the knowledge root
  and, per collection, every document's path, title and description: roughly
  5.2K tokens for 58 documents, paid only when the model reaches for it.
- **`enabled` is the only gate.** A collection is one `knowledge` Resource with
  no per-agent reach: every enabled collection is named in the one rendered
  skill, a disabled one in none. It gates what an agent is told, not what a
  process can open.

**Removed:** `coffer__list`, `coffer__grep`, `coffer__read`, `coffer__search`,
`coffer__delete`, `coffer__list_skills`, `coffer__load_skill`; `.history/` and
`.raw/`; the `sources/` ÷ `topics/` lanes and the `coffer_ingested_at`
watermark; keeping an upload's original or its extracted text as a file; the
`tidy_owner_machine_id`/`auto_tidy_enabled` pair's default-off posture; the
per-agent reach and the per-agent skill copy.

**Kept:** no index of any kind — no vectors, no FTS5, no sidecar, no chunking,
no reindex; path as identity; frontmatter as metadata; a collection describing
itself in its own `README.md`; the `knowledge` Resource kind; no table in
`coffer.db`; and the rule that this layer pushes nothing into a session.

## Consequences

### Positive

- **The documents are the person's again.** A correction is made where the
  mistake is, in the person's own editor, and is live on the next read;
  curation then carries it to the other documents that repeated it.
- **The collection grows by integration, not accumulation.** Each upload adds
  what is new in it to the documents that already cover the subject, instead of
  adding a file — two files, before — that the next reader has to reconcile.
- **The corpus can still reorganise itself.** Duplication, drift and
  contradictions are something the layer resolves rather than accumulates.
- **The agent stops guessing.** It never has to name a collection, guess a
  phrase or remember a tool: the catalogue is in front of it, with absolute
  paths, and the tools it reads with are the ones it uses all day.
- **Broken internal links become structurally impossible.**

### Negative

- **Curation rewrites the only copy.** The 2026-09-17 design made unattended
  rewriting safe by keeping an untouched lane beside it; that lane is gone.
  What protects a document now is the rule that a person's edit is never
  reverted, the eight-write bound, one pass per collection, the audit event
  every pass records, and — where vault sync is configured — the git history of
  the vault. A bad merge is repaired by editing the document, not by re-running
  curation from a pristine source.
- **An upload's original is gone once it is submitted.** A bad conversion
  cannot be redone from a file Coffer kept; the person re-uploads from their own
  copy.
- **Material waits until a pass runs.** An agent cannot read what is in the
  inbox. The sweep's one-minute cadence and the no-model promotion keep the wait
  short, but it is a wait.
- **The migration re-distils the whole corpus.** Every file of both lanes is
  queued as material, topic documents first, and comes back in a machine's
  words one pass at a time; uploaded originals survive only in the backup taken
  first (`<root>.pre-0101.bak`).
- **Losing the tools loses the invocation record for reads.** `mcp_invocations`
  can no longer answer "is this layer being used". The replacement measurement
  is the agents' own transcripts, which Coffer already reads for other reasons
  and which are retroactive — so nothing is lost by not building it yet.

### Neutral

- **Delivery still happens at the agent's initiative.** Nothing is pushed into a
  session and no agent's memory is written. What changed is what prompts the
  reach, not who initiates it.
- **`enabled` is non-disclosure, not access control.** An agent holding shell
  tools can read any file under `~/.coffer/knowledge/`; a disabled collection is
  one no skill names, not one no process can open.

## Revision history

- **2026-09-12** — Initial decision: knowledge is a directory of Markdown files
  an agent greps and reads; no derived index, no lanes, no derived scope. Later
  the same day, document upload and a ranked `coffer__search` were restored on
  the grounds that the filesystem is unreachable from a phone and that spec
  `memory` needed ranking.
- **2026-09-14** — Ranked retrieval removed again, and every use of embeddings
  with it. `coffer__search` kept its name and became the literal tier that had
  been its fallback. Recorded as a deliberate reduction of something that
  worked, not a cleanup of dead code.
- **2026-09-17** — **Two lanes, curation, and no retrieval tools.** A
  collection became `sources/`, written by a person, an upload and
  `coffer__write`, and `topics/`, written only by a curation pass that agents
  read; an upload's original was kept visibly beside its extracted text, and a
  `coffer_ingested_at` stamp marked a source as consumed. The lanes were
  withdrawn on 2026-09-23; the retrieval tools stayed withdrawn. Prompted by the 448-session audit: the skill had never been
  loaded, no knowledge tool had ever been called from Claude Code, and 86% of
  the corpus's internal references were broken. The 2026-09-12 and 2026-09-14
  revisions were both arguments about *which* retrieval mechanism to expose;
  this one concludes the layer should expose none, and spend its effort on
  what the agent is told instead. Files as truth narrows to **sources** as
  truth, which is what makes the curation this layer always needed safe to run.
- **2026-09-18** — **Per-agent reach withdrawn from the kind.** The 2026-09-17
  revision had moved authorization to the skill, delivered as a per-agent copy;
  this revision removes it.
  Measured on the maintainer's own vault: no collection had ever carried a
  scope, so the mechanism had never once narrowed anything — and it could not
  have, because the skill it narrows hands the agent the knowledge root and
  tells it to grep. Every enabled collection is now served to every agent, and
  `enabled` is the only gate the kind has. The independent per-agent skill
  **copy** was kept in that revision, on the grounds that it stops a delivery
  writing through a shared link; the next revision withdrew that too. See
  [Per-Agent Resource Scope](per-agent-resource-scope.md).
- **2026-09-18, later the same day** — **the generated skill leaves this layer.**
  Coffer's manual and this catalogue merge into one skill, `coffer-guide`, which
  is an ordinary `skill` Resource: one master folder, one row, delivered by the
  same predicate and the same links as any imported skill, and regenerated from
  the running build at every boot. This layer renders the text and no longer
  writes, delivers or reclaims anything. The per-agent copy goes with it — a
  master that is re-rendered in place, and a reclaim the skill kind already
  performs per agent, answer the two objections that kept it. What this decision
  still owns is unchanged: the files, the lanes (until 2026-09-23), curation,
  one tool, and no index. See [Coffer Ships Its Own Skill](coffer-ships-its-own-skill.md).
- **2026-09-23** — **One tree, co-created.** The two lanes collapse into one
  tree of documents that the person and curation both edit, and new knowledge
  arrives as material in a hidden `.inbox/` that curation merges in and then
  deletes. The user's reason, verbatim in substance: knowledge is co-created by
  AI and people; source files come in different formats, are parsed to
  Markdown on upload, and are then edited by AI and people together; each
  upload appends the new knowledge in the file to the knowledge base. So an
  upload keeps neither its original nor its extracted text, a person may edit
  or delete any document, and the sweep comes back for a document edited out of
  band — carrying the edit into the rest of the collection and never reverting
  it — tracked by a `coffer_curated_at` stamp that replaces
  `coffer_ingested_at`. With no internal model, material is promoted to a
  document as it stands rather than waiting. "Sources are truth; topics are
  derived" goes with the lanes: the rule that protected the person's writing
  by fencing curation out of it is replaced by one that lets both edit and
  forbids curation to undo the person. Migration 0101 backs the root up, queues
  every Markdown file of both lanes (topics first) in the inbox for the sweep to
  distil again, and drops the non-Markdown originals.
