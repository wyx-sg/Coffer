# Sync Only Project Memories

**Status**: Accepted
**Date**: 2026-11-11
**Deciders**: Yuxing Wu
**Related**: [Sync Memories, Not Task Notes](sync-memories-not-task-notes.md) (what counts as a memory inside a project), [Memory Is About the Person, Knowledge Is About the World](memory-is-about-the-person-knowledge-is-about-the-world.md) (superseded in part: task notes are no longer flagged, held back or sorted), [Claude Code Reads Other Agents' Memories as Text It Loads](claude-code-reads-other-agents-memories-as-text.md) (superseded in part: no global rules file), [File a Memory Where Its Agent Filed It](file-a-memory-where-its-agent-filed-it.md) (superseded in part: nothing is filed under `global`), [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](sync-memory-into-each-agents-own-memory.md), spec memory "Sync only project memories"

## Context

The memory sync kept every memory any agent wrote for itself in a hub in the
vault, under `global` or under a project, and wrote it into the other agents.
Global memories went into Claude Code's `rules/coffer-memory.md`, loaded in
every session. Task notes (a Codex task-group bullet, a Claude Code memory
typed `reference`) were flagged, kept with their own agent, counted on the
Memory page and handed to Claude Code to sort into knowledge on request.

On 2026-11-11 the maintainer looked at the Memory page and said most of what it
held was useless. The hub on their Mac:

| Where | Entries | What they are |
| --- | --- | --- |
| global, Codex task groups | 88 | one piece of work each: "when the user said 'check this account's audit log'…", a ticket's batch counts |
| global, Codex profile and preferences | 59 | mostly rules of one employer's tools (Jira wording, a Config Center CLI, how to split Digital Worker tasks), loaded into every Claude Code session, including sessions on unrelated projects |
| projects, Codex task groups | 215 | per-task notes; 312 memories waited "to be sorted" |
| projects, Claude Code | 69 | mostly `feedback` and `project` |

The sort hand-off never ran. The global rules file put an employer's tool
habits into every session of every project, and the "waiting to be sorted"
count was one more thing on the page asking the person for work they were not
going to do.

### How comparable products scope memory

| Product | Memory outside a project | Task notes |
| --- | --- | --- |
| Claude Code auto memory | none: memory is per project directory; person-wide instructions are the hand-written `~/.claude/CLAUDE.md` | kept in the project's memory, curated by Auto Dream |
| Codex | a profile in `memory_summary.md`, Codex's own, never shared | kept in task groups, consolidated by Codex |
| Cursor | removed Memories in 2.1; person-wide text is user rules a person writes | none |
| Windsurf | global rules, written by a person | auto memories per workspace |
| Memorix, agentmemory, MemPalace | per project or per person in their own store; hooks or a model capture, then a person approves (Memorix, MemPalace) or decay and dedup prune (agentmemory) | captured like anything else; noise is their most common complaint |

No product found writes one agent's automatically learned, person-wide memory
into another agent's every session. Person-wide instructions are, everywhere,
text a person writes.

## Options Considered

1. **Keep it.** Each agent's person-wide memories reach the other agents.
   Pros: a preference Codex learned reaches Claude Code. Cons: what Codex
   learns outside a repository is mostly one employer's tool habits, loaded
   into every session; the 8 KB rules file is spent on them.
2. **Keep only Codex's profile and preferences, not task groups filed globally.**
   Pros: drops the 88 per-task entries. Cons: the remaining 59 are still
   employer-specific and still load everywhere.
3. **Drop it (chosen).** A memory learned outside any repository is not
   published; the rules file goes. Pros: no session carries text from an
   unrelated context; the writer, the rules renderer and the global scope on
   the page go. Cons: a preference Codex learned outside a repository no
   longer reaches Claude Code. A person-wide preference belongs in
   `~/.claude/CLAUDE.md` or `AGENTS.md`, which the person writes, and both
   agents already keep their own.

What happens to task notes inside a project was decided with this and then
revised two days later; that decision, with its options, is
[Sync Memories, Not Task Notes](sync-memories-not-task-notes.md).

## Decision

Coffer syncs only memories learned in a repository. A memory learned outside
any repository stays with its own agent: it is not published, and no global
copy of it is written anywhere. The vault's own checkout, `~/.coffer/vault`, is
not a project either: what an agent learns there is about Coffer's data, not a
codebase.

## Consequences

- The Memory page lists projects only; the copy states `rules` and
  `stays_home` are gone. `/memory/global` opens the page.
- Only `vault/memory/projects/` is read; a `global/` or `sorted/` folder an
  earlier build wrote is ignored.
- If a person-wide preference later needs to cross agents, it is written by a
  person into each agent's own instructions file, not learned and synced.
