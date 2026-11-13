# A Memory Outlives Its Checkout

**Status**: Accepted
**Date**: 2026-11-13
**Deciders**: Yuxing Wu
**Related**: [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](sync-memory-into-each-agents-own-memory.md), [File a Memory Where Its Agent Filed It](file-a-memory-where-its-agent-filed-it.md), spec memory "Publish only what the origin agent wrote, and only from its machine"

## Context

A hub entry is filed under the project its agent learned it in, and the
project is found by resolving the working directory the agent recorded to a
git repository. Only the origin machine deletes its entries: when a source no
longer yields a memory, its hub entry goes.

That rule had a hole. When the person deleted a checkout (a finished worktree,
a repository moved to another disk), the agent's memory files for it stayed,
but their directory no longer resolved to a repository. The next time one of
those sources was re-read (an edit to the file, or a reader-revision bump that
re-reads everything) its memories could not be placed, were treated as "no
longer yielded", and were deleted from the hub and then from every other
machine's agents. The person had not removed any memory.

## Options Considered

1. **Delete (the behaviour found).** An entry that cannot be placed is gone.
   Pros: the hub never holds a project nobody can check out. Cons: deleting a
   folder silently deletes lessons on every machine; a reader-revision bump
   turns into a mass delete for anyone who cleaned up old checkouts; the
   project may well be checked out on the person's other machine.
2. **Keep while the source still holds the memory and its directory is gone
   (chosen).** An entry already in the hub stays when its source still yields
   it but the recorded directory no longer exists. Pros: only the agent or the
   person removing the memory removes it; the copies elsewhere stay. Cons: the
   entry is frozen: an edit to that memory is not published, because Coffer
   can no longer build its portable paths; a stale project stays listed until
   the agent's own memory for it is cleared.
3. **Remember each entry's project in the ledger and keep publishing under
   it.** Pros: edits still travel. Cons: the ledger becomes a source of truth
   for filing, and losing it would then lose placements; more state for a rare
   case.
4. **Ask the person.** Pros: explicit. Cons: one more thing on the Memory page
   waiting for an answer about folders the person already decided to delete.

## Decision

A memory already in the hub is kept when its source still yields it and the
directory it was learned in no longer exists on the origin machine. It is
deleted when the source stops yielding it. A memory whose directory exists but
is not in a repository is not kept: that is the ordinary "learned outside any
repository" case.

## Consequences

- Cleaning up checkouts never removes memories from other machines.
- A frozen entry leaves the hub when the person deletes the agent's memory for
  that project (Claude Code: the project's folder under `projects/`).
- A new memory learned in a directory that is gone before the first sync is
  never published; there is nothing to keep.
