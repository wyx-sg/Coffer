# Claude Code Reads Other Agents' Memories as Text It Loads: a Project's in Its MEMORY.md Block, the Global Ones in a Rules File

**Status**: Accepted
**Date**: 2026-11-03
**Deciders**: Yuxing Wu
**Related**: [Memory Is About the Person, Knowledge Is About the World](memory-is-about-the-person-knowledge-is-about-the-world.md), [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](sync-memory-into-each-agents-own-memory.md), [File a Memory Where Its Agent Filed It](file-a-memory-where-its-agent-filed-it.md), [Curate Claude Code's Memory in the Open](curate-claude-memory-in-the-open.md), research note [agent memory](../research/agent-memory.md), spec memory "Write the hub into Claude Code as text it loads"

This decision replaces two earlier ones, now deleted: *Global Memories Live in
a Claude Code Project of Their Own, Pointed at From a Rules File* (2026-10-13)
and *The Claude Code Rules File Lists Only Standing Memories and Names the Task
Topics* (2026-10-28). Both are in git history.

## Context

Coffer wrote each hub entry into Claude Code as a `coffer_<slug>.md` topic
file. A project's copies were indexed by one line in a marked block of the
project's `MEMORY.md`; global copies went into a project of their own,
`-coffer-global`, which no session opens, and the rules file
`~/.claude/rules/coffer-memory.md` listed the standing ones, one line of at most
120 characters of title and description plus the file name, and named the task
topics.

What reaches a session, measured on the maintainer's Mac:

- **Only loaded text is used.** In 14 days, 0 of 180 Claude Code sessions
  opened a `coffer_*.md` file. Claude Code loads the first 200 lines and 25 KB
  of a project's `MEMORY.md` and every file under `rules/`; it opens a topic
  file only when its model decides to.
- **Pulling fails.** The `coffer__recall` tool was called 5 times in its life;
  in 448 sessions the knowledge skill was never loaded.
- **A cut index fails.** In the 2026-09-29 evaluation (107 runs), an untruncated
  index covered 76% of what was needed and a truncated one 4%; a session-start
  index avoided a known trap first time in 1 of 18 runs, retrieval at prompt
  time in 15 of 18. The traps were all about outside systems, which now belong
  in knowledge. The one case that failed in every arm was "reply in Chinese", a
  preference that holds every turn.
- **Codex absorbs what Coffer writes.** Its consolidation took 34 lines tagged
  `[via Coffer]` from the extension folder into its own memory.
- **Per-prompt injection was not wanted.** The removed hook layer delivered 414
  times in 30 days; the person did not want memory attached per message.

Since [Memory Is About the Person](memory-is-about-the-person-knowledge-is-about-the-world.md),
task notes no longer cross to other agents, so what Claude Code receives
shrinks to the profile, preferences, corrections and project state: about 28
global memories on the 2026-10-28 data, not 74.

Comparable products:

| Product | How memory about the person reaches the model |
| --- | --- |
| Letta | memory blocks and MemFS `system/` files: always in context, full text, each with a character limit |
| Codex | `memory_summary.md` injected, truncated to 2,500 tokens; `MEMORY.md` grepped on demand |
| Windsurf | global rules, always on, 6,000 characters |
| ChatGPT, Claude.ai | memory about the person, always in context |
| agentmemory, claude-mem | a session-start hook injects a bounded index of about 2,000 tokens |
| mem0, Basic Memory, MCP memory server | tools the model calls when it decides to |

## Options Considered

### Option A — Keep the copies; the rules file and block point at them

- **Pros.** Built and working; Codex's side is proven.
- **Cons.** On Claude Code's side only the 120-character line is read; the text
  sits in files nobody opens. The echo detection and the edited or merged copy
  states serve copies with no reader.

### Option B — The text Claude Code loads: a project's in its block, global in the rules file (chosen)

The hub stays the store. Into Claude Code, Coffer writes no file per memory.
A project's memories go as full text into that project's `MEMORY.md` block,
loaded only in sessions in that project. Global memories go as full text into
the rules file, loaded in every session. Each is bounded, and what does not fit
is counted with the command that lists it. Codex keeps its extension copies.

- **Pros.** It uses the only channel shown to work, and as whole text, not half
  a sentence. A project's memories cost nothing outside that project. No
  daemon, hook or tool is needed at session time. The cost has a hard bound of
  the same order as Codex's own summary. The copy machinery on Claude Code's
  side goes: no `coffer_*.md`, no `-coffer-global` project, no copy states for
  Auto Dream to merge away.
- **Cons.** The budget can fill; past it, memories are only counted. A rules
  file is a user rule and weighs more than memory, so a stale memory is
  followed more firmly; the file's header says it is learned by other agents
  and Coffer brings changes from the agent that wrote it. A full-text block in
  `MEMORY.md` is more likely to be touched by Claude Code's own writing; the
  backup before each write and the marked boundaries stay.

### Option C — A session-start or per-prompt hook

- **Pros.** Codex gets the text without waiting for consolidation; retrieval at
  prompt time scored best on traps.
- **Cons.** On Claude Code a session-start hook gives what the rules file gives,
  plus a daemon or CLI dependency and a `settings.json` change. On Codex a hook
  needs the person's approval, again whenever it changes, and is skipped
  silently until then, which is why Coffer's earlier Codex hook never ran.
  Retrieval serves traps, which are knowledge now; a preference that holds
  every turn is exactly what it misses. The person removed per-message memory
  on 2026-10-09.

### Option D — Only an index in `CLAUDE.md`, `AGENTS.md` or a rules file

- **Pros.** Smallest always-loaded cost; the agents' own shape for task notes.
- **Cons.** Option A's Claude side, measured at 0 of 180. A model does not go
  looking for a preference it does not know it needs. `CLAUDE.md` and
  `AGENTS.md` are the person's files.

### Option E — Only MCP tools

- **Pros.** Touches no agent file.
- **Cons.** 5 calls in its life. Preferences must apply without being asked
  for.

### Option F — Memory as files pulled like knowledge

- **Pros.** One mechanism.
- **Cons.** 0 loads in 448 sessions; pulling cannot serve a preference the
  model does not think to look up.

## Decision

Option B.

1. **No file per memory in Claude Code.** The writer wants no copy; the first
   sync after upgrading removes the `coffer_*.md` copies still as written,
   through the usual plan, so the large-sync preview holds it for the person,
   and empties the `-coffer-global` block.
2. **A project's memories** go, for each project checked out with Claude Code,
   into the marked block at the end of that project's `MEMORY.md`, one line per
   memory with its text and the agent it came from, within 4 KB (the file's own
   lines come first, and Claude Code loads its first 25 KB).
3. **Global memories** go into `~/.claude/rules/coffer-memory.md`, Codex's User
   Profile first, then newest first, within 8 KB, about 2k tokens.
4. **One memory's text** is at most 800 characters, with its title in front
   when the text does not open with it.
5. **What does not fit** is one last line counting it and naming
   `coffer memory entries --project <project or global>`.
6. **Codex is unchanged**: extension copies, absorbed by its consolidation.

## Consequences

- A Codex project memory is task material by where Codex files it, so it
  reaches Claude Code only after the person sorts it back into memory.
- Claude Code's "copy edited" and "merged away" states, and its echo by file
  name, apply only to copies earlier builds left; reading back keeps
  recognising them.
- Curate now on Claude Code consolidates Claude Code's own memory and leaves
  Coffer's block and rules file as they are.
- Whether channel turns driven by the Agent SDK load user rules is not yet
  checked on the person's Mac; if they do not, those turns see only the project
  blocks.
