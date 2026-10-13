# Global Memories Live in a Claude Code Project of Their Own, Pointed at From a Rules File

**Status**: Accepted
**Date**: 2026-10-13
**Deciders**: Yuxing Wu
**Related**: [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](sync-memory-into-each-agents-own-memory.md), research note [agent memory](../research/agent-memory.md), spec memory "Write global memories into a Claude Code global project and point at them from a rules file"

## Context

Claude Code's own memory exists only per project
(`~/.claude/projects/<project>/memory/`, opened when a session starts in that
project). It has no global memory. Coffer's `global` hub entries (about the
person, or learned outside any repository) therefore need a place in it. They
were written whole into `~/.claude/rules/coffer-memory.md`, which every
session loads, up to 25 KB: more context than memories should cost every
session.

Comparable products: Windsurf keeps a short always-on global rules file
(6,000 characters) beside per-workspace memories; Codex keeps one global store
and loads a bounded summary, searching the rest on demand; Claude Code loads
the first 200 lines of a project's `MEMORY.md` and reads topic files on
demand.

## Options Considered

### Option 1 — Keep the whole text in the rules file

- **Pros.** Nothing changes; every global memory is always visible.
- **Cons.** Up to 25 KB in every session.

### Option 2 — Rules file holds the text up to a size, an index past it

- **Pros.** Small sets stay visible; cost is bounded.
- **Cons.** Two forms to explain. The index points into `~/.coffer/vault/`,
  outside Claude Code's own tree, in a format that is not Claude Code's.

### Option 3 — Copy global memories into every checked-out project's folder

- **Pros.** Read on demand through each project's index.
- **Cons.** One copy per project, and the index lines compete with the
  project's own memories.

### Option 4 — A project of its own for global memories; the rules file only points (chosen)

Global entries are written like project copies into
`~/.claude/projects/-coffer-global/memory/`. No session starts there, so Claude
Code never opens it by itself; the rules file says where it is and lists one
line per memory (title, description, path), never the text.

- **Pros.** One copy. The same file format, index block, states and undo as
  every other copy, so no second writer path. The files sit in Claude Code's
  own tree. The always-loaded cost is bounded (25 KB cap, normally far less).
- **Cons.** Claude Code does not read the folder unless the rules file says
  so, so that file carries the whole mechanism. A project with no sessions
  may show in Claude Code's project list. Whether Auto Dream curates the
  folder is unknown; Coffer rewrites the rules file whole on each sync.

## Decision

Option 4. Scope is unchanged: a memory learned outside any repository, or of
type `user`, is global.
