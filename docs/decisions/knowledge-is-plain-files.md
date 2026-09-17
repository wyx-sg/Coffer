# The knowledge layer is a directory of files, not an index

**Status**: Accepted
**Date**: 2026-09-12 (revised 2026-09-14 and 2026-09-17; see Revision history)
**Deciders**: Yuxing Wu
**Supersedes**: [Retrieval Stack — Markdown Files as Truth, SQLite FTS5 + sqlite-vec](files-as-truth-sqlite-retrieval.md)
**Related**: spec [knowledge](../../specs/knowledge/spec.md); [Everything Is a Resource Kind](everything-is-a-resource-kind.md) and [Per-Agent Resource Scope](per-agent-resource-scope.md), both of which survive; [Aggregate Agent Memory](aggregate-agent-memory-never-write-it.md); [Cross-Platform Skill Delivery](cross-platform-skill-delivery.md)

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

## Decision

**Knowledge is a directory of files in two lanes: `sources/`, which people
write, and `topics/`, which Coffer's internal model curates from them and an
agent reads with its own tools. There is still no derived index.**

- **Two lanes, and they mean who may write.** `~/.coffer/knowledge/<collection>/`
  holds `sources/` and `topics/`. A person, an upload and `coffer__write` write
  `sources/`; the curation pass alone writes `topics/`. This is the only
  directory division the system assigns meaning to, and it is a directory
  because "who may write here" is the one property a frontmatter key cannot
  carry. The 2026-09-12 refusal of lanes stands for everything else — there is
  still no `notes/` ÷ `docs/`, no `global` ÷ `project-<ULID>`, no cwd-derived
  scope, no auto-provisioning.
- **Sources are truth; topics are derived.** A topic document must be
  reconstructible from the sources behind it; deleting `topics/` and re-running
  curation must produce a corpus carrying the same facts. This inverts what the
  earlier revisions asserted, and it is what makes unattended rewriting safe:
  the thing being rewritten is not the only copy. `.history/` goes with the
  reason it existed, and `.raw/` stops being hidden — an uploaded original is an
  ordinary visible file in `sources/`, beside the text extracted from it.
- **Curation is the normal path, not an optional tidy.** A bounded agentic pass
  runs when material changes: immediately for the entrances Coffer serves, and
  on an interval sweep for files changed out of band, found by comparing each
  source's modification time with a `coffer_ingested_at` key Coffer writes into
  its frontmatter. One pass sees one source in full, at most five candidate
  topic documents in full, and the collection's whole catalogue of titles and
  descriptions — the catalogue so the model can conclude none of the candidates
  is the right home. It may make at most eight writes, so a note can never
  trigger a corpus-wide rewrite. It defaults **on**, where tidy defaulted off,
  because it is now the only path from a source to something an agent can read.
- **A contradiction resolves in favour of the newer source, and says so.** The
  resulting document keeps the superseded statement legible as a dated
  correction. Knowledge is about a world that changes, and when it changed is
  itself worth keeping — the user's own corpus already writes this way, with a
  verification date on every document.
- **A topic may not name another file.** Enforced at the write, not asked for in
  a prompt, because this is what produced 343 broken links. A document names its
  subject; the catalogue resolves subjects to paths, and the catalogue is
  generated.
- **One tool: `coffer__write`.** `list`, `grep`, `read`, `search` and `delete`
  are removed. Retrieval is the agent's own `Read` and `Grep` against an
  absolute path. `write` survives because writing is where an agent genuinely
  needs Coffer — the collection, the frontmatter, the lane and the audit entry
  are Coffer's to decide — and because it is the one place an invocation record
  still gets written. Deletion becomes a person's action on the human surfaces.
- **The skill is generated per agent, and it carries the catalogue.** Its
  frontmatter description names the subjects of the collections that agent may
  see, drawn from their READMEs — that description is the only part of this
  layer always in a model's context, so it must carry matchable specifics. Its
  body carries the absolute knowledge root and, per collection, every topic
  document's path, title and description: roughly 5.2K tokens for 58 documents,
  cheaper than the memory layer's session-start digest and paid only when the
  model reaches for it. It is re-rendered whenever the catalogue changes.
