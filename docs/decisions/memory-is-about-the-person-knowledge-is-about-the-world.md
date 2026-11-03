# Memory Is About the Person, Knowledge Is About the World; Task Notes Are Sorted Into Knowledge on Request

**Status**: Accepted
**Date**: 2026-11-03
**Deciders**: Yuxing Wu
**Related**: [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](sync-memory-into-each-agents-own-memory.md) (amended by this decision), [Claude Code Reads Other Agents' Memories as Text It Loads](claude-code-reads-other-agents-memories-as-text.md) (how what is left reaches Claude Code), [Knowledge Is a Wiki of Pages Compiled From Kept Sources](knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md), [Tidying Knowledge Is the Agent's Job, One Hand-Off Recorded as One Change](tidying-knowledge-is-the-agents-job.md), [Curate Claude Code's Memory in the Open](curate-claude-memory-in-the-open.md), research notes [agent memory](../research/agent-memory.md) and [knowledge structures](../research/knowledge-structures.md)

## Context

Coffer has two stores an agent learns from. **Memory** is a sync: what each
agent wrote into its own native memory is kept in a hub in the vault and
written into the other agents' native memory. **Knowledge** is a wiki of
collections: kept sources compiled into linked pages, with every page naming
its sources and flagged when it is due a recheck. The architecture pages drew
the line between them by **origin**: memory is what agents learned on their
own while working, knowledge is what someone deliberately wrote down. Nothing
at write time judged what a memory was about.

Living with that line showed where it fails. On the maintainer's Mac on
2026-10-28:

- 74 global memories, all from Codex. About 28 were the person's profile and
  standing preferences. About 30 were notes on how outside systems and
  processes work (an IA sheet's remarks, PIC notices, SeaTalk cards, Jira
  conventions, an account audit log), about 10 were procedures (an
  appraisal, a PRD review, a 1:1 note), and about 6 were one-off requests.
- In 14 days, 0 of 180 Claude Code sessions opened a `coffer_*.md` copy. Only
  text injected into the session (the rules file, a `MEMORY.md` block) is
  used. The task notes were already left out of the rules file, so their
  copies in Claude Code reached nobody.
- Codex's consolidation does absorb Coffer's copies (34 `[via Coffer]` lines),
  so what Coffer writes into Codex is used.

The task notes are exactly what the knowledge layer was built for: facts about
an outside system, which need a source, go stale, and are worth sharing. In
memory they have no source, no recheck date and no reader on the Claude Code
side.

### How comparable products draw the line

| Product | Always loaded | Read on demand | What the agent writes on its own |
| --- | --- | --- | --- |
| Claude Code | `CLAUDE.md`, the first 200 lines of `MEMORY.md` | memory topic files, skill bodies | auto memory typed `user`, `feedback`, `project`, `reference`; "what can be derived from the code is not remembered" |
| Codex | `AGENTS.md`, `memory_summary.md` (profile and preferences, 2,500 tokens) | `MEMORY.md` task groups, grepped; skills | a two-phase distillation; the docs call memories "a recall aid" and send critical rules to `AGENTS.md` |
| Cursor | always-apply rules | rules picked by description | **removed** Memories in 2.1 and asked users to export them into rules |
| Devin | repo-pinned Knowledge | Knowledge picked by trigger; DeepWiki, a compiled repo wiki | Devin suggests, a person approves; Knowledge is being folded into Skills |
| Windsurf | global rules (6,000 characters) | rules picked by the model | auto memories only in the legacy agent; "durable, shareable knowledge" goes to rules |
| GitHub Copilot | custom instructions | Copilot Memory: each fact cites code, is checked before use and expires after 28 unused days | repository-scoped, with citations |
| Letta Code | `system/` files | every other file, the tree always shown | memory and knowledge are one git-backed tree |
| ChatGPT, Claude.ai | memory about the person | a project's files | memory holds who the person is; files hold material |

Three things recur. Memory is **about the person**, material is **about the
world**. What is always loaded is small and budgeted. And agent-written memory
is moving into files a person curates (Cursor, Devin, Windsurf). Copilot shows
why facts about the world want a source and an expiry.

## Options Considered

### Option 1 — Keep the line by origin

- **Pros.** Nothing to build; nobody has to judge what a memory is about.
- **Cons.** Task notes keep piling into memory with no source or recheck date,
  copies nobody reads keep being written, and a fact can sit in both stores.
- **Why it lost.** No comparable product draws the line this way, and the data
  above shows the cost.

### Option 2 — Split by content; Coffer flags, the agent sorts on request (chosen)

Define the stores by what a statement is about. Coffer flags, from where the
agent itself filed a memory, the memories that look like task notes; flagged
memories stop crossing to other agents; a hand-off the person starts from the
Memory page has their agent sort the flagged memories into knowledge, a skill,
memory or nothing.

- **Pros.** The line comparable products draw. Memory shrinks to what is used
  as injected text. Task notes land where they get a source and a recheck date,
  through the tidy the knowledge layer already has. Coffer judges nothing: the
  flag is read from the agent's own filing, and the sorting is the agent's,
  with the person watching.
- **Cons.** Sorting costs the person's tokens and needs them to press a button.
  The agent can sort wrongly; the vault history and the hand-off's
  propose-first step are the guard. A note sorted into knowledge still lives in
  Codex's own memory, which Coffer does not edit.

### Option 3 — Split by content; Coffer routes flagged memories into knowledge at sync

- **Pros.** No button; knowledge sees the notes at once.
- **Cons.** The routing is by filing alone and misfiles many (a task group holds
  preferences too). Codex keeps rewriting its task groups, so the sources would
  churn, while sources are meant never to change. Collections fill with
  unsorted sources.
- **Why it lost.** It makes Coffer the judge, and the noise lands in the store
  meant to be curated.

### Option 4 — One store with an always-loaded part and an on-demand part

Letta Code's and Basic Memory's shape: no separate memory and knowledge.

- **Pros.** No line to draw; one tidy, one history, one check.
- **Cons.** The agents keep writing their own native memory regardless, so the
  result is three stores, not one, unless Coffer switched their memory off,
  which it did once and removed as too intrusive. It reverses both the memory
  and the knowledge decisions.
- **Why it lost.** Highest cost, and it fights the agents.

### Option 5 — Stop syncing memory; keep only knowledge

Cursor's direction.

- **Pros.** Simplest; deletes the sync.
- **Cons.** Loses the profile and preferences crossing between agents and
  machines, which is the part shown to be used.
- **Why it lost.** It throws away the part that works.

### How sorting is started

The person chose, among an unattended weekly run that only adds, an
unattended run that also deletes, and a reminder with a button, the
**reminder with a button**. Coffer starts no agent run on its own, as for every
other hand-off.

## Decision

Option 2.

1. **What goes where.**

   | Store | Holds | Reaches the agent |
   | --- | --- | --- |
   | Memory | who the person is; how to work with them (preferences, corrections, approval habits); a project's current state and decisions not in the repository, dated | the agent's native memory, injected each session |
   | Knowledge | how outside systems, teams and processes work; their pitfalls; imported documents; anything that needs a source, goes stale or is worth sharing | the catalogue in `coffer-guide`, pages read on demand |
   | Skills | a fixed sequence of steps done repeatedly | the skill's description, its body on demand |
   | Nothing | what the repository already says; one-off requests | |

   The guide asks three questions in order: would it still hold for someone
   else (no: memory); is it about an outside system, team or process, or does it
   need a source (yes: knowledge); is it a fixed sequence of steps (yes: skill).

2. **The flag.** A hub entry is flagged **to sort** when its agent filed it as
   task material: a Codex bullet of a `MEMORY.md` task group, or a Claude Code
   memory typed `reference`. The profile and preferences of Codex's summary and
   Claude Code's `user`, `feedback` and `project` memories are never flagged.
   Coffer reads the flag from the entry's own origin and type and judges no
   text. When Codex's newer memory layout is read, its per-project "What's in
   Memory" items are task material and its profile and preferences are not.

3. **Flagged memories stay with their own agent.** A flagged entry is not
   written into another agent's memory until it is sorted back into memory. It
   still reaches its own agent on the person's other machines. Copies already
   written are removed by the next sync, which the large-sync preview holds for
   the person.

4. **The reminder.** The Memory page shows how many memories wait to be sorted,
   and the attention list (Overview, sidebar badge, menu bar) carries one item
   once at least ten wait.

5. **Sorting is a hand-off.** **Sort into knowledge** on the Memory page opens
   Claude Code in a terminal with a prompt that lists each waiting memory's hub
   file and the collections. The agent proposes, for each memory, knowledge,
   skill, memory or drop, and acts only after the person agrees:
   - knowledge: written into a collection inside a `tidy-start` / `tidy-finish`
     pair, as a source kept as the memory said it plus the pages it belongs in,
     so each collection's change is one commit that can be undone;
   - skill: drafted into a folder and imported through the skill import only
     when the person agrees;
   - memory or drop: nothing is written;
   - each memory: recorded as sorted with `coffer memory sorted`.

6. **Sorted records.** A sorting is one file per memory under
   `vault/memory/sorted/<id>.md`, naming the outcome, where it went and when;
   vault sync carries it, so no other machine asks again. A memory sorted to
   *memory* is unflagged and syncs to every agent again. A sorted memory stays
   sorted when its agent rewords it (Codex rewrites its task groups often, and
   asking again for each rewording would be noise). A record whose memory left
   the hub is deleted by the next sync. The sorting never edits or deletes an agent's
   own memory; the drop list is the person's to act on.

7. **Delivery into Claude Code** is decided separately, in
   [Claude Code Reads Other Agents' Memories as Text It Loads](claude-code-reads-other-agents-memories-as-text.md):
   the text of what is left, in the rules file and each project's `MEMORY.md`
   block, with no topic line for task memories.

8. **Claude Code's Curate now stays** on the agent's Memory tab. It stands in
   for Auto Dream, which merges and prunes Claude Code's own memory; sorting is
   about the hub and belongs to the Memory page.

## Consequences

- Memory written into each agent shrinks to the profile, preferences, project
  state and corrections: on the 2026-10-28 data, from 74 global entries to
  about 28.
- Task notes reach Claude Code only after they are sorted into knowledge (or
  back into memory). Until then, a Claude Code session does not see what Codex
  learned in a task; it did not read those copies before either. Codex files
  every project memory in a task group, so its project memories reach Claude
  Code only once sorted back into memory.
- Codex still holds its own task notes and consolidates them as before.
- Whether agents read the knowledge layer often enough for sorted notes to be
  found is not yet measured; if they do not, the rules file can name the
  collections next.
- `coffer-guide` tells agents which store a fact belongs in.
