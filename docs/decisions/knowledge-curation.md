# Knowledge Curation Merges New Material Into the Documents

**Status**: Accepted
**Date**: 2026-09-23
**Deciders**: Yuxing Wu
**Related**: spec knowledge; [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md); [One Owner Machine for Unattended Rewrites](single-owner-machine-for-unattended-rewrites.md); [Coffer's Model Is an Internal Engine](coffer-model-is-an-internal-engine.md); [Audit and Retention](audit-and-retention.md); research note [knowledge curation](../research/knowledge-curation.md); PR #418

## Context

[Knowledge Is Plain Files](knowledge-is-plain-files.md) makes each collection
one tree of Markdown documents that a person and Coffer both write, with the
files as the only copy. That leaves a question the tree itself cannot answer:
**what happens when new knowledge arrives?** It arrives from three entrances — an
agent writing a Markdown file into a collection's `.inbox/`, a document
uploaded on the Knowledge page, and a document sent to a channel and saved
with `/kb` — and from a fourth, unannounced one: a person or an agent editing
a document directly.

Three measured facts constrain the answer:

- **A corpus left to accumulate rots.** 343 of the 398 `*.md` cross-references
  in the maintainer's corpus (86%) were dead, each one a file name written into
  prose and invalidated by a rename the prose never saw.
- **A pass that may not rewrite anything does not run.** While every file was
  treated as untouchable truth, the tidy pass shipped off by default and ran
  once; a layer that cannot reorganise itself accumulates the duplication it
  was built to prevent.
- **Keeping a pristine copy took the documents away from the person.** The
  `sources/` ÷ `topics/` design made rewriting safe by keeping people's writing
  in a lane curation never touched — and so a person could no longer correct
  the document an agent read; a correction had to be filed as new material and
  wait. Each upload stayed in the tree twice, as original and extracted text.

The product statement that settled it (2026-09-23): knowledge is co-created by
AI and people; each upload appends the new knowledge in it to the knowledge
base.

## Options Considered

### Option A — An inbox merged by a fenced, bounded pass; the newer or better-evidenced statement wins (chosen)

Every entrance submits **material** into the collection's hidden `.inbox/`. A
pass driven by Coffer's internal model takes one item, folds what is new in it
into whichever documents own its subject, and deletes it. The same sweep also
picks up documents edited out of band and carries the edit into the rest of the
collection as a newer statement.

- **Pros.** The collection grows by integration rather than accumulation: an
  upload adds what is new to the documents that already cover the subject
  instead of adding a file. The person owns the documents again — a correction
  is made where the mistake is and is live on the next read. Duplication,
  drift and contradictions get resolved rather than piling up.
- **Cons.** It rewrites the only copy, unattended. Material waits until a pass
  runs, and no agent tool reads the inbox (a person can see it in the web UI). A bad merge is repaired by editing
  the document, not by re-running from a pristine source. An upload's original
  is not kept.
- **Why it wins.** It is the only option that lets both a person and a model
  edit one tree. What makes unattended rewriting tolerable is not a protected
  lane but a set of hard bounds (below) and the rule that no writer is exempt: the newer
  statement wins unless the older one is shown to be right.

### Option B — Keep the originals and index them (no rewriting)

Store each upload and each submission as its own file, never merge, and rely on
retrieval to find the relevant pieces.

- **Pros.** Nothing is ever rewritten; every original survives.
- **Cons.** The collection grows by one file per arrival, and the reader — an
  agent reading whole files — has to reconcile contradictions itself, every
  time. It needs an index to be navigable, which
  [Knowledge Is Plain Files](knowledge-is-plain-files.md) rejects.
- **Why it lost.** It is the accumulation that produced the rotted corpus.

### Option C — A pristine lane plus a derived lane

People and uploads write `sources/`; only curation writes `topics/`, which
agents read. Shipped and withdrawn.

- **Pros.** Curation can be re-run from untouched input; a bad merge is
  recoverable by construction.
- **Cons.** The person cannot edit the document an agent reads; uploads stay
  twice; callers classify which lane a fact belongs in.
- **Why it lost.** It made curation safe by making the documents the person's
  no longer. Replaced in PR #418.

### Option D — Append-only notes

Each arrival appends a dated section to a document chosen by name; nothing is
ever rewritten in place.

- **Pros.** No fact can be lost by a rewrite; history is visible inline.
- **Cons.** A superseded statement and its correction both stand, and the
  reader decides which is current. Documents grow into changelogs organised by
  provenance ("from the upload of …") rather than by subject.
- **Why it lost.** A reader wants the document to say what is true now. Option
  A keeps what an append log is good at — a superseded statement stays legible
  with the date it changed — as a sentence where the corrected fact is.

### Option E — An unfenced model rewrite

Hand the model the collection directory and a general file-editing toolset, and
let it reorganise as it sees fit.

- **Pros.** Maximum freedom to restructure; simplest to build.
- **Cons.** One piece of material can trigger a corpus-wide rewrite. Nothing
  stops the model from writing into the inbox, the README or another
  collection, or from naming files in prose, which is what produced the dead
  links.
- **Why it lost.** "Asked in the prompt" is not a bound. Every rule that
  matters is enforced by the tool handlers instead (below).

### Option F — Human-only curation

Coffer files material as documents and a person merges by hand.

- **Pros.** No unattended rewriting at all.
- **Cons.** It did not happen: the tidy pass that needed a person to switch it
  on ran once. Agents write faster than a person tidies.
- **Why it lost.** A corpus nobody tidies is the rotted one. An edit made outside a pass is
  still first-class input — curation carries it outward — but as a statement
  to weigh, not one to protect.

### Option G — Curate on read

Merge lazily, when an agent opens a document or the catalogue is rendered.

- **Pros.** No background worker; work is done only for what is read.
- **Cons.** Reads are the agent's own `Read`, which Coffer never sees. A
  read-path rewrite would add model latency to a render that must be cheap and
  deterministic.
- **Why it lost.** Coffer has no read hook to curate on.

## Decision

**New knowledge arrives as material in a hidden inbox, and a bounded curation
pass merges it into the documents and deletes it. A document edited out of
band is carried into the rest of the collection as a newer statement. Where
two statements disagree the newer one wins unless the older one is shown to be
right, and no writer — person, agent or pass — is exempt.**

- **Every entrance submits material.** An agent's Markdown file written into
  `<collection>/.inbox/`, an upload (converted to Markdown by `markitdown`,
  plus plain text and CSV) and a channel's `/kb` all land in `.inbox/`. The
  sweep fills the frontmatter an agent's file lacks (`title`, `description`,
  `actor`, timestamps), keeps every key the writer set, and audits the item as
  `knowledge_written`; a non-Markdown file there is left in place and logged. Neither an upload's original bytes nor its extracted text is kept
  as a file: once the knowledge is merged the carrier has nothing left to say.
  The inbox is the one hidden directory Coffer writes. The web UI's tree and
  the read route list and read it for a person, so what is waiting can be
  seen; nothing but curation writes or deletes it.
