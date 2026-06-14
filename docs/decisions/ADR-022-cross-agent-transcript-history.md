# ADR-022 — Cross-Agent Transcript History: a Local Derived Index for Search & Browse

> 中文版: [ADR-022-cross-agent-transcript-history.zh.md](./ADR-022-cross-agent-transcript-history.zh.md)

- **Status:** Superseded (2026-06-14)
- **Spec:** [007-memory](../../specs/007-memory/spec.md) (extension — no new spec number), surfaced in [008-agent-chat](../../specs/008-agent-chat/spec.md) via [ADR-021](./ADR-021-chat-as-vault-console.md)
- **Related:** [ADR-020](./ADR-020-transcript-distillation.md) (transcript distillation — partially supersedes its Alternative B), [ADR-012](./ADR-012-files-as-truth-sqlite-retrieval.md) (files-as-truth + SQLite retrieval), [ADR-016](./ADR-016-multi-machine-sync.md) (multi-machine sync), Spec 004 (read-only workspace invariant)

> **Superseded (2026-06-14).** The raw cross-agent transcript browse/search
> surface described here has been removed. Managing or sharing raw chat
> transcripts across heterogeneous agents proved to carry little value: only
> **distilled memory** ([ADR-020](./ADR-020-transcript-distillation.md)) is
> shared, so a project can continue on another machine through its facts rather
> than its raw conversations. The distillation→memory pipeline stays intact;
> this document is kept as a historical record of the rejected approach.

## Context

