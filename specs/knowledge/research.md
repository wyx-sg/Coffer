# Research — Knowledge Layer

The questions this layer had to answer, and what each was decided to be. Most
of the original research — mem0 versus a shared store, the FTS5/sqlite-vec
retrieval stack, embedding-provider selection, scope resolution from an agent's
cwd, native projection into agents' own memory files — described machinery that
no longer exists. What survives is recorded here; the reasoning behind the
reduction, including the audits of the live installation that
motivated it, lives in
[Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md).

Two of the conclusions below have since moved. They are kept as they were
decided, with what moved them recorded underneath, because a decision that was
reversed is more useful than one quietly overwritten: what is worth carrying
forward is not the answer but why the evidence changed.

## 1. No LLM at write time

**Question**: should a write extract facts with a model, the way mem0 does?

**Decision**: **No.** LLM-at-write is friction when the consumer is already a
model that can decide what is worth remembering and write a clean note itself.
mem0's default `llm_provider="none"` made its `add_memory` return 503 — the
feature was unusable out of the box. A write is a plain file write. mem0,
chroma and LlamaIndex are absent from the codebase and banned by an importlinter
contract so they cannot return.

Still true of the write itself: `coffer__write` puts a file in `sources/` and
does nothing else — no model, no conversion, no indexing step. What changed is
what happens afterwards. A model now curates that material into the `topics/`
lane, and it is no longer an occasional tidy but the normal path. The reason
that is a different question from LLM-at-write is that the model never touches
what was written: it derives a second copy, and the source it derived from is
still there to derive it again.

## 2. One shared store, not a per-agent silo

**Question**: where does an agent's knowledge live?

**Decision**: in **one store shared across every agent**, not in each agent's
own memory directory. A private per-agent silo diverges: the same project fact
ends up copied and drifting across Claude's memory dir, Codex's memories, and
so on. Coffer keeps one copy and every agent reads and writes it over MCP.

Still true, and more literally than it was: with no index and no read tool in
between, the human's editor and the agent's `Read` reach the same bytes. The
only per-agent artifact is the generated skill, and that is a *rendering* of the
one store, regenerated from it, never a copy that can drift.

## 3. Per-file Markdown with YAML frontmatter is the truth

**Question**: what is the on-disk format?

**Decision**: one Markdown file per note, with a `---`-fenced YAML frontmatter
block carrying its metadata.

The format survived every redesign; the field list did not. Frontmatter is now
exactly `title`, `description`, `actor`, `created_at`, `updated_at` — there is
no `id`, because the path is the identity, and no field describing an index,
a lane or an external source — and none describing a conversion either, although
a converted document keeps its original: which converter ran is reported on the
upload response and nowhere on disk, because a file that has landed is just a
file. Every derived index is gone too: a generated `MEMORY.md`, then a generated
`INDEX.md`, then the database index itself.

One key was added, and it is the exception that proves the rule.
`coffer_ingested_at` sits on a source and says when curation last consumed it;
the sweep finds work by comparing it with the file's own modification time.
It is in the frontmatter rather than a table or a state file for the same reason
everything else is: the answer must not be able to disagree with the disk, and a
person who edits a file in their own editor has already told Coffer everything it
needs to know.

The lane, notably, is **not** a key. Which lane a file is in says who may write
it, and that is the one thing a value inside a file cannot enforce — hence two
directories.

## 4. Sharing is MCP-only

**Question**: how does the one store reach each agent?

**Decision**: through Coffer's MCP gateway, and nothing else. An earlier design
also projected canonical content into agents' native locations — a directory
symlink for Claude Code, a marker-fenced block in `AGENTS.md` for Codex — and
that half was removed
([Aggregate Agent Memory](../../docs/decisions/aggregate-agent-memory-never-write-it.md)):
Coffer never writes into an agent's own memory files, disables nothing, and
injects nothing into a session.

**What that left open** was delivery, and the answer tried was a **delivered
skill**: Coffer rendered one skill describing the layer and shipped it through
the channel that already delivers its other `coffer-*` skills, on the reasoning
that a tool's own description does not make a model remember the tool exists.
It was recorded here as a hypothesis with evidence behind it rather than a proven
fix, to be settled by the invocation log within a week of ordinary work.

**It was settled, and it failed.** Across 448 Claude Code sessions after the
corpus was built, that skill was loaded **zero** times and no knowledge tool was
called **once**. The hypothesis was half right and half wrong in an instructive
way: a skill *is* the right carrier — it sits in the agent's context natively,
with no hook and nothing written into its memory — but the skill described the
*layer* ("a fact about THIS user's working environment"), and a model working on
a `session` service had nothing in that sentence to match against. So the
delivery survives and its content changed: the description now names the subjects
the corpus actually covers, drawn from the collections' own READMEs, and the body
carries the whole catalogue with absolute paths.