- **No model, no waiting.** With no internal model configured, material is
  promoted on the spot to a document at the collection root, as it stands, and
  a pass promotes whatever is already in the inbox (`no_model`). Merging is the
  model's job, but knowledge sitting in a hidden directory for a connection
  nobody set up is knowledge no agent can read.
- **The newer or better-evidenced statement wins.** Where material contradicts
  a document, or two documents disagree, the newer statement wins unless the
  older one is shown to be right by evidence — a source, a date, a command's
  output, the code. The superseded statement stays legible with the date it
  changed. No writer is exempt: a person's edit, an agent's file and a
  pass's own earlier rewrite are all statements, and a later item may correct
  any of them. Where the item is a document edited out of band, the pass
  carries it outward — correcting other documents that disagree — as a newer
  statement. Both are instructions to the model
  (`application/knowledge/curate_prompt.py`), because no code can adjudicate a
  contradiction. Two guards protect data rather than a writer, and are code: a
  pass never overwrites a file whose bytes changed after it read them, and a
  rewrite keeps every frontmatter key it did not set. History, per-version
  restore and whole-pass undo are the recovery path for a wrong merge.
- **Out-of-band edits are found by content, not by time.** Curation keeps a
  record of its own, `~/.coffer/local/curation.json`: for each document, the
  content id (git blob) it had when curation last settled it, after a pass
  over it, after a pass wrote it, or when material was promoted into it. A
  document is *pending* when its current blob differs from the settled one and
  the newest commit that touched it was made by a person or an agent, not by
  curation or by sync (`infrastructure/knowledge/curation_state.py`). A file's
  modification time never decides, so a checkout, a backup restore or a clock
  change that only moves times makes nothing pending. Nothing is written into
  the document to mark it; the record is machine-local, never committed or
  synced, and losing it costs one more pass over each document. Curation's own
  writes are recorded as settled as they are written, so the sweep never hands
  a pass its own output back.
