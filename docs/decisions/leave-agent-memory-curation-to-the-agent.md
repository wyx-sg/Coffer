# Leave an Agent's Memory Curation to the Agent

**Status**: Accepted
**Date**: 2026-11-13
**Deciders**: Yuxing Wu
**Related**: [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](sync-memory-into-each-agents-own-memory.md), [Claude Code Reads Other Agents' Memories as Text It Loads](claude-code-reads-other-agents-memories-as-text.md), spec memory "Show on each agent what Coffer wrote into it"

## Context

Coffer leaves merging and forgetting memories to each agent's own curation:
Claude Code's Auto Dream, Codex's consolidation. From 2026-10-16 it also
surfaced that curation on each agent's Memory tab:

- whether the agent's own memory and its curation were on. For Auto Dream,
  an undocumented preview, that meant reading `autoDreamEnabled` in
  `~/.claude/settings.json`, falling back to an account flag Claude Code caches
  in `~/.claude.json`, and reading the newest `.consolidate-lock` for when it
  last ran;
- **Turn on**, which wrote `"autoDreamEnabled": true` after a confirm;
- **Curate now**, which opened Claude Code in a terminal with a prompt listing
  the memory folders Coffer had written into and asking it to consolidate
  them.

A review on 2026-11-13 found:

- **Curate now had been broken for two weeks without anyone noticing.** The
  prompt listed folders from the ledger's per-file Claude Code copies. Since
  Claude Code's copies became one block per project there are no such rows,
  so the prompt always said there was nothing to consolidate.
- **The state rested on two undocumented sources** (a settings key and a
  cached account default), each of which Claude Code can rename without
  notice. A wrong "off" invites the person to write a setting that does
  nothing.
- **Coffer's own output no longer needs curating.** The block is rewritten
  whole on every sync, so Coffer leaves no duplicates in Claude Code for
  Auto Dream to merge. What remains to curate is the agent's own memory,
  which is the agent's business.
- The maintainer's rule, restated on 2026-11-06: Coffer stays lean, and what
  the agent can do itself Coffer does not do.

### How comparable products handle another tool's curation

| Product | Shows or drives the host agent's own memory curation? |
| --- | --- |
| Claude Code | its own `/memory` shows and toggles auto memory and Auto Dream |
| Codex | consolidation has no switch of its own; it runs while memories are on |
| Memorix, agentmemory, MemPalace | curate their own store; none reads or flips a host agent's memory settings |
| Cursor, Windsurf | manage only their own rules and memories |

No tool found manages a switch that belongs to a different tool.

## Options Considered

1. **Keep the panel, fix Curate now** (list the project memory folders from
   the block targets instead). Pros: a person can start a tidy from Coffer.
   Cons: keeps a reader of two undocumented sources, a settings writer, two
   routes, two CLI commands, two audit events and a prompt, for something
   Claude Code offers in `/memory` and a person can ask for in one sentence in
   any session; two weeks of a dead button showed nobody uses it.
2. **Keep only the read-only state.** Pros: the person sees why duplicates
   linger. Cons: the state is the least reliable part, and showing it without
   being able to explain or change it sends the person to Claude Code anyway.
3. **Show only Coffer's side (chosen).** The Memory tab says what Coffer wrote
   into the agent, or why it cannot write (with how to turn the agent's own
   memory on when that is the reason, because that blocks Coffer's own work).
   Nothing about curation. Pros: Coffer reads and writes no agent setting for
   curation; about 600 lines and a private-format dependency go. Cons: a person
   who wants Auto Dream on has to find it in Claude Code.

## Decision

Coffer does not show, switch on or start an agent's own memory curation. It
reads no setting, cache or lock file of an agent for it and writes none. Each
agent's Memory tab shows only the copies Coffer wrote there or why it cannot
write.

## Consequences

- `coffer memory curate` and `coffer memory curation-enable`,
  `/api/v1/memory/sync/curation/handoff` and `/curation/enable` are removed.
  The `memory_curation_requested` and `memory_curation_enabled` event types
  stay only so older Activity rows keep their names.
- `~/.coffer/local/curation.json`, where an earlier build cached what it read,
  is no longer written or read and can be deleted.
- A setting an earlier **Turn on** wrote stays in the person's
  `settings.json`: it is theirs.
- The guide tells a person who sees duplicates to wait for the agent's
  curation or ask the agent in a session.