[ADR-020](./ADR-020-transcript-distillation.md) distills agent transcripts into
**memory facts** — a lossy extraction of durable knowledge ("what did we
learn"). It deliberately rejected (A) a synced transcript _kind_, (B) a
browse/continue feature, and (C) write-back into the agent's session store.

Users still want to **find and revisit the actual conversations** across all
their agents in one place — to manage chat history the way memory is managed:
ingest from many agents → one hub → search and recall. Distillation does not
answer "show me the session where we tried approach X"; only the conversations
themselves do.

The objections in ADR-020 Alternative A were specifically against persisting
**raw transcripts as a synced system-of-record**: their size, the secrets / tool
payloads / file contents they carry, git-sync bloat, and the files-as-truth
model. **Those objections do not apply to a local-only, rebuildable derived
index that points at the on-disk files.** ADR-020 Alternative B (browse) was
deferred for lack of ecosystem traction and a home, _not_ because it was wrong;
[ADR-021](./ADR-021-chat-as-vault-console.md)'s Vault Console now gives it one.

## Decision

Add a **cross-agent transcript history index**: a **local-only, rebuildable**
index over the in-place `.jsonl` transcripts Coffer already reads
(`~/.claude/projects/`, `~/.codex/sessions/`), exposed in the Vault Console as
unified **search** and read-only **browse** across all agents — and the local
web/IM conversations.

- **Reuse the distill slice's reader and scrubber.** Indexing reuses
  `transcript_reader.py` (`parse_claude_code` / `parse_codex`) and `scrub.py`.
  Only **scrubbed natural-language turns** are indexed into the existing SQLite
  `documents` / FTS substrate ([ADR-012](./ADR-012-files-as-truth-sqlite-retrieval.md)),
  under an **index-only discriminator** — **not** a synced resource kind. Raw
  transcript bytes are never copied into files-as-truth and never enter git sync.
- **Browse reads on demand.** A session is rendered by reading its file
  read-only; it shows scrubbed turns. Any future unredacted replay reads the
  user's own file directly and is never persisted.
- **Search uses the existing retrieval primitives** (FTS5 BM25 default; vector
  optional) over the scrubbed text, scoped by agent / project / time.
- **`continue`/`resume` stays out of scope** (deferred, as in ADR-020 B). The
  resumable session ids already stored on conversations make it reachable later
  if demand appears.

### Two layers: local raw history vs. synced distilled handoff

The split that makes "local-only" lose nothing across machines:

- **Layer 1 — raw history (local, never synced).** The transcript index of this
  ADR. It answers "show me / search the actual conversations on _this_ machine."
  It is a rebuildable local derivative; it never travels over the Spec 010 git
  medium. Raw conversations are the thing you would not want bloating git or
  leaking secrets anyway.
- **Layer 2 — distilled artifacts (synced).** What crosses agents and machines
  is the _condensation_ of history, not history itself: ADR-020 **memory facts**
  today, and a session-level **summary / handoff** artifact as the natural next
  step — a compact, scrubbed "where we got to / what's next" that lets another
  agent or another machine pick up a thread. These are small, reviewable, and
  already governed by Spec 007 + Spec 010, so syncing them respects every
  ADR-020 Alternative A objection.

So the cross-machine value (a handoff you can resume from elsewhere) rides the
synced distilled layer; the bulky, secret-bearing raw layer stays local and
rebuildable. The handoff/summary artifact's own design is deferred to a separate
note (it builds on ADR-020's distillation pipeline); this ADR only fixes the
**layering boundary**: raw history never syncs, distilled summaries do.

### Architecture

- Extend the `distill` slice (or add a sibling `history` slice) reusing the
  reader/scrubber **ports**; a new indexer writes to the SQLite index only.
  Cross-kind wiring stays at the composition root (import-linter Contract 5);
  `application/*` does not import `infrastructure.*`.
- The index is a **derived artifact**: `coffer history reindex` (CLI) and/or a
  background watcher rebuild it from the on-disk files. Deleting the index loses
  nothing durable.

### Invariants

- **Local-only, never synced.** The raw history index (Layer 1) is
  machine-local and never travels over the Spec 010 git medium — only the
  distilled Layer 2 (ADR-020 memory facts, and the future summary/handoff
  artifact) syncs. (Constitution I: no new synced system-of-record; the index is
  a rebuildable local derivative, like the FTS index itself.)
- **No new resource kind.** The index is an internal discriminator in the
  `documents` table, not a hub resource with UI/API/sync/contract surface — this
  is exactly the distinction ADR-020 Alternative A turned on.
- **Files-as-truth preserved.** The agent's own `.jsonl` is the truth; Coffer
  reads, never writes (Spec 004). Browse is read-only.
- **Scrub before index.** The ADR-020 scrubber runs before any text enters the
  index; `tool_use`/`tool_result` blocks, file contents, and command output are
  dropped at parse, exactly as in distillation.
- **No tool-call-content persistence.** The roadmap non-goal ("tool call
  argument or result persistence") holds: only scrubbed natural-language turns
  are indexed.

## Alternatives considered

### A — Persist transcripts as a synced `conversation` kind

(= ADR-020 Alternative A.) **Still rejected**, same reasons: size, secrets,
git-sync bloat, files-as-truth.

### B — Keep only distillation; no browse/search (ADR-020 status quo)

**Rejected now.** Distillation is lossy and answers "what did we learn," not
"show me that conversation." A searchable history answers a different, real
question, and the Vault Console ([ADR-021](./ADR-021-chat-as-vault-console.md))
gives it a home that did not exist when ADR-020 deferred browse.

### C — Copy scrubbed transcripts into Coffer-owned files, then index those

**Rejected.** Duplicates content, risks drift from the agent's real history, and
re-raises storage/secret concerns. Indexing **in place** avoids all of it; the
agent's file stays the single source of truth.

### D — Ship `continue`/`resume` now

**Deferred.** Additive session-resumption problem with still-low ecosystem
traction; reachable later via the resumable session ids already stored on
conversations.

## Consequences

- A local index over agent transcripts is built and kept fresh (CLI reindex +
  optional watcher); it is rebuildable and never synced.
- The Vault Console gains a **cross-agent history search + read-only browse**
  surface — the capability that distinguishes Coffer's chat surface from any
  native client, and the concrete payoff of [ADR-021](./ADR-021-chat-as-vault-console.md).
- ADR-020 Alternative B is **partially superseded**: search/browse is now in;
  `continue`/`resume` stays deferred.
- Parser fragility carries over from ADR-020 (undocumented `.jsonl` formats;
  defensive adapters that skip bad records and never raise).
- Reindex cost and index size scale with transcript volume; the index is
  prunable and rebuildable, so the cost is bounded and stays local.