- **The pass is fenced.** Its tool surface is exactly `list_documents`,
  `read_document`, `write_document` and `retire_document`, over one
  collection's documents: no handler can reach the inbox, the collection's
  `README.md`, or another collection (`application/knowledge/curate_tools.py`).
  A retire is allowed only for a document the pass has read and whose content it
  has since written into a *different* document.
- **The pass is bounded.** At most **eight** writes, a retire counting as one
  (`MAX_WRITES_PER_PASS`), and a recursion limit. An item cut off by the
  limit three times in a row is settled as it stands (`gave_up`); an item past
  120,000 characters is never shown to a model (`too_large`). A pass sees the
  item in full, at most **five** candidate documents in full, and the
  collection's whole catalogue of titles and descriptions. Candidates are chosen
  by literal matching: distinctive strings pulled from the item — backticked
  identifiers, dotted names, constants, headings, CJK runs — are handed to
  ripgrep (`infrastructure/knowledge/grep.py`), with a pure-Python walk of the
  same semantics where `rg` is absent (`infrastructure/knowledge/grep_fallback.py`). Selection may miss,
  because the catalogue is in the prompt too: a model shown five wrong
  candidates can still open a new document.
- **A document may not name another knowledge file.** Enforced at
  `write_document` — a write whose body names a file of this collection is
  refused — not requested in a prompt, because a prompt is what produced 343
  dead references. A document names its subject; the generated catalogue maps
  subjects to paths.
- **Settle last.** Material leaves the inbox, or an edited document is recorded as
  settled, only after the pass completes; a pass that raises leaves the item for
  a later sweep.
- **Scheduling.** A sweep runs one minute after boot and then every 60 minutes
  by default, the one global curation interval in Settings, re-read on every
  sweep; it takes inbox material first,
  oldest first, then edited documents, at most five passes per collection per
  sweep (`application/knowledge/curate_worker.py`). One pass per collection at
  a time: a manual trigger during one is refused with `UPKEEP_ALREADY_RUNNING`
  (409). A pass takes the vault-write lock a sync round takes and is skipped
  while a round waits on the user.
- **One owner machine.** Auto-curation is on by default (`auto_curate_enabled`)
  and runs only where `curate_owner_machine_id` names this machine, or is null
  on a single-machine vault — two machines folding the same material would
  write it into two different documents that git merges cleanly
  ([One Owner Machine for Unattended Rewrites](single-owner-machine-for-unattended-rewrites.md)).

## Consequences

- **The documents belong to the person again, and the corpus reorganises
  itself.** An upload integrates instead of accumulating; a correction made in
  one document reaches the others that repeated the mistake.
- **Curation rewrites the only copy.** What protects a document is the
  changed-since-read guard, the evidence clause of the precedence rule, the
  eight-write bound, one pass per
  collection, an audit event per pass, and the vault's git history, where a
  pass is one commit that can be undone as a whole. A bad merge is fixed by
  editing the document or undoing the pass.
- **Uploads are not archival.** A bad conversion cannot be redone from a file
  Coffer kept; the person re-uploads from their own copy.
- **There is a wait.** Material is unreadable until a pass runs, up to the
  sweep interval; the manual *Curate now* trigger and the no-model promotion
  shorten it.
- **Broken internal links are structurally impossible**, and the catalogue is
  the only map.
- **Every outcome is a status, not an error.** The curation route answers 200
  with `ok`, `no_model`, `up_to_date`, `too_large`, `truncated` or `failed`,
  404 for an unknown collection and 409 while a pass runs.
- **Enforcement.** Spec knowledge "Submit every entrance's input as material",
  spec knowledge "Curate through a fenced four-tool pass",
  spec knowledge "Assemble a pass from a bounded context",
  spec knowledge "Bound a pass to eight writes",
  spec knowledge "Let the newer or better-evidenced statement win",
  spec knowledge "Submit material by writing a file into the inbox",
  spec knowledge "Refuse file-name references in documents",
  spec knowledge "Settle an item only after its pass completes",
  spec knowledge "Promote material directly when no model is configured",
  spec knowledge "Curate on one owner machine only".