What did not survive is "MCP-only". Reading no longer goes through MCP at all —
the agent uses the file tools it already has. MCP keeps exactly one knowledge
tool, `coffer__write`, because writing is the one operation where an agent
genuinely needs Coffer: the collection, the lane, the frontmatter and the audit
entry are Coffer's to decide.

## 5. Retrieval: why no index at all

**Question**: what replaces FTS5 + sqlite-vec?

**Decision**: **a generated catalogue plus a literal matcher over the files, and
nothing else.**

The one capability an index offers that a literal matcher cannot is conceptual
recall — matching a query for *鉴权* against a document that says *认证*. That
needs embeddings, and embeddings were never configured on the live installation
(`embedding_config` was an empty table). What FTS5 adds over ripgrep once
embeddings are gone is BM25 ordering and chunk granularity, and an agent does
both for itself: it reads the matching lines, decides which file is relevant,
and reads the whole file anyway. On a corpus of a few dozen files a ripgrep
query returns the same answer set as FTS5 in tens of milliseconds, and needs no
tokenizer to match CJK.

There is no good middle here: either the full semantic stack, or no index. FTS5
alone is the worst ratio of cost to capability in that range. When the corpus
outgrows a catalogue that fits in context — roughly 40 tokens an entry, so
hundreds of files are comfortable — the answer is a real semantic stack built
for that need, not a re-enabling of the component that was never switched on.

That matcher was then exposed as two tools: `coffer__grep`, reporting a line at
a time, and `coffer__search`, reporting a file at a time with its title and
description, sharing one matcher and one file set so that neither could reach an
answer the other could not.

**The half of this that held, and the half that did not.** *No index* held
completely and is now a standing constraint: there are still no vectors, no
FTS5, no sidecar, no chunking and no reindex, and the arguments above are the
reason. What did not hold was the assumption underneath the tools — that the
question was *which literal retrieval mechanism to expose*. The 2026-09-17 audit
measured that the question had never come up. Over 448 sessions neither tool was
called once, and the same audit found **343 of 398** internal references inside
the corpus broken, because a hand-written index of file names could not survive
the renames migration 0066 made underneath it. Two conclusions follow, and they
are what moved the decision:

- **A tool an agent does not remember to call is not retrieval**, however good
  its matching is. Every agent Coffer supports already has `Read` and `Grep`,
  which need no remembering, so the layer's job narrows from *matching well* to
  *putting the right absolute paths in front of the model*. `grep`, `search`,
  `read`, `list` and `delete` are removed; the catalogue moved into the skill,
  where it is generated and cannot rot.
- **The corpus cannot hold its own map.** A file name written into prose is a
  link invalidated by the next rename, which is why a topic document may no
  longer name another file at all, and why that is refused at the write rather
  than asked for in a prompt.

The matcher itself survives, one layer in: ripgrep is how a curation pass picks
which existing documents a new source might belong to. It is reachable by nothing
outside the process, which is the honest place for a mechanism whose callers were
never the agents.

## 6. Ingestion: the filesystem, plus one entrance for when it is out of reach

**Question**: how does a document get in?

**Decision**: **someone puts a Markdown file in the directory — and, when they
cannot, they upload one and Coffer converts it.**

The filesystem is the primary way and remains a complete one (FR-015): adding
knowledge by hand costs one file copy, which is cheaper than any upload surface
could be.

It was briefly the *only* way, on the strength of an audit finding: the
any-format pipeline that preceded this converted through MarkItDown, kept the
original in a `.raw/` lane for re-conversion and tracked external sources, and
on the live installation **50 of 50** documents carried `converter: passthrough`
with the 50 `.raw/` files byte-identical to their converted counterparts. What
that finding did not weigh is **where the user is**. "Put a file in the
directory" is an entrance that exists only while they are sitting at the
machine, and their live entrance is a phone. A channel already accepts
attachments and already extracts them for a turn (spec
[channels](../channels/spec.md) FR-021), so a document forwarded to a Coffer
channel landing in a collection is an entrance the filesystem cannot be, and
that makes the Web upload worth having as the same path's other end.

So conversion is back, and only conversion: `markitdown` plus plain text and
CSV. The mechanisms the audit condemned — re-conversion on a schedule, the
`source_mode` lock, the external-source table — stay gone.

