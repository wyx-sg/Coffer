# Sync Memories, Not Task Notes: Read Codex Only From Its v2 Summary

**Status**: Accepted
**Date**: 2026-11-13
**Deciders**: Yuxing Wu
**Related**: [Sync Only Project Memories](sync-only-project-memories.md) (its task-notes decision is replaced by this one), [Follow Codex's Memory Into Every Version Folder It Keeps](follow-codex-memory-into-every-version-folder.md) (its "read both versions" decision is replaced by this one; writing into every folder stands), [Claude Code Reads Other Agents' Memories as Text It Loads](claude-code-reads-other-agents-memories-as-text.md), [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](sync-memory-into-each-agents-own-memory.md), spec memory "Read Codex's memory from its v2 summary", "Sync only project memories"

## Context

Since 2026-11-11 the sync has published every memory an agent learned in a
repository, task notes included, on the reasoning that Coffer should not judge
a memory by where its agent filed it. Two days later a review of the memory
design measured what that produced on the maintainer's Mac:

| Source | Hub entries |
| --- | --- |
| Codex v1, `memories/MEMORY.md` task-group bullets | 232 |
| Codex v2, `memories_v2/memory_summary.md` topics | 7 |
| Claude Code memory files | 69 |

Three quarters of the hub was Codex's v1 task groups: one group per piece of
work, each with bullets of preferences, reusable knowledge and failures ("when
the user said 'check this account's audit log'…", a ticket's batch counts).
They are the working notes of single tasks, written for Codex's own
consolidation to read.

Where they land matters more than how many there are. Claude Code reads other
agents' memories only as the text of a 4 KB block in the project's
`MEMORY.md`, newest first. Per project, that block held 14 of 90, 10 of 78 and
13 of 23 memories. The rest were counted in a last line no session acts on.
So for the two largest projects, eight memories in nine never reached Claude
Code, and which ones did was decided by recency among task notes, not by
worth.

Codex itself does not load those bullets into a session either. What it loads
is `memory_summary.md`, where its consolidation keeps what it judged worth
carrying: a topic sentence per piece of work, capped at about 10 KB.

### How comparable products treat task notes

| Product | What is kept as memory | Task or session notes |
| --- | --- | --- |
| Claude Code auto memory | one file per lesson the model chose to save, per project | session transcripts stay transcripts; never loaded as memory |
| Codex | `memory_summary.md`, consolidated and capped, loaded every session | task groups (v1) and rollout summaries are inputs to consolidation, opened on demand |
| Cursor | removed learned Memories in 2.1; rules a person writes | none |
| Windsurf | auto memories per workspace, retrieved when relevant | none shared |
| Memorix, agentmemory, MemPalace | captured observations in their own store, then approval or decay | captured like anything else; noise is their most common complaint |

Every product that distils sessions separates the distilled layer from the
notes it was distilled from, and loads only the first.

## Options Considered

1. **Keep reading everything (the 2026-11-11 design).** Task-group bullets and
   v2 topics both publish. Pros: nothing Codex wrote is left behind, and Coffer
   makes no judgment. Cons: the measurement above. The hub is three quarters
   task notes, the Claude Code block is full of them, and the same piece of
   work arrives twice while Codex writes both versions. It also needs the
   machinery that kept task-group bullets stable across Codex's rewrites: an
   identity derived from content, carry-over by 0.6 similarity, search terms
   joined from the summary.
2. **Keep reading everything and make the Claude Code block bigger or
   smarter.** Raise the 4 KB bound, or rank memories instead of taking the
   newest. Pros: more reaches Claude Code. Cons: `MEMORY.md` is loaded only to
   200 lines and 25 KB and the person's own index shares it, so the room does
   not exist for 90 entries of up to 800 characters; ranking means Coffer
   judging memories by content, which it has no model for and should not grow
   one for.
3. **Read v1 but only its `User preferences` sections.** Those are closest to
   standing lessons. Pros: fewer entries. Cons: still one set per task, still
   repetitive across tasks, and it is Coffer picking sections of a private
   format by guess.
4. **Read Codex only from its v2 summary (chosen).** A topic of `What's in
   Memory` is one memory; `memories/` is not read. Pros: Coffer takes what
   Codex's own consolidation decided to keep, which is the same layer Claude
   Code's memory files are; the hub drops from 308 to 76 entries on the
   maintainer's Mac and the block has room for all of a project's memories; no
   piece of work arrives twice; the content-identity module, the carry-over,
   the search terms and the v1 parser's sync path are deleted. Cons: a topic is
   one sentence, so the detail in the bullets does not travel; a Codex that has
   not produced a v2 summary yet (v2 is ready after about 20 consolidated
   threads) publishes nothing until it does.

## Decision

Coffer reads Codex's memory only from `memories_v2/memory_summary.md`: each
topic of `What's in Memory` is one memory, filed under the `cwd:` in the header
of the rollout summary it points at. The v1 folder `memories/` is not read as a
memory source. A topic's identity is its scope and the hash of its text, so a
topic Codex rewrote is a new memory and the old one leaves the hub in the same
sync; nothing carries an identity across a rewrite.

Coffer still does not judge a memory an agent kept: within a project, every
Claude Code memory file and every Codex topic syncs, whatever its type. What
changed is which layer of Codex counts as its memory.

Writing is unchanged: Coffer writes its extension folder into every Codex
memory folder that is there, v1 included, because a session may still read
either.

## Consequences

- The ledger's reader revision is bumped. The first sync on each machine
  re-reads every source and deletes the v1 entries that machine published
  (232 on the maintainer's Mac); the copies of them in Claude Code's blocks and
  Codex's extension folders on every machine go with the next sync there, as a
  preview when more than 50 copies change.
- `search_terms` leaves the hub's frontmatter; nothing read it.
- A memory's row on the Memory page now says when it did not fit in Claude
  Code's block (the copy state `over_limit`), so a full block is visible
  instead of silent.
- If Codex drops the v2 summary's `What's in Memory` section or moves the
  directory out of the rollout summary's header, the reader fails loudly for
  Codex and the hub keeps what it had.
- If detail from task groups turns out to be missed, the place for it is
  knowledge: the person asks an agent to write the procedure into a
  collection.
