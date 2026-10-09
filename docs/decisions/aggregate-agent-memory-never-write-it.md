# Aggregate the Agents' Memory; Never Write It

**Status**: Superseded by [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](sync-memory-into-each-agents-own-memory.md)
**Date**: 2026-09-17
**Deciders**: Yuxing Wu
**Related**: [Tidying Knowledge and Memory Is the Agent's Job](tidying-knowledge-and-memory-is-the-agents-job.md); [Memory Reaches a Session at Two Moments: an Index at Start and the Notes a Prompt Names](memory-reaches-a-session-at-prompt-time-and-before-a-known-trap.md); spec memory; spec knowledge; [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md); [Coffer's Agent Hooks Are Marker-Scoped, Explicit, Audited and Repaired When Stale](agent-hook-installation.md); [Experimental Features Instead of a Release Branch](experimental-features-instead-of-a-release-branch.md); [Sync Withholds Derived Output](sync-withholds-derived-output.md); research note [agent memory](../research/agent-memory.md)

## Context

A developer running Claude Code and Codex over the same work has two memories
that learn separately. Claude Code writes one titled Markdown file per topic
under its config directory, indexed by `MEMORY.md`; Codex keeps three tiers —
raw capture, distilled task groups, and a `memory_summary.md` that states search
terms per entry. A lesson one agent learns, the other never sees. Coffer's
memory layer exists to let both benefit from both.

The load-bearing question is **who owns the memory**. Coffer has tried to be
the place agent memory lives four times:

1. **Native projection.** Coffer owned the store and symlinked or rendered it
   into each agent's memory location, switching the agent's native memory off
   so no second copy could diverge. Removed 2026-06-18.
2. **Coffer-held store behind MCP tools.** Coffer kept its own per-fact store
   that agents wrote to and read from through `coffer__` tools, with ambient
   loading deferred to a hook.
3. **Transcript distillation.** Coffer read session transcripts and distilled
   them into a journal lane. Removed 2026-09-09.
4. **Session-context injection.** A per-agent SessionStart hook replacing
   projection's one real benefit, ambient loading. Removed 2026-09-10 — it had
   never once been installed on the maintainer's machine, so in two months the
   path never ran. Delivery came back later as an explicit, audited install,
   decided in [Memory Reaches a Session at Two Moments](memory-reaches-a-session-at-prompt-time-and-before-a-known-trap.md).

Aggregation — reading the agents' own memories — shipped 2026-09-12, installed
and ran. It was the first attempt whose failure could be measured, and on
2026-09-17 it was, against the maintainer's live vault:

| Measurement | Value |
| --- | --- |
| Facts aggregated, by source agent | 284 from Codex, 94 from Claude Code |
| Entries Codex's own index distils that same Codex material into | **16** |
| Facts with two origins — the cross-agent merge this layer exists for | **0** |
| `coffer__recall` calls, lifetime / in the preceding three weeks | **5 / 0** |
| Facts delivered at session start, of 189 visible | **8**, all from `global`, none about the open project |

Meanwhile the two agents had each solved retrieval over their own memory, and
neither built a search engine to do it:

| | Claude Code | Codex |
| --- | --- | --- |
| Storage | one Markdown file per **topic**, rewritten as it learns more | raw capture → distilled task groups → a summary |
| Index | `MEMORY.md`, one line per topic, conclusion written into the line | `memory_summary.md`, grouped by project, **search terms stated per entry** |
| Loaded per session | the **whole** index — 94 entries, ~9k tokens | profile + summary, ~4k tokens |
| Reaching a body | an ordinary file read | an ordinary file read |
| Search tool | none | none |

## Options Considered

### Option A — Read the agents' memory, turn each entry into a note, let the agent tidy, deliver through hooks (chosen)