The original is still kept, and it stopped being hidden. `.raw/` existed to keep
an uploaded PDF out of a ranked index that would have answered with noise; with
no retrieval surface at all there is nothing for hiding it to buy, and a person
scrolling their own `sources/` should see what they actually sent. So the
original is an ordinary visible file beside the text extracted from it — which is
also the truer description of what it is. A PDF somebody chose to upload is the
most source-like thing in the collection.

## 7. Boundaries: one, and it exists to be authorized

**Question**: how is knowledge separated?

**Decision**: by **collection**, and by nothing else. A collection is a
top-level folder the human created deliberately, and it is a Resource so the
framework's per-agent scope can authorize it
([Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md)).

The earlier `global` ÷ `project-<ULID>` ÷ collection axis tried to say "what is
this knowledge about", which is a property of the content, and paid the full
cost of physical structure for it: migrations, empty shells auto-provisioned by
a read-only search, and cross-boundary fusion at query time. That retrieval had
to fuse across scopes by reciprocal rank to be useful at all was the tell — the
isolation was never the point. Nothing is derived from a cwd now, nothing
auto-provisions, and an agent reaches every collection it is authorized for.

**Where the scope is enforced moved, and nothing else about it did.** There is no
retrieval tool left to check a scope at, so it is checked at **delivery**: the
skill rendered for an agent names only the collections activated for it, and an
unauthorized collection's name, subjects, catalogue and paths never appear in
that agent's file. `coffer__write` checks it too, on the way in. Authorization is
still **non-disclosure, not access control** — an agent holding shell or
file-read tools can read anything under `~/.coffer/knowledge/`, exactly as it
could before — so the system says so rather than implying an isolation it does
not provide. The previous enforcement point was equally bypassable; what changed
is that the new one is where the agent's *knowledge of the path* comes from,
which is the only thing that was ever actually being controlled.

## 8. Atomicity

File writes go through a same-directory temp file and `replace`, so a reader
never sees a half-written file and a crash never truncates one. Decided once for
the shared file helpers and unchanged since; the helper itself is the record.

## 9. Whether the layer may rewrite itself

**Question**: may anything but a person rewrite a knowledge file?

**Decision (2026-09-12)**: essentially no. Every file was authoritative, so
rewriting one risked the only copy; the tidy pass that could do it archived
every revision into `.history/`, shipped **off** by default, and in practice ran
once.

**Decision (2026-09-17)**: yes, in one lane, and by default. The premise changed
rather than the caution: **sources are truth and topics are derived**, so the
thing being rewritten is not the only copy and the material it was derived from
is in a lane the rewriter cannot reach. That is what made an unattended pass safe
to run, and the 448-session audit is what made it necessary — a corpus that
cannot reorganise itself accumulates exactly the duplication and drift it was
supposed to survive, and no human was going to maintain the map by hand.

Three bounds do the work that a review step would have done, and they are
enforced rather than requested: eight writes per pass, so one note can never
trigger a corpus-wide rewrite; one pass per collection at a time, so two passes
cannot interleave over the same documents; and the watermark written last, so a
pass that fails leaves its material to a later sweep instead of losing it.
`.history/` goes with the reason it existed — recovery is re-running curation
from sources, not reading back a revision.

## 10. What this layer deliberately does not do

- Expose any tool for reading, listing, grepping or searching knowledge. The
  agent reads with the tools it already has, at paths the delivered skill gives
  it (FR-033).
- Rerank, HyDE, multi-query or LLM synthesis at read time — the agent
  synthesizes.
- Parse a proprietary agent memory format back into canonical form
  (industry-unsolved; avoided by sharing one directory instead).
- Push anything into a session, or write into any agent's own memory files.
  Knowledge is pulled; session-start delivery belongs to spec
  [memory](../memory/spec.md), which carries its own budget and its own consent.
- Watch the filesystem. The sweep compares a source's modification time with its
  own frontmatter stamp, which needs nothing resident and cannot drift from the
  disk.
- Converge its own corpus across machines. The files do travel — spec
  [vault-sync](../vault-sync/spec.md) converges the vault bidirectionally with a
  git remote the user owns — but nothing here knows about it. The one thing this
  layer owes that mechanism is that an unattended rewriter runs on exactly one
  machine (FR-032).
- Keep a revision of what a pass replaced. `sources/` is the safety net, and an
  archive of derived files would be a second thing to reconcile.
- Categorize beyond what a file's own `title` and `description` say, and beyond
  the one division that means who may write it.
- Accept a document as an agent tool call. Upload is a human surface — the
  Knowledge page, the CLI, or a channel confirming the collection with its
  paired owner (FR-018).