- **Authorization moves to delivery.** A collection is still one `knowledge`
  Resource with the framework's per-agent scope, but the scope now decides what
  an agent's skill file says rather than what a tool returns. So the skill is
  delivered as an independent **copy** per agent rather than a symlink into one
  master folder. `coffer__load_skill`, which reads that master unscoped, is
  deleted with `coffer__list_skills`: both existed for agents without a native
  skill mechanism, and both agents Coffer supports have one.

**Removed:** `coffer__list`, `coffer__grep`, `coffer__read`, `coffer__search`,
`coffer__delete`, `coffer__list_skills`, `coffer__load_skill`; `.history/` and
`.raw/`; the `tidy_owner_machine_id`/`auto_tidy_enabled` pair's default-off
posture; shared-master delivery for this one skill.

**Kept:** no index of any kind — no vectors, no FTS5, no sidecar, no chunking,
no reindex; path as identity; frontmatter as metadata; a collection describing
itself in its own `README.md`; the `knowledge` Resource kind; no table in
`coffer.db`; and the rule that this layer pushes nothing into a session.

## Consequences

### Positive

- **The corpus can reorganise itself.** Duplication, drift and contradictions
  are now something the layer resolves rather than accumulates, and it is safe
  to let it, because the sources it derives from are untouched.
- **The agent stops guessing.** It never has to name a collection, guess a
  phrase or remember a tool: the catalogue is in front of it, with absolute
  paths, and the tools it reads with are the ones it uses all day.
- **The always-in-context budget finally carries information.** The skill
  description and the gateway instructions were spending roughly 300 tokens per
  session on abstractions; they now name subjects a model can match.
- **Broken internal links become structurally impossible.**
- **Authorization is enforced by what an agent is told**, which is what it
  always actually was — the previous enforcement point was equally bypassable by
  any agent holding a shell.

### Negative

- **Curation is an unattended rewriter, and now it is on by default.** The pass
  can merge badly, lose nuance, or split a document the user liked. `sources/`
  is the safety net and it is a real one, but recovering means re-running
  curation, not reading back a prior revision. The eight-write bound and the
  one-pass-per-collection lock are what keep a bad pass small.
- **`topics/` is empty until the first pass runs**, and stays empty on an
  installation with no internal connection configured. The layer has acquired a
  hard dependency on the internal model that it did not have.
- **The migration empties the lane agents read.** The existing 58 documents
  become sources; the topics are rebuilt from them, which means a corpus the
  user wrote by hand comes back in a machine's words. This is the cost the user
  accepted in exchange for the 343 broken references going away.
- **Losing the tools loses the invocation record for reads.** `mcp_invocations`
  can no longer answer "is this layer being used". The replacement measurement
  is the agents' own transcripts, which Coffer already reads for other reasons
  and which are retroactive — so nothing is lost by not building it yet.
- **Per-agent skill copies must be reconciled.** A shared master needed one
  write; N agents need N, and a stale copy is a new drift class.

### Neutral

- **Per-agent authorization remains non-disclosure, not access control.** An
  agent holding shell tools can read any file under `~/.coffer/knowledge/`. This
  was equally true before; only the enforcement point moved.
- **Delivery still happens at the agent's initiative.** Nothing is pushed into a
  session and no agent's memory is written. What changed is what prompts the
  reach, not who initiates it.

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
- **2026-09-17** — **Two lanes, curation, and no retrieval tools**, as the body
  above records. Prompted by the 448-session audit: the skill had never been
  loaded, no knowledge tool had ever been called from Claude Code, and 86% of
  the corpus's internal references were broken. The 2026-09-12 and 2026-09-14
  revisions were both arguments about *which* retrieval mechanism to expose;
  this one concludes the layer should expose none, and spend its effort on
  what the agent is told instead. Files as truth narrows to **sources** as
  truth, which is what makes the curation this layer always needed safe to run.