Coffer reads each registered agent's native memory read-only, keeps what it read
verbatim in a hidden `.raw/`, and turns each entry into a note of its own — one
topic per file, partitioned by repository plus `global` — mechanically, as the
entry stands. Merging across agents by meaning is the person's agent's job: the
**Tidy** button on a partition hands it the task, and the `coffer-guide` skill
says how ([Tidying Knowledge and Memory Is the Agent's Job](tidying-knowledge-and-memory-is-the-agents-job.md)).
Delivery is by hook, at two moments (decided in
the delivery ADR above): a session opens with the index of its repository's
partition and `global`, bounded to what a hook can carry, plus the absolute
path of the notes directory; each substantive prompt brings in up to three
notes it names.

- **Pros.** The agents keep the canonical copy, so nothing Coffer does can
  corrupt a tool's memory. Notes start from the agents' finished work (Codex's
  16 entries, not its 284 raw bullets). A merge by meaning, made by the person's
  agent when asked, can match two agents' differently-worded accounts of one
  lesson, which string comparison never did. No model connection is needed for
  the layer to work. Delivery is the mechanism both agents already use for their own
  memory: an index in front of the model and bodies read as files.
- **Cons.** Notes duplicate across agents until someone presses Tidy, and the
  index is budgeted, so delivery truncates sooner. Two readers coupled to two
  undocumented private formats. A session's opening costs an index instead of
  eight lines. A rebuild gives back the mechanical notes, not a tidied tree.
- **Why it wins.** It is the only option that keeps the prohibition below and
  still reaches the session with something the session uses. The principle
  it narrows is "pull, not push": Coffer never *writes* into an agent's own
  memory, but it does *deliver* its own notes through hooks the user installed.

### Option A2 — Distil the entries with Coffer's own model on a timer

The design this replaced. A two-stage pass, driven by a model Coffer called
through its own connection, decided per entry whether to merge it into an
existing note, open a new one, retire one or keep nothing.

- **Pros.** The cross-agent merge happens with nobody asking.
- **Cons.** A model connection to configure, with a mechanical fallback that
  was the real behaviour on any machine without one. A weaker model than the
  agent the person already uses, run where nobody watches. A model call on every
  changed partition.
- **Why it lost.** The judgement is better made by the person's own agent with
  the person watching, on one click.

### Option B — Native projection (Coffer owns the store and writes into each agent)

- **Pros.** Ambient loading: each agent reads the facts natively at session
  start with no hook.
- **Cons.** Writing and disabling another tool's configuration is intrusive and
  illegible; a developer finds their agent's memory switched off. Every agent
  needs a hand-maintained adapter tracking a format that moves upstream.
  Round-tripping a proprietary, evolving memory format losslessly in both
  directions is unsolved and inherently lossy. No comparable system writes into
  another agent's memory files.
- **Why it lost.** Built and removed; its reasons are now the prohibition.

### Option C — A Coffer-held store agents write through MCP tools

- **Pros.** One canonical store, agent-agnostic tools, no native files touched.
- **Cons.** The agents already write their own memory, well, and would keep
  doing so; a second store is a second place a fact might live. Retrieval
  depends on an agent choosing to call a tool — the recall figures above show
  it does not.
- **Why it lost.** It competes with the agents' own memory instead of
  harvesting it.

### Option D — Transcript distillation

- **Pros.** Captures what the agents never wrote down.
- **Cons.** Both agents already distil their own sessions into memory, better
  than Coffer's pass did; reading transcripts is reading past that finished
  work, and far more data.
- **Why it lost.** Removed 2026-09-09; this layer reads no transcripts or
  rollouts.

### Option E — Verbatim aggregation, literal merge, budgeted digest (the 2026-09-12 design)

Store every source entry in its own words, merge entries across agents by
literal comparison, and deliver a ~600-token three-layer digest spent on
`global` first, with `coffer__recall` for the rest.

- **Pros.** Cheapest; no model in the loop; byte-reproducible.
- **Cons.** All four measured failures: Codex's untitled bullets became 284
  facts whose title, description and body were the same sentence; two agents
  describing one lesson share no phrasing, so literal merge matched nothing in
  378 facts; the budget delivered 8 generic lines and none about the open
  repository; and the "call `coffer__recall` for the rest" line was never acted
  on.
- **Why it lost.** Replaced by this design on 2026-09-17. Raising the ceiling
  alone would have been a larger bad index.

### Option F — Keep verbatim facts and make retrieval smarter

Multi-term, fuzzy or embedding search behind `coffer__recall`.

- **Pros.** Recovers queries phrased in the caller's own words.
- **Cons.** The tool was called five times in its life: the problem was never
  that queries missed, it was that no query was made.
- **Why it lost.** Both agents reached the same conclusion independently and
  ship no search tool over their own memory. Coffer ships none either: every
  partition's notes sit under one memory root, so an agent greps that one
  directory with its own file tools.

### Option G — Write the distilled notes back into each agent's native memory

- **Pros.** Delivery would need no hook.
- **Cons.** It is native projection (Option B) under a new name, with the same
  reversibility and legibility problems.
- **Why it lost.** The prohibition.

## Decision

**Coffer never writes an agent's native memory. It reads each registered agent's
memory read-only, turns each entry into a note of its own — one topic per file, filed
by repository — and delivers them through hooks: the index of that set plus
the path to read the bodies as files at session start, then the notes a prompt
names.**

1. **Read, never write.** Coffer reads the native memory of each registered
   agent from a path derived from its own `config_dir`, and modifies
   nothing there — not a file, not a format, not the agent's memory setting. It
   reads no transcripts or rollouts. Where a source states its own search terms,
   as Codex's summary does, those travel with the entry.
2. **Two layers on disk.** `.raw/` holds what was read, verbatim, written only
   by aggregation; it is the distil pass's input, not shown in the web UI nor
   readable through the partition file routes. `notes/` holds the notes: the
   distil pass writes them, and an agent or a person may edit them. A bad
   tidy is repaired by deleting the derived tree and rebuilding it, without
   re-reading the agents.
3. **The distil pass is mechanical.** Each new raw entry becomes a note as it
   stands, and the index is rendered. Matching by meaning is not Coffer's job:
   the person's agent merges notes when the person presses Tidy, keeping each
   merged note's `origins` so its entries stay accounted for.
4. **A retirement is written down.** An agent retires a note by marking its
   frontmatter `retired:`; the next distil pass records it in `RETIRED.md` with
   its origin entry ids, the reason and what replaced it, and removes the file.
   In a store whose sources live outside it, an unrecorded deletion is undone
   by the next pass, and an agent cannot compute raw entry ids itself.
5. **At session start the index, and the bodies are files.** A session
   opens with `global`'s index, the index of the current repository's
   partition — the conclusion written into each line — and the absolute path
   of the notes directory. It names no tool for reaching a body. The delivery
   is bounded to 9,500 UTF-8 bytes, which both agents' hook output limits
   require; when the index does not fit, the trim drops the oldest lines,
   prefers the open repository over `global`, and names the directory holding
   what it dropped. Partitions are identified by repository, which collapses
   worktrees and second clones and excludes scratch directories.
6. **After the start, retrieval.** Each substantive prompt ranks
   the notes lexically and adds the top three. Decided in [Memory Reaches a Session at Two Moments](memory-reaches-a-session-at-prompt-time-and-before-a-known-trap.md).
7. **Two delivery paths.** A session the developer drives themselves receives
   both moments through hooks in the agent's own settings, installed only
   on request and repaired when stale — see
   [Agent Hook Installation](agent-hook-installation.md). A channel-driven turn
   receives the index and the prompt's notes through the system-prompt append
   the turn platform already composes, with no hook of its own for those two
   moments; the guard still runs through the hook the driven agent loads.
8. **Behind the `memory` experimental feature.** Aggregation, distil and
   delivery run when `memory` is on (spec experimental-features "Close the
   memory feature's surfaces"); with it off the routes close and the hook is
   withdrawn.

## Consequences

- **The cross-agent merge can happen.** It is a judgement about meaning, made
  by the person's agent on request, instead of a string comparison that never
  matched.
- **Coffer stops re-importing raw material** its sources had already distilled.
- **Nothing is left to fetch.** The delivered payload is an index the agent has
  been shown, and the notes a prompt names arrive unasked; the "8 lines and a
  tool name" failure is not repeated by a bigger ceiling but by there being
  nothing to go and fetch.
- **A note is an ordinary Markdown file at a path**, read the way both agents
  read their own memory.
- **"Delete and rebuild" gives back the mechanical notes.** `.raw/` is
  byte-reproducible and is what notes' provenance points at; the tidying an
  agent did is not part of what is rebuilt.
- **Duplicates wait for a Tidy.** The distil pass costs no model call, so the
  layer works on any installation; the price is that notes from different
  agents stay separate until the person presses Tidy.
- **Two readers stay coupled to two private formats.** A format change must
  break one reader loudly and locally, not the layer.
- **Every partition is served to every agent.** A partition has no per-agent
  reach and no enabled switch; handing an agent a path is handing it the file,
  so a switch could only govern what Coffer serves, never what a process can
  open.
- **A session's opening is more expensive** — an index up to the 9,500-byte
  ceiling rather than eight lines; Claude Code spends ~9k tokens on its own index every
  session, so this is the ecosystem's normal price for not searching.
- **No table, no `remember` tool.** Notes, raw entries, the index and the
  retirement record are files; an agent records something the way it already
  does and Coffer picks it up on the next pass. The derived tree does not travel
  to the sync remote ([Sync Withholds Derived Output](sync-withholds-derived-output.md)).
- **Enforcement.** Spec memory "Never write an agent's native memory",
  spec memory "Read no transcripts or rollouts",
  spec memory "Distil each raw entry into a note mechanically",
  spec memory "Record retirements so they stick",
  spec memory "Deliver the index and the notes path at session start",
  spec memory "Deliver to channel turns through the system prompt",
  spec memory "Retrieve the notes a prompt names",
  spec memory "Reintroduce no retired mechanism".
