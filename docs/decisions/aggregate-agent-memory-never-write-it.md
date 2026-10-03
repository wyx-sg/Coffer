# Aggregate the Agents' Memory; Never Write It

**Status**: Accepted
**Date**: 2026-09-17
**Deciders**: Yuxing Wu
**Related**: [Memory Reaches a Session at Two Moments: an Index at Start and the Notes a Prompt Names](memory-reaches-a-session-at-prompt-time-and-before-a-known-trap.md); spec memory; spec knowledge; [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md); [Coffer's Agent Hooks Are Marker-Scoped, Explicit, Audited and Repaired When Stale](agent-hook-installation.md); [Experimental Features Instead of a Release Branch](experimental-features-instead-of-a-release-branch.md); [Sync Withholds Derived Output](sync-withholds-derived-output.md); research note [agent memory](../research/agent-memory.md)

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

### Option A — Read the agents' memory, distil it into Coffer's own notes, deliver them through hooks (chosen)

Coffer reads each enabled agent's native memory read-only, keeps what it read
verbatim in a hidden `.raw/`, and has its internal model distil it into notes of
its own — one topic per file, partitioned by repository plus `global` — merging
across agents by meaning. Delivery is by hook, at two moments (decided in
the delivery ADR above): a session opens with the index of its repository's
partition and `global`, bounded to what a hook can carry, plus the absolute
path of the notes directory; each substantive prompt brings in up to three
notes it names.

- **Pros.** The agents keep the canonical copy, so nothing Coffer does can
  corrupt a tool's memory. Distilling starts from the agents' finished work
  (Codex's 16 entries, not its 284 raw bullets). A merge by meaning can match
  two agents' differently-worded accounts of one lesson, which string comparison
  never did. Delivery is the mechanism both agents already use for their own
  memory: an index in front of the model and bodies read as files.
- **Cons.** A model call on every changed partition. Two readers coupled to two
  undocumented private formats. A session's opening costs an index instead of
  eight lines. A rebuild gives back equivalent notes, not identical wording.
- **Why it wins.** It is the only option that keeps the prohibition below and
  still reaches the session with something the session uses. The principle
  it narrows is "pull, not push": Coffer never *writes* into an agent's own
  memory, but it does *deliver* its own notes through hooks the user installed.

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

**Coffer never writes an agent's native memory. It reads each enabled agent's
memory read-only, distils it into notes of its own — one topic per file, filed
by repository — and delivers them through hooks: the index of that set plus
the path to read the bodies as files at session start, then the notes a prompt
names.**

1. **Read, never write.** Coffer reads the native memory of each registered,
   enabled agent from a path derived from its own `config_dir`, and modifies
   nothing there — not a file, not a format, not the agent's memory setting. It
   reads no transcripts or rollouts. Where a source states its own search terms,
   as Codex's summary does, those travel with the entry.
2. **Two layers on disk, one writer each.** `.raw/` holds what was read,
   verbatim, written only by aggregation; it is the distil pass's input, not
   shown in the web UI nor readable through the partition file routes.
   `notes/` holds Coffer's own writing,
   written only by the distil pass. A bad distillation is re-run without
   re-reading the agents.
3. **The product is a distillation, not a copy.** A note is one topic, in
   Coffer's words, accumulated across passes and agents. Matching is by meaning,
   done by the internal model. The pass is incremental — new entries plus the
   existing index, never the existing bodies — and may merge, open, retire or
   keep nothing per entry. With no internal model configured each entry becomes
   a note of its own and the index is written mechanically.
4. **A retirement is written down.** `RETIRED.md` records what was retired, why
   and what replaced it, and is input to the next pass. In a store whose sources
   live outside it, an unrecorded deletion is undone by the next pass.
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
  by a model, instead of a string comparison that never matched.
- **Coffer stops re-importing raw material** its sources had already distilled.
- **Nothing is left to fetch.** The delivered payload is an index the agent has
  been shown, and the notes a prompt names arrive unasked; the "8 lines and a
  tool name" failure is not repeated by a bigger ceiling but by there being
  nothing to go and fetch.
- **A note is an ordinary Markdown file at a path**, read the way both agents
  read their own memory.
- **"Delete and rebuild" is equivalent, not identical.** `.raw/` is
  byte-reproducible and is what notes' provenance points at; the notes are a
  distillation.
- **The distil pass is the layer's cost.** A model call per changed partition;
  the mechanical path keeps an installation without a connection working,
  visibly worse.
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
  spec memory "Record provenance and merge by meaning",
  spec memory "Record retirements so they stick",
  spec memory "Deliver the index and the notes path at session start",
  spec memory "Deliver to channel turns through the system prompt",
  spec memory "Retrieve the notes a prompt names",
  spec memory "Reintroduce no retired mechanism".
