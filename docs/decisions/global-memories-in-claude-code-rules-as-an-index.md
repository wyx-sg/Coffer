# Global Memories Stay in Claude Code's Rules File, Shrinking to an Index When Long

**Status**: Accepted
**Date**: 2026-10-13
**Deciders**: Yuxing Wu
**Related**: [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](sync-memory-into-each-agents-own-memory.md), research note [agent memory](../research/agent-memory.md), spec memory "Write global memories into a Claude Code rules file"

## Context

Claude Code's own memory exists only per project
(`~/.claude/projects/<project>/memory/`, read when a session starts in that
project). It has no global memory. Coffer's `global` hub entries (memories
about the person, or learned outside any repository) therefore need a place of
their own in Claude Code. They were written whole into
`~/.claude/rules/coffer-memory.md`, which every session loads, up to 25 KB.
That is more context than memories should take in every session.

Comparable products: Windsurf keeps a short always-on global rules file
(6,000 characters) beside per-workspace memories; Codex keeps one global store
and loads a bounded summary, searching the rest on demand; Claude Code loads
only the first 200 lines of a project's `MEMORY.md` and reads topic files on
demand.

## Options Considered

### Option 1 — Keep the rules file as it was

- **Pros.** Nothing changes. Every global memory is always visible.
- **Cons.** The file grows to 25 KB in every session.

### Option 2 — A pseudo "global" project memory folder

- **Pros.** On demand, like other memory.
- **Cons.** Claude Code finds a memory folder from the session's working
  directory. No session would ever match it, so it would never be read.

### Option 3 — Copy global memories into every checked-out project's memory folder

- **Pros.** Read on demand through each project's index.
- **Cons.** One copy per project, and the index lines compete with the
  project's own memories.

### Option 4 — Keep the rules file; past 8 KB hold an index instead of the text (chosen)

One line per memory: title, description and the path of its full text in the
hub (`~/.coffer/vault/memory/global/<id>.md`), which the agent reads when the
title is relevant. Up to 8 KB the text is written whole.

- **Pros.** Small memory sets stay fully visible. The always-loaded cost stays
  small however many memories there are. No copies. The hub is already on disk.
- **Cons.** Past 8 KB the agent has to open a file to read a memory. Claude
  Code's own curation (Auto Dream) does not work on `rules/`, so a global
  memory is not merged with the agent's own; Coffer rewrites the file whole on
  each sync and the origin agent curates its own side.

## Decision

Option 4. Scope is unchanged: a memory learned outside any repository, or of
type `user`, is global.
