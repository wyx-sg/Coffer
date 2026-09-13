# Aggregate the agents' memory; never write it

> 中文版: [aggregate-agent-memory-never-write-it.zh.md](aggregate-agent-memory-never-write-it.zh.md)

**Status**: Proposed
**Date**: 2026-09-12
**Deciders**: Yuxing Wu
**Rewrites**: *Memory via MCP, not native projection* (2026-06-18) — this ADR replaces it, keeping its prohibition and replacing its answer. See [Revision history](#revision-history).
**Related**: spec [memory](../../specs/memory/spec.md), spec [knowledge](../../specs/knowledge/spec.md), [Knowledge Is Plain Files](knowledge-is-plain-files.md), [One Shared Knowledge Store](agent-native-shared-memory.md), [`docs/research/memory-systems-landscape.md`](../research/memory-systems-landscape.md)

## Context

Coffer has tried three times to be the place a developer's agent memory lives, and each attempt was removed:

1. **Native projection** (removed 2026-06-18): Coffer owned the store and symlinked or rendered it into each agent's own memory location, disabling the agent's native memory so no second copy could diverge. Removed as intrusive and illegible — and because no comparable system in the field writes into another agent's memory files.
2. **Transcript distillation** (removed 2026-09-09): Coffer read session transcripts and distilled them into a journal lane. Removed along with the lane.
3. **Session-context injection** (removed 2026-09-10): the replacement for projection's one real benefit — ambient loading — shipped as a per-agent SessionStart hook, and was removed for a reason worth stating plainly: **it had never once been installed on the maintainer's machine**, so in two months the path never ran.

What remains is a pull-only layer with five tools and a skill that tells agents it exists. Measured on the live vault, that is not working: the knowledge corpus holds 58 files and every tool call against it in a month landed on the single day an agent built it.

Meanwhile, on the same machine, both supported agents run memory loops of their own that are working:

| | Claude Code | Codex |
| --- | --- | --- |
| Shape | one Markdown file per fact, frontmatter-typed | one `MEMORY.md` of task groups, plus a distilled profile |
| Size | 69 facts for this project alone | 127 KB of groups, 172 KB of raw, a 9 KB profile |
| Written by | the agent, continuously, unprompted | a distillation pipeline over its own rollouts |
| Loaded by | the agent itself, ambiently, at session start | the agent itself, two-tier: profile always, groups on demand |
| Visible to the other agent | no | no |

Three things follow from that table. **Coffer cannot win the job of accruing memory** — the host is inside the loop and Coffer is not; competing produced an empty store next to two full ones. **The hosts cannot do the job Coffer can**: neither can see the other, neither survives the machine, and neither is inspectable or correctable by the user in one place. And **Codex has already validated the delivery shape** the injection layer was reaching for: a small always-on profile plus a large corpus fetched on demand.

The prohibition from 2026-06-18 is not in question. Nothing here writes an agent's memory files.

## Decision

**Coffer aggregates the agents' native memories read-only, normalises them into one derived, project-partitioned set of facts, organises that set, and pushes a budgeted digest back into every agent's session.** Five moves.

1. **Read, never write.** Coffer reads the native memory of each registered, enabled agent from a path derived from its own `config_dir`, and modifies nothing there — not a file, not a format, not the agent's memory setting. It does not read transcripts or rollouts either: both agents already distil their own, better than Coffer's removed distillation did, so this layer starts from their output.

2. **Everything Coffer holds is derived, except the developer's decisions.** The whole tree under `~/.coffer/memory/` can be deleted and rebuilt from the agents' own copies. The one piece of state that cannot be recomputed — which fact the developer hid, pinned, superseded or settled a conflict on — is stored apart, keyed to an origin identity that survives recomputation, and reapplied after every pass. That separation is what makes the rest safe to rewrite at will.

3. **Partition by project, plus `global`.** A fact belongs to the project it was learned in; a fact about the person rather than a project belongs to `global` wherever it came from. Partitions are named by a readable slug derived from the project root — never an opaque id, which is the specific illegibility that killed native projection. Each partition is a Resource, so the framework's per-agent scope authorises it, defaulting to the agents it was aggregated from so memory flows back to its sources with no setup step.

4. **Organise aggressively, because it is derived.** Merging duplicates across agents, marking a fact superseded by a later contradiction, flagging an unsettleable pair as a conflict, and rewriting the digest are all done by the internal connection with no archival step. Knowledge's `.history/` rule exists because knowledge is the only copy; memory is not, so it does not apply. With no internal connection configured the digest is still produced mechanically — the feature degrades, it does not disappear.

5. **Delivery is a push, in three layers, installed on purpose.** L0 (always, a few hundred tokens): who the developer is, what this project holds, how to ask for more. L1 (when it fits the budget): the digest, one line per fact. L2 (on request): a `recall` tool over the same ranked retrieval spec `knowledge` provides. A channel-driven turn gets L0 and L1 through the system-prompt append Coffer already composes — no hook needed, because Coffer owns that context. An agent the developer drives themselves gets it through that agent's own session-start hook, installed by an explicit act, marker-scoped and removable. **Coffer reports whether delivery is installed and when it last fired**, because the previous injection layer's failure was invisible for two months and a feature that cannot say whether it ran cannot be trusted to have run.

## Consequences

### Positive

- What one agent learns reaches the other, which is the thing three attempts were for, and no agent's own loop is touched to get it.
- The store cannot rot into a second truth: it is derived, so drift is impossible by construction and a bad organise pass costs a re-sync.
- Aggregated memory enters the vault, so it survives the machine through export and backup — the native stores do not.
- The developer gets one place to see, correct and settle what their agents believe, which neither host offers.
- Coffer stops competing with the hosts at the thing hosts are better at, and does the thing only it can do.

### Negative

- Two readers are coupled to two undocumented private formats. A format change breaks a reader; the mitigation is that it must break loudly and locally (spec memory FR-005) rather than silently emptying the store.
- An agent with no native memory contributes nothing. Both supported agents have one today, so this costs nothing now and would need answering before adding an agent that does not.
- Installing a session-start hook writes into an agent's settings file. That is not a memory file and the prohibition still holds, but it is a write into the user's own tool, so it is only ever done on their explicit instruction.
- Facts are duplicated between the agent's store and Coffer's derived copy. Accepted: the copy is disposable, and the alternative is the projection design that was already removed.

### Neutral

- One new table, holding the developer's overrides and nothing else.
- No `remember` tool. An agent records something the way it already does; Coffer picks it up on the next pass.

## Alternatives considered

- **Coffer as the sole store; agents' native memory disabled.** The cleanest model on paper, and rejected because it means switching off the only two memory loops that are demonstrably working, and because disabling them is a write into the user's configuration of exactly the intrusive kind removed in 2026-06-18.
- **Write the aggregated view back into each agent's native memory.** Delivery would then need no hook at all. Rejected: this is native projection under a new name, with the same reversibility and legibility problems, and it would make Coffer's copy a second writer of a file the agent also writes.
- **Leave it to a skill and better tool descriptions.** The current design, measured: one day of use in a month. A skill can tell an agent a store exists; it cannot make the store's contents present at the moment the agent needs them.
- **Distil transcripts again, in Coffer.** Rejected twice over: it was removed for good reason, and both hosts now do it better, on data Coffer would have to re-read at far greater cost.

## Revision history

- **2026-06-18** — *Memory via MCP, not native projection*: the native-projection layer was removed; Coffer kept its own per-fact store, agents reached it through MCP tools, and ambient loading was deferred to a session hook.
- **2026-09-12** — Rewritten as this ADR. The prohibition survives verbatim and is now load-bearing; the ownership model inverts. Coffer no longer holds the canonical store that agents write into — the agents hold it, Coffer aggregates it. The MCP surface narrows to one `recall` tool, and ambient loading returns as an explicit, observable install rather than a deferred follow-up.
