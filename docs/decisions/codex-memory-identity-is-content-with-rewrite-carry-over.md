# A Codex Memory Is Identified by Its Content, and a Rewrite Keeps the Identity

**Status**: Accepted
**Date**: 2026-10-12
**Deciders**: Yuxing (owner)
**Related**: [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](sync-memory-into-each-agents-own-memory.md)

## Context

The memory hub gives every memory an id derived from the machine, the agent
and the memory's source identity. A Claude Code memory is a file, so its path
is a natural identity. A Codex memory is one bullet in a generated
`MEMORY.md`, and Codex's consolidation rewrites that file whenever its inputs
change: it adds, drops, reorders and rewords bullets in one pass.

The first hub release identified a Codex bullet by file, task group, section
and its **position** in the section, so that an edited bullet would stay an
update rather than become a new memory. On the owner's Mac on 2026-10-12 one
consolidation removed several bullets from the middle of sections. The sync
that followed reported 11 created, 18 deleted and 5 updated Codex memories.
All 5 "updates" were the same failure: the bullet after a removed one moved
up into its position and took over its id, so the hub entry for "For Coffer
QA, use real supported cases…" now held "In Chinese technical explanations…".
Every copy Coffer had written into Claude Code under that id was overwritten
with an unrelated memory. The deletes, checked against `MEMORY.md`, were all
genuine.

A position is not an identity for a list that its owner rewrites freely.

## Options Considered

### A. Position in the section (the first release)

- Pro: an edited bullet that stays in place is an update.
- Con: any insertion, removal or reorder above a bullet gives it a
  neighbour's id. The hub then reports an update that is really a different
  memory, and copies in other agents are overwritten with the wrong text.
  This is the observed failure.

### B. Content hash only

- Pro: an id can never move to a different memory; reorders change nothing.
- Con: every rewording is a delete plus a create. The copy in the other
  agent is removed and a new one written, and anything tied to the old id is
  lost. Consolidation rewords often.

### C. Content hash, plus carry-over for a rewrite (chosen)

Identify a bullet by its content hash. A bullet whose content identity is not
in the hub takes over the identity of the most alike entry that the same
source published in the same section and that no current bullet holds, if
the two are at least 0.6 alike (`difflib` ratio over the descriptions).
Matching is greedy from the most alike pair, so each old entry is taken at
most once.

- Pro: reorders and unrelated insertions never touch an existing id, and a
  rewording stays an update.
- Pro: entries published under the position scheme keep their ids. An
  unchanged bullet matches its old entry at ratio 1.0, so no migration is
  needed; the old identity string stays in the entry's origin.
- Con: a threshold is a judgement. On the 2026-10-12 sync, the pairs that
  were the same memory scored 1.0 and the highest unrelated pair in the same
  sync scored 0.41, so 0.6 sits between them with margin.
- Con: a bullet rewritten beyond recognition is a delete plus a create. That
  is the honest reading of such a change.

### D. Ask Codex for stable ids

- Con: Codex's memory format has no ids and Coffer does not control it.
  Coffer reads an agent's memory and does not change its format.

## How Others Do It

- **git** has no file identity across a rename. `git diff -M` pairs a deleted
  and an added file when they are at least 50% similar by default, which is
  option C's carry-over applied to files.
- **Mem0** decides between ADD, UPDATE and DELETE for an incoming memory by
  retrieving the most similar stored memories and asking a model to choose.
  Coffer runs no model over memory, so it uses a lexical ratio in the same
  place.
- **Diff tools that keep line identity**, such as `diff3` and editor
  change-tracking, anchor on content and fall back to similarity for edited
  lines. None of them anchor on line numbers once lines are inserted.

## Decision

Option C. The source identity of a Codex memory is its file, task group,
section and content hash, and a rewritten bullet keeps the identity of the
most alike memory its section lost, at a ratio of 0.6 or more.

## Consequences

- A consolidation that only reorders, inserts or removes bullets changes no
  surviving memory's id and reports no updates.
- A reworded bullet is still one update to one memory.
- Two identical bullets in one section are told apart by a `#2`, `#3` suffix
  in their identity.
- The threshold is a constant in `application/memory/sync_publish.py`. The
  acceptance tests for spec `memory` cover a move and an unrelated
  replacement.
