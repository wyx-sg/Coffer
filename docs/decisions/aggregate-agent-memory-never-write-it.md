# Aggregate the agents' memory; never write it

**Status**: Accepted
**Date**: 2026-09-17
**Deciders**: Yuxing Wu
**Rewrites**: *Memory via MCP, not native projection* (2026-06-18) — this ADR replaces it, keeping its prohibition and replacing its answer. See [Revision history](#revision-history).
**Related**: spec [memory](../../specs/memory/spec.md), spec [knowledge](../../specs/knowledge/spec.md), [Knowledge Is Plain Files](knowledge-is-plain-files.md), [One Shared Knowledge Store](agent-native-shared-memory.md), [`docs/research/memory-systems-landscape.md`](../research/memory-systems-landscape.md)

## Context

Coffer has tried three times to be the place a developer's agent memory lives, and each attempt was removed:

1. **Native projection** (removed 2026-06-18): Coffer owned the store and symlinked or rendered it into each agent's own memory location, disabling the agent's native memory so no second copy could diverge. Removed as intrusive and illegible — and because no comparable system in the field writes into another agent's memory files.
2. **Transcript distillation** (removed 2026-09-09): Coffer read session transcripts and distilled them into a journal lane. Removed along with the lane.
3. **Session-context injection** (removed 2026-09-10): the replacement for projection's one real benefit — ambient loading — shipped as a per-agent SessionStart hook, and was removed for a reason worth stating plainly: **it had never once been installed on the maintainer's machine**, so in two months the path never ran.

The fourth attempt — aggregation, decided here on 2026-09-12 — shipped, installed and ran. It is the first one that did. It is also the first whose failure could be *measured*, and on 2026-09-17 it was, against the maintainer's live vault. Four numbers decided this rewrite:

| Measurement | Value |
| --- | --- |
| Facts aggregated, by source agent | 284 from Codex, 94 from Claude Code |
| Entries Codex's own index distils that same Codex material into | **16** |
| Facts with two origins — the cross-agent merge this layer exists for | **0** |
| `coffer__recall` calls, lifetime / in the preceding three weeks | **5 / 0** |
| Facts delivered at session start, of 189 visible | **8**, all from `global`, none about the open project |

Each number names a distinct mistake, and they compound.

**Storing the sources' words verbatim was the first.** Claude Code writes one titled file per topic; Codex writes untitled prose bullets inside task groups. Carrying both verbatim meant Codex's bullets arrived with no title, so one was synthesised by truncating the first clause — producing 284 facts whose title, description and body were the same sentence three times over, against the 16 entries Codex had already distilled the same material into. Coffer was reading past its source's finished work to copy its raw material.

**Matching those words literally was the second.** Two agents describing one lesson share no phrasing, so the cross-agent merge — the single thing this layer exists to do — matched **nothing, ever**. 378 facts, zero merges.

**Budgeting the delivery was the third.** A ~600-token ceiling spent on `global` first meant 8 lines arrived, every one of them a generic preference, and the 65 well-titled notes about the repository the session was actually open in never appeared at all.

**Pointing at a tool for the rest was the fourth.** Every session's opening line said "179 more — call `coffer__recall`". In three weeks no agent called it once.

Meanwhile the two hosts, on the same machine, had both solved retrieval — and neither built a search engine to do it:

| | Claude Code | Codex |
| --- | --- | --- |
| Storage | one Markdown file per **topic**, rewritten as it learns more | three tiers: raw capture → distilled task groups → a summary |
| Index | `MEMORY.md`, one line per topic, conclusion written into the line | `memory_summary.md`, grouped by project, **search terms stated per entry** |
| Loaded per session | the **whole** index — 94 entries, ~9k tokens | profile + summary, ~4k tokens |
| Reaching a body | an ordinary file read | an ordinary file read |
| Search tool | none | none |

The prohibition from 2026-06-18 is not in question. Nothing here writes an agent's memory files.

## Decision

**Coffer reads the agents' native memories read-only, distils them into notes of its own — one topic per file, filed by repository — and hands each session the whole index of that set plus the path to read the bodies as files.** Five moves.

1. **Read, never write.** Coffer reads the native memory of each registered, enabled agent from a path derived from its own `config_dir`, and modifies nothing there — not a file, not a format, not the agent's memory setting. It does not read transcripts or rollouts either: both agents already distil their own, better than Coffer's removed distillation did, so this layer starts from their output. Where a source states its own search terms, as Codex's summary does per task group, those travel with the entry instead of being discarded.

2. **Two layers on disk, with one writer each.** `.raw/` holds what was read, verbatim, and only aggregation writes it. `notes/` holds **Coffer's own writing**, and only the distil pass writes it. That separation is what lets a bad distillation be re-run without re-reading the agents, and it is where the 2026-09-12 design's verbatim rule survives — as the input layer, not as the product.

3. **The product is a distillation, not a copy.** A note is one topic, in Coffer's words, accumulated across passes and across agents: a later entry on a covered topic rewrites that note rather than adding a second beside it, and two agents' differently-worded accounts become one note naming both. Matching is done by the internal connection on meaning, because literal matching demonstrably matches nothing. The pass is incremental — new entries plus the existing *index*, never the existing bodies — and may do exactly four things per entry: merge, open, retire, or keep nothing. With no internal connection configured each entry becomes a note of its own and the index is written mechanically: thinner, not absent.

4. **A retirement is written down, because that is what makes it stick.** `RETIRED.md` records what was retired, why, and what replaced it, and is part of the next pass's input. In a store whose sources live outside it, an unrecorded deletion is undone by the next pass — so the retirement file is not a bin, it is the mechanism.

5. **Delivery is the index, and the bodies are files.** A session opens with what is known about the developer, **the whole index** of the current repository's partition — the conclusion written into each line, so most lines need no follow-up — and the absolute path of the directory holding the bodies. It names no tool for reaching one: every consumer is a process on this machine with filesystem access, including a channel-driven turn, which drives a local Claude Code or Codex rather than answering from the daemon. A ceiling still exists, sized for an index rather than for a handful of lines, and when it binds it prefers the open repository over `global` and names the directory holding what it dropped. `coffer__recall` survives with a narrower job: locating notes in a partition the session was *not* opened in, answering with paths rather than bodies. Installation stays an explicit act, marker-scoped and removable, and **every fire is an audit event**, because the 2026-09-10 failure was invisible for two months.

## Consequences

### Positive

- The cross-agent merge can finally happen: it is a judgement about meaning, made by a model, instead of a string comparison that never matched.
- Coffer stops reading past its sources' finished work. Codex distilled 284 bullets into 16 entries; Coffer now starts where that ended rather than re-importing the raw material.
- The delivered payload is an index the agent has been *shown*, not a pointer to a store it has to be curious about. The measured failure of "8 lines and a tool name" is not repeated by making the ceiling bigger; it is repeated by nobody, because there is nothing left to go and fetch.
- A note is an ordinary Markdown file at a path. The retrieval mechanism is the one both hosts already use for their own memory, so there is nothing new for an agent to learn and nothing to keep level with the disk.
- Partitioning by repository rather than by path collapses worktrees and second clones into one store, and stops a dated scratch directory from becoming a permanent partition.

### Negative

- **"Delete and rebuild" weakens from identical to equivalent.** The product is a distillation, so a rebuild gives back the same subjects from the same sources, not the same wording. Accepted: `.raw/` is still byte-reproducible, and it is what the notes' provenance points at.
- **The distil pass is the layer's cost.** It calls a model on every changed partition, where the old organise pass was optional polish. FR-024's mechanical path keeps an installation without a connection working, but visibly worse — which is the honest trade, not a hidden one.
- Two readers remain coupled to two undocumented private formats. A format change breaks a reader; it must break loudly and locally (spec memory FR-005).
- Per-agent scope governs what Coffer serves, not what a process on this machine can open. Handing an agent a path is handing it the file; the layer says so rather than implying a boundary it does not have.
- A session's opening is measurably more expensive — an index of a hundred notes instead of eight lines. Claude Code spends ~9k tokens on exactly this, of its own accord, every session; this is the ecosystem's normal price for not searching.

### Neutral

- No table. Notes, raw entries, the index and the retirement record are files; a partition is a Resource row like every other kind.
- No `remember` tool. An agent records something the way it already does; Coffer picks it up on the next pass.
- The derived tree still does not travel to the sync remote, and the partition's Resource row does not either.

## Alternatives considered

- **Keep verbatim storage and raise the delivery ceiling.** The cheapest fix, and it addresses only the third mistake. 284 triple-redundant entries at a higher ceiling is a larger bad index, and the cross-agent merge still matches nothing.
- **Make retrieval smarter instead of showing the index.** Multi-term matching, fuzzy matching, or restoring embeddings. Rejected on the evidence: the tool was called five times in its life, so the problem was never that queries missed — it was that no query was ever made. Both hosts reached the same conclusion independently and neither ships a search tool over its own memory.
- **Store notes only, with no `.raw/`.** Smaller, and it makes the distillation unrepeatable without re-reading every agent, and leaves a note's claim unquotable back to its source. The raw layer is cheap and hidden; the two properties it buys are not.
- **Delete a retired note outright, with no record.** What the maintainer first proposed, and it does not hold: the source still holds the material, so the next pass re-imports what the last one deleted. Recording the retirement is the only way a deletion survives a pass.
- **Write the distilled notes back into each agent's native memory.** Delivery would need no hook. Rejected: this is native projection under a new name, with the same reversibility and legibility problems.

## Revision history

- **2026-06-18** — *Memory via MCP, not native projection*: the native-projection layer was removed; Coffer kept its own per-fact store, agents reached it through MCP tools, and ambient loading was deferred to a session hook.
- **2026-09-12** — Rewritten as this ADR. The prohibition survives verbatim and is now load-bearing; the ownership model inverts. Coffer no longer holds the canonical store that agents write into — the agents hold it, Coffer aggregates it. Facts were stored in the sources' own words, merged by literal comparison, and delivered as a budgeted three-layer digest with `coffer__recall` for the remainder.
- **2026-09-17** — Rewritten again, against measurements of the shipped design. The prohibition is untouched for the third time; what changes is everything downstream of the read. Verbatim storage becomes a hidden input layer and the product becomes Coffer's own distilled notes, one topic per file. Literal cross-agent matching — which matched nothing in 378 facts — becomes a judgement the internal connection makes. Retirement gains a written record, without which a deletion cannot survive the next pass. The budgeted three-layer digest becomes the whole index plus a directory path, and `coffer__recall` narrows from the way bodies are reached to a locator for partitions the session was not opened in. Partition identity moves from the working directory's path to the repository, collapsing worktrees and excluding scratch directories.
